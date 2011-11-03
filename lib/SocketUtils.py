from string import zfill
import logging

logging.basicConfig(format='%(asctime)s %(levelname)s [%(lineno)d] ' + \
                    '%(message)s', level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)

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
        while totalsent < toSendLen:
            sent = self.sock.send(msg[totalsent:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            totalsent = totalsent + sent
    #---------------------------------------------------------------------------
    def recvBounded(self, toRecvLen):
        msg = ''        
        while len(msg) < toRecvLen:
            chunk = self.sock.recv(toRecvLen-len(msg))
            if chunk == '':
                raise RuntimeError("socket connection broken")
            msg = msg + chunk
        return msg
    #---------------------------------------------------------------------------
    def send(self, msg):
        toSendLen = len(msg)
        toSendLenFilled = zfill(str(toSendLen), self.SIZE_STAMP_LEN)
        self.sendBounded(toSendLenFilled, self.SIZE_STAMP_LEN)
        self.sendBounded(msg, toSendLen)
    #---------------------------------------------------------------------------
    def recv(self):
        toRcvLen = self.recvBounded(self.SIZE_STAMP_LEN)
        msg = ''
        try:
            toRcvLen = int(toRcvLen)
            msg = self.recvBounded(toRcvLen)
        except ValueError, e:
            LOGGER.exception(e)
        return msg
