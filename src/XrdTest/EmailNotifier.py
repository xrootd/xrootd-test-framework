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
# File:    EmailNotifier.py
# Desc:    Functionality for sending email notifications to a set of email 
#          addresses in case of test suite success/failure, based on policies 
#          about the frequency and type of notifications desired.
#
#-------------------------------------------------------------------------------
from Utils import Logger
LOGGER = Logger(__name__).setup()

try:
    import sys
    import os
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
except ImportError, e:
    LOGGER.error(str(e))
    sys.exit(1)

class EmailNotifierException(Exception):
    '''
    General Exception raised by EmailNotifier.
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

class EmailNotifier(object):
    
    POLICY_CASE = "CASE"
    POLICY_SUITE = "SUITE"
    POLICY_NONE = "NONE"
    
    SUITE_EVENT = 0
    CASE_EVENT = 1
    TIMEOUT_EVENT = 3
    
    SENDER = 'XRootD Testing Framework <master@xrd.test>'
    
    def __init__(self, emails, success_policy, failure_policy):
        self.emails = emails
        self.success_policy = success_policy
        self.failure_policy = failure_policy
    
        
    def notify_success(self, args, desc, type):
        send = False
        
        if self.success_policy == self.POLICY_CASE:
            send = True
        elif self.success_policy == self.POLICY_SUITE:
            if type in (self.SUITE_EVENT, self.TIMEOUT_EVENT):
                send = True
        elif self.success_policy == self.POLICY_NONE:
            return
        else:
            LOGGER.error('Invalid success alert policy: %s' \
                                         % self.success_policy)
        
        if send:
            msg = self._build(args, desc, type)
            self._send(msg, self.emails)
    
    def notify_failure(self, args, desc, type):
        send = False
        
        if self.failure_policy == self.POLICY_CASE:
            send = True
        elif self.failure_policy == self.POLICY_SUITE:
            if type in (self.SUITE_EVENT, self.TIMEOUT_EVENT):
                send = True
        elif self.failure_policy == self.POLICY_NONE:
            return
        else:
            LOGGER.error('Invalid failure alert policy: %s' \
                                         % self.failure_policy)
        
        if send:
            msg = self._build(args, desc, type)
            self._send(msg, self.emails)
    
    def _build(self, args, desc, type):
        en = EmailNotification()
        
        # Create message container - correct MIME type is multipart/alternative.
        msg = MIMEMultipart('alternative')
        subject = '%s (suite: %s%s%s)' % (desc, args['testsuite'], \
                    ' test case: ' + args['testcase'] if args['testcase'] else '',
                    ' slave: ' + args['slave'] if args['slave'] else '')
        
        msg['Subject'] = subject % args
        msg['From'] = self.SENDER
                                    
        if args['failed_cases'] and int(args['failure']):
            args['failed_cases'] = 'Failed test cases: <strong>' + \
                            ', '.join([c.name for c in args['failed_cases']]) + \
                            '</strong>'
        else: args['failed_cases'] = ''
                            
        if int(args['failure']):
            args['failure'] = 'Failure'
        else:
            args['failure'] = 'Success'
            
        if args['testcase']:
            args['testcase'] = 'Test case: <strong>' + \
                               args['testcase'] + '</strong><br />'
        
        if args['slave']: 
            args['slave'] = 'Slave: <strong>' + \
                            args['slave'] + '</strong><br />'
                            
        if args['result']: 
            args['result'] = 'Output from slave: <br /><strong>' + \
                            args['result'] + '</strong><br />'
   
        args.update({'desc': desc, 'css': en.css})
        
        text = en.body_text % args
        html = en.body_html % args

        # Record the MIME types of both parts - text/plain and text/html.
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        # Attach parts into message container.
        msg.attach(part1)
        msg.attach(part2)
        return msg
        
    def _send(self, msg, recipients):
        msg['To'] = ', '.join([r for r in recipients])
        # Send the message via local SMTP server.
        s = smtplib.SMTP('localhost')
        s.sendmail(self.SENDER, recipients, msg.as_string())
        s.quit()
    
    
class EmailNotification(object):
    
    @property
    def body_text(self):
        return \
        """
        Test suite: %(testsuite)s
        Description: %(desc)s
        Time: %(time)s
        %(slave)s
        %(testcase)s
        %(failed_cases)s

        %(result)s
        """

    @property
    def body_html(self):
        return \
        """
        <html>
          <head>
              <style type="text/css">%(css)s</style>
          </head>
          <body>
            <p>
                Test suite: <strong>%(testsuite)s</strong>
                <br />
                Description: <strong>%(desc)s</strong>
                <br />
                Time: <strong>%(time)s</strong>
                <br />
                %(slave)s
                %(testcase)s
                %(failed_cases)s
            </p>
            <p>
                <code>%(result)s</code>
            </p>
          </body>
        </html>
        """

    @property
    def css(self):
        return \
        """
        html,body,div,span,h1,h2,h3,h4,h5,h6,p,code,em,small,strong,i {
            font-size: 100%;
            font-family: Courier New, Courier, monospace;
        }
        code {
            white-space: pre-wrap;
        }
        """
