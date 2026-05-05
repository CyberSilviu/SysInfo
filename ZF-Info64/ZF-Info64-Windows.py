"""
ZF-Info64 Pro v2.0 — System Information & Benchmark Tool for Windows
"""
APP_EDITION = "Pro"   # change to "Free" for the Free build

import tkinter as tk
from tkinter import ttk
import threading, time, os, sys, math, random, ctypes
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import platform, concurrent.futures, tempfile, subprocess, multiprocessing

def _resource_path(name):
    """Resolve a bundled resource path for both script and PyInstaller frozen modes."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0D1117"
BG2      = "#161B22"
CARD     = "#1C2333"
ELEV     = "#242D3D"
BORDER   = "#30363D"
CYAN     = "#00D4FF"
GREEN    = "#00E676"
ORANGE   = "#FFA726"
RED      = "#FF5252"
PURPLE   = "#B388FF"
YELLOW   = "#FFEB3B"
T1       = "#F0F6FC"
T2       = "#8B949E"
T3       = "#484F58"

MAX_SCORE = 10_000

# ── Utilities ─────────────────────────────────────────────────────────────────
def fmt_bytes(b):
    if b >= 1<<30: return f"{b/(1<<30):.2f} GB"
    if b >= 1<<20: return f"{b/(1<<20):.1f} MB"
    if b >= 1<<10: return f"{b/(1<<10):.0f} KB"
    return f"{b} B"

def fmt_large(n):
    if n >= 1_000_000_000: return f"{n/1e9:.1f}G"
    if n >= 1_000_000:     return f"{n/1e6:.1f}M"
    if n >= 1_000:         return f"{n/1e3:.1f}K"
    return str(n)

def clamp(v, lo, hi): return max(lo, min(hi, v))

# ── Windows hardware query helpers ────────────────────────────────────────────
import os as _os
_PS = _os.path.join(
    _os.environ.get("SystemRoot", r"C:\Windows"),
    "System32", "WindowsPowerShell", "v1.0", "powershell.exe")

# One combined PowerShell call — all hardware data in a single process launch.
_HW_CACHE = None

def _load_hw_cache():
    global _HW_CACHE
    if _HW_CACHE is not None:
        return _HW_CACHE
    ps_script = r"""
$ErrorActionPreference = 'SilentlyContinue'
# CPU
$cpu = (Get-WmiObject Win32_Processor | Select-Object -First 1).Name
"CPU:$($cpu.Trim())"
# Disks
Get-WmiObject Win32_DiskDrive | ForEach-Object { "DISK:$($_.Model.Trim())" }
# Active NICs
Get-WmiObject Win32_NetworkAdapter | Where-Object { $_.NetConnectionStatus -eq 2 } |
    ForEach-Object { "NIC:$($_.Name.Trim())" }
