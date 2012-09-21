#!/usr/bin/env python
#-------------------------------------------------------------------------------
#
# Copyright (c) 2011-2012 by European Organization for Nuclear Research (CERN)
# Author: Lukasz Trzaska <ltrzaska@cern.ch>
#
# This file is part of XrdTest.
#
# XrdTest is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# XrdTest is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with XrdTest.  If not, see <http://www.gnu.org/licenses/>.
#
#-------------------------------------------------------------------------------
#
# File:    XrdTestSlave
# Desc:    XRootD Testing Framework Slave component. 
#          * The actual application which runs tests
#          * Daemon that may be run on virtual or physical machines
#          * Receives test cases from Master and runs them synchronously 
#            with other Slaves
#          * Creates sandbox to run shell scripts securely
#-------------------------------------------------------------------------------
from XrdTest.Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import logging
    import sys
    import ConfigParser
    import Queue
    import os
    import socket
    import ssl
    import subprocess
    import threading

    from XrdTest.Daemon import Daemon, DaemonException, Runnable
    from XrdTest.TCPClient import TCPReceiveThread
    from XrdTest.SocketUtils import FixedSockStream, XrdMessage, SocketDisconnectedError
    from XrdTest.TestUtils import TestSuite
    from XrdTest.Utils import State, redirectOutput
    from optparse import OptionParser
    from string import join
    from copy import copy
    from subprocess import Popen
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)


class XrdTestSlaveException(Exception):
    '''
    General Exception raised by XrdTestSlave.
    '''
    def __init__(self, desc):
        '''
        Constructs Exception
        @param desc: description of an error
        '''
        self.desc = desc
        
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)

