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

from __future__ import print_function
import Tkinter as tk
import tkMessageBox as tm
from Cocoa import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
from Foundation import NSBundle
import argparse
import os
import httplib
import json
import base64
import sys
import subprocess

"""
Reads from an extension attribute in Jamf Pro with a list of testing group options, creates a Tkinter window,
and allows the user to choose a testing group and it writes that data back to the computer's inventory.
Intended to be run via Self Service.
"""


class EntryWindow:
    def __init__(self, args):
        self.server = args.server
        self.user = args.user
        self.password = args.password
        self.id = args.id
        self.auth = self.get_authorization_header()
        self.serial_number = self.get_serial_number()
        self.extension_attribute = self.get_extension_attribute()
        self.extension_attribute_name = self.extension_attribute['computer_extension_attribute']['name']
        self.testing_groups = [choice for choice in
                               self.extension_attribute['computer_extension_attribute']['input_type']['popup_choices']]
        self.root = tk.Tk()
        self.root.attributes("-topmost", True)
        self.root.title("Choose Testing Group")
        self.testing_groups_var = tk.StringVar(self.root)
        self.testing_groups_var.set(None)
        self.l1 = tk.Label(self.root, text="Testing Groups:", padx=10, pady=5).grid(row=0)
        # self.e1 = tk.Entry(self.root, width=25)
        self.e1 = tk.OptionMenu(self.root, self.testing_groups_var, *self.testing_groups)

        self.e1.grid(row=0, column=1, padx=10, sticky=tk.E)

        tk.Button(self.root, text="Continue", command=self.set_extension_attribute).grid(row=4, column=1, padx=4,
                                                                                         pady=4,
                                                                                         sticky=tk.E)
        self.center()
        self.app = NSRunningApplication.runningApplicationWithProcessIdentifier_(os.getpid())
        self.app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        self.bundle = NSBundle.mainBundle()
        if self.bundle:
            self.info = self.bundle.localizedInfoDictionary() or self.bundle.infoDictionary()
            if self.info and self.info['CFBundleName'] == 'Python':
                self.info['CFBundleName'] = "Testing Group Enrollment"
        self.root.mainloop()

    def center(self):
        self.root.update_idletasks()
        w = self.root.winfo_screenwidth()
        h = self.root.winfo_screenheight()
        size = tuple(int(_) for _ in self.root.geometry().split('+')[0].split('x'))
        x = w / 2 - size[0] / 2
        y = h / 2 - size[1] / 2
        self.root.geometry("%dx%d+%d+%d" % (size + (x, y)))

    @staticmethod
    def get_serial_number():
        import plistlib
        cmd = ['system_profiler', 'SPHardwareDataType', '-xml']
        return plistlib.readPlistFromString(subprocess.check_output(cmd))[0]['_items'][0]['serial_number']

    def get_authorization_header(self):
        auth = base64.b64encode("{}:{}".format(self.user, self.password))
        return "Basic {}".format(auth)

    def get_extension_attribute(self):
        request = httplib.HTTPSConnection(self.server)
        headers = {
            'Authorization': self.auth, 'Accept': 'application/json'
        }
        try:
            request.request("GET", "/JSSResource/computerextensionattributes/id/{}".format(self.id), headers=headers)
            response = request.getresponse()
            json_data = json.loads(response.read())
            return json_data
        except httplib.HTTPException as e:
            print("Exception: %s" % e)
            sys.exist(1)

    def set_extension_attribute(self):
        choice = self.testing_groups_var.get()
        xml = """
        <computer>
            <extension_attributes>
                <attribute>
                    <name>{}</name>
                    <value>{}</value>
                </attribute>
            </extension_attributes>
        </computer>
            """.format(self.extension_attribute_name, choice)
        request = httplib.HTTPSConnection(self.server)
        headers = {
            'Authorization': self.auth, 'Content-type': 'application/xml'
        }
        try:
            request.request("PUT", "/JSSResource/computers/serialnumber/{}".format(self.serial_number), xml,
                            headers=headers)
            response = request.getresponse()
            if response.status == 201:
                if self.testing_groups_var.get() is None:
                    self.show_message(title="Reset", message="Testing group has been set to: {}".format(choice))
                    self.root.destroy()
                else:
                    self.show_message(title="Success!", message="Testing group changed to: {}.".format(choice))
                    self.root.destroy()
            else:
                self.show_message(title="Failure!", message="Couldn't change group to: {}.".format(choice), icon=tm.WARNING)
                self.root.destroy()
        except httplib.HTTPException as e:
            print("Exception: %s" % e)
            sys.exit(1)

    def show_message(self, title="", message="", icon=tm.INFO):
        tm.showinfo(title=title, message=message, icon=icon)


def arguments():
    parser = argparse.ArgumentParser(description='Jamf testing group enrollment script')
    parser.add_argument('-s,', '--server', help='Jamf Pro Server url', required=True)
    parser.add_argument('-u,', '--user', help='Jamf Pro Server api user', required=True)
    parser.add_argument('-p,', '--password', help='Jamf Pro Server api password', required=True)
    parser.add_argument('--id', help='id of extension attribute to pull list of testing groups from', type=int,
                        required=True)

    all_options = ['-s', '-u', '-p', '--server', '--user', '--password', '--id']

    # Test if options are being passed from the command line with flags or if they are positional arguments supplied by JSS
    if any((True for option in all_options if option in sys.argv)):
        args = parser.parse_args()
    else:
        # If none of the argparse flags are found, assume arguments are being provided as positional arguments by the JSS,
        # and create an argparse Namespace object to match what we would have gotten from true argparse and not have to
        # change our code that runs later
        if len(sys.argv) < 8:
            print("Missing positional arguments!")
            sys.exit(1)
        args = argparse.Namespace()
        args.server = sys.argv[4]
        args.user = sys.argv[5]
        args.password = sys.argv[6]
        args.id = sys.argv[7]

    return args


def main():
    args = arguments()
    entrywindow = EntryWindow(args)


if __name__ == '__main__':
    main()
