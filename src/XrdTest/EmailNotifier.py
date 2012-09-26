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
            <p>
                Something bad happened in %(testsuite)s
            </p>
          </body>
        </html>
        """
        
    def notify_success(self, args):
        msg_text = self.template_success_text % args
        msg_html = self.template_success_html % args
        self._notify(self.success_policy, msg_text, msg_html)
    
    def notify_failure(self, args):
        msg_text = self.template_failure_text % args
        msg_html = self.template_failure_html % args
        self._notify(self.failure_policy, msg_text, msg_html)
    
    def _notify(self, policy, text, html):
        if policy == self.POLICY_CASE:
            pass
        elif policy == self.POLICY_SUITE:
            pass
        elif policy == self.POLICY_NONE:
            pass
        else:
            pass
        
        self._send(text, html)
        
    def _send(self, text, html):
        recipients = ', '.join([e for e in self.emails])
        
        # Create message container - correct MIME type is multipart/alternative.
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "XRootD Testing Framework Event"
        msg['From'] = self.SENDER
        msg['To'] = recipients

        # Record the MIME types of both parts - text/plain and text/html.
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        # Attach parts into message container.
        msg.attach(part1)
        msg.attach(part2)
        
        # Send the message via local SMTP server.
        s = smtplib.SMTP('localhost')
        s.sendmail(self.SENDER, recipients.split(','), msg.as_string())
        s.quit()
    
    
