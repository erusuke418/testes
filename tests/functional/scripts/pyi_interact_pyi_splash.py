# -----------------------------------------------------------------------------
# Copyright (c) 2019-2020, PyInstaller Development Team.
#
# Distributed under the terms of the GNU General Public License (version 2
# or later) with exception for distributing the bootloader.
#
# The full license is in the file COPYING.txt, distributed with this software.
#
# SPDX-License-Identifier: (GPL-2.0-or-later WITH Bootloader-exception)
# -----------------------------------------------------------------------------

# This script establishes a simple communication with the bootloader to test
# the functions. If an error is detected, the program is closed before the
# timeout and thus counts as failed.
# The error can occur in different areas. If either the bootloader fails to
# create the GUI (should only happen on Windows headless systems) or this
# Python script cannot connect to the bootloader.

from time import sleep


def main():
    # Init pyi_splash/Connect to the bootloader
    import pyi_splash

    # Simulate users program startup
    sleep(1)
    pyi_splash.update_text("This is a test text")
    sleep(2)
    pyi_splash.update_text("Second time's a charm")

    # Close the splash screen to check if that works
    sleep(1)
    pyi_splash.close()

    # Test if the pyi_splash module disabled itself
    assert pyi_splash._pipe_write_file is None

    # Wait for the timeout
    sleep(20)


if __name__ == '__main__':
    main()
