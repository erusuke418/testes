# -*- mode: python -*-
#-----------------------------------------------------------------------------
# Copyright (c) 2013-2017, PyInstaller Development Team.
#
# Distributed under the terms of the GNU General Public License with exception
# for distributing bootloader.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

import sys

# TESTING MULTIPROCESS FEATURE: file A (onedir pack) depends on file B (onefile pack).


__testname__ = '../scripts/test_multipackage3'
__testdep__ = '../scripts/multipackage3_B'

a = Analysis([__testname__ + '.py'],
             pathex=['.'])
b = Analysis([__testdep__ + '.py'],
             pathex=['.'])

pyz = PYZ(a.pure, b.pure)

exe = EXE(pyz,
          a.scripts,
          a.dependencies,
          exclude_binaries=1,
          name=os.path.basename(__testname__),
          debug=True,
          strip=False,
          upx=True,
          console=1 )

exeB = EXE(pyz,
          b.scripts,
          b.binaries,
          b.zipfiles,
          b.datas,
          b.dependencies,
          name=os.path.join('dist', __testdep__ + '.exe'),
          debug=True,
          strip=False,
          upx=True,
          console=1 )

coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        exeB,
        b.binaries,
        b.zipfiles,
        b.datas,
        strip=False,
        upx=True,
        name=os.path.join('dist', __testname__ ))
