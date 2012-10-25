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
# File:   Utils
# Desc:   TODO:
#-------------------------------------------------------------------------------
import logging
import datetime
import subprocess
import os
import sys
import threading

from copy import copy
from threading import Lock, Condition

class State(object):
    '''
    Represents current state of some entity.
    '''
    def __init__(self, status_tuple, additDesc=''):
        '''
        Creates a state information.
        @param status_tuple: tuple comprised from at least (id, name)
        @param additDesc: additional descriptin of a status, e.g. Exception
        '''
        self.id = status_tuple[0]
        self.name = status_tuple[1]
        self.datetime = datetime.datetime.now()
        self.time = self.datetime.strftime("%d-%m-%Y %H:%M:%S")
        if additDesc:
            self.addDesc(additDesc)

    def isError(self):
        return self.id < 0

    def addDesc(self, anyStr):
        self.name = self.name + ' ' + str(anyStr)

    def __eq__(self, oth):
        if not isinstance(oth, State):
            if not isinstance(oth, tuple) or len(oth) != 2:
                raise RuntimeError("Comparison between non-comparable types.")
            else:
                return oth[0] == self.id
        else:
            return oth.id == self.id

    def __ne__(self, oth):
        return not self == oth

    def __str__(self):
        return "[%s] %s at %s" % \
                (str(self.id), self.name, self.time)

class Stateful(object):
    '''
    Represents stateful entity and remember its previous states.
    '''
    def __init__(self):
        self.states = []

    def getState(self):
        if len(self.states):
            return self.states[-1]
        else:
            return None

    def setState(self, state):
        return self.states.append(state)

    state = property(getState, setState)

class SafeCounter(object):
    '''
    TODO:
    '''
    def __init__(self):
        self.lock = Lock()
        self.criticalSection = Condition(self.lock)
        self.counter = 0

    def inc(self):
        self.criticalSection.acquire()
        LOGGER.debug("COUNTER += 1")
        self.counter += 1
        self.criticalSection.notify()
        self.criticalSection.release()

    def get(self):
        self.criticalSection.acquire()
        self.criticalSection.wait()
        num = copy(self.counter)
        LOGGER.debug("COUNTER get")
        self.criticalSection.release()
        return num

class Command(object):
    '''
    Execute a subprocess command.
    '''
    def __init__(self, cmd, cwd):
        self.cmd = cmd
        self.cwd = cwd
    
    def execute(self):
        LOGGER.debug('Running command: %s' % self.cmd)
        proc = subprocess.Popen(self.cmd, shell=True, stdout=subprocess.PIPE,
                                             cwd=self.cwd)
        stdout = proc.communicate()[0]
        retcode = proc.returncode
        
        if retcode != 0:
            LOGGER.error('Command returned with non-zero exit code: %s' % retcode)
        
        output = stdout
        if output == '': 
            LOGGER.debug('Command returned no output.') 
        #else: 
            #LOGGER.debug('Command output: \n%s' % output.rstrip('\n'))
        return (output, retcode)
    
class Logger(object):
    '''
    Generic logging class
    '''
    def __init__(self, filename):
        self.filename = filename
    
    def setup(self):
        logging.basicConfig(format='%(asctime)s %(levelname)s \t' + \
                    '[%(filename)s %(lineno)d] ' + \
                    '%(message)s', datefmt="[%H:%M:%S]")
        return logging.getLogger(self.filename)
        
def redirectOutput(logFile):
    '''
    Redirect the stderr and stdout to a file
    '''
    try:
        devNull = file(os.devnull, 'r')
        os.close(sys.stdin.fileno())
        os.dup2(devNull.fileno(), sys.stdin.fileno())
        os.chdir('/')
        
        outLog = file(logFile, 'a+')
        sys.stdout.flush()
        sys.stderr.flush()
        os.close(sys.stdout.fileno())
        os.close(sys.stderr.fileno())

        os.dup2(outLog.fileno(), sys.stdout.fileno())
        os.dup2(outLog.fileno(), sys.stderr.fileno())
    except IOError, e:
        raise Exception('Cannot redirect output to the log file: ' + 
                              str(e))

LOGGER = Logger(__name__).setup()
    
