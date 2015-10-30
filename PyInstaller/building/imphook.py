#-----------------------------------------------------------------------------
# Copyright (c) 2005-2015, PyInstaller Development Team.
#
# Distributed under the terms of the GNU General Public License with exception
# for distributing bootloader.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------


"""
Code related to processing of import hooks.
"""

import glob
import os.path
import re

from collections import OrderedDict
from .. import log as logging
from .utils import format_binaries_and_datas
from ..compat import expand_path
from ..compat import importlib_load_source
from .imphookapi import PostGraphAPI

logger = logging.getLogger(__name__)


# Reproducible freeze: OrderedDict ensures hooks are always applied in the same
# order.
class ExcludedImports(OrderedDict):
    """
    Dictionary mapping for hook attribute 'excludedimports'.
    'excludedimports' is a list of Python module names that PyInstaller
    should not detect as dependency of some module names.

    Excludedimports attribute is parsed from all post-import hooks
    before analyzing any Python code. This ensures that all excluded
    modules are checked in the right time when they get imported.
    """
    def __init__(self, hooks_files):
        """
        Initialize this dictionary.
        """
        super(ExcludedImports, self).__init__()
        logger.info('Loading excluded imports...')
        self._parser = re.compile('excludedimports = (.+)$', flags=re.MULTILINE)
        # TODO find out better way how to obtain 'excludedimports' from hooks.
        for modname, filenames in hooks_files.items():
            # TODO parse all files not just first one.
            code = self._parse_code(filenames[0])
            if not code:  # hook does not contain 'excludedimports'
                continue
            # Evaluate code and update self dict.
            excl_imports = eval(code)
            excl_imports.sort()
            logger.info('  Excluded imports for %r -> %s', modname, ', '.join(excl_imports))
            for excl_mod in excl_imports:
                if excl_mod not in self:
                    self[excl_mod] = set()
                self[excl_mod].add(modname)

    def _parse_code(self, filename):
        code = None
        with open(filename, 'r') as f:
            match = self._parser.search(f.read())
            if match is not None:
                code = match.groups()[0]
        return code


# Reproducible freeze: OrderedDict ensures hooks are always applied in the same
# order.
class HooksCache(OrderedDict):
    """
    Dictionary mapping from the fully-qualified names of each module hooked by
    at least one hook script to lists of the absolute paths of these scripts.

    This `dict` subclass caches the list of all hooks applicable to each module,
    permitting Pythonic mapping, iteration, addition, and removal of such hooks.
    Each dictionary key is a fully-qualified module name. Each dictionary value
    is a list of the absolute paths of all hook scripts specific to that module,
    including both official PyInstaller hooks and unofficial user-defined hooks.

    See Also
    ----------
    `_load_file_list()`
        For details on hook priority.
    """
    def __init__(self, hooks_dir):
        """
        Initialize this dictionary.

        Parameters
        ----------
        hook_dir : str
            Absolute or relative path of the directory containing hooks with
            which to populate this cache. By default, this is the absolute path
            of the `PyInstaller/hooks` directory containing official hooks.
        """
        super(HooksCache, self).__init__()
        self._load_file_list(hooks_dir)

    def _load_file_list(self, hooks_dir):
        """
        Cache all hooks in the passed directory.

        **Order of caching is significant** with respect to hooks for the same
        module, as the values of this dictionary are ordered lists. Hooks for
        the same module will be run in the order in which they are cached.
        Previously cached hooks are always preserved (rather than overidden).

        Specifically, any hook in the passed directory having the same module
        name as that of a previously cached hook will be appended to the list of
        hooks for that module name. By default, official hooks are cached
        _before_ user-defined hooks. For modules with both official and
        user-defined hooks, this implies that the former take priority over and
        will be run _before_ the latter.

        Parameters
        ----------
        hooks_dir : str
            Absolute or relative path of the directory containing additional
            hooks to be cached. For convenience, tilde and variable expansion
            will be applied to this path (e.g., a leading `~` will be replaced
            by the absolute path of the corresponding home directory).
        """
        # Perform tilde and variable expansion and validate the result.
        hooks_dir = expand_path(hooks_dir)
        if not os.path.isdir(hooks_dir):
            logger.error('Hook directory %r not found',
                         os.path.abspath(hooks_dir))
            return

        # For each hook in the passed directory...
        hook_files = glob.glob(os.path.join(hooks_dir, 'hook-*.py'))
        hook_files.sort()
        for hook_file in hook_files:
            # Absolute path of this hook's script.
            hook_file = os.path.abspath(hook_file)

            # Fully-qualified name of this hook's corresponding module,
            # constructed by removing the "hook-" prefix and ".py" suffix.
            module_name = os.path.basename(hook_file)[5:-3]

            # If this module already has cached hooks, append this hook's path
            # to the existing list of such paths.
            if module_name in self:
                self[module_name].append(hook_file)
            # Else, default to a new list containing only this hook's path.
            else:
                self[module_name] = [hook_file]

    def add_custom_paths(self, hooks_dirs):
        """
        Cache all hooks in the list of passed directories.

        Parameters
        ----------
        hooks_dirs : list
            List of the absolute or relative paths of all directories containing
            additional hooks to be cached.
        """
        for hooks_dir in hooks_dirs:
            self._load_file_list(hooks_dir)

    def remove(self, module_names):
        """
        Remove all key-value pairs whose key is a fully-qualified module name in
        the passed list from this dictionary.

        Parameters
        ----------
        module_names : list
            List of all fully-qualified module names to be removed.
        """
        for module_name in set(module_names):  # Eliminate duplicate entries.
            if module_name in self:
                del self[module_name]

    def copy(self):
        """
        Return a copy of internal dict structure.
        """
        c = OrderedDict()
        for k, v in self.items():
            c[k] = v
        return c


