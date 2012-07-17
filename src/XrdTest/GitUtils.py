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
# File:    GitUtils
# Desc:    Utilities for interacting with git repositories.
#            TODO: add more error handling.
#
#-------------------------------------------------------------------------------
from Utils import get_logger
LOGGER = get_logger(__name__)

import os
from Utils import execute

def sync_remote_git(config):
    '''
    Fetch the status of a remote git repository for new commits. If
    new commits, pull the new changes.

    Need key-based SSH authentication for this method to work. Also, on AFS
    systems like lxplus, a valid kerberos ticket is needed.
    
    @param config: configuration file containing repository information
    '''
    user = config.get('remote_git_defs', 'user')
    host = config.get('remote_git_defs', 'host')
    remote_repo = config.get('remote_git_defs', 'remote_repo')
    local_repo = config.get('remote_git_defs', 'local_repo')
    local_branch = config.get('remote_git_defs', 'local_branch')
    remote_branch = config.get('remote_git_defs', 'remote_branch')
    
    # Clone the repo if we don't have it yet.
    if not os.path.exists(local_repo):
        git_clone(user, host, remote_repo, local_repo, local_repo)
    
    git_fetch(local_repo)
    output = git_diff(local_branch, remote_branch, local_repo)
    
    # If git-diff prints to stdout, then we have changes (or an error).
    # TODO: handle errors with incorrect branch names
    if output != '':
        LOGGER.info('Remote branch has changes. Pulling.')
        git_pull(local_repo)
    return output


def git_diff(local_branch, remote_branch, cwd):
    '''
    Perform a diff operation between a local and remote repository.
    
    @param local_branch: the local repository branch name.
    @param remote_branch: the remote branch name.
    @param cwd: the working directory in which to execute.
    '''
    return execute('git diff %s %s' % (local_branch, remote_branch), cwd)

def git_fetch(cwd):
    '''
    Fetch objects and refs from a remote repository.
    
    @param cwd: the working directory in which to execute.
    '''
    return execute('git fetch', cwd)

def git_pull(cwd):
    '''
    Fetch from and merge with a remote repository.
    
    @param cwd: the working directory in which to execute.
    '''
    return execute('git pull', cwd)

def git_clone(user, host, remote_repo, local_repo, cwd):
    '''
    Clone a remote repository into a new local directory. Must have key-based
    authentication set up for this to work.
    
    TODO: handle exceptions for no key-based auth
    
    @param user: the username of the owner of the repository to clone.
    @param host: the name/address of the remote host.
    @param remote_repo: the repository path on the remote host. 
    @param local_repo: the local path in which to clone the new repo.
    @param cwd: the working directory in which to execute.
    '''
    os.mkdir(local_repo)
    execute('git clone %s@%s:%s %s' % (user, host, remote_repo, local_repo), cwd)
    
    