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
from XrdTest.Utils import get_logger
LOGGER = get_logger(__name__)

import logging
import sys
import ConfigParser
import Queue
import os
import socket
import ssl
import subprocess
import threading

try:
    from XrdTest.Daemon import Daemon, readConfig, DaemonException, Runnable
    from XrdTest.SocketUtils import FixedSockStream, XrdMessage, SocketDisconnectedError
    from XrdTest.TestUtils import TestSuite
    from XrdTest.Utils import State 
    from optparse import OptionParser
    from string import join
    from copy import copy
    from subprocess import Popen
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)

# Globals and configurations
currentDir = os.path.dirname(os.path.abspath(__file__))
os.chdir(currentDir)
#Default daemon configuration
defaultConfFile = '/etc/XrdTest/XrdTestSlave.conf'
defaultPidFile = '/var/run/XrdTestSlave.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestSlave.log'

class TCPReceiveThread(object):
    ''' TODO: '''
    def __init__(self, sock, recvQueue):
        '''
        TODO: 

        @param sock:
        @param recvQueue:
        '''
        self.sockStream = sock
        self.stopEvent = threading.Event()
        self.stopEvent.clear()
        self.recvQueue = recvQueue

    def close(self):
        ''' TODO: '''
        self.stopEvent.set()

    def run(self):
        ''' TODO: '''
        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                LOGGER.debug("Received raw: " + str(msg))
                self.recvQueue.put(msg)
            except SocketDisconnectedError, e:
                LOGGER.info("Connection to XrdTestMaster closed.")
                sys.exit(1)
                break

class XrdTestSlave(Runnable):
    '''
    Test Slave main executable class.
    '''
    def __init__(self, config):
        ''' TODO: '''
        self.sockStream = None
        #Blocking queue of commands received from XrdTestMaster
        self.recvQueue = Queue.Queue()
        self.config = config
        self.stopEvent = threading.Event()
        # Ran test cases, indexed by test.uid
        self.cases = {}

    def executeSh(self, cmd):
        '''
        @param cmd:
        '''
        command = ""
        cmd = cmd.strip()

        LOGGER.info("executeSh: %s" % cmd)
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

        command = command.replace("@slavename@", socket.gethostname())
        LOGGER.info("Shell script to run: " + command)

        res = ('Nothing executed', '', '0')
        localError = ''
        try:
            process = Popen(command, shell="None", \
                        stdout=subprocess.PIPE, \
                        stderr=subprocess.STDOUT)

            stdout, stderr = process.communicate()
            res = (stdout, stderr, str(process.returncode))
        except ValueError, e:
            localError += str(e)
            LOGGER.error("Execution of shell script failed: %s" % e)
        except e:
            localError += str(e)
            LOGGER.error("Execution of shell script failed: %s" % e)
        except Exception, e:
            localError += str(e)
            LOGGER.error("Execution of shell script failed: %s" % e)

        if localError:
            (a, b, c) = res
            t = "\nERRORS THAT OCCURED ON TEST SLAVE:\n "
            res = (a, b + t + str(localError), '1')

        return res

    def connectMaster(self, masterName, masterPort):
        ''' TODO: '''
        global currentDir
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
                LOGGER.info("Connection from master refused.")
            else:
                LOGGER.info("Connection with master could not be established.")
                LOGGER.exception(e)
            return None
        else:
            LOGGER.debug("Connected to master.")
        try:
            self.sockStream = FixedSockStream(self.sockStream)

            #authenticate in master
            self.sockStream.send(\
                self.config.get('test_master', 'connection_passwd'))
            msg = self.sockStream.recv()
            LOGGER.info('Received msg: ' + msg)
            if msg == "PASSWD_OK":
                LOGGER.info("Connected and authenticated to XrdTestMaster " + \
                            "successfully. Waiting for commands " + \
                            "from the master.")
            else:
                LOGGER.info("Password authentication in master failed.")
                return None
        except socket.error, e:
            LOGGER.exception(e)
            return None

        self.sockStream.send(("slave", socket.gethostname()))

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
                    (testName, suiteName, msg.result))

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
                    (testName, suiteName, msg.result))

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
                    (testName, suiteName, msg.result))

        return msg

    def handleTestSuiteInitialize(self, msg):
        ''' TODO: '''
        cmd = msg.cmd
        jobGroupId = msg.jobGroupId
        suiteName = msg.suiteName

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
        # re-up logging level for logfile
        LOGGER.setLevel(level=logging.DEBUG)
    
        sock = self.connectMaster(self.config.get('test_master', 'ip'),
                           self.config.getint('test_master', 'port'))
        if not sock:
            return

        tcpReceiveTh = TCPReceiveThread(self.sockStream, self.recvQueue)
        thTcpReceive = threading.Thread(target=tcpReceiveTh.run)
        thTcpReceive.start()

        self.recvLoop()


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
    
    # suppress output on daemon start
    if options.backgroundMode:
        LOGGER.setLevel(level=logging.ERROR)

    isConfigFileRead = False
    config = ConfigParser.ConfigParser()

    # read the config file
    global defaultConfFile
    LOGGER.info("Loading config file: %s" % options.configFile)
    try:
        confFile = ''
        if options.configFile:
            confFile = options.configFile
        if not os.path.exists(confFile):
            confFile = defaultConfFile
        config = readConfig(confFile)
        isConfigFileRead = True
    except (RuntimeError, ValueError, IOError), e:
        LOGGER.exception()
        sys.exit(1)

    testSlave = XrdTestSlave(config)

    # run the daemon
    if options.backgroundMode:
        LOGGER.info("Run in background: %s" % options.backgroundMode)

        pidFile = defaultPidFile
        logFile = defaultLogFile
        if isConfigFileRead:
            pidFile = config.get('daemon', 'pid_file_path')
            logFile = config.get('daemon', 'log_file_path')

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
