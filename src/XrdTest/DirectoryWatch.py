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
from Utils import get_logger
LOGGER = get_logger(__name__)

import sys
import types
import subprocess
import os

try:
    from pyinotify import WatchManager, ThreadedNotifier, ProcessEvent
    from apscheduler.scheduler import Scheduler
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)


class DirectoryWatch(object):
    '''
    Base class for monitoring directories and invoking callback on change.
    '''
    def __init__(self, config, callback, watch_type=None):
        self.config = config
        self.callback = callback
        self.watch_type = watch_type
        
        if watch_type:
            self.watch_type = types.MethodType(watch_type, self, DirectoryWatch)
        
    def watch(self):
        self.watch_type()
        

def watch_remote(self):
    '''
    Monitor a remote directory by polling at a set interval.
    '''
    sched = Scheduler()
    sched.start()

    sched.add_interval_job(poll_remote, seconds=10, args=[self.callback])
    
def poll_remote(callback):
    '''
    Fetch the status of a remote (git) repository for new commits. If
    new commits, trigger a definition change event and pull the new changes.

    Need key-based SSH authentication for this method to work.
    '''
    
    #TODO: refactor params into config file
    user = 'jsalmon'
    host = 'lxplus.cern.ch'
    remote_repo = "~/www/personal/repos/xrootd-testsuites.git"
    local_repo = "/var/tmp/xrootd-testsuites"
    local_branch = 'master'
    remote_branch = 'origin/master'
    
    if not os.path.exists(local_repo):
        os.mkdir(local_repo)
        execute('git clone %s@%s:%s %s' % (user, host, remote_repo, local_repo), local_repo)
        
    execute('git fetch', local_repo)
    output = execute('git diff %s %s' % (local_branch, remote_branch), local_repo)
    
    if output != '':
        LOGGER.info('Remote branch has changes. Pulling.')
        execute('git pull', local_repo)
        LOGGER.info('Triggering test suite run.')
        callback('REMOTE')
    
def execute(cmd, cwd):
    '''
    Execute a subprocess command.
    '''
    LOGGER.info('Running command: %s' % cmd)
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, cwd=cwd)
    p.wait()
    output = p.stdout.read()
    if output == '': 
        LOGGER.info('Command returned no output.') 
    else: 
        LOGGER.info('Command output: %s' % output)
    return output
    
def watch_local(self):
    '''
    Monitor a local directory for changes.
    '''
    wm = WatchManager()
    wm2 = WatchManager()
    # constants from /usr/src/linux/include/linux/inotify.h
    IN_MOVED = 0x00000040L | 0x00000080L    # File was moved to or from X
    IN_CREATE = 0x00000100L                 # Subfile was created
    IN_DELETE = 0x00000200L                 # was delete
    IN_MODIFY = 0x00000002L                 # was modified
    mask = IN_DELETE | IN_CREATE | IN_MOVED | IN_MODIFY
    
    clusterNotifier = ThreadedNotifier(wm, \
                        ClustersDefinitionsChangeHandler(\
                        masterCallback=self.callback))
    suiteNotifier = ThreadedNotifier(wm2, \
                        SuiteDefinitionsChangeHandler(\
                        masterCallback=self.callback))
    clusterNotifier.start()
    suiteNotifier.start()

    wm.add_watch(self.config.get('local', \
                       'clusters_definition_path'), \
                       mask, rec=True)
    wm2.add_watch(self.config.get('local', \
                       'testsuits_definition_path'), \
                       mask, rec=True)
        

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
        self.callback("SUIT", event)
        