# RAM modules
Get-WmiObject Win32_PhysicalMemory | ForEach-Object {
    $cap  = [math]::Round($_.Capacity / 1GB, 0)
    $type = switch ([int]$_.SMBIOSMemoryType) {
        20 {"DDR"} 21 {"DDR2"} 24 {"DDR3"}
        26 {"DDR4"} 27 {"LPDDR4"} 34 {"DDR5"} 35 {"LPDDR5"} default {"DDR"}
    }
    $mfr = $_.Manufacturer.Trim()
    $pn  = $_.PartNumber.Trim()
    $spd = $_.Speed
    "RAM:${cap}GB $type ${spd}MHz $mfr $pn"
}
# Battery cycle count
$bat = (Get-WmiObject Win32_Battery | Select-Object -First 1).CycleCount
if ($bat -gt 0) { "BATCYCLE:$bat" }
"""
    result = {"cpu": None, "disks": [], "nics": [], "ram": [], "bat_cycle": None}
    try:
        r = subprocess.run(
            [_PS, "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=20,
            creationflags=0x08000000)
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("CPU:"):
                v = line[4:].strip()
                if v:
                    result["cpu"] = v
            elif line.startswith("DISK:"):
                v = line[5:].strip()
                if v:
                    result["disks"].append(v)
            elif line.startswith("NIC:"):
                v = line[4:].strip()
                if v:
                    result["nics"].append(v)
            elif line.startswith("RAM:"):
                v = line[4:].strip()
                if v:
                    result["ram"].append(v)
            elif line.startswith("BATCYCLE:"):
                v = line[9:].strip()
                if v and v != "0":
                    result["bat_cycle"] = v
    except Exception:
        pass
    _HW_CACHE = result
    return result

def _get_cpu_name_windows():
    # winreg is instantaneous and works without any subprocess
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        key.Close()
        if name:
            return name
    except Exception:
        pass
    return _load_hw_cache().get("cpu")

def _get_disk_models():
    return _load_hw_cache()["disks"]

def _get_active_nics():
    return _load_hw_cache()["nics"]

def _get_ram_modules():
    return _load_hw_cache()["ram"]

def _get_battery_cycle_count():
    return _load_hw_cache()["bat_cycle"]

# ── GPU enumeration (WMIC + DXGI) ────────────────────────────────────────────
def _get_gpu_list():
    """Returns list of {'name', 'vram_mb'} via WMIC Win32_VideoController."""
    try:
        r = subprocess.run(
            ['wmic', 'path', 'Win32_VideoController',
             'get', 'Name,AdapterRAM', '/format:csv'],
            capture_output=True, text=True, timeout=12,
            creationflags=0x08000000)
        gpus = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 3:
                continue
            ram_str, name = parts[1], parts[2]
            if not name or name in ('AdapterRAM', 'Name'):
                continue
            try:
                vram_mb = max(0, int(ram_str or '0')) >> 20
            except ValueError:
                vram_mb = 0
            gpus.append({'name': name, 'vram_mb': vram_mb})
        return gpus
    except Exception:
        return []


def _enumerate_dxgi_adapters():
    """Returns list of {'index', 'name', 'vram_mb'} via DXGI COM vtables."""
    try:
        import ctypes, ctypes.wintypes as wt

        class DXGI_ADAPTER_DESC(ctypes.Structure):
            _fields_ = [
                ("Description",           ctypes.c_wchar * 128),
                ("VendorId",              ctypes.c_uint),
                ("DeviceId",              ctypes.c_uint),
                ("SubSysId",              ctypes.c_uint),
                ("Revision",              ctypes.c_uint),
                ("DedicatedVideoMemory",  ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory",    ctypes.c_size_t),
                ("AdapterLuid",           ctypes.c_int64),
            ]

        dxgi = ctypes.WinDLL("dxgi")
        dxgi.CreateDXGIFactory.restype  = ctypes.c_int
        dxgi.CreateDXGIFactory.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(ctypes.c_void_p)]
        # IID_IDXGIFactory {7b7194f4-3514-4d46-9722-d10b8512f863}
        iid = (ctypes.c_byte * 16)(
            0xf4,0x94,0x71,0x7b, 0x14,0x35, 0x46,0x4d,
            0x97,0x22,0xd1,0x0b,0x85,0x12,0xf8,0x63)
        ppF = ctypes.c_void_p(0)
        if dxgi.CreateDXGIFactory(iid, ctypes.byref(ppF)) != 0 or not ppF.value:
            return []

        def vtbl_fn(obj, idx, restype, *argtypes):
            vp = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))
                             .contents.value,
                             ctypes.POINTER(ctypes.c_void_p))
            return ctypes.cast(vp[idx], ctypes.CFUNCTYPE(restype, ctypes.c_void_p,
                                                          *argtypes))

        fn_fRelease     = vtbl_fn(ppF.value, 2, ctypes.c_ulong)
        fn_EnumAdapters = vtbl_fn(ppF.value, 7, ctypes.c_int,
                                  ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
        adapters = []
        for i in range(16):
            ppA = ctypes.c_void_p(0)
            if fn_EnumAdapters(ppF.value, i, ctypes.byref(ppA)) != 0:
                break
            fn_aRelease = vtbl_fn(ppA.value, 2, ctypes.c_ulong)
            fn_GetDesc  = vtbl_fn(ppA.value, 8, ctypes.c_int,
                                  ctypes.POINTER(DXGI_ADAPTER_DESC))
            desc = DXGI_ADAPTER_DESC()
            if fn_GetDesc(ppA.value, ctypes.byref(desc)) == 0:
                name = desc.Description
                if "Microsoft Basic" not in name and "WARP" not in name:
                    adapters.append({'index': i, 'name': name,
                                     'vram_mb': desc.DedicatedVideoMemory >> 20})
            fn_aRelease(ppA.value)
        fn_fRelease(ppF.value)
        return adapters
    except Exception:
        return []


# ── Module-level workers (must be top-level for multiprocessing/ProcessPoolExecutor) ──
def _cpu_stress_worker_fn():
    import math
    try:
        import ctypes
        h = ctypes.windll.kernel32.GetCurrentThread()
        ctypes.windll.kernel32.SetThreadPriority(h, 2)  # THREAD_PRIORITY_HIGHEST
    except Exception:
        pass
    x = 1.0
    while True:
        for i in range(500_000):
            x = math.sin(x) * math.cos(x) + math.sqrt(abs(x) + 1.0)
            x = math.log(abs(x) + 1.0) * math.exp(x * 0.0001)

def _gpu_stress_worker_fn(adapter_index=0):
    """GPU stress in a separate process — crashes here don't affect the main app."""
    import os as _os_w, tempfile as _tmp
    _log_path = _os_w.path.join(_tmp.gettempdir(), "ZFInfo64_gpu_stress.log")
    def _log(msg):
        try:
            with open(_log_path, "a", encoding="utf-8") as _f:
                import time as _tt
                _f.write(f"[{_tt.strftime('%H:%M:%S')}] adapter={adapter_index} {msg}\n")
        except Exception: pass

    _log("worker started")

    # ── Try D3D11 compute shader on selected adapter (best approach) ──────────
    try:
        import ctypes, time as _t

        import os as _os_d3d
        _sys32 = _os_d3d.path.join(_os_d3d.environ.get("SystemRoot", r"C:\Windows"), "System32")
        _log(f"sys32={_sys32}")
        d3d11 = ctypes.WinDLL("d3d11")
        dxgi  = ctypes.WinDLL("dxgi")
        _d3dc_path = _os_d3d.path.join(_sys32, "d3dcompiler_47.dll")
        _log(f"loading {_d3dc_path}")
        d3dc  = ctypes.WinDLL(_d3dc_path)
        _log("DLLs loaded OK")

        class DXGI_ADAPTER_DESC(ctypes.Structure):
            _fields_ = [
                ("Description",           ctypes.c_wchar * 128),
                ("VendorId",              ctypes.c_uint),
                ("DeviceId",              ctypes.c_uint),
                ("SubSysId",              ctypes.c_uint),
                ("Revision",              ctypes.c_uint),
                ("DedicatedVideoMemory",  ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory",    ctypes.c_size_t),
                ("AdapterLuid",           ctypes.c_int64),
            ]

        def vtbl_fn(obj, idx, restype, *argtypes):
            vp = ctypes.cast(
                ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value,
                ctypes.POINTER(ctypes.c_void_p))
            return ctypes.cast(vp[idx],
                               ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *argtypes))

        # Get DXGI adapter at adapter_index
        iid = (ctypes.c_byte * 16)(
            0xf4,0x94,0x71,0x7b, 0x14,0x35, 0x46,0x4d,
            0x97,0x22,0xd1,0x0b,0x85,0x12,0xf8,0x63)
        dxgi.CreateDXGIFactory.restype  = ctypes.c_int
        dxgi.CreateDXGIFactory.argtypes = [ctypes.c_void_p,
                                            ctypes.POINTER(ctypes.c_void_p)]
        ppF = ctypes.c_void_p(0)
        hr_fac = dxgi.CreateDXGIFactory(iid, ctypes.byref(ppF))
        if hr_fac != 0 or not ppF.value:
            raise RuntimeError(f"CreateDXGIFactory failed hr={hr_fac:#010x}")
        _log("factory OK")

        fn_fRel  = vtbl_fn(ppF.value, 2, ctypes.c_ulong)
        fn_Enum  = vtbl_fn(ppF.value, 7, ctypes.c_int,
                           ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))

        ppA = ctypes.c_void_p(0)
        hr  = fn_Enum(ppF.value, adapter_index, ctypes.byref(ppA))
        fn_fRel(ppF.value)
        if hr != 0 or not ppA.value:
            raise RuntimeError(f"EnumAdapters({adapter_index}) failed hr={hr:#010x}")
        _log(f"adapter[{adapter_index}] OK")

        fn_aRel = vtbl_fn(ppA.value, 2, ctypes.c_ulong)

        # Create D3D11 device on this adapter
        d3d11.D3D11CreateDevice.restype  = ctypes.c_int
        d3d11.D3D11CreateDevice.argtypes = [
            ctypes.c_void_p,   # pAdapter
            ctypes.c_uint,     # DriverType (0=UNKNOWN when adapter given)
            ctypes.c_void_p,   # Software
            ctypes.c_uint,     # Flags
            ctypes.c_void_p,   # pFeatureLevels
            ctypes.c_uint,     # FeatureLevels count
            ctypes.c_uint,     # SDKVersion
            ctypes.POINTER(ctypes.c_void_p),  # ppDevice
            ctypes.c_void_p,   # pFeatureLevel output
            ctypes.POINTER(ctypes.c_void_p),  # ppImmediateContext
        ]
        ppDev = ctypes.c_void_p(0)
        ppCtx = ctypes.c_void_p(0)
        hr = d3d11.D3D11CreateDevice(
            ppA.value, 0, None, 0, None, 0, 7,   # SDK=7
            ctypes.byref(ppDev), None, ctypes.byref(ppCtx))
        fn_aRel(ppA.value)
        if hr != 0 or not ppDev.value:
            raise RuntimeError(f"D3D11CreateDevice failed hr={hr:#010x}")
        _log("D3D11 device OK")

        # Compile compute shader (cs_5_0) — 1024 heavy trig ops per thread
        HLSL = (
            b"[numthreads(256,1,1)]\n"
            b"void CSMain(uint3 id : SV_DispatchThreadID) {\n"
            b"    float v = (float)id.x / 65536.0f + (float)id.y * 0.0001f;\n"
            b"    for (int i = 0; i < 1024; i++) {\n"
            b"        v = sin(v * 6.283185f) + cos(v * 3.141592f);\n"
            b"        v = sqrt(abs(v) + 1.0f) * 0.9999f;\n"
            b"    }\n"
            b"    if (v > 1e10f) { v = 0; }\n"
            b"}\n"
        )
        ppBlob = ctypes.c_void_p(0)
        ppErr  = ctypes.c_void_p(0)
        d3dc.D3DCompile.restype  = ctypes.c_int
        d3dc.D3DCompile.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.c_uint, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
        hr = d3dc.D3DCompile(HLSL, len(HLSL), None, None, None,
                             b"CSMain", b"cs_5_0", 0, 0,
                             ctypes.byref(ppBlob), ctypes.byref(ppErr))
        if hr != 0 or not ppBlob.value:
            raise RuntimeError(f"D3DCompile failed hr={hr:#010x}")
        _log("shader compiled OK")

        fn_bPtr  = vtbl_fn(ppBlob.value, 3, ctypes.c_void_p)
        fn_bSize = vtbl_fn(ppBlob.value, 4, ctypes.c_size_t)
        fn_bRel  = vtbl_fn(ppBlob.value, 2, ctypes.c_ulong)
        bytecode = ctypes.string_at(fn_bPtr(ppBlob.value),
                                    fn_bSize(ppBlob.value))
        fn_bRel(ppBlob.value)

        # Create compute shader
        fn_CreateCS = vtbl_fn(ppDev.value, 18, ctypes.c_int,  # ID3D11Device::CreateComputeShader = vtbl[18]
                               ctypes.c_void_p, ctypes.c_size_t,
                               ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        ppCS  = ctypes.c_void_p(0)
        bc    = ctypes.create_string_buffer(bytecode)
        hr    = fn_CreateCS(ppDev.value, bc, len(bytecode), None, ctypes.byref(ppCS))
        if hr != 0 or not ppCS.value:
            raise RuntimeError(f"CreateComputeShader failed hr={hr:#010x}")
        _log("compute shader created OK")

        fn_csRel = vtbl_fn(ppCS.value, 2, ctypes.c_ulong)

        # ID3D11DeviceContext vtable (IUnknown[0-2] + ID3D11DeviceChild[3-6] + ctx methods):
        # vtbl[41] = Dispatch
        # vtbl[69] = CSSetShader
        fn_Dispatch    = vtbl_fn(ppCtx.value, 41, None,
                                  ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
        fn_CSSetShader = vtbl_fn(ppCtx.value, 69, None,
                                  ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)
        fn_ctxRel      = vtbl_fn(ppCtx.value, 2, ctypes.c_ulong)
        fn_devRel      = vtbl_fn(ppDev.value, 2, ctypes.c_ulong)

        fn_CSSetShader(ppCtx.value, ppCS.value, None, 0)
        _log("D3D11 dispatch loop starting")

        # Dispatch loop — 512×512×1 = 262 144 groups × 256 threads × 1024 ops
        while True:
            fn_Dispatch(ppCtx.value, 512, 512, 1)
            _t.sleep(0.001)

        fn_csRel(ppCS.value)
        fn_ctxRel(ppCtx.value)
        fn_devRel(ppDev.value)
        return
    except Exception as _e:
        _log(f"D3D11 failed: {_e}")

    # ── D3D9 fallback (supports adapter selection, no shader compiler needed) ──
    _log("trying D3D9 fallback")
    try:
        import ctypes, ctypes.wintypes as wt, time as _t

        def _vtbl9(obj, idx, restype, *argtypes):
            vp = ctypes.cast(
                ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value,
                ctypes.POINTER(ctypes.c_void_p))
            return ctypes.cast(vp[idx],
                               ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *argtypes))

        d9dll = ctypes.WinDLL("d3d9")
        d9dll.Direct3DCreate9.restype  = ctypes.c_void_p
        d9dll.Direct3DCreate9.argtypes = [ctypes.c_uint]
        pD3D = d9dll.Direct3DCreate9(32)  # D3D_SDK_VERSION = 32
        if not pD3D:
            raise RuntimeError("Direct3DCreate9 failed")

        fn_d3d_rel = _vtbl9(pD3D, 2, ctypes.c_ulong)

        k32_d9  = ctypes.windll.kernel32
        user_d9 = ctypes.windll.user32
        WNDPROC9 = ctypes.WINFUNCTYPE(ctypes.c_longlong, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
        _proc9 = WNDPROC9(lambda h, m, w, l: user_d9.DefWindowProcW(h, m, w, l))

        class _WNDCLS9(ctypes.Structure):
            _fields_ = [
                ("style", wt.UINT), ("lpfnWndProc", WNDPROC9),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
            ]

        hinst9 = k32_d9.GetModuleHandleW(None)
        cls9   = "ZFD3D9Stress"
        wc9 = _WNDCLS9(); wc9.lpfnWndProc = _proc9
        wc9.hInstance = hinst9; wc9.lpszClassName = cls9
        user_d9.RegisterClassW(ctypes.byref(wc9))
        hwnd9 = user_d9.CreateWindowExW(0, cls9, "ZF D3D9",
                                         0, 0, 0, 1, 1, None, None, hinst9, None)
        if not hwnd9:
            fn_d3d_rel(pD3D)
            raise RuntimeError("CreateWindow for D3D9 failed")

        class _D3DPP(ctypes.Structure):
            _fields_ = [
                ("BackBufferWidth",            ctypes.c_uint),
                ("BackBufferHeight",           ctypes.c_uint),
                ("BackBufferFormat",           ctypes.c_uint),   # D3DFMT_X8R8G8B8=22
                ("BackBufferCount",            ctypes.c_uint),
                ("MultiSampleType",            ctypes.c_uint),
                ("MultiSampleQuality",         ctypes.c_ulong),
                ("SwapEffect",                 ctypes.c_uint),   # D3DSWAPEFFECT_DISCARD=1
                ("hDeviceWindow",              wt.HWND),
                ("Windowed",                   ctypes.c_int),
                ("EnableAutoDepthStencil",     ctypes.c_int),
                ("AutoDepthStencilFormat",     ctypes.c_uint),
                ("Flags",                      ctypes.c_ulong),
                ("FullScreen_RefreshRateInHz", ctypes.c_uint),
                ("PresentationInterval",       ctypes.c_uint),
            ]

        pp9 = _D3DPP()
        pp9.BackBufferFormat     = 22   # D3DFMT_X8R8G8B8
        pp9.BackBufferCount      = 1
        pp9.SwapEffect           = 1    # D3DSWAPEFFECT_DISCARD
        pp9.hDeviceWindow        = hwnd9
        pp9.Windowed             = 1
        pp9.PresentationInterval = 0    # D3DPRESENT_INTERVAL_IMMEDIATE

        # IDirect3D9::CreateDevice = vtbl[16]
        fn_CreateDev9 = _vtbl9(pD3D, 16, ctypes.c_int,
                                ctypes.c_uint, ctypes.c_uint, wt.HWND,
                                ctypes.c_ulong, ctypes.c_void_p,
                                ctypes.POINTER(ctypes.c_void_p))
        ppDev9 = ctypes.c_void_p(0)
        hr = fn_CreateDev9(pD3D, adapter_index, 1, hwnd9,  # D3DDEVTYPE_HAL=1
                            0x40,  # D3DCREATE_HARDWARE_VERTEXPROCESSING
                            ctypes.byref(pp9), ctypes.byref(ppDev9))
        if hr != 0 or not ppDev9.value:
            # retry with software VP
            pp9b = _D3DPP(); ctypes.memmove(ctypes.byref(pp9b), ctypes.byref(pp9), ctypes.sizeof(_D3DPP))
            hr = fn_CreateDev9(pD3D, adapter_index, 1, hwnd9,
                                0x20,  # D3DCREATE_SOFTWARE_VERTEXPROCESSING
                                ctypes.byref(pp9b), ctypes.byref(ppDev9))
        fn_d3d_rel(pD3D)
        if hr != 0 or not ppDev9.value:
            raise RuntimeError(f"D3D9 CreateDevice failed hr={hr:#010x}")

        fn_dev9_rel = _vtbl9(ppDev9.value, 2, ctypes.c_ulong)

        # IDirect3DDevice9::CreateRenderTarget = vtbl[28]
        fn_CreateRT = _vtbl9(ppDev9.value, 28, ctypes.c_int,
                              ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                              ctypes.c_uint, ctypes.c_ulong, ctypes.c_int,
                              ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
        ppS0 = ctypes.c_void_p(0)
        ppS1 = ctypes.c_void_p(0)
        FW9, FH9 = 1920, 1080
        r0 = fn_CreateRT(ppDev9.value, FW9, FH9, 22, 0, 0, 0, ctypes.byref(ppS0), None)
        r1 = fn_CreateRT(ppDev9.value, FW9, FH9, 22, 0, 0, 0, ctypes.byref(ppS1), None)
        if r0 != 0 or r1 != 0 or not ppS0.value or not ppS1.value:
            fn_dev9_rel(ppDev9.value)
            raise RuntimeError("D3D9 CreateRenderTarget failed")

        fn_s0_rel = _vtbl9(ppS0.value, 2, ctypes.c_ulong)
        fn_s1_rel = _vtbl9(ppS1.value, 2, ctypes.c_ulong)

        # IDirect3DDevice9::StretchRect = vtbl[34]
        fn_StretchRect = _vtbl9(ppDev9.value, 34, ctypes.c_int,
                                 ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)

        # IDirect3DDevice9::Present = vtbl[17]
        fn_Pres9 = _vtbl9(ppDev9.value, 17, ctypes.c_int,
                           ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, ctypes.c_void_p)

        surfs9 = [ppS0.value, ppS1.value]
        cur9 = 0
        _log("D3D9 dispatch loop starting")
        while True:
            for _ in range(32):
                fn_StretchRect(ppDev9.value, surfs9[cur9], None,
                               surfs9[1 - cur9], None, 2)  # D3DTEXF_LINEAR
                cur9 ^= 1
            fn_Pres9(ppDev9.value, None, None, None, None)
            _t.sleep(0.001)

        fn_s0_rel(ppS0.value); fn_s1_rel(ppS1.value)
        fn_dev9_rel(ppDev9.value)
        return
    except Exception as _e9:
        _log(f"D3D9 failed: {_e9}")

    # ── OpenGL fallback (creates visible window) ──────────────────────────────
    _log("trying OpenGL fallback (no adapter selection)")
    try:
        import ctypes, ctypes.wintypes as wt, time, math

        gl   = ctypes.WinDLL("opengl32")
        gdi  = ctypes.windll.gdi32
        user = ctypes.windll.user32
        k32  = ctypes.windll.kernel32

        class PIXELFORMATDESCRIPTOR(ctypes.Structure):
            _fields_ = [
                ("nSize", wt.WORD), ("nVersion", wt.WORD), ("dwFlags", wt.DWORD),
                ("iPixelType", ctypes.c_ubyte), ("cColorBits", ctypes.c_ubyte),
                ("cRedBits",   ctypes.c_ubyte), ("cRedShift",   ctypes.c_ubyte),
                ("cGreenBits", ctypes.c_ubyte), ("cGreenShift", ctypes.c_ubyte),
                ("cBlueBits",  ctypes.c_ubyte), ("cBlueShift",  ctypes.c_ubyte),
                ("cAlphaBits", ctypes.c_ubyte), ("cAlphaShift", ctypes.c_ubyte),
                ("cAccumBits", ctypes.c_ubyte), ("cAccumRedBits", ctypes.c_ubyte),
                ("cAccumGreenBits", ctypes.c_ubyte), ("cAccumBlueBits", ctypes.c_ubyte),
                ("cAccumAlphaBits", ctypes.c_ubyte), ("cDepthBits", ctypes.c_ubyte),
                ("cStencilBits", ctypes.c_ubyte), ("cAuxBuffers", ctypes.c_ubyte),
                ("iLayerType", ctypes.c_ubyte), ("bReserved", ctypes.c_ubyte),
                ("dwLayerMask", wt.DWORD), ("dwVisibleMask", wt.DWORD),
                ("dwDamageMask", wt.DWORD),
            ]

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong,
                                     wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
        _proc = WNDPROC(lambda h, m, w, l: user.DefWindowProcW(h, m, w, l))

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
            ]

        hinstance  = k32.GetModuleHandleW(None)
        class_name = "ZFGLStressProc"
        wc = WNDCLASSW()
        wc.lpfnWndProc   = _proc
        wc.hInstance     = hinstance
        wc.lpszClassName = class_name
        user.RegisterClassW(ctypes.byref(wc))

        W, H = 1280, 720
        sw = user.GetSystemMetrics(0)
        sh = user.GetSystemMetrics(1)
        hwnd = user.CreateWindowExW(
            0x00000080, class_name, "ZF-Info64 GPU Stress",
            0x80000000 | 0x10000000,
            (sw - W) // 2, (sh - H) // 2, W, H,
            None, None, hinstance, None)
        if not hwnd:
            return
        user.ShowWindow(hwnd, 1)

        hdc = user.GetDC(hwnd)
        pfd = PIXELFORMATDESCRIPTOR()
        pfd.nSize = ctypes.sizeof(PIXELFORMATDESCRIPTOR)
        pfd.nVersion = 1
        pfd.dwFlags = 4 | 32 | 1
        pfd.cColorBits = 32
        pfd.cDepthBits = 24
        pf = gdi.ChoosePixelFormat(hdc, ctypes.byref(pfd))
        gdi.SetPixelFormat(hdc, pf, ctypes.byref(pfd))

        gl.wglGetProcAddress.restype  = ctypes.c_void_p
        gl.wglGetProcAddress.argtypes = [ctypes.c_char_p]

        def get_proc(name, restype, *argtypes):
            addr = gl.wglGetProcAddress(name)
            if not addr:
                raise RuntimeError(f"{name} not found")
            return ctypes.cast(addr, ctypes.CFUNCTYPE(restype, *argtypes))

        # Bootstrap: GL1 context → upgrade to GL2 via wglCreateContextAttribsARB
        tmp = gl.wglCreateContext(hdc)
        gl.wglMakeCurrent(hdc, tmp)

        try:
            _mkctx = get_proc(b"wglCreateContextAttribsARB",
                               wt.HANDLE, wt.HDC, wt.HANDLE,
                               ctypes.POINTER(ctypes.c_int))
            attribs = (ctypes.c_int * 5)(0x2091, 2, 0x2092, 0, 0)
            hglrc = _mkctx(hdc, None, attribs)
            if not hglrc:
                raise RuntimeError("GL2 context creation returned NULL")
            gl.wglMakeCurrent(None, None)
            gl.wglDeleteContext(tmp)
            gl.wglMakeCurrent(hdc, hglrc)
        except Exception:
            hglrc = tmp  # stay on GL1; shader compilation will fail below → legacy fallback

        try:
            get_proc(b"wglSwapIntervalEXT", ctypes.c_int, ctypes.c_int)(0)
        except Exception:
            pass

        # Try to load GL2 functions and compile shaders
        use_shaders = False
        try:
            _ui = ctypes.c_uint;  _i  = ctypes.c_int;    _f  = ctypes.c_float
            _vp = ctypes.c_void_p; _cp = ctypes.c_char_p
            _pi = ctypes.POINTER(ctypes.c_int)
            _pu = ctypes.POINTER(ctypes.c_uint)

            glCreateShader            = get_proc(b"glCreateShader",            _ui,  _ui)
            glShaderSource            = get_proc(b"glShaderSource",            None, _ui, _i,
                                                 ctypes.POINTER(_cp), _pi)
            glCompileShader           = get_proc(b"glCompileShader",           None, _ui)
            glGetShaderiv             = get_proc(b"glGetShaderiv",             None, _ui, _ui, _pi)
            glCreateProgram           = get_proc(b"glCreateProgram",           _ui)
            glAttachShader            = get_proc(b"glAttachShader",            None, _ui, _ui)
            glLinkProgram             = get_proc(b"glLinkProgram",             None, _ui)
            glGetProgramiv            = get_proc(b"glGetProgramiv",            None, _ui, _ui, _pi)
            glUseProgram              = get_proc(b"glUseProgram",              None, _ui)
            glGetAttribLocation       = get_proc(b"glGetAttribLocation",       _i,   _ui, _cp)
            glGetUniformLocation      = get_proc(b"glGetUniformLocation",      _i,   _ui, _cp)
            glEnableVertexAttribArray = get_proc(b"glEnableVertexAttribArray", None, _ui)
            glVertexAttribPointer     = get_proc(b"glVertexAttribPointer",     None, _ui, _i,
                                                 _ui, ctypes.c_ubyte, _i, _vp)
            glUniform1f               = get_proc(b"glUniform1f",               None, _i, _f)
            glUniform1i               = get_proc(b"glUniform1i",               None, _i, _i)
            glActiveTexture           = get_proc(b"glActiveTexture",           None, _ui)
            glGenFramebuffers         = get_proc(b"glGenFramebuffers",         None, _i, _pu)
            glBindFramebuffer         = get_proc(b"glBindFramebuffer",         None, _ui, _ui)
            glFramebufferTexture2D    = get_proc(b"glFramebufferTexture2D",    None, _ui, _ui,
                                                 _ui, _ui, _i)
            glCheckFramebufferStatus  = get_proc(b"glCheckFramebufferStatus",  _ui,  _ui)
            glDeleteShader            = get_proc(b"glDeleteShader",            None, _ui)
            glDeleteProgram           = get_proc(b"glDeleteProgram",           None, _ui)

            gl.glGenTextures.argtypes   = [_i, _pu]
            gl.glBindTexture.argtypes   = [_ui, _ui]
            gl.glTexImage2D.argtypes    = [_ui, _i, _i, _i, _i, _i, _ui, _ui, _vp]
            gl.glTexParameteri.argtypes = [_ui, _ui, _i]
            gl.glViewport.argtypes      = [_i, _i, _i, _i]
            gl.glDrawArrays.argtypes    = [_ui, _i, _i]

            VERT = b"""
attribute vec2 aPos;
varying vec2 vUV;
void main() {
    vUV = aPos * 0.5 + 0.5;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
"""
            STRESS_FRAG = b"""
varying vec2 vUV;
uniform float uTime;
uniform sampler2D uPrev;
void main() {
    vec4 seed = texture2D(uPrev, vUV);
    float v = seed.r * 2.0 - 1.0;
    float w = seed.g * 2.0 - 1.0;
    float s = seed.b * 2.0 - 1.0;
    float q = seed.a * 2.0 - 1.0;
    for (int i = 0; i < 80; i++) {
        float fi = float(i) * 0.09;
        v += sin(vUV.x*19.0 + uTime*1.1 + fi) * cos(vUV.y*17.0 - uTime*1.3 + fi);
        w += cos(sqrt((vUV.x-0.5)*(vUV.x-0.5)+(vUV.y-0.5)*(vUV.y-0.5))*25.0
                 - uTime*2.0 + fi*0.5);
        s += sin(vUV.x*vUV.y*13.0 + uTime*0.8 + fi)
           + cos(vUV.x*7.0 - vUV.y*11.0 + uTime*1.5 + fi);
        q += sin(v*0.3 + w*0.2 - s*0.1 + uTime*0.6 + fi);
    }
    gl_FragColor = vec4(fract(abs(v)*0.1+0.5), fract(abs(w)*0.1+0.5),
                        fract(abs(s)*0.1+0.5), fract(abs(q)*0.1+0.5));
}
"""
            BLIT_FRAG = b"""
varying vec2 vUV;
uniform sampler2D uTex;
void main() { gl_FragColor = texture2D(uTex, vUV); }
"""

            def compile_shader(kind, src):
                sh  = glCreateShader(kind)
                arr = (ctypes.c_char_p * 1)(src)
                glShaderSource(sh, 1, arr, None)
                glCompileShader(sh)
                st = ctypes.c_int(0)
                glGetShaderiv(sh, 0x8B81, ctypes.byref(st))
                if not st.value:
                    glDeleteShader(sh); return 0
                return sh

            def build_program(vs, fs):
                v = compile_shader(0x8B31, vs)
                f = compile_shader(0x8B30, fs)
                if not v or not f:
                    if v: glDeleteShader(v)
                    if f: glDeleteShader(f)
                    return 0
                p = glCreateProgram()
                glAttachShader(p, v); glAttachShader(p, f)
                glLinkProgram(p)
                glDeleteShader(v); glDeleteShader(f)
                st = ctypes.c_int(0)
                glGetProgramiv(p, 0x8B82, ctypes.byref(st))
                if not st.value:
                    glDeleteProgram(p); return 0
                return p

            stress_prog = build_program(VERT, STRESS_FRAG)
            blit_prog   = build_program(VERT, BLIT_FRAG)

            if stress_prog and blit_prog:
                s_pos  = glGetAttribLocation(stress_prog,  b"aPos")
                s_time = glGetUniformLocation(stress_prog, b"uTime")
                s_prev = glGetUniformLocation(stress_prog, b"uPrev")
                b_pos  = glGetAttribLocation(blit_prog,    b"aPos")
                b_tex  = glGetUniformLocation(blit_prog,   b"uTex")

                FBO_W, FBO_H = 1920, 1080
                GL_TEXTURE_2D = 0x0DE1; GL_RGBA = 0x1908; GL_UNSIGNED_BYTE = 0x1401
                GL_LINEAR = 0x2601; GL_TEXTURE_MIN_FILTER = 0x2801
                GL_TEXTURE_MAG_FILTER = 0x2800; GL_TEXTURE_WRAP_S = 0x2802
                GL_TEXTURE_WRAP_T = 0x2803; GL_CLAMP_TO_EDGE = 0x812F
                GL_FRAMEBUFFER = 0x8D40; GL_COLOR_ATTACHMENT0 = 0x8CE0
                GL_FRAMEBUFFER_COMPLETE = 0x8CD5; GL_TEXTURE0 = 0x84C0
                GL_FLOAT = 0x1406; GL_TRIANGLES = 0x0004

                tex_ids = (ctypes.c_uint * 2)(0, 0)
                fbo_ids = (ctypes.c_uint * 2)(0, 0)
                gl.glGenTextures(2, tex_ids)
                glGenFramebuffers(2, fbo_ids)

                fbo_ok = True
                for i in range(2):
                    gl.glBindTexture(GL_TEXTURE_2D, tex_ids[i])
                    gl.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, FBO_W, FBO_H, 0,
                                    GL_RGBA, GL_UNSIGNED_BYTE, None)
                    gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                    gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                    gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                    gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                    glBindFramebuffer(GL_FRAMEBUFFER, fbo_ids[i])
                    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                                           GL_TEXTURE_2D, tex_ids[i], 0)
                    if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                        fbo_ok = False; break

                glBindFramebuffer(GL_FRAMEBUFFER, 0)
                gl.glBindTexture(GL_TEXTURE_2D, 0)

                if fbo_ok:
                    use_shaders = True

        except Exception:
            pass  # fall through to legacy render loop

        quad    = (ctypes.c_float * 12)(
            -1.0, -1.0,  1.0, -1.0,  -1.0,  1.0,
             1.0, -1.0,  1.0,  1.0,  -1.0,  1.0)
        quad_vp = ctypes.cast(quad, ctypes.c_void_p)

        if use_shaders:
            # ── GLSL shader path: 60 FBO passes × 1920×1080 × 80 trig iters ──
            PASSES = 60
            t0 = time.time()
            while True:
                t = ctypes.c_float(time.time() - t0)
                gl.glViewport(0, 0, FBO_W, FBO_H)
                glUseProgram(stress_prog)
                glUniform1f(s_time, t)
                glEnableVertexAttribArray(s_pos)
                glVertexAttribPointer(s_pos, 2, GL_FLOAT, 0, 0, quad_vp)
                cur = 0
                for _ in range(PASSES):
                    glBindFramebuffer(GL_FRAMEBUFFER, fbo_ids[cur])
                    glActiveTexture(GL_TEXTURE0)
                    gl.glBindTexture(GL_TEXTURE_2D, tex_ids[1 - cur])
                    glUniform1i(s_prev, 0)
                    gl.glDrawArrays(GL_TRIANGLES, 0, 6)
                    cur ^= 1
                glBindFramebuffer(GL_FRAMEBUFFER, 0)
                gl.glViewport(0, 0, W, H)
                glUseProgram(blit_prog)
                glActiveTexture(GL_TEXTURE0)
                gl.glBindTexture(GL_TEXTURE_2D, tex_ids[1])
                glUniform1i(b_tex, 0)
                glEnableVertexAttribArray(b_pos)
                glVertexAttribPointer(b_pos, 2, GL_FLOAT, 0, 0, quad_vp)
                gl.glDrawArrays(GL_TRIANGLES, 0, 6)
                gdi.SwapBuffers(hdc)
        else:
            # ── Legacy fallback: fixed-function fill-rate flood ───────────────
            gl.glEnableClientState.argtypes = [ctypes.c_uint]
            gl.glVertexPointer.argtypes     = [ctypes.c_int, ctypes.c_uint,
                                               ctypes.c_int, ctypes.c_void_p]
            gl.glDrawArrays.argtypes        = [ctypes.c_uint, ctypes.c_int, ctypes.c_int]
            gl.glClear.argtypes             = [ctypes.c_uint]
            gl.glColor4f.argtypes           = [ctypes.c_float] * 4
            gl.glViewport.argtypes          = [ctypes.c_int] * 4
            gl.glEnable.argtypes            = [ctypes.c_uint]
            gl.glBlendFunc.argtypes         = [ctypes.c_uint, ctypes.c_uint]
            gl.glViewport(0, 0, W, H)
            gl.glEnableClientState(0x8074)
            gl.glVertexPointer(2, 0x1406, 0, quad_vp)
            gl.glEnable(0x0BE2)
            gl.glBlendFunc(0x0302, 0x0303)
            t = 0.0
            while True:
                gl.glClear(0x00004000)
                gl.glColor4f(abs(math.sin(t)), abs(math.cos(t*1.3)),
                             abs(math.sin(t*0.7)), 0.003)
                for _ in range(5000):
                    gl.glDrawArrays(0x0004, 0, 6)
                gdi.SwapBuffers(hdc)
                t += 0.01

    except Exception:
        pass  # process exits cleanly if anything fails


