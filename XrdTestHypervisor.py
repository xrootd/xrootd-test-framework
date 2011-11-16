from Daemon import Daemon, readConfig, DaemonException, Runnable
from SocketUtils import FixedSockStream, XrdMessage, SocketDisconnected
from optparse import OptionParser
import ConfigParser
import Queue
import copy
import hashlib
import logging
import os
import socket
import ssl
import sys
import threading
import time

logging.basicConfig(format='%(asctime)s %(levelname)s [%(lineno)d] ' + \
                    '%(message)s', level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
currentDir = os.path.dirname(os.path.abspath(__file__))

#Default daemon configuration
defaultConfFile = './XrdTestHypervisor.conf'
defaultPidFile = '/var/run/XrdTestHipervisor.pid'
defaultLogFile = '/var/log/XrdTest/XrdTestHipervisor.log'

#-------------------------------------------------------------------------------
class TCPReceiveThread(object):
    #---------------------------------------------------------------------------
    def __init__(self, sock, recvQueue):
        '''
        @param sock:
        @param recvQueue:
        '''
        self.sockStream = sock
        self.stopEvent = threading.Event()
        self.stopEvent.clear()
        self.recvQueue = recvQueue
    #---------------------------------------------------------------------------
    def close(self):
        self.stopEvent.set()
    #---------------------------------------------------------------------------
    def run(self):
        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                LOGGER.debug("Received raw: " + str(msg))
                self.recvQueue.put(msg)
            except SocketDisconnected, e:
                LOGGER.info("Connection to XrdTestMaster closed.")
                break
#-------------------------------------------------------------------------------
class ExecutorThread(object):
    '''
    Thread retrieving incoming command from recvQueue, executing the job and 
    sending response to the master.
    '''
    #---------------------------------------------------------------------------
    def __init__(self, config, sock, recvQueue):
        self.sockStream = sock
        self.stopEvent = threading.Event()
        self.stopEvent.clear()
        self.recvQueue = recvQueue
        self.config = config
    #---------------------------------------------------------------------------
    def close(self):
        self.stopEvent.set()
    #---------------------------------------------------------------------------
    def handleStartCluster(self, msg):
        cluster = msg.clusterDef

#-------------------------------------------------------------------------------
class XrdTestHipervisor(Runnable):
    '''
    Test Hipervisor main executable class.
    '''
    sockStream = None
    recvQueue = Queue.Queue()
    config = None
    #---------------------------------------------------------------------------
    def __init__(self, config):
        self.sockStream = None
        #Blocking queue of commands received from XrdTestMaster
        self.recvQueue = Queue.Queue()
        self.config = config
        self.stopEvent = threading.Event()
    #---------------------------------------------------------------------------
    def connectMaster(self, masterIp, masterPort):
        global currentDir
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sockStream = ssl.wrap_socket(sock, server_side=False,
                                        certfile=\
                                        self.config.get('security', 'certfile'),
                                        keyfile=\
                                        self.config.get('security', 'keyfile'),
                                        ssl_version=ssl.PROTOCOL_TLSv1)
            #self.sockStream = sock
            self.sockStream.connect((masterIp, masterPort))
        except socket.error, e:
            LOGGER.info("Connection with master could not be established.")
            LOGGER.exception(e)
            return None
        else:
            LOGGER.info("No exceptions occured")
        try:
            self.sockStream = FixedSockStream(self.sockStream)

            #authenticate in master
            self.sockStream.send(\
                self.config.get('test_master', 'connection_passwd'))
            msg = self.sockStream.recv()
            LOGGER.info('Received msg: ' + msg)
            if msg == "PASSWD_OK":
                LOGGER.info("Connected to XrdTestMaster successfull." + \
                            " Waiting for commands from the master.")

            return self.sockStream
        except socket.error, e:
            LOGGER.exception(e)
        else:
            LOGGER.info("No exceptions occured")

        return self.sockStream
    #---------------------------------------------------------------------------
    def recvLoop(self):
        global LOGGER
        while not self.stopEvent.isSet():
            try:
                #receive msg from master
                addrMsg = self.recvQueue.get()
                msg = addrMsg
                LOGGER.info("Received msg: " + str(msg.name))

                resp = XrdMessage(XrdMessage.MSG_UNKNOWN)
                if msg.name is XrdMessage.MSG_HELLO:
                    resp = XrdMessage(XrdMessage.MSG_HELLO)
                elif msg.name is XrdMessage.MSG_START_CLUSTER:
                    self.handleStartCluster(msg)
                else:
                    LOGGER.info("Received unknown message: " + str(msg.name))

                self.sockStream.send(resp)
                LOGGER.debug("Sent msg: " + str(resp))
            except SocketDisconnected, e:
                LOGGER.info("Connection to XrdTestMaster closed.")
                break
    #---------------------------------------------------------------------------
    def run(self):
        sock = self.connectMaster(self.config.get('test_master', 'ip'), 
                           self.config.getint('test_master', 'port'))
        if not sock:
            return

        tcpReceiveTh = TCPReceiveThread(self.sockStream, self.recvQueue)
        thTcpReceive = threading.Thread(target=tcpReceiveTh.run)
        thTcpReceive.start()

        self.recvLoop()

#-------------------------------------------------------------------------------
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

    isConfigFileRead = False
    config = ConfigParser.ConfigParser()
    #---------------------------------------------------------------------------
    # read the config file
    #---------------------------------------------------------------------------
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

    testHipervisor = XrdTestHipervisor(config)
    #--------------------------------------------------------------------------
    # run the daemon
    #--------------------------------------------------------------------------
    if options.backgroundMode:
        LOGGER.info("Run in background: %s" % options.backgroundMode)

        pidFile = defaultPidFile
        logFile = defaultLogFile
        if isConfigFileRead:
            pidFile = config.get('daemon', 'pid_file_path')
            logFile = config.get('daemon', 'log_file_path')

        dm = Daemon("XrdTestHipervisor.py", pidFile, logFile)
        try:
            if options.backgroundMode == 'start':
                dm.start(testHipervisor)
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
            LOGGER.exception(e)
            sys.exit(1)
    #--------------------------------------------------------------------------
    # run test master in standard mode. Used for debugging
    #--------------------------------------------------------------------------
    if not options.backgroundMode:
        testHipervisor.run()
#-------------------------------------------------------------------------------
# Start place
#-------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
