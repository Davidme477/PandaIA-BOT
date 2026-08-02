# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH).parent
datas = [
    (str(project / 'app' / 'styles'), 'app/styles'),
    (str(project / 'overlay' / 'templates'), 'overlay/templates'),
    (str(project / 'overlay' / 'static'), 'overlay/static'),
    (str(project / 'resources' / 'defaults'), 'resources/defaults'),
    (str(project / 'resources' / 'icons'), 'resources/icons'),
]
binaries = []
hiddenimports = ['overlay.server', 'soundfile', 'numpy', 'kokoro', 'torch']

a = Analysis([str(project / 'main.py')], pathex=[str(project)], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['pytest', 'tests', 'win32com', 'pythoncom', 'pywintypes'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PandaIA', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(project / 'resources' / 'icons' / 'pandaia.ico'),
          version=str(project / 'packaging' / 'version_info.txt'),
          manifest=str(project / 'packaging' / 'PandaIA.manifest'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PandaIA')
