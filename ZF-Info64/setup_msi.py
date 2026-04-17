"""
cx_Freeze setup script — generates MSI installer for ZF-Info64.
Usage: python setup_msi.py bdist_msi
"""
import sys
from pathlib import Path
from cx_Freeze import setup, Executable

build_exe_options = {
    "packages": ["psutil", "tkinter", "PIL", "urllib"],
    "include_files": [
        ("logo ZF-Logo64.png", "logo ZF-Logo64.png"),
    ],
    "excludes": ["unittest", "email", "html", "http",
                 "xmlrpc", "pydoc", "doctest", "difflib"],
    "optimize": 1,
}

bdist_msi_options = {
    "product_code":   "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}",
    "upgrade_code":   "{B2C3D4E5-F6A7-8901-BCDE-F12345678901}",
    "add_to_path":    False,
    "initial_target_dir": r"[ProgramFilesFolder]\ZF-Info64",
    "summary_data": {
        "author":   "ZF-Info64",
        "comments": "System Information & Benchmark Tool",
    },
}

setup(
    name        = "ZF-Info64",
    version     = "2.0",
    description = "System Information & Benchmark Tool",
    author      = "ZF-Info64",
    options     = {
        "build_exe":  build_exe_options,
        "bdist_msi":  bdist_msi_options,
    },
    executables = [
        Executable(
            "ZF-Info64-Windows.py",
            base            = "Win32GUI",   # no console
            target_name     = "ZF-Info64.exe",
            icon            = "zf_icon.ico",
            shortcut_name   = "ZF-Info64",
            shortcut_dir    = "DesktopFolder",
        )
    ],
)
