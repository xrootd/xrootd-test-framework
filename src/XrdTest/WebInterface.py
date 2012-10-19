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
    
    from Utils import Command
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
        
        cherrypy.config.update({'tools.allow.on': True,
                                'request.error_response': self.handleCherrypyError,
                                'error_page.401': os.path.join(self.webroot, 'err/401.html'),
                                'error_page.403': os.path.join(self.webroot, 'err/403.html'),
                                'error_page.404': os.path.join(self.webroot, 'err/404.html'),
                                'error_page.500': os.path.join(self.webroot, 'err/500.html'),
                                'error_page.503': os.path.join(self.webroot, 'err/503.html')
                                })
        
        cherrypy.tools.allow = cherrypy.Tool('on_start_resource', self.http_methods_allowed)
    
    def http_methods_allowed(self, methods=['GET', 'POST']):
        method = cherrypy.request.method.upper()
        if method not in methods:
            cherrypy.response.headers['Allow'] = ", ".join(methods)
            raise cherrypy.HTTPError(405)

    def disp(self, body, tvars):
        '''
        Utility method for displying a Cheetah template file with the
        supplied variables.

        @param body: to be displayed as HTML page
        @param tvars: variables to be used in HTML page, Cheetah style
        '''
        try:
            head = open(os.path.join(self.webroot, 'header.html'), 'r').read()
            body = open(os.path.join(self.webroot, body), 'r').read()
            foot = open(os.path.join(self.webroot, 'footer.html'), 'r').read()
        
            template = head + body + foot
            template = Template(source=template, searchList=[tvars])
        except Exception, e:
            LOGGER.error(str(e))
            return "An error occurred. Check log for details."
        else:
            return template.respond()
        
    def vars(self):
        '''Return the variables necessary for a webpage template.'''
        current_run = None
        if self.testMaster.runningSuite:
            current_run = self.testMaster.retrieveSuiteSession(self.testMaster.runningSuite.name)
            
        tvars = {   
                    'title' : self.title,
                    'webroot' : self.webroot,
                    'protocol': self.protocol,
                    'port': self.port,
                    'clusters' : self.testMaster.clusters,
                    'hypervisors': self.testMaster.hypervisors,
                    'suite_hist' : self.testMaster.suiteSessions,
                    'current_run': current_run,
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
    
    def ts_vars(self, ts_name):
        vars = self.vars()
        vars['testsuite'] = self.testMaster.testSuites[ts_name] \
            if self.testMaster.testSuites.has_key(ts_name) else ts_name
        
        inner = []
        outer = {}
        all_runs = self.testMaster.retrieveAllSuiteSessions()
        for key, runs in all_runs.iteritems():
            for run in runs.itervalues():
                if run.name == ts_name:
                    inner.append(run)
            outer.update({key: sorted(inner, key=lambda x: x.initDate, reverse=True)})

        vars['all_runs'] = outer
        return vars

    @cherrypy.expose
    def index(self):
        cherrypy.tools.allow.callable()
        return self.disp("index.html", self.vars())
    
    @cherrypy.expose
    def testsuites(self, ts_name=None):
        cherrypy.tools.allow.callable()
        if ts_name:
            vars = self.ts_vars(ts_name)
            return self.disp("testsuite.html", vars)
        else:
            return self.disp("testsuites.html", self.vars())
    
    @cherrypy.expose
    def clusters(self):
        cherrypy.tools.allow.callable()
        return self.disp("clusters.html", self.vars())
    
    @cherrypy.expose
    def hypervisors(self):
        cherrypy.tools.allow.callable()
        return self.disp("hypervisors.html", self.vars())
    
    @cherrypy.expose
    def documentation(self):
        cherrypy.tools.allow.callable()
        return self.disp('documentation.html', self.vars())

    @cherrypy.expose
    def indexRedirect(self):
        '''
        Page that at once redirects user to index. Used to clear URL parameters.
        '''
        cherrypy.tools.allow.callable()
        tvars = {   
                    'hostname': socket.gethostname(),
                    'protocol': self.protocol,
                    'port': self.port,
                    'title': self.title
                }
        return self.disp("index_redirect.tmpl", tvars)
    
    @cherrypy.expose
    def unsupported(self):
        cherrypy.tools.allow.callable()
        return self.disp('err/unsupported.html', {})

    @cherrypy.expose
    def downloadScript(self, *script_name):
        '''
        Enable slave to download some script as a regular file from master and
        run it.

        @param script_name:
        '''
        cherrypy.tools.allow.callable()
        
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
        cherrypy.tools.allow.callable()
        path = self.webroot
        
        for i in xrange(0, len(script_name)):
            path += os.sep + script_name[i]

        if os.path.exists(path):
            return serve_file(path , "text/html")

        return "%s: not found in any repository" % path
    
    @cherrypy.expose
    def getTrustedCACertificate(self, **kwargs):
        cherrypy.tools.allow.callable()
        
        try:
            ca_crt = self.config.get('security', 'ca_certfile')
            with open(ca_crt, 'r') as f:
                return f.read()
            
        except NoOptionError, e:
            LOGGER.error('CA configuration error: %s' % e)
        except IOError, e:
            LOGGER.error('Error reading CA certificate: %s' % e)
    
    @cherrypy.expose
    def getSignedCertificate(self, **kwargs):
        cherrypy.tools.allow.callable()
        
        slave_name = None
        csr_raw = None
        
        if kwargs.has_key('slave_name'):
            slave_name = kwargs['slave_name']
        if kwargs.has_key('csr'):
            csr_raw = kwargs['csr']
            csr = '/tmp/%s-req.pem' % slave_name
            crt = '/tmp/%s-cert.pem' % slave_name
            with open(csr, 'wb') as f:
                raw = csr_raw.file.read()
                f.write(raw)
                f.close()
            
        if slave_name is None or csr_raw is None:
            return
        else:
            try:
                args = {'csr': csr, 
                        'ca_crt': self.config.get('security', 'ca_certfile'),
                        'ca_key': self.config.get('security', 'ca_keyfile'),
                        'crt': crt
                       }
            except NoOptionError, e:
                LOGGER.error('CA configuration error: %s' % e)
                return
        
        gen_cert = \
        '''        
        # Sign the server key with our CA
        openssl x509 -req -days 365 -in %(csr)s -CA %(ca_crt)s -CAkey %(ca_key)s \
                -out %(crt)s -CAcreateserial
        ''' % args
        
        Command(gen_cert, '.').execute()
        
        try:
            with open(crt, 'r') as f:
                crt_raw = f.read()
                return crt_raw
        except IOError, e:
            LOGGER.error('Error reading signed certificate: %s' % e)
    
    @cherrypy.expose    
    def getSSSKeytable(self):
        cherrypy.tools.allow.callable()
        
        if not os.path.exists('/tmp/sss.keytab'):
            LOGGER.debug('Creating new sss keytable file ...')
            Command('xrdsssadmin -u anybody -g usrgroup -k xrootdfs_key add /tmp/sss.keytab', '.').execute()
            
        with open('/tmp/sss.keytab', 'r') as f:
            return f.read()
    
    @cherrypy.expose
    def auth(self, password=None, testsuite=None, cluster=None, type=None):
        cherrypy.tools.allow.callable()
        
        if testsuite:
            if not self.testMaster.testSuites.has_key(testsuite):
                return 'Not authorized: unknown test suite'
            elif not password == self.suiteRunPass:
                return 'Not authorized: incorrect password'
            elif not type or not type in ('run', 'cancel'):
                return 'Not authorized: invalid action'
            else:
                if type == 'run':
                    self.testMaster.runTestSuite(testsuite)
                elif type == 'cancel':
                    self.testMaster.cancelTestSuite(testsuite)
                return 'Password OK'
        
        elif cluster:
            if not self.testMaster.clusters.has_key(cluster):
                return 'Not authorized: unknown cluster'
            elif not password == self.suiteRunPass:
                return 'Not authorized: incorrect password'
            elif not type or not type in ('activate', 'deactivate'):
                return 'Not authorized: invalid action'
            else:
                if type == 'activate':
                    self.testMaster.activateCluster(cluster)
                elif type == 'deactivate':
                    self.testMaster.stopCluster(cluster)
                return 'Password OK'
            
    @cherrypy.expose
    def action(self, type=None, testsuite=None, cluster=None, location=None): 
        cherrypy.tools.allow.callable()
        tvars = self.vars()
        tvars['type'] = type
        tvars['testsuite'] = testsuite
        tvars['cluster'] = cluster
        tvars['location'] = location
        
        template = os.path.join(self.webroot, 'auth.html')
        template = Template(file=template, searchList = [tvars])
        return template.respond()
    
    @cherrypy.expose
    def update(self, path):
        cherrypy.tools.allow.callable()
        template = None
        vars = self.vars()
        
        if '#' in path:
            path = path.split('#')[0]

        file = path.split(os.sep)[-1]
        if file in self.testMaster.testSuites.keys():
            vars.update(self.ts_vars(file))
            file = 'testsuite'
        
        if not file: file = 'index'
        
        if os.path.exists(os.path.join(self.webroot, file + '.html')):
            tfile = os.path.join(self.webroot, file + '.html')

        try:
            template = Template(file=tfile, searchList=[vars])
        except Exception, e:
            LOGGER.error(str(e))
            return "An error occurred. Check log for details."
        else:
            return template.respond()

    def handleCherrypyError(self):
            cherrypy.response.status = 500
            cherrypy.response.body = ["An error occurred. Check log for details."]
            LOGGER.error("Cherrypy error: %s" % str(cherrypy._cperror.format_exc()))
    