def _bench_cpu_worker_fn(n_iters):
    """Worker for ProcessPoolExecutor multi-core benchmark."""
    import math
    try:
        import ctypes
        h = ctypes.windll.kernel32.GetCurrentThread()
        ctypes.windll.kernel32.SetThreadPriority(h, 2)
    except Exception:
        pass
    x = 0.0
    for i in range(n_iters):
        x += math.sin(i) * math.cos(i) + math.sqrt(i + 1.0)
    return x

# ── Windows CPU temperature (psutil returns nothing on Windows) ──
_win_temp_cache = [-1.0, 0.0]

def _get_windows_temp():
    now = time.time()
    if now - _win_temp_cache[1] < 5.0 and _win_temp_cache[0] > 0:
        return _win_temp_cache[0]
    try:
        ps_cmd = (
            "try{$t=(Get-WmiObject MSAcpi_ThermalZoneTemperature"
            " -Namespace root/wmi|Select-Object -First 1).CurrentTemperature;"
            " [math]::Round($t/10-273.15,1)}catch{-1}"
        )
        r = subprocess.run(
            [_PS, "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=4,
            creationflags=0x08000000)
        val = float(r.stdout.strip())
        if 0 < val < 150:
            _win_temp_cache[0] = val
            _win_temp_cache[1] = now
            return val
    except Exception:
        pass
    return -1.0

# ── Scrollable Frame helper ───────────────────────────────────────────────────
class ScrollFrame(tk.Frame):
    """A Frame with a built-in vertical scrollbar that works with the mousewheel."""
    def __init__(self, parent, bg=BG, **kw):
        super().__init__(parent, bg=bg, **kw)

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb    = tk.Scrollbar(self, orient="vertical",
                                   command=self.canvas.yview)
        self.inner  = tk.Frame(self.canvas, bg=bg)

        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Bind mousewheel only when the mouse is over this widget
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        self.inner.bind("<Enter>",  self._bind_wheel)
        self.inner.bind("<Leave>",  self._unbind_wheel)

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self._win, width=event.width)

    def _bind_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>",   self._on_wheel)
        self.canvas.bind_all("<Button-4>",     self._on_wheel)
        self.canvas.bind_all("<Button-5>",     self._on_wheel)

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ── Reusable UI building blocks ───────────────────────────────────────────────

