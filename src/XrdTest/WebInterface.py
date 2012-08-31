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
        # default page title
        self.title = 'XRootD Testing Framework - Web Interface'
        
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

    def disp(self, tfile, tvars):
        '''
        Utility method for displying a Cheetah template file with the
        supplied variables.

        @param tfile: to be displayed as HTML page
        @param tvars: variables to be used in HTML page, Cheetah style
        '''
        template = None
        tfile = os.path.join(self.webroot, tfile)

        try:
            template = Template(file=tfile, searchList=[tvars])
        except Exception, e:
            LOGGER.error(str(e))
            return "An error occurred. Check log for details."
        else:
            return template.respond()
        
    def vars(self):
        '''Return the variables necessary for a webpage template.'''
        tvars = {   
                    'title' : self.title,
                    'webroot' : self.webroot,
                    'protocol': self.protocol,
                    'port': self.port,
                    'clusters' : self.testMaster.clusters,
                    'hypervisors': self.testMaster.hypervisors,
                    'suite_hist' : self.testMaster.suiteSessions,
                    'running_suite_uids' : self.testMaster.runningSuiteUids,
                    'slaves': self.testMaster.slaves,
                    'hostname': socket.gethostname(),
                    'testsuites': self.testMaster.testSuites,
                    'pending_jobs': self.testMaster.pendingJobs,
                    'pending_jobs_dbg': self.testMaster.pendingJobsDbg,
                    'user_msgs' : self.testMaster.userMsgs,
                    'test_master': self.testMaster, 
                }
        return tvars

    @cherrypy.expose
    def index(self):
        return self.disp("index.html", self.vars())
    
    @cherrypy.expose
    def testsuites(self, ts_name=None):
        if ts_name:
            tvars = self.vars()
            tvars['testsuite'] = self.testMaster.testSuites[ts_name] \
                if self.testMaster.testSuites.has_key(ts_name) else ts_name
            tvars['run_hist'] = [run for run in self.testMaster.suiteSessions.itervalues() if run.name == ts_name]
            return self.disp("testsuite.html", tvars)
        
        else:
            return self.disp("testsuites.html", self.vars())
    
    @cherrypy.expose
    def clusters(self):
        return self.disp("clusters.html", self.vars())
    
    @cherrypy.expose
    def hypervisors(self):
        return self.disp("hypervisors.html", self.vars())
    
    @cherrypy.expose
    def slaves(self):
        return self.disp("slaves.html", self.vars())
    
    @cherrypy.expose
    def documentation(self):
        return self.disp("documentation.html", self.vars())

    @cherrypy.expose
    def indexRedirect(self):
        '''
        Page that at once redirects user to index. Used to clear URL parameters.
        '''
        tvars = {   
                    'hostname': socket.gethostname(),
                    'protocol': self.protocol,
                    'port': self.port
                }
        return self.disp("index_redirect.tmpl", tvars)

    @cherrypy.expose
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

    @cherrypy.expose
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
    
    @cherrypy.expose
    def auth(self, password=None, testsuite=None):
        if not self.testMaster.testSuites.has_key(testsuite):
            return 'Not authorized: unknown test suite'
        elif not password == self.suiteRunPass:
            return 'Not authorized: incorrect password'
        else:
            self.testMaster.enqueueJob(testsuite)
            self.testMaster.startNextJob()
            return 'Password OK'
    
    @cherrypy.expose
    def runTestSuite(self, testsuite=None): 
        tvars = self.vars()
        tvars['testsuite'] = testsuite if self.testMaster.testSuites.has_key(testsuite) else None
        return self.disp("auth.html", tvars)
        

def handleCherrypyError():
        cherrypy.response.status = 500
        cherrypy.response.body = \
                        ["An error occured. Check log for details."]
        LOGGER.error("Cherrypy error: " + \
                     str(cherrypy._cperror.format_exc(None)))
    
