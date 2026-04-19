"""
ZF-Info64 v2.0 — System Information & Benchmark Tool for Windows
"""

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

    def start(self, stype, n_threads, duration, on_stats, on_done):
        if self._running.is_set(): return
        self._running.set(); self._iters = 0; self._chunks.clear()

        cpu_count = n_threads if stype == "CPU" else (n_threads // 2 if stype == "MIXED" else 0)
        mem_count = n_threads if stype == "MEM" else (n_threads - n_threads // 2 if stype == "MIXED" else 0)

        for _ in range(cpu_count):
            p = multiprocessing.Process(target=_cpu_stress_worker_fn, daemon=True)
            p.start()
            self._cpu_procs.append(p)

        for _ in range(mem_count):
            threading.Thread(target=self._mem, daemon=True).start()

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
        self.title("ZF-Info64")
        self.configure(bg=BG)
        self.geometry("860x680")
        self.minsize(700, 520)

        # Set window + taskbar icon
        icon_path = Path(__file__).parent / "zf_icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
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
        logo_path = Path(__file__).parent / "logo ZF-Logo64.png"
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
        for txt, val, c in [
            ("CPU Stress — încărcare maximă pe toate nucleele",   "CPU",   GREEN),
            ("Memory Stress — alocare/dealocare intensivă RAM",   "MEM",   PURPLE),
            ("Mixed Stress — CPU + Memorie combinat",             "MIXED", CYAN),
        ]:
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
        self._log_write("Selectează tipul de test și apasă START.\n")

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
            self._btn_stress.config(text="■   STOP", bg=RED)
            self._stress_status.config(text="Rulează...", fg=GREEN)
            dtxt = f"{dur}s" if dur > 0 else "∞"
            self._log_write(f"▶ {stype} • {threads} thread-uri • {dtxt}\n")
            self._stress.start(stype, threads, dur,
                               self._on_stats, self._on_done)

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

    app = App()
    app.mainloop()
