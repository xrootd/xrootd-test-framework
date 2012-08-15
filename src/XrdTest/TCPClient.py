#!/usr/bin/env python
#-------------------------------------------------------------------------------
#
# Copyright (c) 2011-2012 by European Organization for Nuclear Research (CERN)
# Author: Justin Salmon <jsalmon@cern.ch>
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
# File:   XrdTCPClient
# Desc:   TODO:
#-------------------------------------------------------------------------------
from XrdTest.Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import threading
    import sys
    
    from XrdTest.SocketUtils import SocketDisconnectedError
    from XrdTest.Utils import Stateful
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)
    

class TCPClient(Stateful):
    '''
    Represents any type of TCP client that connects to XrdTestMaster. Base
    class for Hypervisor and Slave.
    '''
    # states of a client
    S_CONNECTED_IDLE = (1, "Connected")
    S_NOT_CONNECTED = (2, "Not connected")
    
    def __init__(self, socket, hostname, address, state):
        Stateful.__init__(self)
        self.socket = socket
        self.hostname = hostname
        self.state = state
        self.address = address

    def send(self, msg):
        try:
            LOGGER.debug('Sending: %s to %s[%s]' % \
                        (msg.name, self.hostname, str(self.address)))
            self.socket.send(msg)
        except SocketDisconnectedError, e:
            LOGGER.error("Socket to client %s[%s] closed during send." % \
                         (self.hostname, str(self.address)))
            
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
                break

class Hypervisor(TCPClient):
    '''
    Wrapper for any hypervisor connection established.
    '''
    def __init__(self, socket, hostname, address, state):
        TCPClient.__init__(self, socket, hostname, address, state)
        self.runningClusterDefs = {}

    def __str__(self):
        return "Hypervisor %s [%s]" % (self.hostname, self.address)

class Slave(TCPClient):
    '''
    Wrapper for any slave connection established.
    '''
    # constants representing states of slave
    S_SUITE_INIT_SENT = (10, "Test suite init sent to slave")
    S_SUITE_INITIALIZED = (11, "Test suite initialized")
    S_SUITE_FINALIZE_SENT = (12, "Test suite finalize sent to slave")

    S_TEST_INIT_SENT = (21, "Sent test case init to slave")
    S_TEST_INITIALIZED = (22, "Test case initialized")
    S_TEST_RUN_SENT = (23, "Sent test case run to slave")
    S_TEST_RUN_FINISHED = (24, "Test case run finished")
    S_TEST_FINALIZE_SENT = (25, "Sent test case finalize to slave")
    #S_TEST_FINALIZED        = Slave.S_SUITE_INITIALIZED

    def __str__(self):
        return "Slave %s [%s]" % (self.hostname, self.address)