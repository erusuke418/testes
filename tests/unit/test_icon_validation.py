#-----------------------------------------------------------------------------
# Copyright (c) 2005-2022, PyInstaller Development Team.
#
# Distributed under the terms of the GNU General Public License (version 2
# or later) with exception for distributing the bootloader.
#
# The full license is in the file COPYING.txt, distributed with this software.
#
# SPDX-License-Identifier: (GPL-2.0-or-later WITH Bootloader-exception)
#-----------------------------------------------------------------------------

import os
import sys

import pytest


def test_icon_validation(monkeypatch):
    from PyInstaller.building.icon import validate_icon

    # Currently assumes PIL/Pillow is installed on the testing machine

    workpath = data_dir = "PyInstaller/bootloader/images"

    # Nonexistent image - FileNotFoundError

    icon = "this_is_not_a_file.ico"
    with pytest.raises(FileNotFoundError):
        validate_icon(icon, ("ico",), "ico", workpath)

    # Native image - file path is passed through unchanged

    icon = os.path.join(data_dir, 'icon-console.ico')
    ret = validate_icon(icon, ("ico",), "ico", workpath)
    if ret != icon:
        pytest.fail("icon validation changed path even though the format was correct already", False)

    # Alternative image - output is a different file with the correct suffix

    icon = os.path.join(data_dir, 'github_logo.png')
    ret = validate_icon(icon, ("ico",), "ico", workpath)

    _, ret_filetype = os.path.splitext(ret)
    if ret_filetype != ".ico":
        pytest.fail("icon validation didn't convert to the right format", False)

    os.remove(ret)  # cleanup

    # Some random non-image file: Raises an image conversion error

    icon = os.path.join(data_dir, 'pyi_icon.notanicon')
    with open(icon, "w") as f:
        f.write("this is in fact, not an icon")

    with pytest.raises(ValueError):
        validate_icon(icon, ("ico",), "ico", workpath)

    os.remove(icon)  # cleanup

    # Alternative image - after calling monkeypatch.setitem(sys.modules, "PIL", None): Raise the install pillow error

    monkeypatch.setitem(sys.modules, "PIL", None)
    icon = os.path.join(data_dir, 'github_logo.png')
    with pytest.raises(ValueError):
        validate_icon(icon, ("ico",), "ico", workpath)