class XrdTestSlave(Runnable):
    '''
    Test Slave main executable class.
    '''
    def __init__(self, configFile, backgroundMode):
        ''' TODO: '''
        #Default daemon configuration
        self.defaultConfFile = '/etc/XrdTest/XrdTestSlave.conf'
        self.defaultPidFile = '/var/run/XrdTestSlave.pid'
        self.defaultLogFile = '/var/log/XrdTest/XrdTestSlave.log'
        self.logLevel = 'INFO'

        if not configFile:
            configFile = self.defaultConfFile
        self.config = self.readConfig(configFile)
        
        if self.config.has_option('daemon', 'log_level'):
            self.logLevel = self.config.get('daemon', 'log_level')
        logging.getLogger().setLevel(getattr(logging, self.logLevel))
            
        # redirect output on daemon start
        if backgroundMode:
            if self.config.has_option('daemon', 'log_file_path'):
                redirectOutput(self.config.get('daemon', 'log_file_path'))
        
        LOGGER.info("Using config file: %s" % configFile)
        
        self.sockStream = None
        #Blocking queue of commands received from XrdTestMaster
        self.recvQueue = Queue.Queue()
        self.stopEvent = threading.Event()
        # Ran test cases, indexed by test.uid
        self.cases = {}
        # Values to replace @tags@ with
        self.tags = {}

    def executeSh(self, cmd):
        '''
        @param cmd:
        '''
        command = ""
        cmd = cmd.strip()

        #reading a file contents
        if cmd[0:2] == "#!":
            LOGGER.info("Direct shell script to be executed.")
            command = cmd
        else:
            import urllib
            f = urllib.urlopen(cmd)
            lines = f.readlines()
            f.close()
            command = join(lines, "\n")

            if "http:" in cmd:
                LOGGER.info("Loaded script from url: " + cmd)
            else:
                LOGGER.info("Running script from file: " + cmd)

        command = self.parseTags(command)

        res = ('Nothing executed', '', '0')
        localError = ''
        try:
            process = Popen(command, shell=True, stdout=subprocess.PIPE)

            output = "".join(process.stdout.readlines())
            retcode = process.returncode
            if retcode is None: retcode = 0

            if self.tags.has_key('@logfiles@'):
                LOGGER.info("Grabbing current logs ...")

                logs = {}
                for log in self.tags['@logfiles@']:
                    log = log.replace('@slavename@', socket.gethostname())
                    command = 'tail -100 %s' % log
                    process = Popen(command, shell=True, executable="/bin/bash", \
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    logtext = process.communicate()[0]
                    logs[log] = logtext

            res = (output, '', str(retcode), logs)

        except ValueError, e:
            localError += str(e)
            LOGGER.error("Execution of shell script failed: %s" % e)
        except Exception, e:
            localError += str(e)
            LOGGER.error("Execution of shell script failed: %s" % e)

        if localError:
            (a, b, c, d) = res
            t = "\nERRORS THAT OCCURED ON TEST SLAVE:\n "
            res = (a, b + t + str(localError), '1', d)

        return res

    def requestTags(self, hostname):
        ''' TODO: '''
        LOGGER.info('Requesting tags from master ...')
        
        msg = XrdMessage(XrdMessage.M_TAG_REQUEST)
        msg.hostname = hostname
        self.sockStream.send(msg)
        
        resp = self.recvQueue.get(block=True, timeout=1000)
        if resp:
            LOGGER.info('Received tags.')
            
            # Compulsory tags
            self.tags['@proto@'] = resp.proto
            self.tags['@port@'] = str(resp.port)
            self.tags['@slavename@'] = socket.getfqdn()
            
            if hasattr(resp, 'diskMounts'):
                self.tags['@diskmounts@'] = resp.diskMounts
            else:
                LOGGER.info('No disk mount tags received.')
                self.tags['@diskmounts@'] = ''
                
            if hasattr(resp, 'logFiles'):
                self.tags['@logfiles@'] = resp.logFiles
            else:
                LOGGER.info('No log file tags received.')
                self.tags['@logfiles@'] = ''
        else:
            raise XrdTestSlaveException('Could not get tag values for slave ' + \
                                        '%s.', hostname)
    
    def parseTags(self, command):
        ''' TODO: '''
        LOGGER.info('Parsing tags ...')
        
        if self.tags:
            for tag, value in self.tags.iteritems():
                if isinstance(value, basestring):
                    command = command.replace(tag, value)
                    LOGGER.debug('%s: %s' % (tag, value))
        return command
            
    def connectMaster(self, masterName, masterPort):
        ''' TODO: '''
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sockStream = ssl.wrap_socket(sock, server_side=False,
                                        certfile=\
                                        self.config.get('security', 'certfile'),
                                        keyfile=\
                                        self.config.get('security', 'keyfile'),
                                        ssl_version=ssl.PROTOCOL_TLSv1)

            LOGGER.info('Connecting to master: %s' % masterName)
            self.sockStream.connect((socket.gethostbyname(masterName), masterPort))
        except socket.error, e:
            if e[0] == 111:
                LOGGER.error("Connection from master refused.")
            else:
                LOGGER.info("Connection with master could not be established.")
                LOGGER.exception(e)
            return None
        else:
            LOGGER.debug("Connected to master.")
        try:
            self.sockStream = FixedSockStream(self.sockStream)
            self.sockStream.send(("slave", socket.getfqdn()))
        except socket.error, e:
            LOGGER.exception(e)
            return None

        return self.sockStream

    def handleTestCaseInitialize(self, msg):
        ''' TODO: '''
        suiteName = msg.suiteName
        testName = msg.testName
        testUid = msg.testUid
        jobGroupId = msg.jobGroupId

        self.cases[testUid] = copy(msg.case)

        msg = XrdMessage(XrdMessage.M_TESTSUITE_STATE)
        msg.testUid = testUid
        msg.suiteName = suiteName
        msg.testName = testName
        msg.jobGroupId = jobGroupId

        msg.result = self.executeSh(self.cases[testUid].initialize)
        msg.state = State(TestSuite.S_SLAVE_TEST_INITIALIZED)

        LOGGER.info("Initialized test %s [%s] with result %s:" % \
                    (testName, suiteName, msg.result[2]))

        return msg

    def handleTestCaseRun(self, msg):
        ''' TODO: '''
        suiteName = msg.suiteName
        testName = msg.testName
        testUid = msg.testUid

        msg = XrdMessage(XrdMessage.M_TESTSUITE_STATE)
        msg.testUid = testUid
        msg.suiteName = suiteName
        msg.testName = testName

        msg.result = self.executeSh(self.cases[testUid].run)
        msg.state = State(TestSuite.S_SLAVE_TEST_RUN_FINISHED)

        LOGGER.info("Run finished test %s [%s] with result %s:" % \
                    (testName, suiteName, msg.result[2]))

        return msg

    def handleTestCaseFinalize(self, msg):
        ''' TODO: '''
        suiteName = msg.suiteName
        testName = msg.testName
        testUid = msg.testUid

        msg = XrdMessage(XrdMessage.M_TESTSUITE_STATE)
        msg.testUid = testUid
        msg.suiteName = suiteName
        msg.testName = testName

        msg.result = self.executeSh(self.cases[testUid].finalize)
        msg.state = State(TestSuite.S_SLAVE_TEST_FINALIZED)

        LOGGER.info("Finalized test %s [%s] with result %s:" % \
                    (testName, suiteName, msg.result[2]))

        return msg

    def handleTestSuiteInitialize(self, msg):
        ''' TODO: '''
        cmd = msg.cmd
        jobGroupId = msg.jobGroupId
        suiteName = msg.suiteName
        
        # Ask the master for the necessary tags so we can replace them in
        # the scripts
        self.requestTags(socket.getfqdn())

        msg = XrdMessage(XrdMessage.M_TESTSUITE_STATE)
        msg.suiteName = suiteName
        msg.result = self.executeSh(cmd)
        msg.state = State(TestSuite.S_SLAVE_INITIALIZED)
        msg.jobGroupId = jobGroupId

        return msg

    def handleTestSuiteFinalize(self, msg):
        ''' TODO: '''
        cmd = msg.cmd
        suiteName = msg.suiteName
        
        msg = XrdMessage(XrdMessage.M_TESTSUITE_STATE)
        msg.suiteName = suiteName
        msg.result = self.executeSh(cmd)
        msg.state = State(TestSuite.S_SLAVE_FINALIZED)

        return msg

    def recvLoop(self):
        ''' TODO: '''
        while not self.stopEvent.isSet():
            try:
                #receive msg from master
                msg = self.recvQueue.get()
                LOGGER.info("Received msg: " + str(msg.name))

                resp = XrdMessage(XrdMessage.M_UNKNOWN)
                if msg.name is XrdMessage.M_HELLO:
                    resp = XrdMessage(XrdMessage.M_HELLO)
                elif msg.name == XrdMessage.M_TESTSUITE_INIT:
                    resp = self.handleTestSuiteInitialize(msg)
                elif msg.name == XrdMessage.M_TESTSUITE_FINALIZE:
                    resp = self.handleTestSuiteFinalize(msg)
                
                elif msg.name == XrdMessage.M_TESTCASE_INIT:
                    resp = self.handleTestCaseInitialize(msg)
                elif msg.name == XrdMessage.M_TESTCASE_RUN:
                    resp = self.handleTestCaseRun(msg)
                elif msg.name == XrdMessage.M_TESTCASE_FINALIZE:
                    resp = self.handleTestCaseFinalize(msg)
                else:
                    LOGGER.info("Received unknown message: " + str(msg.name))
                self.sockStream.send(resp)
                LOGGER.debug("Sent msg: " + str(resp))
            except SocketDisconnectedError:
                LOGGER.info("Connection to XrdTestMaster closed.")
                sys.exit()
                break

    def run(self):
        ''' TODO: '''
        sock = self.connectMaster(self.config.get('test_master', 'ip'),
                           self.config.getint('test_master', 'port'))
        if not sock:
            return

        tcpReceiveTh = TCPReceiveThread(self.sockStream, self.recvQueue)
        thTcpReceive = threading.Thread(target=tcpReceiveTh.run)
        thTcpReceive.start()

        self.recvLoop()

    def readConfig(self, confFile):
            '''
            Reads configuration from given file or from default if None given.
            @param confFile: file with configuration
            '''  
            config = ConfigParser.ConfigParser()
            if os.path.exists(confFile):
                try:
                    fp = file(confFile, 'r')
                    config.readfp(fp)
                    fp.close()
                except IOError, e:
                    LOGGER.exception(e)
            else:
                raise XrdTestSlaveException("Config file %s could not be read" % confFile)
            return config
    
def main():
    '''
    Program begins here.
    '''
    parse = OptionParser()
    parse.add_option("-c", "--configfile", dest="configFile", type="string", \
                     action="store", help="config (.conf) file location")
    parse.add_option("-b", "--background", dest="backgroundMode", \
                     type="string", action="store", \
                      help="run runnable as a daemon")

    (options, args) = parse.parse_args()

    configFile = None
    if options.configFile:
        configFile = options.configFile    
    
    # Initialize the slave
    testSlave = XrdTestSlave(configFile, options.backgroundMode)

    # run the daemon
    if options.backgroundMode:
        LOGGER.info("Run in background: %s" % options.backgroundMode)

        pidFile = testSlave.config.get('daemon', 'pid_file_path')
        logFile = testSlave.config.get('daemon', 'log_file_path')

        dm = Daemon("XrdTestSlave.py", pidFile, logFile)
        try:
            if options.backgroundMode == 'start':
                dm.start(testSlave)
            elif options.backgroundMode == 'stop':
                dm.stop()
            elif options.backgroundMode == 'check':
                res = dm.check()
                print 'Result of runnable check: %s' % str(res)
            elif options.backgroundMode == 'reload':
                dm.reload()
                print 'You can either start, stop, check or reload the deamon'
                sys.exit(3)
        except (DaemonException, RuntimeError, ValueError, IOError), e:
            LOGGER.error(str(e))
            sys.exit(1)

    # run test master in standard mode. Used for debugging
    if not options.backgroundMode:
        testSlave.run()


if __name__ == '__main__':
    main()
