#!/usr/bin/python

"""
This Nagios plugin can get the config of a network device and check it for differences against a 'golden config image'.
The code uses Cisco PyATS to connect to the device and check for differences.
CREDITS:
The python code to create golden config image and check for differences was created with Katerina Dardoufa, Cisco PyATS team was consulted, thank you guys for your support!
The plugin structure is borrowed (although a little modified) from the check_cisco_ip_sla plugin by Maarten Hoogveld, maarten@hoogveld.org. I would have probably created something myself as it's not the first Nagios plugin I create but his work saved me some time, especially for arg parse.
PRIOR TO USE:
You need to have a 'testbeds' directory and a 'configs' directory under the one where you run the plugin (usually it's /usr/local/nagios/libexec). If any of them or both do not exist, the plugin will exit. Make sure the directories are there and readable, that the 'testbeds' dir contains the necessary testbeds and that the hostname you are interested in is correct and exists in the testbed. No exceptions are defined in the code to handle that.
In order for the plugin to be used a golden config file is necessary.
You can do this using the script create-golden-config.py in the same repository.
Or you can run the plugin and it will give a WARNING status and a warning message the first time, but will query the device for the config and save it as a golden config.
You can then use the create-golden-config.py script to rearm the check, or delete the current golden config.

POSSIBLE RESULTS:
If the current config found to be the same as the golden config, an OK status is returned
If the current config found to be different than the golden config, a CRITICAL status is returned.
If the golden config is not present on disk, the current config is saved as the golden config and a WARNING status is returned. That status will surely return to OK when the plugin is run again as the golden config will be found and probably no differences will be found.
In any case, a status and a text message are returned.
"""

from genie.testbed import load
from genie.utils.config import Config
from genie.utils.diff import Diff
import subprocess
import argparse
import os.path

__author__ = "Ioannis Theodoridis"
__version__ = "1.0"
__email__ = "itheodori@gmail.com"
__licence__ = "MIT"
__status__ = "Production"


class ConfigChecker:
    STATUS_OK = 0
    STATUS_WARNING = 1
    STATUS_CRITICAL = 2
    STATUS_UNKNOWN = 3

    def __init__(self):
        self.status = None
        self.messages = []
        self.perfdata = []
        self.options = None
        self.golden_config = None
        self.current_config = None

    def run(self):
        self.parse_options()

        self.get_golden_config()

        if self.status == None:
            self.get_current_config()
            self.compare_configs()

        self.print_output()

        return self.status

    def parse_options(self):
        parser = argparse.ArgumentParser(
            description="Monitoring check plugin to check network configs for differences against golden configs."
                        "The code uses Cisco PyATS to connect to the device and check for differences."
                        "In order for the plugin to be used than a golden config file is necessary."
                        "You can do this using the script create-golden-config.py in the same repository."
                        "Future versions of this plugin will create the golden configs if they are not found on disk."
                        "If the current config found to be the same as the golden config, an OK status is returned"
                        "If the current config found to be different than the golden config, a CRITICAL status is returned."
                        "If the golden config is not present on disk, the current config is saved as the golden config and a WARNING status is returned. That status will surely return to OK when the plugin is run again as the golden config will be found and probably no differences will be found."
                        "UNKNOWN is returned if there is a failure."
        )

        parser.add_argument("-H", "--hostname",
                            type=str, help="Hostname defined in the testbed")
        parser.add_argument("-t", "--testbed",
                            type=str, help="PyATS Testbed file")

        self.options = parser.parse_args()

        if not self.are_options_valid():
            print("Run with --help for usage information")
            print("")
            exit(0)

        if (not os.path.isdir("testbeds")) or (not os.path.isdir("configs")):
            print("directories testbeds or configs not present under current dir")
            print("")
            exit(0)


    def are_options_valid(self):
        if not self.options.hostname:
            print("You must specify a hostname")
            return False
        if not self.options.testbed:
            print("You must specify a testbed")
            return False
        return True

    def print_output(self):
        """ Prints the final output (in Nagios plugin format if self.status is set)
        :return:
        """
        output = ""
        if self.status == self.STATUS_OK:
            output = "OK"
        elif self.status == self.STATUS_WARNING:
            output = "Warning"
        elif self.status == self.STATUS_CRITICAL:
            output = "Critical"
        elif self.status == self.STATUS_UNKNOWN:
            output = "Unknown"

        if self.messages:
            if len(output):
                output += " - "
            # Join messages like sentences. Correct those messages which already ended with a period or a newline.
            output += ". ".join(self.messages).replace(".. ", ".").replace("\n. ", "\n")

        if self.perfdata:
            if len(output):
                output += " | "
            output += " ".join(self.perfdata)

        print(output)

    def get_golden_config(self):
        #print("Reading Golden Config")
        golden_config_filename = "configs/" + self.options.hostname + "-golden.conf"

        if not os.path.isfile(golden_config_filename):
            testbed_filename = "testbeds/" + self.options.testbed
            testbed = load(testbed_filename)
            TR = testbed.devices[self.options.hostname]
            TR.connect(log_stdout=False)
            output = TR.execute('show running-config')
            with open(golden_config_filename, 'w') as f:
                f.write(output)
            self.status = self.STATUS_WARNING
            self.set_message("Golden Config did not exist. Created for : {}".format(self.options.hostname))

        with open(golden_config_filename, 'r') as f:
                output=f.read()
        self.golden_config=Config(output)
        self.golden_config.tree()

        return()

    def get_current_config(self):
        #print("Getting Current Config")
        testbed_filename = "testbeds/" + self.options.testbed
        testbed = load(testbed_filename)
        TR = testbed.devices[self.options.hostname]
        TR.connect(log_stdout=False)
        output = TR.execute('show running-config')
        self.current_config = Config(output)
        self.current_config.tree()

    def compare_configs(self):
        dd = Diff(self.golden_config, self.current_config)
        dd.findDiff()
        #import ipdb; ipdb.set_trace()

        if len(str(dd)) == 0 :
            self.status = self.STATUS_OK
            self.set_message("No changes in Running Config")
        else:
            self.status = self.STATUS_CRITICAL
            self.set_message("Running Config has changed: {}".format(dd))

    def add_status(self, status):
        """ Set the status only if it is more severe than the present status
        The order of severity being OK, WARNING, CRITICAL, UNKNOWN
        :param status: Status to set, one of the self.STATUS_xxx constants
        :return: The current status
        """
        if self.status is None or status > self.status:
            self.status = status

    def set_message(self, message):
        self.messages = [message]

    def add_message(self, message):
        self.messages.append(message)

    def add_perfdata(self, perfitem):
        self.perfdata.append(perfitem)

if __name__ == "__main__":
    checker = ConfigChecker()
    result = checker.run()
    exit(result)
