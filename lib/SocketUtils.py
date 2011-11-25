from ClusterManager import Status
from heapq import heappush, heappop
from string import zfill
from threading import Condition
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
    sectLock = Condition()
    #---------------------------------------------------------------------------
    def __init__(self):
        pass
    #---------------------------------------------------------------------------
    def put(self, elem):
        '''
        Puts element to the queue.
        @param elem: a tuple in the form: (priority_number[int], data).
        '''
        self.sectLock.acquire()
        heappush(self.h, elem)
        if len(self.h) == 1:
            self.sectLock.notify()

        self.sectLock.release()
    #---------------------------------------------------------------------------
    def rawGet(self):
        '''
        Retrieves tuple element (priority, data) 
        with the lowest priority from the queue.
        '''
        self.sectLock.acquire()

        while len(self.h) <= 0:
            self.sectLock.wait()
        elem = heappop(self.h)
        self.sectLock.release()

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
    M_HELLO = 'hello'
    M_START_CLUSTER = 'start_cluster'
    M_CLUSTER_STATUS = 'cluster_status'
    M_UNKNOWN = 'unknown'
    
    name = M_UNKNOWN
    #---------------------------------------------------------------------------
    def __init__(self, name):
        '''
        Constructor
        @param name: string, name of the message
        '''
        self.name = name
#-------------------------------------------------------------------------------
class SocketDisconnected(Exception):
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
                    raise SocketDisconnected("Socket connection ended")
                totalsent = totalsent + sent
        except socket.error, e:
            LOGGER.exception(e)
            raise SocketDisconnected("Socket connection ended")
    #---------------------------------------------------------------------------
    def recvBounded(self, toRecvLen):
        try:
            msg = ''
            while len(msg) < toRecvLen:
                chunk = self.sock.recv(toRecvLen - len(msg))
                if chunk == '':
                    #socket disconnected
                    raise SocketDisconnected("Socket connection ended")
                msg = msg + chunk
        except socket.error, e:
            LOGGER.exception(e)
            raise SocketDisconnected("Socket connection ended")
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
