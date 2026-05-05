"""
Build MSI for a specific edition (Pro or Free).
Usage:
  python build_msi_edition.py Pro
  python build_msi_edition.py Free
"""
import sys, os, shutil, subprocess
from pathlib import Path

EDITION  = sys.argv[1] if len(sys.argv) > 1 else "Pro"
HERE     = Path(__file__).parent
EXE_SRC  = HERE / "dist" / EDITION / f"ZF-Info64-{EDITION}.exe"
BUILD_DIR = HERE / "build" / f"exe-msi-{EDITION}"
OUT_DIR  = HERE / "dist" / EDITION

if not EXE_SRC.exists():
    sys.exit(f"EXE not found: {EXE_SRC}")

# ── Create a clean build dir with just the single EXE ────────────────────────
shutil.rmtree(BUILD_DIR, ignore_errors=True)
BUILD_DIR.mkdir(parents=True)
shutil.copy(EXE_SRC, BUILD_DIR / f"ZF-Info64-{EDITION}.exe")

# ── Write a temporary cx_Freeze setup targeting this edition ──────────────────
codes = {
    "Pro":  ("{A1B2C3D4-E5F6-7890-ABCD-EF1234567891}", "{B2C3D4E5-F6A7-8901-BCDE-F12345678902}"),
    "Free": ("{C3D4E5F6-A7B8-9012-CDEF-123456789013}", "{D4E5F6A7-B8C9-0123-DEF0-234567890124}"),
}
prod_code, upg_code = codes[EDITION]

setup_code = f"""
import sys
sys.argv = ['setup', 'bdist_msi', '--skip-build']
from pathlib import Path
from cx_Freeze import setup, Executable

build_exe_options = {{
    "build_exe": str(Path(r"{BUILD_DIR}")),
}}
bdist_msi_options = {{
    "product_code":   "{prod_code}",
    "upgrade_code":   "{upg_code}",
    "add_to_path":    False,
    "initial_target_dir": r"[ProgramFilesFolder]\\ZF-Info64 {EDITION}",
    "dist_dir":       str(Path(r"{OUT_DIR}")),
    "summary_data": {{
        "author":   "ZF-Info64",
        "comments": "System Information & Benchmark Tool - {EDITION}",
    }},
}}
setup(
    name        = "ZF-Info64 {EDITION}",
    version     = "2.0",
    description = "System Information & Benchmark Tool - {EDITION}",
    author      = "ZF-Info64",
    options     = {{
        "build_exe":  build_exe_options,
        "bdist_msi":  bdist_msi_options,
    }},
    executables = [
        Executable(
            str(Path(r"{BUILD_DIR}") / "ZF-Info64-{EDITION}.exe"),
            base        = "gui",
            target_name = "ZF-Info64-{EDITION}.exe",
            icon        = str(Path(r"{HERE}") / "zf_icon.ico"),
            shortcut_name   = "ZF-Info64 {EDITION}",
            shortcut_dir    = "DesktopFolder",
        )
    ],
)
"""

tmp_setup = HERE / f"_setup_msi_{EDITION}.py"
tmp_setup.write_text(setup_code, encoding="utf-8")

result = subprocess.run([sys.executable, str(tmp_setup)], cwd=str(HERE))
tmp_setup.unlink(missing_ok=True)

# Find and rename output MSI
for f in OUT_DIR.glob("*.msi"):
    target = OUT_DIR / f"ZF-Info64-{EDITION}-2.0-win64.msi"
    if f != target:
        f.rename(target)
        f = target
    print(f"MSI: {f}  ({f.stat().st_size // 1024 // 1024} MB)")
    break

sys.exit(result.returncode)
