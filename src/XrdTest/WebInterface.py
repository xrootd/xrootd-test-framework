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
# File:    WebInterface
# Desc:    TODO:
#-------------------------------------------------------------------------------
from Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import sys
    import os
    import socket
    import cherrypy
    
    from Cheetah.Template import Template
    from cherrypy.lib.static import serve_file
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)

class XrdWebInterfaceException(Exception):
    '''
    General Exception raised by WebInterface.
    '''
    def __init__(self, desc):
        '''
        Constructs Exception
        @param desc: description of an error
        '''
        self.desc = desc
        
    def __str__(self):
        '''
        Returns textual representation of an error
        '''
        return repr(self.desc)

class WebInterface:
    '''
    All pages and files available via Web Interface,
    defined as methods of this class.
    '''
    def __init__(self, config, test_master_ref):
        # reference to XrdTestMaster main object
        self.testMaster = test_master_ref
        # reference to loaded config
        self.config = config
        # absolute path to webpage root
        self.webroot = '/usr/share/XrdTest/webpage'
        # default server type
        self.protocol = 'http'
        # default port settings
        self.port = 0
        self.defaultHttpPort = 8080
        self.defaultHttpsPort = 8443
        
        # default test suite run password = empty
        self.suiteRunPass = ''
        
        # override default web root if specified in config
        if self.config.has_option('webserver', 'webpage_dir'):
            webroot = self.config.get('webserver', 'webpage_dir')
            if os.path.exists(webroot):
                self.webroot = webroot
            else:
                raise XrdWebInterfaceException('Path to web root does not exist at %s' % webroot)
            
        if self.config.has_option('webserver', 'protocol'):
            self.protocol = self.config.get('webserver', 'protocol')
            
        # do the same with the web ports
        if self.config.has_option('webserver', 'port'):
            self.port = self.config.getint('webserver', 'port')
        elif self.protocol == 'http':
            self.port = self.defaultHttpPort
        elif self.protocol == 'https':
            self.port = self.defaultHttpsPort
            
        # ..and the suite run password
        if self.config.has_option('webserver', 'suite_run_pass'):
            self.suiteRunPass = self.config.get('webserver', 'suite_run_pass')    
        
        self.cp_config = {'request.error_response': handleCherrypyError,
                          'error_page.404': \
                          self.webroot + \
                          os.sep + "page_404.tmpl"}

    def disp(self, tpl_file, tpl_vars):
        '''
        Utility method for displying tpl_file and replace tpl_vars.

        @param tpl_file: to be displayed as HTML page
        @param tpl_vars: vars can be used in HTML page, Cheetah style
        '''
        tpl = None
        tplFile = self.webroot + os.sep + tpl_file

        tpl_vars['port'] = self.port
        try:
            tpl = Template(file=tplFile, searchList=[tpl_vars])
        except Exception, e:
            LOGGER.error(str(e))
            return "An error occured. Check log for details."
        else:
            return tpl.respond()

    def index(self):
        '''
        Main page of web interface, shows definitions.
        '''
        tplVars = { 'title' : 'Xrd Test Master - Web Interface',
                    'webroot' : self.webroot,
                    'clusters' : self.testMaster.clusters,
                    'hypervisors': self.testMaster.hypervisors,
                    'suiteSessions' : self.testMaster.suiteSessions,
                    'runningSuiteUids' : self.testMaster.runningSuiteUids,
                    'slaves': self.testMaster.slaves,
                    'hostname': socket.gethostname(),
                    'testSuites': self.testMaster.testSuites,
                    'pendingJobs': self.testMaster.pendingJobs,
                    'pendingJobsDbg': self.testMaster.pendingJobsDbg,
                    'userMsgs' : self.testMaster.userMsgs,
                    'testMaster': self.testMaster, }
        return self.disp("main.tmpl", tplVars)

    def suiteSessions(self):
        '''
        Page showing suit sessions runs.
        '''
        tplVars = { 'title' : 'Xrd Test Master - Web Interface',
                    'webroot': self.webroot,
                    'suiteSessions' : self.testMaster.suiteSessions,
                    'runningSuiteUids' : self.testMaster.runningSuiteUids,
                    'slaves': self.testMaster.slaves,
                    'hostname': socket.gethostname(),
                    'testSuites': self.testMaster.testSuites,
                    'testMaster': self.testMaster}
        return self.disp("suite_sessions.tmpl", tplVars)

    def indexRedirect(self):
        '''
        Page that at once redirects user to index. Used to clear URL parameters.
        '''
        tplVars = { 'hostname': socket.gethostname(),
                    'port': self.port}
        return self.disp("index_redirect.tmpl", tplVars)

    def downloadScript(self, *script_name):
        '''
        Enable slave to download some script as a regular file from master and
        run it.

        @param script_name:
        '''
        
        for repo in self.config.get('general', 'test-repos').split(','):
            repo = 'test-repo-' + repo
            
            if self.config.get(repo, 'type') == 'localfs':
                path = os.path.abspath(self.config.get(repo, 'local_path'))
            elif self.config.get(repo, 'type') == 'git':
                path = self.config.get(repo, 'local_path')     

            for i in xrange(0, len(script_name)):
                path += os.sep + script_name[i]
    
            if os.path.exists(path):
                return serve_file(path , "application/x-download", "attachment")

        return "%s: not found in any repository" % path

    def showScript(self, *script_name):
        '''
        Enable slave to view some script as text from master and
        run it.

        @param script_name:
        '''        
        path = self.config.get('webserver', 'webpage_dir')
        
        for i in xrange(0, len(script_name)):
            path += os.sep + script_name[i]

        if os.path.exists(path):
            return serve_file(path , "text/html")

        return "%s: not found in any repository" % path
    
    def runTestSuite(self, password=None, testsuite=None): 
        if not password == self.suiteRunPass:
            return 'Incorrect password.'
        else:
            self.testMaster.enqueueJob(testsuite)
            self.testMaster.startNextJob()
            raise cherrypy.HTTPRedirect("index")

    index.exposed = True
    suiteSessions.exposed = True
    downloadScript.exposed = True
    showScript.exposed = True
    runTestSuite.exposed = True
    

def handleCherrypyError():
        cherrypy.response.status = 500
        cherrypy.response.body = \
                        ["An error occured. Check log for details."]
        LOGGER.error("Cherrypy error: " + \
                     str(cherrypy._cperror.format_exc(None)))
    
