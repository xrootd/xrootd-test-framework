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
# File:  DirectoryWatch
# Desc:  Classes to handle monitoring of both local and remote directories for
#        changes. Local directories are monitored for general changes using 
#        pyinotify. Remote directories are test suite repositories, and are 
#        polled for new commits. Currently supported repository types: Git
#-------------------------------------------------------------------------------
from Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import sys
    import types
    
    from pyinotify import WatchManager, ThreadedNotifier, ProcessEvent, WatchManagerError
    from apscheduler.scheduler import Scheduler
    from GitUtils import sync_remote_git
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)


class DirectoryWatch(object):
    '''
    Base class for monitoring directories and invoking callback on change.
    Instantiation of this class defines which type of watch will happen (local
    or remote)
    '''
    # constants from /usr/src/linux/include/linux/inotify.h
    IN_MOVED = 0x00000040L | 0x00000080L    # File was moved to or from X
    IN_CREATE = 0x00000100L                 # Subfile was created
    IN_DELETE = 0x00000200L                 # was delete
    IN_MODIFY = 0x00000002L                 # was modified
    mask = IN_DELETE | IN_CREATE | IN_MOVED | IN_MODIFY
    
    def __init__(self, repo, config, callback, watch_type=None):
        '''
        TODO:
        '''
        self.repo = repo
        self.config = config
        self.callback = callback
        self.watch_type = watch_type
        
        if watch_type:
            self.watch_type = types.MethodType(watch_type, self, DirectoryWatch)
        
    def watch(self):
        self.watch_type()
        
    def watch_localfs(self):
        '''
        Monitor a local directory for changes.
        '''
        wm = WatchManager()
        wm2 = WatchManager()
        
        clusterNotifier = ThreadedNotifier(wm, \
                            ClustersDefinitionsChangeHandler(\
                            masterCallback=self.callback))
        suiteNotifier = ThreadedNotifier(wm2, \
                            SuiteDefinitionsChangeHandler(\
                            masterCallback=self.callback))
        clusterNotifier.start()
        suiteNotifier.start()
    
        wm.add_watch(self.config.get(self.repo, \
                           'cluster_defs_path'), \
                           self.mask, rec=True)
        wm2.add_watch(self.config.get(self.repo, \
                           'suite_defs_path'), \
                           self.mask, rec=True)
        
    def watch_remote_git(self):
        '''
        Monitor a remote git repository by polling at a set interval.
        '''
        sched = Scheduler()
        sched.start()
        sched.add_interval_job(sync_remote_git, seconds=30, args=[self.repo, self.config])
        
        wm = WatchManager()
        wm2 = WatchManager()
        
        clusterNotifier = ThreadedNotifier(wm, \
                            ClustersDefinitionsChangeHandler(\
                            masterCallback=self.callback))
        suiteNotifier = ThreadedNotifier(wm2, \
                            SuiteDefinitionsChangeHandler(\
                            masterCallback=self.callback))
        clusterNotifier.start()
        suiteNotifier.start()
    
        try:
            wm.add_watch(self.config.get(self.repo, 'cluster_defs_path'), \
                               self.mask, rec=True, quiet=False)
            wm2.add_watch(self.config.get(self.repo, 'suite_defs_path'), \
                               self.mask, rec=True, quiet=False)
        except WatchManagerError, e:
            LOGGER.error(e)


class ClustersDefinitionsChangeHandler(ProcessEvent):
    '''
    If cluster definition file changes - it runs.
    '''
    def __init__(self, pevent=None, **kwargs):
        '''
        Init signature copy from base class. Created to save some callback
        parameter in class param.
        @param pevent:
        '''
        ProcessEvent.__init__(self, pevent=pevent, **kwargs)
        self.callback = kwargs['masterCallback']
        
    def process_default(self, event):
        '''
        Actual method that handle incoming dir change event.
        @param event:
        '''
        self.callback("CLUSTER", event)

class SuiteDefinitionsChangeHandler(ProcessEvent):
    '''
    If suite definition file changes it runs
    '''
    def __init__(self, pevent=None, **kwargs):
        '''
        Init signature copy from base class. Created to save some callback
        parameter in class param.
        @param pevent:
        '''
        ProcessEvent.__init__(self, pevent=pevent, **kwargs)
        self.callback = kwargs['masterCallback']

    def process_default(self, event):
        '''
        Actual method that handle incoming dir change event.
        @param event:
        '''
        self.callback("SUITE", event)
        
