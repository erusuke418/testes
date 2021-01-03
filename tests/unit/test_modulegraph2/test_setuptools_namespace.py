import os
import pathlib
import sys
import unittest

import modulegraph2

from . import util

INPUT_DIR = pathlib.Path(__file__).resolve().parent / "setuptools-dir"


class TestSetuptoolsNamespacePackage(unittest.TestCase):
    def setUp(self):
        for subdir in ("pkg1", "pkg2"):
            sys.path.insert(0, os.fspath(INPUT_DIR / subdir))

    def tearDown(self):
        del sys.path[0]
        del sys.path[0]

        util.clear_sys_modules(INPUT_DIR)

    def test_setuptools_namespace(self):
        mg = modulegraph2.ModuleGraph()
        mg.add_module("mynamespace.pkg1_mod")
        mg.add_module("mynamespace.pkg2_mod")

        n = mg.find_node("mynamespace.pkg1_mod")
        self.assertIsInstance(n, modulegraph2.SourceModule)

        n = mg.find_node("mynamespace.pkg2_mod")
        self.assertIsInstance(n, modulegraph2.SourceModule)

        n = mg.find_node("mynamespace")
        self.assertIsInstance(n, modulegraph2.Package)

        self.assertCountEqual(
            n.search_path,
            [INPUT_DIR / subdir / "mynamespace" for subdir in ("pkg1", "pkg2")],
        )

        n = mg.find_node("pkg_resources")
        self.assertIsInstance(n, (modulegraph2.SourceModule, modulegraph2.Package))

        try:
            mg.edge_data("mynamespace", "pkg_resources")
        except KeyError:
            self.fail("No edge between mynamespace and pkg_resources")