def lbl(parent, text="", fg=T1, bg=CARD, size=10, bold=False, mono=False,
        anchor="w", **kw):
    w = "bold" if bold else "normal"
    f = "Courier New" if mono else "Segoe UI"
    return tk.Label(parent, text=text, fg=fg, bg=bg,
                    font=(f, size, w), anchor=anchor, **kw)

def section_header(parent, text, icon="", color=CYAN, bg=BG):
    """Colored section header with divider."""
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", padx=16, pady=(14, 0))
    tk.Label(row, text=f"{icon}  {text}" if icon else text,
             fg=color, bg=bg,
             font=("Segoe UI", 11, "bold")).pack(side="left")
    tk.Frame(parent, height=1, bg=BORDER).pack(fill="x", padx=16, pady=(4, 0))

def card(parent, bg=CARD):
    """Bordered card frame."""
    outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    outer.pack(fill="x", padx=16, pady=4)
    inner = tk.Frame(outer, bg=bg, padx=16, pady=12)
    inner.pack(fill="both", expand=True)
    return inner

def info_row(parent, label, value, bg=CARD, color=T1):
    """One label=value row inside a card."""
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=3)
    tk.Label(row, text=label, fg=T2, bg=bg,
             font=("Segoe UI", 10), anchor="w").pack(side="left")
    tk.Label(row, text=value, fg=color, bg=bg,
             font=("Courier New", 10), anchor="e").pack(side="right")
    tk.Frame(row, height=1, bg=BORDER).place(relx=0, rely=1,
                                              relwidth=1, anchor="sw")

