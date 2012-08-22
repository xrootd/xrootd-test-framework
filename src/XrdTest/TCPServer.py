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
# File:   XrdTCPServer
# Desc:   TODO:
#-------------------------------------------------------------------------------
from Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import ssl 
    import sys
    import threading
    import SocketServer
    
    from XrdTest.SocketUtils import FixedSockStream, SocketDisconnectedError
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)


class XrdTCPServer(SocketServer.TCPServer):
    '''
    Wrapper for SocketServer.TCPServer, to enable setting beneath params.
    '''
    allow_reuse_address = True

class ThreadedTCPServer(SocketServer.ThreadingMixIn, XrdTCPServer):
    '''
    Wrapper to create threaded TCP Server.
    '''
    
class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):
    """
    Client's TCP request handler.
    """
    C_SLAVE = "slave"
    C_HYPERV = "hypervisor"

    def setup(self):
        '''
        Initiate class properties
        '''
        self.stopEvent = threading.Event()
        self.stopEvent.clear()
        self.sockStream = None
        self.clientType = ThreadedTCPRequestHandler.C_SLAVE

    def authClient(self, clientType):
        '''
        Check if hypervisor is authentic. It will provide the connection password.
        '''
        msg = self.sockStream.recv()
        if msg == self.server.config.get('server', 'connection_passwd'):
            self.sockStream.send('PASSWD_OK')
        else:
            self.sockStream.send('PASSWD_WRONG')
            LOGGER.info("Incoming hypervisor connection rejected. " + \
                        "It didn't provide correct password")
            return
        return True

    def handle(self):
        '''
        Handle new incoming connection and keep it to receive messages.
        '''
        self.sockStream = ssl.wrap_socket(self.request, server_side=True,
                                          certfile=\
                                self.server.config.get('security', 'certfile'),
                                          keyfile=\
                                self.server.config.get('security', 'keyfile'),
                                          ssl_version=ssl.PROTOCOL_TLSv1)
        self.sockStream = FixedSockStream(self.sockStream)
        
        # whether client is slave or hypervisor
        (clientType, clientHostname) = self.sockStream.recv()
        # authenticate hypervisors
        if clientType == 'hypervisor':
            self.authClient(clientType)

        LOGGER.info(("%s [%s, %s] establishing connection...") % \
                                (clientType.capitalize(), \
                                 clientHostname, self.client_address))

        self.clientType = ThreadedTCPRequestHandler.C_SLAVE
        if clientType == ThreadedTCPRequestHandler.C_HYPERV:
            self.clientType = ThreadedTCPRequestHandler.C_HYPERV

        # prepare MasterEvent and add it to main program events queue
        # to handle logic of event
        evt = MasterEvent(MasterEvent.M_CLIENT_CONNECTED, (self.clientType,
                            self.client_address, self.sockStream, \
                            clientHostname))
        self.server.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))

        # begin listening on the client's socket.
        # emit MasterEvent in case any message comes
        while not self.stopEvent.isSet():
            try:
                msg = self.sockStream.recv()
                evtType = MasterEvent.M_SLAVE_MSG
                if self.clientType == self.C_HYPERV:
                    evtType = MasterEvent.M_HYPERV_MSG

                LOGGER.debug("Server: Received message %s, enqueuing event: %s" % (msg, str(evtType)))
                msg.sender = self.client_address

                evt = MasterEvent(evtType, msg, self.client_address)
                self.server.recvQueue.put((MasterEvent.PRIO_NORMAL, evt))
            except SocketDisconnectedError, e:
                evt = MasterEvent(MasterEvent.M_CLIENT_DISCONNECTED, \
                                  (self.clientType, self.client_address))
                self.server.recvQueue.put((MasterEvent.PRIO_IMPORTANT, evt))
                break

        LOGGER.info("Server: Closing connection with %s [%s]" % \
                                    (clientHostname, self.client_address))
        self.sockStream.close()
        self.stopEvent.clear()
        return


class MasterEvent(object):
    '''
    Wrapper for all events that comes to XrdTestMaster. MasterEvent can
    be message from slave or hypervisor, system event like socket disconnection,
    cluster or test suite definition file change or scheduler job initiation.
    It has priorities. PRIO_IMPORTANT is processed before PRIO_NORMAL.
    '''
    PRIO_NORMAL = 9
    PRIO_IMPORTANT = 1

    M_UNKNOWN = 1
    M_CLIENT_CONNECTED = 2
    M_CLIENT_DISCONNECTED = 3
    M_HYPERV_MSG = 4
    M_SLAVE_MSG = 5
    M_JOB_ENQUEUE = 6
    M_RELOAD_CLUSTER_DEF = 7
    M_RELOAD_SUITE_DEF = 8

    def __init__(self, e_type, e_data, msg_sender_addr=None):
        self.type = e_type
        self.data = e_data
        self.sender = msg_sender_addr
