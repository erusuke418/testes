#! /usr/bin/env python
#-----------------------------------------------------------------------------
# Copyright (c) 2005-2021, PyInstaller Development Team.
#
# Distributed under the terms of the GNU General Public License (version 2
# or later) with exception for distributing the bootloader.
#
# The full license is in the file COPYING.txt, distributed with this software.
#
# SPDX-License-Identifier: (GPL-2.0-or-later WITH Bootloader-exception)
#-----------------------------------------------------------------------------

import sys
import os
import subprocess
from typing import Type

from setuptools import setup, find_packages


# Hack required to allow compat to not fail when pypiwin32 isn't found
os.environ["PYINSTALLER_NO_PYWIN32_FAILURE"] = "1"


#-- plug-in building the bootloader

from distutils.core import Command
from distutils.command.build import build

try:
    from wheel.bdist_wheel import bdist_wheel
except ImportError:
    raise SystemExit("Error: Building wheels requires the 'wheel' package. "
                     "Please `pip install wheel` then try again.")


class build_bootloader(Command):
    """
    Wrapper for distutil command `build`.
    """

    user_options =[]
    def initialize_options(self): pass
    def finalize_options(self): pass

    def bootloader_exists(self):
        # Checks is the console, non-debug bootloader exists
        from PyInstaller import HOMEPATH, PLATFORM
        from PyInstaller.compat import is_win, is_cygwin
        exe = 'run'
        if is_win or is_cygwin:
            exe = 'run.exe'
        exe = os.path.join(HOMEPATH, 'PyInstaller', 'bootloader', PLATFORM, exe)
        return os.path.isfile(exe)

    def compile_bootloader(self):
        import subprocess
        from PyInstaller import HOMEPATH

        src_dir = os.path.join(HOMEPATH, 'bootloader')
        cmd = [sys.executable, './waf', 'configure', 'all']
        rc = subprocess.call(cmd, cwd=src_dir)
        if rc:
            raise SystemExit('ERROR: Failed compiling the bootloader. '
                             'Please compile manually and rerun setup.py')

    def run(self):
        if getattr(self, 'dry_run', False):
            return
        if self.bootloader_exists():
            return
        print('No precompiled bootloader found. Trying to compile it for you ...',
              file=sys.stderr)
        self.compile_bootloader()


class MyBuild(build):
    # plug `build_bootloader` into the `build` command
    def run(self):
        self.run_command('build_bootloader')
        build.run(self)


# --- Builder classes for separate per-platform wheels. ---


class Wheel(bdist_wheel):
    """Base class for building a wheel for one platform, collecting only the
    relevant bootloaders for that platform."""

    # The setuptools platform tag.
    PLAT_NAME = "manylinux2014_x86_64"
    # The folder of bootloaders from PyInstaller/bootloaders to include.
    PYI_PLAT_NAME = "Linux-64bit"

    def finalize_options(self):
        # Inject the platform name.
        self.plat_name = self.PLAT_NAME
        self.plat_name_supplied = True

        if not self.has_bootloaders():
            raise SystemExit(
                f"Error: No bootloaders for {self.PLAT_NAME} found in "
                f"{self.bootloaders_dir()}. See "
                f"https://pyinstaller.readthedocs.io/en/stable/"
                f"bootloader-building.html for how to compile them.")

        self.distribution.package_data = {
            "PyInstaller": [
                # And add the correct bootloaders as data files.
                f"bootloader/{self.PYI_PLAT_NAME}/*",
                "bootloader/images/*",
                # These files need to be explictly included as well.
                "fake-modules/site.py",
                "hooks/rthooks.dat",
                "lib/README.rst",
            ],
        }
        super().finalize_options()

    def run(self):
        # Note that 'clean' relies on clean::all=1 being set in the
        # `setup.cfg` or the build cache "leaks" into subsequently built
        # wheels.
        self.run_command("clean")
        super().run()

    @classmethod
    def bootloaders_dir(cls):
        """Locate the bootloader folder inside the PyInstaller package."""
        return f"PyInstaller/bootloader/{cls.PYI_PLAT_NAME}"

    @classmethod
    def has_bootloaders(cls):
        """Does the bootloader folder exist and is there anything in it?"""
        dir = cls.bootloaders_dir()
        return os.path.exists(dir) and len(os.listdir(dir))


# Map PyInstaller platform names to their setuptools counterparts.
# Other OSs can be added as and when we start shipping wheels for them.
PLATFORMS = {
    "Windows-64bit": "win_amd64",
    "Windows-32bit": "win32",
    # The manylinux version tag depends on the glibc version compiled against.
    # If we ever change the docker image used to build the bootloaders then we
    # must check/update this tag.
    "Linux-64bit":  "manylinux2014_x86_64",
    "Linux-32bit": "manylinux2014_i686",
    # The macOS version must be kept in sync with the -mmacosx-version-min in
    # the waf build script.
    # TODO: Once we start shipping universal2 bootloaders and PyPA have
    #       decided what the wheel tag should be, we will need to set it here.
    "Darwin-64bit": "macosx_10_13_x86_64",
}

# Create a subclass of Wheel() for each platform.
wheel_commands = {}
for (pyi_plat_name, plat_name) in PLATFORMS.items():
    # This is the name it will have on the setup.py command line.
    command_name = "wheel_" + pyi_plat_name.replace("-", "_").lower()

    # Create and register the subclass, overriding the PLAT_NAME and
    # PYI_PLAT_NAME attributes.
    platform = {"PLAT_NAME": plat_name, "PYI_PLAT_NAME": pyi_plat_name}
    command: Type[Wheel] = type(command_name, (Wheel,), platform)
    command.description = f"Create a {command.PYI_PLAT_NAME} wheel"
    wheel_commands[command_name] = command


class bdist_wheels(Command):
    """Build a wheel for every platform listed in the PLATFORMS dict which has
    bootloaders available in `PyInstaller/bootloaders/[platform-name]`.
    """
    description = "Build all available wheel types"

    # Overload these to keep the abstract metaclass happy.
    user_options = []
    def initialize_options(self): pass
    def finalize_options(self): pass

    def run(self) -> None:
        command: Type[Wheel]
        for (name, command) in wheel_commands.items():
            if not command.has_bootloaders():
                print("Skipping", name, "because no bootloaders were found in",
                      command.bootloaders_dir())
                continue

            print("running", name)
            # This should be `self.run_command(name)` but there is some
            # aggressive caching from distutils which has to be suppressed
            # by us using forced cleaning. One distutils behaviour that
            # seemingly can't be disabled is that each command should only
            # run once - this is at odds with what we want because we need
            # to run 'build' for every platform.
            # The only way I can get it not to skip subsequent builds is to
            # isolate the processes completely using subprocesses...
            subprocess.run([sys.executable, __file__, "-q", name])


#--

setup(
    setup_requires = ["setuptools >= 39.2.0"],
    cmdclass = {'build_bootloader': build_bootloader,
                'build': MyBuild,
                **wheel_commands,
                'bdist_wheels': bdist_wheels,
                },
    packages=find_packages(include=["PyInstaller", "PyInstaller.*"]),
    package_data = {
        "PyInstaller": [
            # Include all bootloaders in wheels by default.
            "bootloader/*/*",
            # These files need to be explictly included as well.
            "fake-modules/site.py",
            "hooks/rthooks.dat",
            "lib/README.rst",
        ],
    },
)