class StatBox(tk.Frame):
    """Small stat tile: title + big value."""
    def __init__(self, parent, title, color=CYAN, **kw):
        super().__init__(parent, bg=ELEV, padx=10, pady=10, **kw)
        tk.Label(self, text=title, fg=T3, bg=ELEV,
                 font=("Segoe UI", 8)).pack()
        self.value_lbl = tk.Label(self, text="—", fg=color, bg=ELEV,
                                  font=("Courier New", 17, "bold"))
        self.value_lbl.pack()

    def set(self, text, color=None):
        self.value_lbl.config(text=text)
        if color:
            self.value_lbl.config(fg=color)

class SmallStatBox(tk.Frame):
    """Smaller stat tile for secondary metrics."""
    def __init__(self, parent, title, color=CYAN, **kw):
        super().__init__(parent, bg=ELEV, padx=10, pady=8, **kw)
        tk.Label(self, text=title, fg=T3, bg=ELEV,
                 font=("Segoe UI", 8)).pack()
        self.value_lbl = tk.Label(self, text="—", fg=color, bg=ELEV,
                                  font=("Courier New", 13, "bold"))
        self.value_lbl.pack()

    def set(self, text, color=None):
        self.value_lbl.config(text=text)
        if color:
            self.value_lbl.config(fg=color)

class ProgressBar(tk.Canvas):
    """Simple colored progress bar."""
    def __init__(self, parent, color=CYAN, height=6, **kw):
        super().__init__(parent, height=height, bg=ELEV,
                         highlightthickness=0, **kw)
        self._color = color
        self._bar   = self.create_rectangle(0, 0, 0, height, fill=color, width=0)
        self.bind("<Configure>", self._redraw)
        self._pct = 0

    def _redraw(self, event=None):
        w = self.winfo_width()
        h = self.winfo_height()
        self.coords(self._bar, 0, 0, int(w * self._pct / 100), h)

    def set_progress(self, pct):
        self._pct = pct
        self._redraw()

def accent_btn(parent, text, command, color=CYAN, **kw):
    return tk.Button(parent, text=text, command=command,
                     bg=color, fg=BG, relief="flat",
                     font=("Segoe UI", 11, "bold"),
                     cursor="hand2", activebackground=color,
                     activeforeground=BG, padx=12, pady=8, **kw)


# ── System Info collector ─────────────────────────────────────────────────────
def collect_sysinfo():
    out = []  # list of (section, label, value, color)

    def S(title): out.append(("__section__", title, "", ""))
    def R(label, value, color=T1): out.append(("row", label, value, color))

    _load_hw_cache()  # one PowerShell call — fills cache for all hw queries below

    S("SISTEM OPERARE")
    R("OS",          platform.system() + " " + platform.release())
    R("Versiune",    platform.version()[:60])
    arch = platform.machine()
    arch_str = f"x64 ({arch})" if arch in ("AMD64", "x86_64") else arch
    R("Arhitectură", arch_str)
    R("Hostname",    platform.node())

    S("PROCESOR (CPU)")
    cpu_name = _get_cpu_name_windows() or platform.processor() or "N/A"
    R("Model", cpu_name[:70])
    if HAS_PSUTIL:
        R("Nuclee fizice",   str(psutil.cpu_count(logical=False)))
        R("Nuclee logice",   str(psutil.cpu_count(logical=True)))
        freq = psutil.cpu_freq()
        if freq:
            R("Frecvență curentă", f"{freq.current:.0f} MHz", CYAN)
            R("Frecvență max",     f"{freq.max:.0f} MHz")
        usage = psutil.cpu_percent(interval=0.3)
        color = RED if usage > 90 else ORANGE if usage > 70 else GREEN
        R("Utilizare", f"{usage:.1f}%", color)

    S("MEMORIE (RAM)")
    ram_modules = _get_ram_modules()
    for i, mod in enumerate(ram_modules):
        R(f"Modul {i}", mod[:65], CYAN)
    if HAS_PSUTIL:
        vm = psutil.virtual_memory()
        pct_c = RED if vm.percent > 90 else ORANGE if vm.percent > 70 else GREEN
        R("Total",      fmt_bytes(vm.total))
        R("Utilizat",   fmt_bytes(vm.used), pct_c)
        R("Disponibil", fmt_bytes(vm.available), GREEN)
        R("Utilizare",  f"{vm.percent:.1f}%", pct_c)
        sw = psutil.swap_memory()
        if sw.total > 0:
            R("Swap total",   fmt_bytes(sw.total))
            R("Swap utilizat",fmt_bytes(sw.used))

    S("PLĂCI VIDEO (GPU)")
    try:
        gpus = _get_gpu_list()
        if gpus:
            for g in gpus:
                vram_str = f"  •  {g['vram_mb']} MB VRAM" if g['vram_mb'] > 0 else ""
                label = "GPU dedicat" if g['vram_mb'] > 512 else "GPU integrat"
                R(label, g['name'][:60] + vram_str, CYAN)
        else:
            R("GPU", "Nedetectat", T2)
    except Exception:
        R("GPU", "Eroare detecție", T2)

    S("STOCARE")
    disk_models = _get_disk_models()
    for i, model in enumerate(disk_models):
        R(f"Disc {i}", model[:60], CYAN)
    if HAS_PSUTIL:
        for part in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(part.mountpoint)
                pc = RED if u.percent > 90 else ORANGE if u.percent > 75 else T1
                R(part.device, f"{fmt_bytes(u.used)} / {fmt_bytes(u.total)}  ({u.percent:.0f}%)", pc)
            except Exception:
                pass

    S("REȚEA")
    active_nics = _get_active_nics()
    for nic in active_nics[:4]:
        R("Adaptor activ", nic[:55], CYAN)
    if HAS_PSUTIL:
        try:
            nio = psutil.net_io_counters()
            R("Bytes trimiși",  fmt_bytes(nio.bytes_sent))
            R("Bytes primiți",  fmt_bytes(nio.bytes_recv))
            for name, addrs in list(psutil.net_if_addrs().items())[:6]:
                for a in addrs:
                    if a.family == 2:
                        R(f"IP  [{name[:12]}]", a.address, CYAN)
                        break
        except Exception:
            pass

    S("BATERIE")
    if HAS_PSUTIL:
        try:
            bat = psutil.sensors_battery()
            if bat:
                pc = bat.percent
                bc = RED if pc < 20 else ORANGE if pc < 40 else GREEN
                R("Nivel",   f"{pc:.0f}%", bc)
                R("Status",  "La priză" if bat.power_plugged else "Pe baterie",
                  GREEN if bat.power_plugged else ORANGE)
                if bat.secsleft and bat.secsleft > 0:
                    h, r = divmod(int(bat.secsleft), 3600)
                    R("Timp rămas", f"{h}h {r//60}m")
                cycle = _get_battery_cycle_count()
                if cycle:
                    R("Cicluri încărcare", cycle, ORANGE)
            else:
                R("Baterie", "Nedetectată / Desktop", T2)
        except Exception:
            R("Baterie", "Indisponibilă", T3)

    if HAS_PSUTIL:
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                S("TEMPERATURI")
                for name, entries in temps.items():
                    for e in entries[:2]:
                        label = (e.label or name)[:24]
                        tc = RED if e.current > 80 else ORANGE if e.current > 60 else GREEN
                        R(label, f"{e.current:.1f}°C", tc)
        except Exception:
            pass

    return out


# ── Benchmark functions ───────────────────────────────────────────────────────
# Reference times calibrated for a mid-range desktop (AMD Ryzen 5 / Intel i5 class)
REF = dict(single=3500.0, integer=2200.0, multi=900.0, memory=800.0, storage=1800.0)
REF_GPU_FPS = 12.0  # reference FPS for PIL render benchmark

