# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SAP GUI Scripting Tool (executável standalone Windows).

Gera um único ``SAPScriptingTool.exe`` (onefile, sem console). Inclui os
módulos do pacote ``src`` e as dependências COM (pywin32) e de UI
(PyQt6 + QScintilla) que o PyInstaller nem sempre detecta automaticamente.

Build:  pyinstaller --noconfirm --clean sap_scripting_tool.spec
        (ou:  python scripts/build.py)
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH)  # noqa: F821 - SPECPATH é injetado pelo PyInstaller

# pywin32/QScintilla nem sempre são rastreados a partir dos imports tardios.
hiddenimports = [
    "PyQt6.Qsci",
    "win32com",
    "win32com.client",
    "win32com.client.connect",
    "win32com.server.policy",
    "win32com.server.util",
    "pythoncom",
    "pywintypes",
    "win32gui",
    "win32api",
    "win32con",
]
hiddenimports += collect_submodules("src")

datas = collect_data_files("PyQt6.Qsci")

a = Analysis(
    [str(PROJECT_ROOT / "src" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "pytest_qt"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SAPScriptingTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # aplicação GUI: sem janela de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
