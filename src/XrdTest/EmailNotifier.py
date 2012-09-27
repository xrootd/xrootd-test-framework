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
#          addresses in case of test suite success/failure, based on some 
#          policies.
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
    
    @property
    def template_success_text(self):
        return \
        """
        Something good happened in %(testsuite)s
        """
        
    @property
    def template_failure_text(self):
        return \
        """
        Something bad happened in %(testsuite)s
        """

    @property
    def template_success_html(self):
        return \
        """
        <html>
          <head>
              <style type="text/css">
                  p { font-family: Courier New, Courier, monospace; }
              </style>
          </head>
          <body>
            <p>Something good happened in %(testsuite)s</p>
            <p>%(state)s</p>
            <p>%(uid)s</p>
            <p>%(slave)s</p>
          </body>
        </html>
        """
    
    @property
    def template_failure_html(self):
        return \
        """
        <html>
          <head>
              <style type="text/css">
                  p { font-family: Courier New, Courier, monospace; }
              </style>
          </head>
          <body>
            <p>Something bad happened in %(testsuite)s</p>
            <p>%(state)s</p>
            <p>%(uid)s</p>
            <p>%(slave)s</p>
          </body>
        </html>
        """
        
    def notify_success(self, args, type):
        msg = self._build_success(args)
        send = False
        
        if self.success_policy == self.POLICY_CASE:
            send = True
        elif self.success_policy == self.POLICY_SUITE:
            if type in (self.SUITE_EVENT, self.TIMEOUT_EVENT):
                send = True
        elif self.success_policy == self.POLICY_NONE:
            return
        else:
            raise EmailNotifierException('Invalid success alert policy: %s' \
                                         % self.success_policy)
        
        self._notify(self.success_policy, msg)
    
    def notify_failure(self, args, type):
        msg = self._build_failure(args)
        send = False
        
        if self.failure_policy == self.POLICY_CASE:
            send = True
        elif self.failure_policy == self.POLICY_SUITE:
            if type in (self.SUITE_EVENT, self.TIMEOUT_EVENT):
                send = True
        elif self.failure_policy == self.POLICY_NONE:
            return
        else:
            raise EmailNotifierException('Invalid failure alert policy: %s' \
                                         % self.failure_policy)
        
        if send:
            self._notify(msg)
    
    def _notify(self, msg):
        self._send(msg, self.emails)
        
    def _build_success(self, args):
        msg_text = self.template_success_text % args
        msg_html = self.template_success_html % args
        return self._build(msg_text, msg_html, args)
    
    def _build_failure(self, args):
        msg_text = self.template_failure_text % args
        msg_html = self.template_failure_html % args
        return self._build(msg_text, msg_html, args)
    
    def _build(self, text, html, args):
        # Create message container - correct MIME type is multipart/alternative.
        msg = MIMEMultipart('alternative')
        subject = '%s in suite %s on slave %s: %s' % \
                    ('Failure' if args['failure'] else 'Success', \
                    args['testsuite'], args['slave'], args['state'].name)
        
        msg['Subject'] = subject % args
        msg['From'] = self.SENDER

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
    
    