def _score(key, ms):
    return clamp(int((REF[key] / max(ms, 1)) * 5000), 1, MAX_SCORE)

def bench_single(prog):
    prog(5); iters = 60_000_000; r = 0.0
    t = time.perf_counter()
    step = iters // 19
    for i in range(iters):
        r += math.sin(i) * math.cos(i) + math.sqrt(i + 1.0)
        if i % step == 0: prog(int(5 + i/iters*90))
    ms = (time.perf_counter()-t)*1000; prog(100)
    return _score("single", ms), f"{iters:,} iterații • {ms:.0f} ms"

def bench_integer(prog):
    prog(5); iters = 80_000_000; acc = 0
    t = time.perf_counter(); step = iters // 19
    for i in range(iters):
        acc = (acc * 6364136223846793005 + 1442695040888963407) ^ (i << 3)
        acc = ((acc << 13) | (acc >> 51)) & 0xFFFFFFFFFFFFFFFF
        if i % step == 0: prog(int(5 + i/iters*90))
    ms = (time.perf_counter()-t)*1000; prog(100)
    mops = iters/(ms/1000)/1_000_000
    return _score("integer", ms), f"{mops:.0f} Mops/s • {ms:.0f} ms"

def bench_multi(prog):
    prog(5)
    cores = os.cpu_count() or 2
    ipc = 60_000_000 // cores
    t = time.perf_counter()
    # ProcessPoolExecutor bypasses the GIL — true parallel execution on all cores
    with concurrent.futures.ProcessPoolExecutor(max_workers=cores) as ex:
        futs = [ex.submit(_bench_cpu_worker_fn, ipc) for _ in range(cores)]
        done = 0
        for f in concurrent.futures.as_completed(futs):
            done += 1
            prog(int(5 + done / cores * 90))
    ms = (time.perf_counter()-t)*1000; prog(100)
    return _score("multi", ms), f"{cores} nuclee • {ms:.0f} ms"

def bench_memory(prog):
    prog(5)
    if HAS_PSUTIL:
        avail = psutil.virtual_memory().available
        target = max(256 << 20, min(int(avail * 0.30), 1 << 30))  # 30% of free RAM, max 1 GB
    else:
        target = 512 << 20
    prog(8)
    try:
        buf = bytearray(target)
    except MemoryError:
        target = 256 << 20
        buf = bytearray(target)
    mv = memoryview(buf)
    pattern = bytes([0xAB, 0xCD, 0xEF, 0x01] * 16384)  # 64 KB pattern
    t = time.perf_counter()
    # Sequential write via C-level memcpy (fast)
    chunk = len(pattern)
    for off in range(0, target, chunk):
        sz = min(chunk, target - off)
        mv[off:off+sz] = pattern[:sz]
        prog(8 + int(off/target * 44))
    # Sequential read — stride every 64 bytes (cache line)
    chk = sum(mv[::64])
    prog(90)
    ms = (time.perf_counter()-t)*1000
    del buf; prog(100)
    bw = target * 2 / (ms/1000) / (1<<20)
    return _score("memory", ms), f"{target>>20} MB • {bw:.0f} MB/s • {ms:.0f} ms"

def bench_gpu(prog):
    prog(5)
    if not HAS_PIL:
        return 0, "PIL nedisponibil — test sărit"
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 1920, 1080
    frames = 0; duration = 5.0
    t_start = time.perf_counter()
    prog(10)
    while time.perf_counter() - t_start < duration:
        el = time.perf_counter() - t_start
        img = Image.new("RGB", (W, H), (8, 8, 18))
        draw = ImageDraw.Draw(img)
        for i in range(80):
            a = el * 1.5 + i * (math.pi * 2 / 80)
            x = int(W/2 + W/3 * math.cos(a))
            y = int(H/2 + H/3 * math.sin(a * 1.3))
            r = int(22 + 12 * math.sin(el * 2 + i))
            col = (
                int(128 + 127 * math.cos(el + i * 0.3)),
                int(128 + 127 * math.sin(el * 2 + i * 0.5)),
                int(200 - 100 * math.cos(el + i)),
            )
            draw.ellipse([x-r, y-r, x+r, y+r], fill=col)
        img = img.filter(ImageFilter.GaussianBlur(radius=3))
        frames += 1
        prog(min(10 + int(el/duration * 85), 95))
    ms = (time.perf_counter()-t_start)*1000; prog(100)
    fps = frames / (ms/1000)
    score = clamp(int(fps / REF_GPU_FPS * 5000), 1, MAX_SCORE)
    return score, f"{fps:.1f} FPS • {frames} frame-uri • PIL Render"

