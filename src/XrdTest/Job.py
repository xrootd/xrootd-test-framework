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
# File:   Job
# Desc:   TODO:
#-------------------------------------------------------------------------------
import datetime
from string import maketrans


class Job(object):
    '''
    Keeps information about job, that is to be run. It's enqueued by scheduler
    and dequeued if fore coming job was handled.
    '''
    # constants representing jobs states
    S_ADDED = (0, "Job added to jobs list.")
    S_STARTED = (1, "Job started. In progress.")
    # constants representing jobs' types
    TEST_JOB = 0
    
    INITIALIZE_TEST_SUITE = 1
    FINALIZE_TEST_SUITE = 2

    INITIALIZE_TEST_CASE = 3
    RUN_TEST_CASE = 4
    FINALIZE_TEST_CASE = 5

    START_CLUSTER = 6
    STOP_CLUSTER = 7

    def __init__(self, job, groupId="", args=None):
        self.job = job              # job type
        self.state = Job.S_ADDED    # initial job state
        self.args = args            # additional job's attributes
                                    # e.g. suite name or cluster_name
        self.groupId = groupId      # group of jobs to which this one belongs


    def genJobGroupId(self, suite_name):
        '''
        Utility function to create unique name for group of jobs.
        @param suite_name:
        '''
        d = datetime.datetime.now()
        r = "%s-%s" % (suite_name, d.isoformat())
        r = r.translate(maketrans('', ''), '-:.')# remove special
        return r
    
