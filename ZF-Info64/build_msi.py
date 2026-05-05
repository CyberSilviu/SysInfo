"""
Build MSI installer wrapping the PyInstaller single-file EXE.
Usage: python build_msi.py
Requires: dist/ZF-Info64.exe already built by PyInstaller
"""
import msilib, msilib.schema, msilib.sequence, msilib.text
import os, uuid, shutil
from pathlib import Path

HERE     = Path(__file__).parent
EXE_SRC  = HERE / "dist" / "ZF-Info64.exe"
ICON_SRC = HERE / "zf_icon.ico"
OUT_MSI  = HERE / "dist" / "ZF-Info64-2.0-win64.msi"

PRODUCT_NAME    = "ZF-Info64"
VERSION         = "2.0.0"
MANUFACTURER    = "ZF-Info64"
PRODUCT_CODE    = "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"
UPGRADE_CODE    = "{B2C3D4E5-F6A7-8901-BCDE-F12345678901}"
INSTALL_DIR     = r"[ProgramFilesFolder]\ZF-Info64"

if not EXE_SRC.exists():
    raise FileNotFoundError(f"PyInstaller EXE not found: {EXE_SRC}")

OUT_MSI.parent.mkdir(exist_ok=True)

db = msilib.OpenDatabase(str(OUT_MSI), msilib.MSIDBOPEN_CREATEDIRECT)
msilib.add_tables(db, msilib.schema)

# ── Summary stream ────────────────────────────────────────────────────────────
si = db.GetSummaryInformation(5)
si.SetProperty(msilib.PID_TITLE,    "Installation Database")
si.SetProperty(msilib.PID_SUBJECT,  f"{PRODUCT_NAME} {VERSION}")
si.SetProperty(msilib.PID_AUTHOR,   MANUFACTURER)
si.SetProperty(msilib.PID_TEMPLATE, "x64;1033")
si.SetProperty(msilib.PID_REVNUMBER, str(uuid.uuid4()).upper())
si.SetProperty(msilib.PID_WORDCOUNT, 2)   # compressed
si.SetProperty(msilib.PID_PAGECOUNT, 200) # MSI spec version
si.Persist()

# ── Property table ────────────────────────────────────────────────────────────
msilib.add_data(db, "Property", [
    ("ProductName",    PRODUCT_NAME),
    ("ProductCode",    PRODUCT_CODE),
    ("ProductVersion", VERSION),
    ("Manufacturer",   MANUFACTURER),
    ("UpgradeCode",    UPGRADE_CODE),
    ("ALLUSERS",       "1"),
    ("ARPPRODUCTICON", "AppIcon"),
    ("ARPNOREPAIR",    "1"),
    ("ARPNOMODIFY",    "1"),
])

# ── Directory table ───────────────────────────────────────────────────────────
msilib.add_data(db, "Directory", [
    ("TARGETDIR",   "SourceDir", "SourceDir"),
    ("ProgramFilesFolder", "TARGETDIR", "PFiles"),
    ("INSTALLDIR",  "ProgramFilesFolder", "ZF-Info64"),
])

# ── Component + File ──────────────────────────────────────────────────────────
comp_id  = str(uuid.uuid4()).upper()
file_key = "ZFInfo64EXE"

msilib.add_data(db, "Component", [
    (file_key, "{" + comp_id + "}", "INSTALLDIR", 0, None, file_key),
])

file_size = EXE_SRC.stat().st_size
msilib.add_data(db, "File", [
    (file_key, file_key, "ZF-Info64.exe", file_size, None, None, 512, 1),
])

# ── Feature ───────────────────────────────────────────────────────────────────
msilib.add_data(db, "Feature", [
    ("DefaultFeature", None, "ZF-Info64", "Complete install", 1, 1, None, 8),
])
msilib.add_data(db, "FeatureComponents", [
    ("DefaultFeature", file_key),
])

# ── Icon ──────────────────────────────────────────────────────────────────────
if ICON_SRC.exists():
    msilib.add_data(db, "Icon", [
        ("AppIcon", str(ICON_SRC)),
    ])

# ── Shortcut (Desktop) ────────────────────────────────────────────────────────
short_comp = "ShortcutComp"
short_comp_id = str(uuid.uuid4()).upper()
msilib.add_data(db, "Directory", [
    ("DesktopFolder", "TARGETDIR", "."),
])
msilib.add_data(db, "Component", [
    (short_comp, "{" + short_comp_id + "}", "DesktopFolder", 0, None, None),
])
msilib.add_data(db, "FeatureComponents", [
    ("DefaultFeature", short_comp),
])
msilib.add_data(db, "Shortcut", [
    ("DesktopShortcut", "DesktopFolder", "ZF-Info64",
     short_comp, "[INSTALLDIR]ZF-Info64.exe", None, None, "AppIcon", 0, None, None, None),
])

# ── RemoveFiles (clean uninstall) ─────────────────────────────────────────────
msilib.add_data(db, "RemoveFile", [
    ("RemoveEXE", file_key, "ZF-Info64.exe", "INSTALLDIR", 2),
])

# ── Media / CAB ───────────────────────────────────────────────────────────────
msilib.add_data(db, "Media", [
    (1, 1, None, "#ZFInfo64CAB", None, None),
])

# ── Standard sequences ────────────────────────────────────────────────────────
msilib.add_data(db, "InstallExecuteSequence", [
    ("InstallInitialize",    None,  1500),
    ("InstallFinalize",      None,  6600),
    ("InstallFiles",         None,  4000),
    ("CreateShortcuts",      None,  4500),
    ("RemoveFiles",          None,  3500),
    ("RemoveShortcuts",      None,  3400),
    ("RegisterProduct",      None,  6100),
    ("PublishProduct",       None,  6400),
    ("PublishFeatures",      None,  6300),
    ("UnpublishFeatures",    None,  1800),
    ("ValidateProductID",    None,  700),
    ("CostInitialize",       None,  800),
    ("FileCost",             None,  900),
    ("CostFinalize",         None,  1000),
])
msilib.add_data(db, "InstallUISequence", [
    ("CostInitialize",  None, 800),
    ("FileCost",        None, 900),
    ("CostFinalize",    None, 1000),
    ("ExecuteAction",   None, 1300),
])

db.Commit()

# ── Embed the EXE into the CAB inside the MSI ─────────────────────────────────
cab_name = "ZFInfo64CAB"
cab = msilib.CAB(cab_name)
cab.append(str(EXE_SRC), file_key, file_key)
cab.commit(db)

db.Commit()
print(f"MSI written to: {OUT_MSI}  ({OUT_MSI.stat().st_size // 1024 // 1024} MB)")