class AdditionalFilesCache(object):
    """
    Cache for storing what binaries and datas were pushed by what modules
    when import hooks were processed.
    """
    def __init__(self):
        self._binaries = {}
        self._datas = {}

    def add(self, modname, binaries, datas):
        self._binaries[modname] = binaries or []
        self._datas[modname] = datas or []

    def __contains__(self, name):
        return name in self._binaries or name in self._datas

    def binaries(self, modname):
        """
        Return list of binaries for given module name.
        """
        return self._binaries[modname]

    def datas(self, modname):
        """
        Return list of datas for given module name.
        """
        return self._datas[modname]


class ImportHook(object):
    """
    Class encapsulating processing of hook attributes like hiddenimports, etc.
    """
    def __init__(self, modname, hook_filename):
        """
        :param hook_filename: File name where to load hook from.
        """
        logger.info('Processing hook   %s' % os.path.basename(hook_filename))
        self._name = modname
        self._filename = hook_filename
        # _module represents the code of 'hook-modname.py'
        # Load hook from file and parse and interpret it's content.
        hook_modname = 'PyInstaller_hooks_' + modname.replace('.', '_')
        self._module = importlib_load_source(hook_modname, self._filename)
        # Public import hook attributes for further processing.
        self.binaries = set()
        self.datas = set()

    # Internal methods for processing.

    def _process_hook_function(self, mod_graph):
        """
        Call the hook function hook(mod).
        Function hook(mod) has to be called first because this function
        could update other attributes - datas, hiddenimports, etc.
        """
        # Process a `hook(hook_api)` function.
        hook_api = PostGraphAPI(self._name, mod_graph)
        self._module.hook(hook_api)

        self.datas.update(set(hook_api._added_datas))
        self.binaries.update(set(hook_api._added_binaries))
        for item in hook_api._added_imports:
            self._process_one_hiddenimport(item, mod_graph)
        for item in hook_api._deleted_imports:
            # Remove the graph link between the hooked module and item.
            # This removes the 'item' node from the graph if no other
            # links go to it (no other modules import it)
            mod_graph.removeReference(hook_api.node, item)

    def _process_hiddenimports(self, mod_graph):
        """
        'hiddenimports' is a list of Python module names that PyInstaller
        is not able detect.
        """
        # push hidden imports into the graph, as if imported from self._name
        for item in self._module.hiddenimports:
            self._process_one_hiddenimport(item, mod_graph)

    def _process_one_hiddenimport(self, item, mod_graph):
        try:
            # Do not try to first find out if a module by that name already exist.
            # Rely on modulegraph to handle that properly.
            # Do not automatically create namespace packages if they do not exist.
            caller = mod_graph.findNode(self._name, create_nspkg=False)
            mod_graph.import_hook(item, caller=caller)
        except ImportError:
            # Print warning if a module from hiddenimport could not be found.
            # modulegraph raises ImporError when a module is not found.
            # Import hook with non-existing hiddenimport is probably a stale hook
            # that was not updated for a long time.
            logger.warn("Hidden import '%s' not found (probably old hook)" % item)

    def _process_datas(self, mod_graph):
        """
        'datas' is a list of globs of files or
        directories to bundle as datafiles. For each
        glob, a destination directory is specified.
        """
        # Find all files and interpret glob statements.
        self.datas.update(set(format_binaries_and_datas(self._module.datas)))

    def _process_binaries(self, mod_graph):
        """
        'binaries' is a list of files to bundle as binaries.
        Binaries are special that PyInstaller will check if they
        might depend on other dlls (dynamic libraries).
        """
        self.binaries.update(set(format_binaries_and_datas(self._module.binaries)))

    def _process_attrs(self, mod_graph):
        # TODO implement attribute 'hook_name_space.attrs'
        # hook_name_space.attrs is a list of tuples (attr_name, value) where 'attr_name'
        # is name for Python module attribute that should be set/changed.
        # 'value' is the value of that attribute. PyInstaller will modify
        # mod.attr_name and set it to 'value' for the created .exe file.
        pass

    # Public methods

    def update_dependencies(self, mod_graph):
        """
        Update module dependency graph with import hook attributes (hiddenimports, etc.)
        :param mod_graph: PyiModuleGraph object to be updated.
        """
        if hasattr(self._module, 'hook'):
            self._process_hook_function(mod_graph)
        if hasattr(self._module, 'hiddenimports'):
            self._process_hiddenimports(mod_graph)
        if hasattr(self._module, 'datas'):
            self._process_datas(mod_graph)
        if hasattr(self._module, 'binaries'):
            self._process_binaries(mod_graph)
        if hasattr(self._module, 'attrs'):
            self._process_attrs(mod_graph)
