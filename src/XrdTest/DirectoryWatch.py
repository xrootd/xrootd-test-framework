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
# File:    DirectoryWatch
# Desc:    TODO
#-------------------------------------------------------------------------------
# Logging settings
#-------------------------------------------------------------------------------
import logging
import sys
import types

logging.basicConfig(format='%(asctime)s %(levelname)s ' + \
                    '[%(filename)s %(lineno)d] ' + \
                    '%(message)s', level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)
LOGGER.debug("Running script: " + __file__)

#-------------------------------------------------------------------------------
# Imports
#-------------------------------------------------------------------------------
try:
    from pyinotify import WatchManager, ThreadedNotifier, ProcessEvent
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)

#-------------------------------------------------------------------------------
class DirectoryWatch(object):
    
    def __init__(self, config, callback, watch_type=None):
        self.config = config
        self.callback = callback
        self.watch_type = watch_type
        
        if watch_type:
            self.watch_type = types.MethodType(watch_type, self, DirectoryWatch)
        
    def watch(self):
        self.watch_type()
        

def watch_remote(self):
        pass # an implementation

def watch_local(self):
        wm = WatchManager()
        wm2 = WatchManager()
        # constants from /usr/src/linux/include/linux/inotify.h
        IN_MOVED = 0x00000040L | 0x00000080L     # File was moved to or from X
        IN_CREATE = 0x00000100L     # Subfile was created
        IN_DELETE = 0x00000200L     # was delete
        IN_MODIFY = 0x00000002L     # was modified
        mask = IN_DELETE | IN_CREATE | IN_MOVED | IN_MODIFY
        
        clustersNotifier = ThreadedNotifier(wm, \
                            ClustersDefinitionsChangeHandler(\
                            masterCallback=self.callback))
        suitsNotifier = ThreadedNotifier(wm2, \
                            SuitsDefinitionsChangeHandler(\
                            masterCallback=self.callback))
        clustersNotifier.start()
        suitsNotifier.start()

        wddc = wm.add_watch(self.config.get('server', \
                           'clusters_definition_path'), \
                           mask, rec=True)
        wdds = wm2.add_watch(self.config.get('server', \
                           'testsuits_definition_path'), \
                           mask, rec=True)
        

class ClustersDefinitionsChangeHandler(ProcessEvent):
    '''
    If cluster' definition file changes - it runs.
    '''
    #---------------------------------------------------------------------------
    def __init__(self, pevent=None, **kwargs):
        '''
        Init signature copy from base class. Created to save some callback 
        parameter in class param.
        @param pevent:
        '''
        ProcessEvent.__init__(self, pevent=pevent, **kwargs)
        self.callback = kwargs['masterCallback']
    #---------------------------------------------------------------------------
    def process_default(self, event):
        '''
        Actual method that handle incoming dir change event.
        @param event:
        '''
        self.callback("CLUSTER", event)
#-------------------------------------------------------------------------------
class SuitsDefinitionsChangeHandler(ProcessEvent):
    '''
    If suit' definition file changes it runs
    '''
    #---------------------------------------------------------------------------
    def __init__(self, pevent=None, **kwargs):
        '''
        Init signature copy from base class. Created to save some callback 
        parameter in class param.
        @param pevent:
        '''
        ProcessEvent.__init__(self, pevent=pevent, **kwargs)
        self.callback = kwargs['masterCallback']
    #---------------------------------------------------------------------------
    def process_default(self, event):
        '''
        Actual method that handle incoming dir change event.
        @param event:
        '''
        self.callback("SUIT", event)
        
