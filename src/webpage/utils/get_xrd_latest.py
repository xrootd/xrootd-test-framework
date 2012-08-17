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
# File:    get_xrd_latest
# Desc:    TODO:
#
#-------------------------------------------------------------------------------

import getopt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib2
import logging
import xml.sax.handler
from string import join

TEAMCITY_SERVER = "https://teamcity-dss.cern.ch:8443"
REST_URL = "/guestAuth/app/rest/builds/buildType:bt45"
INTERNAL_RELEASE_AREA = "xrd_rpms"
BUILD_TYPE_ID = "bt45"


class BuildsListXMLHandler(xml.sax.handler.ContentHandler):
    """
    Class to handle the response from the teamcity server REST build query. E.g
    <builds count="1">
      <build id="8603" number="54"
             status="SUCCESS"
             buildTypeId="bt31"
             href="/guestAuth/app/rest/builds/id:8603"
             webUrl="http://lxbrl2711:8111/viewLog.html?buildId=8603&.... />
    </builds>
    """
    def __init__(self):
        """ BuildsListXMLHandler constructor. """
        self._builds = []

    def startElement(self, name, attributes):
        """ Element processing. """

        # Ignore non <build> element tags.
        if name != "build":
            return

        # Convert the XML information into a dictionary structure and store
        # the result in the builds list.
        buildInfo = {}
        buildInfo['BuildId'] = attributes.get('id')
        buildInfo['BuildTypeId'] = attributes.get('buildTypeId')
        buildInfo['WebURL'] = attributes.get('webUrl')
        buildInfo['ArtifactURL'] = "/".join([
                TEAMCITY_SERVER + "/guestAuth/repository/downloadAll",
                BUILD_TYPE_ID,
                attributes.get('id') + ":id",
                "artifacts.zip" ])
        self._builds.append(buildInfo)

    def getBuilds(self):
        """ Return the list of builds """
        return self._builds


def runCommand(cmdline, useShell=False):
    """ A simple wrapper function for executing a command. """
    process = subprocess.Popen(cmdline, shell=useShell,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    output = process.communicate()[0]

    # If the command returns an error record it to the terminal and exit with
    # a non zero exit code.
    if process.returncode != 0:
        print "\n", output.strip()
        sys.exit(1)

    return output


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s [%(filename)s %(lineno)d] ' + \
                '%(message)s', datefmt='[%H:%M:%S]', level=logging.DEBUG)
    LOGGER = logging.getLogger(__name__)

    # Check the release directory to see if the release already exists.
    releasedir = INTERNAL_RELEASE_AREA
    if os.path.exists(releasedir):
        print >> sys.stderr, "[INFO] Release directory: %s already exists!" % releasedir
        sys.exit(1)

    os.mkdir(releasedir)

    # Create a temporary directory to construct the release artifacts.
    tmpdir = tempfile.mkdtemp()
    rootdir = os.getcwd()
    os.chdir(tmpdir)

    # Query the Teamcity webserver using the REST API to see if a build exists
    # for the tag supplied by the user.2
    # Note: A production/internal release must:
    #  - Not be a personal build
    #  - Have been tagged appropriately eg. v2_1_10_1
    #  - Have been successful
    #  - Must be a pinned build
    url = TEAMCITY_SERVER + REST_URL
    url += "," + ",".join([ "personal:false",
                      "count:1",
                      "status:SUCCESS" ])

    LOGGER.info("Querying TeamCity server: %s for release information" % TEAMCITY_SERVER)
    xml_handler = BuildsListXMLHandler()
    f = urllib2.urlopen(url)
    xml.sax.parseString(f.read(), xml_handler)
    f.close()

    # Check the results from the query to TeamCity, we should have one and only
    # one result!
    if len(xml_handler.getBuilds()) == 0:
        LOGGER.info("No builds found")
        sys.exit(1)

    # Log the information about the release.
    buildInfo = xml_handler.getBuilds()[0]
    LOGGER.info("Found 1 build configuration.")

    # Download the artifacts zip file.
    LOGGER.info("Downloading artifacts ...")

    # Note: We use wget as opposed to the urllib library for convenience!
    zipfile = os.path.join(tmpdir, "artifacts.zip")
    runCommand([ "/usr/bin/wget", buildInfo['ArtifactURL'],
                 "--no-check-certificate", "-O", zipfile ])

    # Decompress the downloaded artifacts
    LOGGER.info("Decompressing: %s" % zipfile)
    runCommand([ "/usr/bin/unzip", zipfile, "-d", tmpdir ])

    # Delete any file from the extracted artifacts which is not an RPM or
    # is not to be distributed.
    for name in os.listdir(tmpdir):
        dirpath = os.path.join(tmpdir, name)
        if not os.path.isdir(dirpath):
            continue
        for name in os.listdir(dirpath):
            filepath = os.path.join(dirpath, name)
            if os.path.isdir(filepath) and name == 'logs':
                shutil.rmtree(filepath)
            elif not os.path.isfile(filepath):
                continue
            elif not name.endswith(".rpm"):
                if os.path.isdir(filepath):
                    shutil.rmtree(filepath)
                else:
                    os.unlink(filepath)

    os.unlink(zipfile)

    # Move the artifacts to the correct directories.
    LOGGER.info("Creating artifact layout ...")
    for name in sorted(os.listdir(tmpdir)):
        filepath = os.path.join(tmpdir, name)
        if not os.path.isdir(filepath):
            continue

        if name.count("-") != 2:
            continue

        (dist, version, arch) = name.split("-")
        dist = dist.upper()[0:2] + version
        if dist != "SL6" or arch != "x86_64":
            continue

        # Copy the srcdir artifacts to their final destination.
        os.chdir(rootdir)
        shutil.move(filepath, releasedir)

    # Remove the temporary directory.
    LOGGER.info("Removing temporary directory: %s" % tmpdir)
    shutil.rmtree(tmpdir)


if __name__ == '__main__':
    main()
    
