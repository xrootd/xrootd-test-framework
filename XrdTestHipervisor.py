from Utils import FixedSockStream
import Queue
import hashlib
import logging
import os
import socket
import ssl
import threading
import time

logging.basicConfig(format='%(asctime)s %(levelname)s [%(lineno)d] ' + \
                    '%(message)s', level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)

currentDir = os.path.dirname(os.path.abspath(__file__))

#Blocking queue of commands received from XrdTestMaster
RECEIVE_QUEUE = Queue.Queue()

ACCESS_PASSWORD = hashlib.sha224("tajne123").hexdigest()
SERVER_IP, SERVER_PORT = '127.0.0.1', 20000

class TCPReceiveThread(object):
    def __init__(self, sock):
        self.sockStream = sock
        self.stopEvent = threading.Event()
        self.stopEvent.clear()

    def close(self):
        self.stopEvent.set()

    def run(self):
        global SERVER_IP, SERVER_PORT, RECEIVE_QUEUE

        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                LOGGER.info("Received: " + str(msg))
                RECEIVE_QUEUE.put(msg)
            except socket.error, e:
                LOGGER.exception(e)

class ExecutorThread(object):
    def __init__(self, sock):
        self.sockStream = sock
        self.stopEvent = threading.Event()
        self.stopEvent.clear()

    def close(self):
        self.stopEvent.set()

    def run(self):
        global SERVER_IP, SERVER_PORT, RECEIVE_QUEUE

        while not self.stopEvent.isSet():
            try:
                time.sleep(5)
                msg = "time runs"

                LOGGER.info("Sending msg: " + msg)
                #receive msg from master
                #msg = RECEIVE_QUEUE.get()

                self.sockStream.send(msg)
                LOGGER.info("Sent: " + str(msg))
            except socket.error, e:
                LOGGER.exception(e)
                break

class XrdTestHipervisor:
    #---------------------------------------------------------------------------
    def __init__(self):
        self.sockStream = None
    #---------------------------------------------------------------------------
    def connectMaster(self, masterIp, masterPort):
        global currentDir, ACCESS_PASSWORD
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sockStream = ssl.wrap_socket(sock, server_side=False,
                                         certfile=\
                                         currentDir + '/certs/hipervisor/hipervisorcert.pem',
                                         keyfile=\
                                         currentDir + '/certs/hipervisor/hipervisorkey.pem',
                                         ssl_version=ssl.PROTOCOL_TLSv1)
            #self.sockStream = sock
            self.sockStream.connect((masterIp, masterPort))
            self.sockStream = FixedSockStream(self.sockStream)

            #authenticate in master
            self.sockStream.send(ACCESS_PASSWORD)
            msg = self.sockStream.recv()
            LOGGER.info('Received msg: ' + msg)
            if msg == "OK":
                LOGGER.info("Connected to XrdTestMaster successfull." + \
                            " Waiting for commands from the master.")

            return self.sockStream
        except socket.error, e:
            LOGGER.exception(e)
        else:
            LOGGER.info("No exceptions occured")

        return self.sockStream
    #---------------------------------------------------------------------------
    def run(self):
        self.connectMaster(SERVER_IP, SERVER_PORT)

        tcpReceiveTh = TCPReceiveThread(self.sockStream)
        thTcpReceive = threading.Thread(target=tcpReceiveTh.run)
        thTcpReceive.start()

        executorTh = ExecutorThread(self.sockStream)
        thExecutor = threading.Thread(target=executorTh.run)
        thExecutor.start()

if __name__ == "__main__":
    hipervisor = XrdTestHipervisor()
    hipervisor.run()

