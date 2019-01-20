import unittest
import os
import pathlib
import shutil
import subprocess
import sys
import importlib

import modulegraph2

INPUT_DIR = pathlib.Path(__file__).resolve().parent / "six-dir"


class TestSixSupport (unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.fspath(INPUT_DIR))

        site_dir = INPUT_DIR / "site-packages"
        sys.path.insert(0, os.fspath(site_dir))

        if site_dir.exists():
            shutil.rmtree(site_dir)

        site_dir.mkdir()

        subprocess.check_call([sys.executable, "-mpip", "-qqq", "install", "--target", os.fspath(site_dir), "six"])

    @classmethod
    def tearDownClass(cls):
        to_remove = []
        for mod in sys.modules:
            if (
                hasattr(sys.modules[mod], "__file__")
                and sys.modules[mod].__file__ is not None
                and sys.modules[mod].__file__.startswith(os.fspath(INPUT_DIR))
            ):
                to_remove.append(mod)
        for mod in to_remove:
            del sys.modules[mod]

        importlib.invalidate_caches()

        assert sys.path[0] == os.fspath(INPUT_DIR / "site-packages")
        del sys.path[0]

        assert sys.path[0] == os.fspath(INPUT_DIR)
        del sys.path[0]

        shutil.rmtree(INPUT_DIR / "site-packages")

    def assert_has_node(self, mg, node_name, node_class=None):
        n = mg.find_node(node_name)
        if n is None:
            self.fail(f"Cannot find {node_name!r} in graph")

        elif node_class is not None and not isinstance(n, node_class):
            self.fail(
                f"Node for {node_name!r} is not an instance of {node_class.__name__} but {type(n).__name__}"
            )

    def assert_has_edge(self, mg, from_name, to_name, edge_data):
        self.assert_has_node(mg, from_name)
        self.assert_has_node(mg, to_name)

        try:
            edge = mg.edge_data(from_name, to_name)

        except KeyError:
            pass
        else:
            self.assertEqual(len(edge), len(edge_data))
            self.assertEqual(edge, edge_data)
            return

        self.fail(f"No edge between {from_name!r} and {to_name!r}")

    def assert_has_roots(self, mg, *node_names):
        roots = set(node_names)
        self.assertEqual({n.identifier for n in mg.roots()}, roots)

    def assert_has_nodes(self, mg, *node_names):
        nodes = set(node_names)
        self.assertEqual({n.identifier for n in mg.iter_graph()}, nodes)

    def assert_edge_count(self, mg, edge_count):
        self.assertEqual(len(list(mg.edges())), edge_count)


    def test_six(self):
        mg = modulegraph2.ModuleGraph()
        mg.add_module("using_six")

        self.assert_has_node(mg, "using_six", modulegraph2.SourceModule)
        self.assert_has_node(mg, "six", modulegraph2.SourceModule)
        self.assert_has_node(mg, "six.moves", modulegraph2.NamespacePackage)
        self.assert_has_node(mg, "six.moves.html_parser", modulegraph2.AliasNode)
        self.assert_has_node(mg, "six.moves.reload_module", modulegraph2.AliasNode)
        self.assert_has_node(mg, "six.moves.urllib_error", modulegraph2.AliasNode)
        self.assert_has_node(mg, "six.moves.reduce", modulegraph2.AliasNode)
        self.assert_has_node(mg, "html", modulegraph2.Package)
        self.assert_has_node(mg, "html.parser", modulegraph2.Package)
        self.assert_has_node(mg, "importlib", modulegraph2.Package)
        self.assert_has_node(mg, "functools", modulegraph2.SourceModule)
        self.assert_has_node(mg, "urllib.error", modulegraph2.Package)

        self.assert_has_edge(mg, "using_six", "six.moves", {modulegraph2.DependencyInfo(False, True, True, None)})
        self.assert_has_edge(mg, "using_six", "six.moves.html_parser", {modulegraph2.DependencyInfo(False, True, True, None)})
        self.assert_has_edge(mg, "using_six", "six.moves.reload_module", {modulegraph2.DependencyInfo(False, True, True, None)})
        self.assert_has_edge(mg, "using_six", "six.moves.urllib_error", {modulegraph2.DependencyInfo(False, True, True, None)})
        self.assert_has_edge(mg, "using_six", "six.moves.reduce", {modulegraph2.DependencyInfo(False, True, True, None)})

        self.assert_has_edge(mg, "six.moves.html_parser", "html.parser", {modulegraph2.DependencyInfo(False, True, False, None)})
        self.assert_has_edge(mg, "six.moves.reload_module", "importlib", {modulegraph2.DependencyInfo(False, True, False, None)})
        self.assert_has_edge(mg, "six.moves.urllib_error", "urllib.error", {modulegraph2.DependencyInfo(False, True, False, None)})
        self.assert_has_edge(mg, "six.moves.reduce", "functools", {modulegraph2.DependencyInfo(False, True, False, None)})

        node = mg.find_node("six.moves")
        self.assertFalse(node.has_data_files)

    def test_vendored_six(self):
        # Same as test_six, but now with six installed as sub package,
        # as used by a number of projects that have vendored six.
        return

        (INPUT_DIR / "site-packages" / "vendored").mkdir()
        with open(INPUT_DIR / "site-packages" / "vendored" / "__init__.py", "w") as fp:
            fp.write("''' init '''\n")

        (INPUT_DIR / "site-packages" / "six").rename(INPUT_DIR / "site-packages" / "vendored" / "six" )

        try:
            mg = modulegraph2.ModuleGraph()
            mg.add_module("using_vendored_six")

            self.assert_has_node(mg, "using_six", modulegraph2.SourceModule)
            self.assert_has_node(mg, "vendored.six", modulegraph2.SourceModule)
            self.assert_has_node(mg, "vendored.six.moves", modulegraph2.NamespacePackage)
            self.assert_has_node(mg, "vendored.six.moves.html_parser", modulegraph2.AliasNode)
            self.assert_has_node(mg, "vendored.six.moves.reload_module", modulegraph2.AliasNode)
            self.assert_has_node(mg, "vendored.six.moves.urllib_error", modulegraph2.AliasNode)
            self.assert_has_node(mg, "vendored.six.moves.reduce", modulegraph2.AliasNode)
            self.assert_has_node(mg, "html.parser", modulegraph2.Package)
            self.assert_has_node(mg, "importlib", modulegraph2.Package)
            self.assert_has_node(mg, "urllib.error", modulegraph2.Package)

            self.assert_has_edge(mg, "using_six", "vendored.six.moves", {modulegraph2.DependencyInfo(False, True, True, None)})
            self.assert_has_edge(mg, "using_six", "vendored.six.moves.html_parser", {modulegraph2.DependencyInfo(False, True, True, None)})
            self.assert_has_edge(mg, "using_six", "vendored.six.moves.reload_module", {modulegraph2.DependencyInfo(False, True, True, None)})
            self.assert_has_edge(mg, "using_six", "vendored.six.moves.urllib_error", {modulegraph2.DependencyInfo(False, True, True, None)})
            self.assert_has_edge(mg, "using_six", "vendored.six.moves.reduce", {modulegraph2.DependencyInfo(False, True, True, None)})

            self.assert_has_edge(mg, "vendored.six.moves.html_parser", "html.parser", {modulegraph2.DependencyInfo(False, True, False, None)})
            self.assert_has_edge(mg, "vendored.six.moves.reload_module", "importlib", {modulegraph2.DependencyInfo(False, True, False, None)})
            self.assert_has_edge(mg, "vendored.six.moves.urllib_error", "urllib.error", {modulegraph2.DependencyInfo(False, True, False, None)})
            self.assert_has_edge(mg, "vendored.six.moves.reduce", "functools", {modulegraph2.DependencyInfo(False, True, False, None)})

        finally:
            (INPUT_DIR / "site-packages" / "vendored" / "six").rename(INPUT_DIR / "site-packages" / "six" )
