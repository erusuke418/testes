#
# Copyright (C) 2012 Bryan A. Jones
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA

# This program will execute any file with name test*<digit>.py. If your test
# need an aditional dependency name it test*<digit><letter>.py to be ignored
# by this program but be recognizable by any one as a dependency of that
# particular test.

# Copied from ../runtests.py
import os

try:
    import PyInstaller
except ImportError:
    # if importing PyInstaller fails, try to load from parent
    # directory to support running without installation
    import imp
    if not hasattr(os, "getuid") or os.getuid() != 0:
        imp.load_module('PyInstaller', *imp.find_module('PyInstaller',
            [os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]))

# Use unittest2 with PyInstaller tweaks. See
# http://www.voidspace.org.uk/python/articles/unittest2.shtml for some
# documentation.
import PyInstaller.lib.unittest2 as unittest

# The function to test
from PyInstaller.hooks.hookutils import remove_prefix
class TestRemovePrefix(unittest.TestCase):
    # Verify that removing a prefix from an empty string is OK.
    def test_0(self):
        self.assertEqual("", remove_prefix("", "prefix"))
        
    # An empty prefix should pass the string through unmodified.
    def test_1(self):
        self.assertEqual("test", remove_prefix("test", ""))
        
    # If the string is the prefix, it should be empty at exit.
    def test_2(self):
        self.assertEqual("", remove_prefix("test", "test"))
        
    # Just the prefix should be removed.
    def test_3(self):
        self.assertEqual("ing", remove_prefix("testing", "test"))
        
    # A matching string not as prefix should produce no modifications
    def test_4(self):
        self.assertEqual("atest", remove_prefix("atest", "test"))

# The function to test
from PyInstaller.hooks.hookutils import remove_extension
class TestRemoveExtension(unittest.TestCase):
    # Removing a suffix from a filename with no extension returns the
    # filename.
    def test_0(self):
        self.assertEqual("file", remove_extension("file"))
        
    # A filename with two extensions should have only the first removed.
    def test_1(self):
        self.assertEqual("file.1", remove_extension("file.1.2"))
        
    # Standard case - remove an extension
    def test_2(self):
        self.assertEqual("file", remove_extension("file.1"))
        
    # Unix-style .files are not treated as extensions
    def test_3(self):
        self.assertEqual(".file", remove_extension(".file"))
        
    # Unix-style .file.ext works
    def test_4(self):
        self.assertEqual(".file", remove_extension(".file.1"))

    # Unix-style .file.ext works
    def test_5(self):
        self.assertEqual("/a/b/c", remove_extension("/a/b/c.1"))

# The name of the hookutils test files directory
HOOKUTILS_TEST_FILES = 'hookutils_test_files'

# The function to test
from PyInstaller.hooks.hookutils import collect_submodules
class TestCollectSubmodules(unittest.TestCase):
    # Use the os module as a test case; all that collect_* functions need
    # is __name__ and __file__ attributes.
    def setUp(self):
        self.mod_list = collect_submodules(
          __import__(HOOKUTILS_TEST_FILES))

    # An error should be thrown if a module, not a package, was passed.
    def test_0(self):
        # os is a module, not a package.
        with self.assertRaises(AttributeError):
            collect_submodules(__import__('os'))

    # The package name itself should be in the returned list
    def test_1(self):
        self.assertTrue(HOOKUTILS_TEST_FILES in self.mod_list)

    # Subpackages without an __init__.py should not be included
    def test_2(self):
        self.assertTrue(HOOKUTILS_TEST_FILES + '.py_files_not_in_package.sub_pkg.three' not in self.mod_list)

    # Check that all packages get included
    def test_3(self):
        self.assertItemsEqual(self.mod_list, 
                              [HOOKUTILS_TEST_FILES,
                               HOOKUTILS_TEST_FILES + '.two',
                               HOOKUTILS_TEST_FILES + '.four',
                               HOOKUTILS_TEST_FILES + '.five',
                               HOOKUTILS_TEST_FILES + '.eight',
                              ])

# The function to test
from PyInstaller.hooks.hookutils import collect_data_files
from os.path import join
class TestCollectDataFiles(unittest.TestCase):
    # Use the os module as a test case; all that collect_* functions need
    # is __name__ and __file__ attributes.
    def setUp(self):
        self.data_list = collect_data_files(
          __import__('hookutils_test_files'))
        # Break list of (source, dest) inst source and dest lists
        self.source_list = [item[0] for item in self.data_list]
        self.dest_list = [item[1] for item in self.data_list]

    # An error should be thrown if a module, not a package, was passed.
    def test_0(self):
        # os is a module, not a package.
        with self.assertRaises(AttributeError):
            collect_data_files(__import__('os'))

    # Make sure only data files are found
    def test_1(self):
#        print(self.data_list)
        basepath = join(os.getcwd(), HOOKUTILS_TEST_FILES)
        subfiles = ('nine.dat',
                    'six.dll',
                    join('py_files_not_in_package', 'ten.dat'),
                    join('py_files_not_in_package', 'data', 'eleven.dat'),
                   )
        self.assertSequenceEqual(self.source_list, 
          [join(basepath, subpath) for subpath in subfiles])

if __name__ == '__main__':
    unittest.main()