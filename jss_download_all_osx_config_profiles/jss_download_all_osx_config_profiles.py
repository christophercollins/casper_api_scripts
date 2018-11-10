#!/usr/bin/python
# Copyright (C) 2015 Christopher Collins
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


"""
This script will grab all the OSX configuration profiles that exist on the JSS. Customize to your environment by editing
the global variables.
"""

import os
from datetime import datetime
import urllib2
import httplib
import socket
import ssl
import base64
import xml.etree.ElementTree as ET

# Global variables
# Change these to set their values for your environment
JSS_URL = 'https://jss.mycompany.com:8443'
API_USER = 'api_user'
API_PASS = 'api_password'
WRITE_PATH = '/tmp/'


class TLS1Connection(httplib.HTTPSConnection):
    """Like HTTPSConnection but more specific"""

    def __init__(self, host, **kwargs):
        httplib.HTTPSConnection.__init__(self, host, **kwargs)

    def connect(self):
        """Overrides HTTPSConnection.connect to specify TLS version"""
        # Standard implementation from HTTPSConnection, which is not
        # designed for extension, unfortunately
        sock = socket.create_connection((self.host, self.port),
                                        self.timeout, self.source_address)
        if getattr(self, '_tunnel_host', None):
            self.sock = sock
            self._tunnel()

        # This is the only difference; default wrap_socket uses SSLv23
        self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file, ssl_version=ssl.PROTOCOL_TLSv1)


class TLS1Handler(urllib2.HTTPSHandler):
    """Like HTTPSHandler but more specific"""

    def __init__(self):
        urllib2.HTTPSHandler.__init__(self)

    def https_open(self, req):
        return self.do_open(TLS1Connection, req)


def get_osx_configuration_profiles(jss_url, api_user, api_pass):
    """
    Get the list of all OS X configuration profile objects in the JSS and return them.
    """
    jss_request = urllib2.Request(jss_url + '/JSSResource/osxconfigurationprofiles')
    jss_request.add_header('Authorization', 'Basic ' + base64.b64encode(api_user + ':' + api_pass))
    request_response = urllib2.urlopen(jss_request)
    if request_response.code == 200:
        return ET.fromstring(request_response.read())


def write_osx_configuration_profiles(jss_url, api_user, api_pass, write_path, osx_configuration_profiles):
    """
    Iterate over list of OSX Configuration Profiles to get data from the JSS on each individual profile and write them
    to a file.
    """
    time = build_time()
    final_write_path = os.path.join(write_path, "JSS_OSXConfigurationProfiles_{}".format(time))
    if not os.path.exists(final_write_path):
        os.mkdir(final_write_path)
    for profile in osx_configuration_profiles.findall('os_x_configuration_profile/id'):
        profile_data = get_individual_profile(jss_url, api_user, api_pass, profile.text)
        # Strip out any characters in profile name which may cause issues when saving
        profile_name = profile_data.find('general/name').text.translate(None, "\!?/:")
        profile_text = profile_data.find('general/payloads').text
        print "Writing {}".format(profile_name)
        write_file(final_write_path, profile_name, profile_text)
        print "Wrote {}".format(final_write_path + '/' + profile_name + '.mobileconfig')


def get_individual_profile(jss_url, api_user, api_pass, profile):
    """
    Get profile object from the JSS.
    """
    jss_request = urllib2.Request(jss_url + '/JSSResource/osxconfigurationprofiles/id/' + profile)
    jss_request.add_header('Authorization', 'Basic ' + base64.b64encode(api_user + ':' + api_pass))
    request_response = urllib2.urlopen(jss_request)
    if request_response.code == 200:
        return ET.fromstring(request_response.read())


def build_time():
    """
    Return current date and time in a format appropriate for using in a folder name.
    """
    t = datetime.now()
    return "{}-{}-{}-{}{}{}".format(t.month, t.day, t.year, t.hour, t.minute, t.second)


def write_file(path, name, text):
    """
    Write profile content to a file.
    """
    file = open(os.path.join(path, name + '.mobileconfig'), 'w')
    file.write(text)
    file.close()


def main():
    """Main function."""
    urllib2.install_opener(urllib2.build_opener(TLS1Handler()))
    osx_configuration_profiles = get_osx_configuration_profiles(JSS_URL, API_USER, API_PASS)
    write_osx_configuration_profiles(JSS_URL, API_USER, API_PASS, WRITE_PATH, osx_configuration_profiles)


if __name__ == "__main__":
    main()