def bench_storage(prog):
    prog(5); block=4096; blocks=4096; buf=bytes(range(256))*(block//256)
    tmp = Path(tempfile.gettempdir())/"zfinfo_bench.tmp"
    t = time.perf_counter()
    try:
        with open(tmp,"wb") as f:
            for i in range(blocks):
                f.write(buf)
                if i%(blocks//10)==0: prog(int(5+i/blocks*45))
            f.flush(); os.fsync(f.fileno())
    except Exception: pass
    prog(50)
    try:
        rb = bytearray(block)
        with open(tmp,"rb") as f:
            for i in range(blocks):
                f.readinto(rb)
                if i%(blocks//10)==0: prog(int(50+i/blocks*45))
    except Exception: pass
    ms = (time.perf_counter()-t)*1000
    try: tmp.unlink()
    except Exception: pass
    prog(100)
    tp = block*blocks*2/(ms/1000)/(1<<20)
    return _score("storage", ms), f"{tp:.0f} MB/s • {ms:.0f} ms"


# ── Stress Engine ─────────────────────────────────────────────────────────────
class StressEngine:
    def __init__(self):
        self._running = threading.Event()
        self._threads = []
        self._cpu_procs = []
        self._iters = 0
        self._chunks = []
        self._lock = threading.Lock()

    @property
    def running(self): return self._running.is_set()

    def start(self, stype, n_threads, duration, on_stats, on_done, gpu_adapter_idx=0):
        if self._running.is_set(): return
        self._running.set(); self._iters = 0; self._chunks.clear()

        if stype == "CPU":
            cpu_count, mem_count, gpu_count = n_threads, 0, 0
        elif stype == "MEM":
            cpu_count, mem_count, gpu_count = 0, n_threads, 0
        elif stype == "GPU":
            cpu_count, mem_count, gpu_count = 0, 0, n_threads
        elif stype == "MIXED":
            cpu_count = n_threads // 2
            mem_count = n_threads - cpu_count
            gpu_count = 0
        else:  # MIXED_ALL
            cpu_count = max(1, n_threads // 3)
            gpu_count = max(1, n_threads // 3)
            mem_count = n_threads - cpu_count - gpu_count

        for _ in range(cpu_count):
            p = multiprocessing.Process(target=_cpu_stress_worker_fn, daemon=True)
            p.start()
            self._cpu_procs.append(p)

        for _ in range(mem_count):
            threading.Thread(target=self._mem, daemon=True).start()

        for _ in range(gpu_count):
            p = multiprocessing.Process(target=_gpu_stress_worker_fn,
                                        args=(gpu_adapter_idx,), daemon=True)
            p.start()
            self._cpu_procs.append(p)

        threading.Thread(target=self._monitor,
                         args=(n_threads, duration, on_stats, on_done),
                         daemon=True).start()

    def stop(self):
        self._running.clear()
        for p in self._cpu_procs:
            try: p.terminate()
            except Exception: pass
        self._cpu_procs.clear()
        with self._lock: self._chunks.clear()

    def _cpu(self):
        try:
            import ctypes
            h = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadPriority(h, 2)
        except Exception:
            pass
        x = 1.0
        while self._running.is_set():
            for i in range(500_000):
                x = math.sin(x)*math.cos(x)+math.sqrt(abs(x)+1.0)
                x = math.log(abs(x)+1.0)*math.exp(x*0.0001)
            with self._lock: self._iters += 500_000

    def _mem(self):
        chunk_size = 64 << 20  # 64 MB per chunk
        if HAS_PSUTIL:
            avail_mb = psutil.virtual_memory().available >> 20
            max_chunks = max(4, int(avail_mb * 0.70 / 64))
        else:
            max_chunks = 64  # 4 GB fallback cap
        pattern = bytes([0xAA, 0xBB, 0xCC, 0xDD] * 1024)  # 4 KB pattern
        while self._running.is_set():
            try:
                c = bytearray(chunk_size)
                # Touch every page to ensure physical RAM allocation
                mv = memoryview(c)
                for off in range(0, chunk_size, 4096):
                    mv[off:off+4] = b'\xAA\xBB\xCC\xDD'
                with self._lock:
                    if len(self._chunks) >= max_chunks:
                        self._chunks.pop(0)
                    self._chunks.append(c)
                    self._iters += chunk_size
                time.sleep(0.05)
            except MemoryError:
                with self._lock:
                    if self._chunks:
                        del self._chunks[:max(1, len(self._chunks)//2)]
                time.sleep(1.0)

    def _monitor(self, n_threads, duration, on_stats, on_done):
        t0 = time.time(); prev_i = 0; prev_cpu = self._cpu_times()
        while self._running.is_set():
            time.sleep(1)
            elapsed = int(time.time()-t0)
            cur_cpu = self._cpu_times()
            load    = self._cpu_load(prev_cpu, cur_cpu); prev_cpu = cur_cpu
            with self._lock:
                cur_i = self._iters
                ram   = sum(len(c) for c in self._chunks)//(1<<20)
            ips = cur_i - prev_i; prev_i = cur_i
            on_stats({"elapsed":elapsed,"load":load,"temp":self._temp(),
                       "threads":n_threads,"total":cur_i,"ips":ips,"ram":ram})
            if duration > 0 and elapsed >= duration:
                self._running.clear(); break
        self.stop()
        on_done(f"Finalizat în {int(time.time()-t0)}s • {n_threads} threads")

    def _cpu_times(self):
        if not HAS_PSUTIL: return (0,1)
        t = psutil.cpu_times(); total = sum(t)
        return (t.idle + getattr(t,"iowait",0), total)

    def _cpu_load(self, p, c):
        dt = c[1]-p[1]; di = c[0]-p[0]
        return clamp(int((1-di/max(dt,1))*100), 0, 100)

    def _temp(self):
        if HAS_PSUTIL:
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for k in ("coretemp","k10temp","acpitz","cpu_thermal"):
                        if k in temps: return temps[k][0].current
                    for v in temps.values():
                        if v: return v[0].current
            except Exception:
                pass
        # Windows fallback via WMI thermal zone
        return _get_windows_temp()


# ── Main App ──────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"ZF-Info64 {APP_EDITION}")
        self.configure(bg=BG)
        self.geometry("860x680")
        self.minsize(700, 520)

        # Set window + taskbar icon
        icon_path = _resource_path("zf_icon.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(default=str(icon_path))
            except Exception:
                pass
            try:
                from PIL import Image, ImageTk
                _img = Image.open(str(icon_path))
                self._icon_ref = ImageTk.PhotoImage(_img)
                self.iconphoto(True, self._icon_ref)
            except Exception:
                pass

        self._stress = StressEngine()
        self._bench_running = False

        self._style_ttk()
        self._build()
        self.after(300, lambda: threading.Thread(
            target=self._load_sysinfo, daemon=True).start())

    # ── TTK style ─────────────────────────────────────────────────────────────
    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook",        background=BG2, borderwidth=0, tabmargins=0)
        s.configure("TNotebook.Tab",    background=BG2, foreground=T2,
                    padding=[20, 8], font=("Segoe UI", 10))
        s.map("TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", CYAN)])
        s.configure("Vertical.TScrollbar",
                    background=ELEV, troughcolor=BG2,
                    arrowcolor=T2, borderwidth=0, arrowsize=12)

    # ── Top header ────────────────────────────────────────────────────────────
    def _build(self):
        # Header bar
        hdr = tk.Frame(self, bg=BG2, pady=0)
        hdr.pack(fill="x")

        # Logo
        logo_path = _resource_path("logo ZF-Logo64.png")
        self._logo = None
        if logo_path.exists() and HAS_PIL:
            try:
                img = Image.open(logo_path).convert("RGBA")
                h = 44
                w = int(img.width * h / img.height)
                img = img.resize((w, h), Image.LANCZOS)
                self._logo = ImageTk.PhotoImage(img)
                tk.Label(hdr, image=self._logo, bg=BG2,
                         padx=16, pady=8).pack(side="left")
            except Exception:
                self._logo = None

        if not self._logo:
            tk.Label(hdr, text="ZF-Info64", fg=CYAN, bg=BG2,
                     font=("Courier New", 18, "bold"),
                     padx=20, pady=10).pack(side="left")

        right_hdr = tk.Frame(hdr, bg=BG2)
        right_hdr.pack(side="right", padx=16)
        tk.Label(right_hdr, text="v2.0", fg=T3, bg=BG2,
                 font=("Segoe UI", 9)).pack(anchor="e")
        if not HAS_PSUTIL:
            tk.Label(right_hdr, text="⚠ pip install psutil",
                     fg=YELLOW, bg=BG2, font=("Segoe UI", 8)).pack(anchor="e")

        tk.Frame(self, height=1, bg=BORDER).pack(fill="x")

        # Notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        nb.add(self._tab_system(nb),    text="   💻  Sistem   ")
        if APP_EDITION != "Free":
            nb.add(self._tab_benchmark(nb), text="   ⚡  Benchmark   ")
        nb.add(self._tab_stress(nb),    text="   🔥  Stress Test   ")

    # ── TAB: System ───────────────────────────────────────────────────────────
    def _tab_system(self, nb):
        root = tk.Frame(nb, bg=BG)

        # Top toolbar
        bar = tk.Frame(root, bg=BG, pady=6, padx=16)
        bar.pack(fill="x")

        self._lbl_refresh_time = tk.Label(bar, text="Încărcare...",
                                          fg=T3, bg=BG, font=("Segoe UI", 9))
        self._lbl_refresh_time.pack(side="right")

        def refresh():
            self._lbl_refresh_time.config(text="Se actualizează...")
            threading.Thread(target=self._load_sysinfo, daemon=True).start()

        accent_btn(bar, "↺  Reîmprospătare", refresh,
                   color=ELEV).config(fg=CYAN)

        tk.Frame(root, height=1, bg=BORDER).pack(fill="x", padx=0)

        # Scrollable area
        sf = ScrollFrame(root, bg=BG)
        sf.pack(fill="both", expand=True)
        self._sysinfo_frame = sf.inner

        return root

    def _load_sysinfo(self):
        global _HW_CACHE
        _HW_CACHE = None  # reset so PowerShell re-runs on manual refresh
        data = collect_sysinfo()
        self.after(0, lambda: self._render_sysinfo(data))

    def _render_sysinfo(self, data):
        for w in self._sysinfo_frame.winfo_children():
            w.destroy()

        current_card = None
        for kind, label, value, color in data:
            if kind == "__section__":
                icons = {"SISTEM OPERARE": "🖥", "PROCESOR (CPU)": "⚙",
                         "MEMORIE (RAM)": "📊", "STOCARE": "💾",
                         "REȚEA": "🌐", "BATERIE": "🔋", "TEMPERATURI": "🌡"}
                icon = icons.get(label, "")
                section_header(self._sysinfo_frame, label, icon, bg=BG)
                current_card = card(self._sysinfo_frame)
            elif current_card is not None:
                info_row(current_card, label, value, color=color)

        # spacing at bottom
        tk.Frame(self._sysinfo_frame, bg=BG, height=20).pack()
        self._lbl_refresh_time.config(
            text="Actualizat: " + time.strftime("%H:%M:%S"))

    # ── TAB: Benchmark ────────────────────────────────────────────────────────
    def _tab_benchmark(self, nb):
        root = tk.Frame(nb, bg=BG)
        sf   = ScrollFrame(root, bg=BG)
        sf.pack(fill="both", expand=True)
        p = sf.inner

        # Score hero card
        hero = tk.Frame(p, bg=CARD, pady=20)
        tk.Frame(p, height=1, bg=BORDER).pack(fill="x", padx=16, pady=(16,0))
        hero.pack(fill="x", padx=16, pady=4)
        tk.Frame(p, height=1, bg=BORDER).pack(fill="x", padx=16, pady=(0,4))

        tk.Label(hero, text="SCOR TOTAL", fg=T2, bg=CARD,
                 font=("Segoe UI", 10)).pack()
        self._total_score_lbl = tk.Label(hero, text="—", fg=CYAN, bg=CARD,
                                          font=("Courier New", 52, "bold"))
        self._total_score_lbl.pack()
        self._rating_lbl = tk.Label(hero, text="Apasă RULEAZĂ pentru a începe",
                                     fg=T3, bg=CARD, font=("Segoe UI", 10))
        self._rating_lbl.pack(pady=(0, 12))

        self._btn_bench = accent_btn(hero, "▶   RULEAZĂ TOATE TESTELE",
                                     self._run_benchmarks, color=CYAN)
        self._btn_bench.pack(padx=40, fill="x")

        # Test rows
        TESTS = [
            ("CPU SINGLE-CORE",  "Operații trigonometrice (FP)",           GREEN,  "single"),
            ("CPU INTEGER",      "Operații întregi, XOR, rotații bit",     CYAN,   "integer"),
            ("CPU MULTI-CORE",   "Calcule paralele pe toate nucleele",     ORANGE, "multi"),
            ("MEMORIE",          "Bandwidth RAM: write / read (30% RAM)",  PURPLE, "memory"),
            ("STOCARE I/O",      "Citire + scriere fișier 16 MB",          YELLOW, "storage"),
            ("GPU / RENDER",     "PIL render 1080p: cercuri + blur (5s)",  RED,    "gpu"),
        ]
        self._bench_w = {}
        for title, sub, color, key in TESTS:
            section_header(p, title, color=color, bg=BG)
            c = card(p)

            top_row = tk.Frame(c, bg=CARD)
            top_row.pack(fill="x")
            tk.Label(top_row, text=sub, fg=T2, bg=CARD,
                     font=("Segoe UI", 9)).pack(side="left")
            score_lbl = tk.Label(top_row, text="—", fg=color, bg=CARD,
                                  font=("Courier New", 22, "bold"))
            score_lbl.pack(side="right")

            bar = ProgressBar(c, color=color, height=6)
            bar.pack(fill="x", pady=(8, 4))

            status_lbl = tk.Label(c, text="Pregătit", fg=T3, bg=CARD,
                                   font=("Courier New", 9), anchor="w")
            status_lbl.pack(fill="x")

            self._bench_w[key] = (score_lbl, bar, status_lbl)

        tk.Frame(p, bg=BG, height=20).pack()
        return root

    def _run_benchmarks(self):
        if self._bench_running: return
        self._bench_running = True
        self._btn_bench.config(state="disabled", text="Rulează...")
        self._total_score_lbl.config(text="—")
        self._rating_lbl.config(text="Testele rulează...", fg=T2)
        for sl, bar, stl in self._bench_w.values():
            sl.config(text="—")
            bar.set_progress(0)
            stl.config(text="Pregătit", fg=T3)
        threading.Thread(target=self._bench_thread, daemon=True).start()

    def _bench_thread(self):
        FUNS = [
            ("single",  bench_single,  GREEN),
            ("integer", bench_integer, CYAN),
            ("multi",   bench_multi,   ORANGE),
            ("memory",  bench_memory,  PURPLE),
            ("storage", bench_storage, YELLOW),
            ("gpu",     bench_gpu,     RED),
        ]
        scores = {}
        for key, fn, color in FUNS:
            sl, bar, stl = self._bench_w[key]
            self.after(0, lambda stl=stl, c=color: stl.config(text="Rulează...", fg=c))
            def prog(pct, bar=bar): self.after(0, lambda: bar.set_progress(pct))
            score, details = fn(prog)
            scores[key] = score
            self.after(0, lambda sl=sl, s=score, c=color: sl.config(text=str(s), fg=c))
            self.after(0, lambda stl=stl, d=details: stl.config(text=d, fg=T2))

        avg = sum(scores.values()) // len(scores)
        rating = ("Flagship — performanță excelentă"   if avg >= 8000 else
                  "High-end — performanță foarte bună" if avg >= 6000 else
                  "Mid-range — performanță bună"        if avg >= 4000 else
                  "Entry-level — performanță medie"     if avg >= 2000 else
                  "Low-end — performanță scăzută")
        self.after(0, lambda: self._total_score_lbl.config(text=str(avg)))
        self.after(0, lambda: self._rating_lbl.config(text=rating, fg=CYAN))
        self.after(0, lambda: self._btn_bench.config(
            state="normal", text="▶   RULEAZĂ TOATE TESTELE"))
        self._bench_running = False

    # ── TAB: Stress Test ──────────────────────────────────────────────────────
    def _tab_stress(self, nb):
        root = tk.Frame(nb, bg=BG)
        sf   = ScrollFrame(root, bg=BG)
        sf.pack(fill="both", expand=True)
        p = sf.inner

        # ── Status card ──
        section_header(p, "STATUS", "📊", color=CYAN, bg=BG)
        sc = card(p)

        self._stress_status = tk.Label(sc, text="Inactiv",
                                        fg=T2, bg=CARD,
                                        font=("Segoe UI", 11))
        self._stress_status.pack()

        self._elapsed_lbl = tk.Label(sc, text="00:00:00",
                                      fg=CYAN, bg=CARD,
                                      font=("Courier New", 38, "bold"))
        self._elapsed_lbl.pack()

        # Stats row 1
        row1 = tk.Frame(sc, bg=CARD)
        row1.pack(fill="x", pady=(10, 2))
        self._s_cpu  = StatBox(row1, "CPU LOAD",    GREEN)
        self._s_temp = StatBox(row1, "TEMPERATURĂ", ORANGE)
        self._s_thr  = StatBox(row1, "THREAD-URI",  PURPLE)
        for w in (self._s_cpu, self._s_temp, self._s_thr):
            w.pack(side="left", expand=True, fill="x", padx=3)

        # Stats row 2
        row2 = tk.Frame(sc, bg=CARD)
        row2.pack(fill="x", pady=(2, 0))
        self._s_ips   = SmallStatBox(row2, "ITER/SEC",   CYAN)
        self._s_ram   = SmallStatBox(row2, "RAM ALOCAT", YELLOW)
        self._s_total = SmallStatBox(row2, "TOTAL ITER", GREEN)
        for w in (self._s_ips, self._s_ram, self._s_total):
            w.pack(side="left", expand=True, fill="x", padx=3)

        # ── Config card ──
        section_header(p, "TIP TEST", "⚙", color=CYAN, bg=BG)
        cc = card(p)
        self._stress_type = tk.StringVar(value="CPU")

        # GPU selector — shown only for GPU / Mixed All (hidden in Free edition)
        gpu_card = tk.Frame(cc, bg=CARD)
        if APP_EDITION != "Free":
            gpu_card.pack(fill="x", pady=(0, 6))
        tk.Label(gpu_card, text="Placă video:", fg=T2, bg=CARD,
                 font=("Segoe UI", 10)).pack(side="left")

        # Build GPU list from DXGI (with fallback to WMIC names)
        self._dxgi_adapters = _enumerate_dxgi_adapters()
        if not self._dxgi_adapters:
            wmic_gpus = _get_gpu_list()
            self._dxgi_adapters = [{'index': i, 'name': g['name'], 'vram_mb': g['vram_mb']}
                                    for i, g in enumerate(wmic_gpus)]
        gpu_labels = [
            f"{g['name']}  ({g['vram_mb']} MB)" if g['vram_mb'] > 0 else g['name']
            for g in self._dxgi_adapters
        ] or ["GPU implicit"]

        self._gpu_sel = ttk.Combobox(gpu_card, values=gpu_labels, state="readonly",
                                      width=46, font=("Segoe UI", 10))
        self._gpu_sel.current(0)
        self._gpu_sel.pack(side="left", padx=(8, 0))

        def _on_type_change(*_):
            stype = self._stress_type.get()
            gpu_card.pack_configure(
                fill="x" if stype in ("GPU", "MIXED_ALL") else "x")
            # Always visible but enabled/disabled
            state = "readonly" if stype in ("GPU", "MIXED_ALL") else "disabled"
            self._gpu_sel.config(state=state)
        self._stress_type.trace_add("write", _on_type_change)
        _on_type_change()  # set initial state

        _stress_options = [
            ("CPU Stress — încărcare maximă pe toate nucleele",   "CPU",      GREEN),
            ("Memory Stress — alocare/dealocare intensivă RAM",   "MEM",      PURPLE),
            ("GPU Stress — D3D11 compute shader / OpenGL 2.0",    "GPU",      RED),
            ("Mixed Stress — CPU + Memorie combinat",             "MIXED",    CYAN),
            ("Mixed All — CPU + Memorie + GPU",                   "MIXED_ALL",ORANGE),
        ]
        if APP_EDITION == "Free":
            _stress_options = [o for o in _stress_options if o[1] == "CPU"]

        for txt, val, c in _stress_options:
            row = tk.Frame(cc, bg=CARD, pady=3)
            row.pack(fill="x")
            tk.Radiobutton(row, text=txt, variable=self._stress_type, value=val,
                           bg=CARD, fg=T1, selectcolor=ELEV,
                           activebackground=CARD, activeforeground=c,
                           font=("Segoe UI", 10), indicatoron=True).pack(side="left")

        # ── Duration card ──
        section_header(p, "DURATĂ", "⏱", color=CYAN, bg=BG)
        dc = card(p)
        self._duration = tk.IntVar(value=60)
        dur_row = tk.Frame(dc, bg=CARD)
        dur_row.pack()
        for txt, val in [("1 min", 60), ("5 min", 300), ("15 min", 900), ("∞", 0)]:
            f = tk.Frame(dur_row, bg=CARD, padx=4)
            f.pack(side="left")
            tk.Radiobutton(f, text=txt, variable=self._duration, value=val,
                           bg=CARD, fg=T1, selectcolor=ELEV,
                           activebackground=CARD,
                           font=("Segoe UI", 11)).pack()

        # ── Threads card ──
        section_header(p, "THREAD-URI", "🔧", color=CYAN, bg=BG)
        tc = card(p)
        thr_top = tk.Frame(tc, bg=CARD)
        thr_top.pack(fill="x")
        tk.Label(thr_top, text="Număr thread-uri:", fg=T2, bg=CARD,
                 font=("Segoe UI", 10)).pack(side="left")
        self._thr_lbl = tk.Label(thr_top, text=str(os.cpu_count() or 4),
                                  fg=CYAN, bg=CARD,
                                  font=("Courier New", 16, "bold"))
        self._thr_lbl.pack(side="right")

        max_threads = os.cpu_count() or 8
        self._thr_var = tk.IntVar(value=max_threads)
        scale = tk.Scale(tc, from_=1, to=max_threads, orient="horizontal",
                         variable=self._thr_var,
                         command=lambda v: self._thr_lbl.config(text=v),
                         bg=CARD, fg=T1, troughcolor=ELEV,
                         highlightthickness=0, sliderrelief="flat",
                         activebackground=CYAN, length=400)
        scale.pack(fill="x", pady=(6, 0))

        # ── Start/Stop ──
        section_header(p, "CONTROL", "▶", color=GREEN, bg=BG)
        bc = card(p)
        self._btn_stress = accent_btn(bc, "▶   START STRESS TEST",
                                      self._toggle_stress, color=GREEN)
        self._btn_stress.pack(fill="x")

        # ── Log ──
        section_header(p, "LOG", "📋", color=T2, bg=BG)
        lc = card(p)
        self._log = tk.Text(lc, height=9, bg=ELEV, fg=T2,
                             font=("Courier New", 9), relief="flat",
                             state="disabled", wrap="word",
                             insertbackground=CYAN)
        self._log.pack(fill="x")
        import tempfile as _tp, os as _ow
        _glog = _ow.path.join(_tp.gettempdir(), "ZFInfo64_gpu_stress.log")
        self._log_write(f"Selectează tipul de test și apasă START.\nGPU log: {_glog}\n")

        tk.Frame(p, bg=BG, height=20).pack()
        return root

    def _toggle_stress(self):
        if self._stress.running:
            self._stress.stop()
            self._log_write("■ Test oprit manual.\n\n")
            self._stress_status.config(text="Oprit", fg=T2)
            self._btn_stress.config(text="▶   START STRESS TEST", bg=GREEN)
        else:
            stype   = self._stress_type.get()
            dur     = self._duration.get()
            threads = self._thr_var.get()
            gpu_idx = self._gpu_sel.current() if self._dxgi_adapters else 0
            gpu_name = (self._dxgi_adapters[gpu_idx]['name']
                        if self._dxgi_adapters else "GPU implicit")
            self._btn_stress.config(text="■   STOP", bg=RED)
            self._stress_status.config(text="Rulează...", fg=GREEN)
            dtxt = f"{dur}s" if dur > 0 else "∞"
            gpu_info = f" • {gpu_name}" if stype in ("GPU", "MIXED_ALL") else ""
            self._log_write(f"▶ {stype} • {threads} thread-uri • {dtxt}{gpu_info}\n")
            self._stress.start(stype, threads, dur,
                               self._on_stats, self._on_done,
                               gpu_adapter_idx=gpu_idx)

    def _on_stats(self, s):
        h, r = divmod(s["elapsed"], 3600)
        m, sc = divmod(r, 60)
        self.after(0, lambda: self._elapsed_lbl.config(
            text=f"{h:02d}:{m:02d}:{sc:02d}"))

        load = s["load"]
        lc = RED if load > 90 else ORANGE if load > 70 else GREEN
        self.after(0, lambda: self._s_cpu.set(f"{load}%", lc))

        t = s["temp"]
        ts = f"{t:.1f}°C" if t > 0 else "--°C"
        tc = RED if t > 80 else ORANGE if t > 60 else GREEN
        self.after(0, lambda: self._s_temp.set(ts, tc))

        self.after(0, lambda: self._s_thr.set(str(s["threads"])))
        self.after(0, lambda: self._s_ips.set(fmt_large(s["ips"])))
        self.after(0, lambda: self._s_ram.set(f"{s['ram']} MB"))
        self.after(0, lambda: self._s_total.set(fmt_large(s["total"])))

    def _on_done(self, summary):
        self.after(0, lambda: self._log_write(f"✓ {summary}\n\n"))
        self.after(0, lambda: self._btn_stress.config(
            text="▶   START STRESS TEST", bg=GREEN))
        self.after(0, lambda: self._stress_status.config(
            text="Finalizat", fg=T2))

    def _log_write(self, text):
        self._log.config(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.config(state="disabled")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    multiprocessing.freeze_support()
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    # Set AppUserModelID so taskbar uses the correct icon instead of Python's
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"ZF.Info64.{APP_EDITION}")
    except Exception: pass

    app = App()
    app.mainloop()
