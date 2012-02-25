from heapq import heappush, heappop
from string import zfill
from threading import Condition, RLock, Lock
import logging
import pickle
import socket
import threading
#------------------------------------------------------------------------------ 
logging.basicConfig(format='%(asctime)s %(levelname)s [%(lineno)d] ' + \
                    '%(message)s', level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)
#-------------------------------------------------------------------------------
class PriorityBlockingQueue(object):
    '''
    Synchronized priority queue. 
    Pattern for entries is a tuple in the form: (priority_number, data).
    Lowest valued entries are retrieved first.
    '''
    h = []
    lock = None
    criticalSection = None
    #---------------------------------------------------------------------------
    def __init__(self):
        self.lock = Lock()
        self.criticalSection = Condition(self.lock)
    #---------------------------------------------------------------------------
    def put(self, elem):
        '''
        Puts element to the queue.
        @param elem: a tuple in the form: (priority_number[int], data).
        '''
        self.criticalSection.acquire()
        heappush(self.h, elem)
        if len(self.h) == 1:
            self.criticalSection.notify()

        self.criticalSection.release()
    #---------------------------------------------------------------------------
    def rawGet(self):
        '''
        Retrieves tuple element (priority, data) 
        with the lowest priority from the queue.
        '''
        self.criticalSection.acquire()
        while len(self.h) <= 0:
            self.criticalSection.wait()
        elem = heappop(self.h)
        self.criticalSection.release()

        return elem
    #---------------------------------------------------------------------------
    def get(self):
        '''
        Retrieves data of an element from (priority, data) 
        with the lowest priority from the queue.
        '''
        return self.rawGet()[1]
#-------------------------------------------------------------------------------
class XrdMessage(object):
    '''
    Network message passed between Xrd Testing Framework nodes.
    '''

    #---------------------------------------------------------------------------
    # Constants for XrdMessage name values 
    M_HELLO = 'hello'
    M_START_CLUSTER = 'start_cluster'
    M_STOP_CLUSTER  = 'stop_cluster'
    M_CLUSTER_STATE = 'cluster_state'
    #--------------------------------------------------------------------------
    M_TESTSUITE_INIT = 'init_test_suite'
    M_TESTSUITE_FINALIZE = 'finalize_test_suite'
    M_TESTSUITE_STATE = "test_suite_state"
    #---------------------------------------------------------------------------
    M_TESTCASE_RUN = 'test_case_run'
    M_TESTSUITE_STATE = 'test_case_state'
    M_TESTCASE_STAGE_RESULT = 'test_case_stage_result'

    M_DISCONNECT = 'disconnect'
    M_UNKNOWN = 'unknown'

    name = M_UNKNOWN
    sender = None
    #---------------------------------------------------------------------------
    def __init__(self, name, msg_sender = None):
        '''
        Constructor
        @param name: constant from this class
        @param msg_sender: address tuple (IP, socket)
        '''
        self.name = name
        self.sender = msg_sender
#-------------------------------------------------------------------------------
class SocketDisconnectedError(Exception):
    desc = ""
    #---------------------------------------------------------------------------
    def __init__(self, desc):
        '''
        Constructs Exception
        @param desc: description of an error
        '''
        self.desc = desc
    #---------------------------------------------------------------------------
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)
#-------------------------------------------------------------------------------
class FixedSockStream(object):
    '''
    Wrapper for socket to ensure correct behaviour of send and recv.
    '''
    #---------------------------------------------------------------------------
    def __init__(self, sock):
        if sock and not isinstance(sock, FixedSockStream):
            self.sock = sock
        else:
            RuntimeError("This class cannot wrap object of it's own instance")
        self.SIZE_STAMP_LEN = 8
    #---------------------------------------------------------------------------
    def sendBounded(self, msg, toSendLen):
        totalsent = 0
        try:
            sent = self.sock.send(msg[totalsent:])
            while totalsent < toSendLen:
                if sent == 0:
                    #socket disconnected
                    raise SocketDisconnectedError("Socket connection ended")
                totalsent = totalsent + sent
        except socket.error, e:
            LOGGER.exception(e)
            raise SocketDisconnectedError("Socket connection ended")
    #---------------------------------------------------------------------------
    def recvBounded(self, toRecvLen):
        try:
            msg = ''
            while len(msg) < toRecvLen:
                chunk = self.sock.recv(toRecvLen - len(msg))
                if chunk == '':
                    #socket disconnected
                    raise SocketDisconnectedError("Socket connection ended")
                msg = msg + chunk
        except socket.error, e:
            LOGGER.exception(e)
            raise SocketDisconnectedError("Socket connection ended")
        return msg
    #---------------------------------------------------------------------------
    def send(self, obj, sendRaw=False):
        if not sendRaw:
            msg = pickle.dumps(obj)
        else:
            msg = obj
        toSendLen = len(msg)
        toSendLenFilled = zfill(str(toSendLen), self.SIZE_STAMP_LEN)
        self.sendBounded(toSendLenFilled, self.SIZE_STAMP_LEN)
        self.sendBounded(msg, toSendLen)
    #---------------------------------------------------------------------------
    def recv(self, recvRaw=False):
        toRcvLen = self.recvBounded(self.SIZE_STAMP_LEN)
        msg = ''
        obj = None
        try:
            toRcvLen = int(toRcvLen)
            msg = self.recvBounded(toRcvLen)
        except ValueError, e:
            LOGGER.exception(e)
        if not recvRaw:
            obj = pickle.loads(msg)
        else:
            obj = msg
        return obj
    #---------------------------------------------------------------------------
    def close(self):
        self.sock.close()
