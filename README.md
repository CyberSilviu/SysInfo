# ZF-INFO64 — Documentație Completă

**Versiune:** 2.0  
**Platform:** Android (minim API 26 / Android 8.0) + Windows (Python/Tkinter)  
**Limbaj Android:** Kotlin  
**Limbaj Windows:** Python 3  
**Build tool:** Gradle 8.13 / Kotlin DSL  

---

## Cuprins

1. [Descriere generală](#1-descriere-generală)
2. [Ediții (Pro / Free)](#2-ediții-pro--free)
3. [Cerințe sistem](#3-cerințe-sistem)
4. [Structura proiectului](#4-structura-proiectului)
5. [Arhitectură](#5-arhitectură)
6. [Funcționalități detaliate](#6-funcționalități-detaliate)
7. [Componente principale — Android](#7-componente-principale--android)
8. [Componente principale — Windows](#8-componente-principale--windows)
9. [GPU Stress Renderer](#9-gpu-stress-renderer)
10. [Permisiuni Android](#10-permisiuni-android)
11. [Acces Sysfs (fără permisiuni manifest)](#11-acces-sysfs-fără-permisiuni-manifest)
12. [Build și instalare](#12-build-și-instalare)
13. [Signing / Keystore](#13-signing--keystore)
14. [Dependențe](#14-dependențe)
15. [Teme vizuale și stiluri](#15-teme-vizuale-și-stiluri)

---

## 1. Descriere generală

**ZF-INFO64** este o suită de aplicații de monitorizare hardware și testare de performanță disponibilă pe două platforme:

- **Android** — aplicație nativă Kotlin cu interfață Material Design 3 dark, pentru dispozitive Android 8.0+
- **Windows** — aplicație desktop Python/Tkinter cu aceeași interfață dark, utilizând WMI/PowerShell pentru date hardware

**Funcționalități principale:**
- 50+ parametri hardware în timp real (CPU, GPU, RAM, display, baterie, stocare, senzori)
- Benchmark cu 5 teste de performanță, scor normalizat față de Snapdragon 865
- Stress test hardware configurable (CPU / Memorie / GPU / Mixed) cu monitorizare live
- Actualizare automată a datelor la fiecare 3 secunde
- Detecție automată SoC cu mapare comercială (50+ chipseturi cunoscute)
- Companion app Windows cu echivalent complet al funcționalităților Android

---

## 2. Ediții (Pro / Free)

Aplicația Android este compilată în două variante prin **product flavors** Gradle:

| Caracteristică | Pro | Free |
|---|---|---|
| Tab Dispozitiv | Complet | Complet |
| Tab Benchmark | Complet (5 teste) | Ascuns |
| Stress Test — CPU | Da | Da |
| Stress Test — Memorie | Da | Ascuns |
| Stress Test — Mixed | Da | Ascuns |
| Stress Test — GPU | Da | Ascuns |
| Stress Test — Mixed All | Da | Ascuns |
| GPU OpenGL Surface | Vizibil | Ascuns |
| Application ID | `com.zfinfo64.app` | `com.zfinfo64.app.free` |
| App Name | ZF-INFO64 Pro | ZF-INFO64 Free |

Comportamentul este controlat prin `BuildConfig.IS_FREE` setat în `app/build.gradle.kts`.

---

## 3. Cerințe sistem

### Android

| Cerință | Valoare |
|---|---|
| Android minim | 8.0 Oreo (API 26) |
| Android target | 14 (API 34) |
| RAM recomandat | 2 GB+ |
| Spațiu stocare | ~8 MB |
| Orientare | Portrait only |
| OpenGL ES | 2.0+ (pentru GPU Stress) |

### Windows

| Cerință | Valoare |
|---|---|
| OS | Windows 10/11 (64-bit) |
| Python | 3.8+ |
| Dependențe opționale | psutil, Pillow |
| Permisiuni | Standard user (WMI queries) |

---

## 4. Structura proiectului

```
SysInfo/
├── app/
│   ├── src/main/
│   │   ├── java/com/sysinfo/app/
│   │   │   ├── MainActivity.kt                    ← Entry point, navigation setup
│   │   │   ├── ui/
│   │   │   │   ├── device/
│   │   │   │   │   └── DeviceFragment.kt          ← Tab hardware info
│   │   │   │   ├── benchmark/
│   │   │   │   │   └── BenchmarkFragment.kt       ← Tab benchmark
│   │   │   │   └── stresstest/
│   │   │   │       ├── StressTestFragment.kt      ← Tab stress test
│   │   │   │       └── GpuStressRenderer.kt       ← OpenGL ES renderer
│   │   │   └── utils/
│   │   │       ├── DeviceInfoCollector.kt         ← Colectare date hardware
│   │   │       ├── BenchmarkEngine.kt             ← Logică benchmark
│   │   │       └── StressTestEngine.kt            ← Logică stress test
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   │   ├── activity_main.xml              ← Layout principal cu header
│   │   │   │   ├── fragment_device.xml            ← 8 carduri info hardware
│   │   │   │   ├── fragment_benchmark.xml         ← Carduri per test + scor total
│   │   │   │   ├── fragment_stress_test.xml       ← Configurare + live stats
│   │   │   │   └── item_info_row.xml              ← Row label-value reutilizabil
│   │   │   ├── navigation/
│   │   │   │   └── nav_graph.xml
│   │   │   ├── menu/
│   │   │   │   └── bottom_nav_menu.xml
│   │   │   └── values/
│   │   │       ├── strings.xml
│   │   │       ├── colors.xml
│   │   │       └── themes.xml
│   │   └── AndroidManifest.xml
│   └── build.gradle.kts
├── build.gradle.kts                               ← Root build config (plugins)
├── settings.gradle.kts                            ← Module config, repositories
├── gradle.properties
├── local.properties
├── sysinfo-release.jks                            ← Keystore release (NU publica!)
└── ZF-Info64/
    ├── ZF-Info64-Windows.py                       ← App Windows (Pro)
    ├── ZF-Info64-Free-Windows.py                  ← App Windows (Free)
    ├── setup_msi.py                               ← Packaging MSI
    ├── build_msi.py                               ← Build script MSI
    ├── build_msi_edition.py                       ← Build per ediție
    └── dist/
        ├── ZF-Info64.exe                          ← Executabil standalone
        └── ZF-Info64-2.0-win64.msi               ← Installer Windows
```

---

## 5. Arhitectură

### Android

Aplicația folosește o arhitectură bazată pe **Fragments** cu **Navigation Component** și **BottomNavigationView**:

```
MainActivity
    ├── Header (logo ZF + versiune v2.0)
    ├── NavHostFragment
    │       ├── DeviceFragment      ← Tab "Dispozitiv"
    │       ├── BenchmarkFragment   ← Tab "Benchmark" (Pro only)
    │       └── StressTestFragment  ← Tab "Stress Test"
    └── BottomNavigationView

Utils (singletons — Kotlin object)
    ├── DeviceInfoCollector  ← Citire hardware/sistem (sysfs + Android API)
    ├── BenchmarkEngine      ← Suspend functions pentru 5 teste
    └── StressTestEngine     ← Coroutine workers multi-thread

GpuStressRenderer           ← GLSurfaceView.Renderer (OpenGL ES 2.0)
```

**Patternuri utilizate:**

| Pattern | Implementare |
|---|---|
| **Singleton** | `object` Kotlin pentru toate utilitarele |
| **Coroutines** | `lifecycleScope.launch`, `async/await`, `Dispatchers.Default/IO` |
| **ViewBinding** | Generat automat pentru fiecare layout |
| **Navigation Component** | `NavController` + `NavGraph` XML |
| **Periodic Refresh** | Loop coroutine cu `delay(3000)` în `DeviceFragment` |
| **Thread Safety** | `AtomicBoolean`, `AtomicInteger`, `AtomicLong` pentru state shared |
| **Feature Flags** | `BuildConfig.IS_FREE` setat la compile-time prin product flavors |

### Windows

Aplicația Windows urmează o arhitectură monolitică Tkinter:

```
ZF-Info64-Windows.py
    ├── Hardware Cache (PowerShell/WMI la startup)
    ├── Tab System     ← Informații sistem, CPU, RAM, disk, rețea
    ├── Tab Benchmark  ← Teste performanță Python-native
    └── Tab Stress     ← Stress test CPU/memorie
```

---

## 6. Funcționalități detaliate

### Tab 1 — Dispozitiv

Afișează informații hardware în timp real, organizate în **8 carduri**. Datele dinamice (CPU, memorie, baterie) se actualizează automat la fiecare **3 secunde**.

#### Secțiunea Sistem
| Câmp | Sursă |
|---|---|
| Producător | `Build.MANUFACTURER` |
| Model | `Build.MODEL` |
| Device | `Build.DEVICE` |
| Brand | `Build.BRAND` |
| Versiune Android | `Build.VERSION.RELEASE` + API |
| Security Patch | `Build.VERSION.SECURITY_PATCH` |
| Build ID | `Build.DISPLAY` |
| Bootloader | `Build.BOOTLOADER` |
| Hardware | `Build.HARDWARE` |
| Board | `Build.BOARD` |
| Fingerprint | `Build.FINGERPRINT` |
| Kernel | `/proc/version` |
| ABI primar | `Build.SUPPORTED_ABIS[0]` |
| Uptime | `SystemClock.elapsedRealtime()` formatat HH:MM:SS |

#### Secțiunea CPU
| Câmp | Sursă |
|---|---|
| SoC | `Build.SOC_MODEL` (API 31+) → `ro.board.platform` → `/proc/cpuinfo Hardware` → `ro.chipname` |
| Procesor | `/proc/cpuinfo` câmpul `Processor` sau `model name` |
| Nuclee | `Runtime.getRuntime().availableProcessors()` |
| Frecvență maximă | `/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq` |
| Frecvență minimă | `/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq` |
| Frecvență curentă | `/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq` |
| CPU Governor | `/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor` |
| ABIs suportate | `Build.SUPPORTED_ABIS` |

**Frecvențe per-core** — actualizate la 3s:
- Verde = core activ (frecvență > 0)
- Gri = core offline sau în idle complet

#### Secțiunea GPU
| Câmp | Sursă |
|---|---|
| Model GPU | Lookup tabel intern `SOC_GPU` → `ro.hardware.egl` fallback |
| OpenGL ES | `ConfigurationInfo.reqGlEsVersion` (ES 3.x pe API 21+) |
| Vulkan | `PackageManager.hasSystemFeature(VULKAN)` cu versiune |
| Driver EGL | `ro.hardware.egl` system property |

#### Detecție SoC — Lookup Tables

`DeviceInfoCollector` conține **2 tabele de lookup** cu 50+ intrări pentru identificarea comercială a chipseturilor:

**`SOC_NAMES`** — mapare cod platformă → nume comercial:

| Exemplu cod | Nume comercial |
|---|---|
| SM8650 | Snapdragon 8 Gen 3 |
| SM8550 | Snapdragon 8 Gen 2 |
| SM8475 | Snapdragon 8+ Gen 1 |
| SM8450 | Snapdragon 8 Gen 1 |
| MT6989 | Dimensity 9300 |
| MT6983 | Dimensity 9200 |
| Exynos 2400 | Exynos 2400 |
| ...50+ altele | ... |

**`SOC_GPU`** — mapare SoC → GPU:

| SoC | GPU |
|---|---|
| Snapdragon 8 Gen 3 | Adreno 750 |
| Snapdragon 8 Gen 2 | Adreno 740 |
| Dimensity 9300 | Immortalis-G720 |
| ...etc | ... |

#### Secțiunea Memorie
- RAM Total, Disponibil, Utilizat, Procent utilizare, Threshold low memory
- **Progress bar orizontal** (cyan) pentru vizualizare utilizare

#### Secțiunea Display
| Câmp | Sursă |
|---|---|
| Tip panel | HDR capability detection (HDR10+/Dolby Vision/HDR10) sau heuristic Samsung |
| Rezoluție | `DisplayMetrics.widthPixels` × `heightPixels` |
| Densitate DPI | `DisplayMetrics.densityDpi` |
| Diagonală | Calculat din xdpi/ydpi și rezoluție în inch |
| Rată reîmprospătare | `Display.getRefreshRate()` |
| Density scale | `DisplayMetrics.density` + bucket (ldpi/mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi) |
| xDPI / yDPI | `DisplayMetrics.xdpi` / `ydpi` |

#### Secțiunea Baterie
- Nivel (%), Status (Charging/Discharging/Full/Not Charging)
- Sursă alimentare (AC / USB / Wireless)
- Sănătate (Good/Overheat/Dead/Over Voltage/Unknown)
- Tehnologie (Li-ion / Li-poly / etc.)
- Temperatură (°C), Tensiune (V)
- Număr cicluri (din `/sys/class/power_supply/*/cycle_count`)
- **Progress bar orizontal** (verde)

#### Secțiunea Stocare
- Model storage: eMMC (cu nume producător + ID) sau UFS
- Internal: Total / Utilizat / Disponibil / Procent
- External: Total / Disponibil
- **Progress bar orizontal** (cyan)

#### Secțiunea Senzori
- 5 senzori esențiali: Accelerometru, Giroscop, Magnetometru, Lumină, Proximitate
- Afișat cu vendor și status (Disponibil / Indisponibil)

---

### Tab 2 — Benchmark

Rulează **5 teste de performanță** secvențiale și calculează un **scor total** (0–10.000 puncte), normalizat față de un dispozitiv de referință **Snapdragon 865**.

#### Teste disponibile

| Test | Descriere | Metrică | Referință |
|---|---|---|---|
| **CPU Single-Core** | 60M operații FP (sin, cos, sqrt) pe 1 nucleu | ms, MFLOPS | 1800 ms |
| **CPU Integer** | 80M operații integer (multiply, XOR, rotate, shift) | ms, MOPS | 1200 ms |
| **CPU Multi-Core** | 60M operații FP distribuite pe toate nucleele | ms, eficiență | 400 ms |
| **Memory Bandwidth** | Write/read secvențial + acces aleator pe array 64 MB (4 passes) | MB/s | 1200 ms |
| **Storage I/O** | Write + read 16 MB în 4 KB blocks în cache dir | MB/s | 1800 ms |

#### Calcul scor

```
scor_test = (timp_referinta_ms / timp_masurat_ms) × 5000
scor_test = clamp(scor_test, 1, 10000)
scor_total = medie(scor_cpu_single, scor_cpu_int, scor_cpu_multi, scor_memory, scor_storage)
```

**Ratinguri (afișate în UI):**

| Scor | Rating |
|---|---|
| 8000+ | Flagship |
| 6000–7999 | High-end |
| 4000–5999 | Mid-range |
| 2000–3999 | Entry |
| < 2000 | Low-end |

#### Detalii tehnice benchmark

- **CPU tests**: thread priority `URGENT_AUDIO` pentru minimizarea interferențelor OS
- **Multi-core**: scor scalat cu `(coreCount / 4)` pentru corectitudine pe dispozitive cu nuclee asimetrice
- **Memory**: RNG seeded pentru acces aleator reproductibil (cache-miss simulation)
- **Storage**: fișier temporar de 16 MB în `cacheDir`, șters după test
- **Progress callbacks**: la fiecare ~10% din iterații

---

### Tab 3 — Stress Test

Test de stres hardware configurable cu monitorizare live în timp real.

#### Tipuri de stress

| Tip | Workers | Descriere |
|---|---|---|
| **CPU** | N thread-uri | Sin/cos/sqrt/tan/ln/exp în buclă, 1M iterații per batch |
| **Memory** | N thread-uri | Alocare/dealcare chunks de 4 MB, max 800 MB total, cu verificare |
| **Mixed** | N×2 thread-uri | CPU + Memory simultan |
| **GPU** | 1 GLSurfaceView | FBO ping-pong 60 passes × 1920×1080, shader de 80 iterații |
| **Mixed All** | N thread-uri + GPU | CPU + Memory + GPU simultan |

*Memory, Mixed, GPU, Mixed All — disponibile doar în ediția Pro.*

#### Opțiuni configurare

| Parametru | Valori |
|---|---|
| Durată | 1 min / 5 min / 15 min / Infinit |
| Thread-uri | 1 — N (N = număr nuclee CPU), controlat prin SeekBar |

#### Statistici live (actualizate la 1 secundă)

| Statistică | Sursă | Color coding |
|---|---|---|
| **Timp scurs** | Timer intern | Cyan |
| **CPU Load (%)** | `/proc/stat` delta calcul | Verde < 70% / Portocaliu 70–90% / Roșu > 90% |
| **Temperatură (°C)** | `/sys/class/thermal/thermal_zone*/temp` | Verde < 60°C / Portocaliu 60–80°C / Roșu > 80°C |
| **Thread-uri active** | `AtomicInteger` | Alb |
| **Iter/sec** | `AtomicLong` delta / secundă | Verde |
| **RAM alocat (MB)** | Tracking chunks memorie | Portocaliu |

**Calcul CPU Load din `/proc/stat`:**
```
CpuStat = user + nice + system + idle + iowait + irq + softirq + steal + guest + guestNice
cpuLoad = (1 - (idleDelta / totalDelta)) × 100
```

---

## 7. Componente principale — Android

### `MainActivity.kt`

Entry point al aplicației. Inițializează navigation graph și `BottomNavigationView`. În ediția Free, elimină din meniu item-ul "Benchmark" (`R.id.benchmarkFragment`) înainte de configurarea controlerului de navigare.

---

### `DeviceInfoCollector.kt`

Singleton (`object`) care expune toate funcțiile de citire hardware. Toate metodele sunt sincrone și sunt apelate din coroutine pe `Dispatchers.Default`.

**Data class returnată de cele mai multe metode:**
```kotlin
data class InfoItem(val label: String, val value: String)
```

**API public:**

```kotlin
// Sistem
DeviceInfoCollector.getSystemInfo(context): List<InfoItem>

// CPU
DeviceInfoCollector.getCpuInfo(): List<InfoItem>
DeviceInfoCollector.getCoreFrequencies(): List<InfoItem>
DeviceInfoCollector.getCpuMaxFreq(): Long          // Hz
DeviceInfoCollector.getSocName(): String
DeviceInfoCollector.getCpuTemperature(): Float     // °C

// GPU
DeviceInfoCollector.getGpuInfo(context): List<InfoItem>

// Memorie
DeviceInfoCollector.getMemoryInfo(context): List<InfoItem>
DeviceInfoCollector.getMemoryUsagePercent(context): Int  // 0-100

// Display
DeviceInfoCollector.getDisplayInfo(context): List<InfoItem>
DeviceInfoCollector.getDisplayPanelType(context): String

// Baterie
DeviceInfoCollector.getBatteryInfo(context): List<InfoItem>
DeviceInfoCollector.getBatteryLevel(context): Int        // 0-100
DeviceInfoCollector.getBatteryCycleCount(context): Int

// Stocare
DeviceInfoCollector.getStorageInfo(): List<InfoItem>
DeviceInfoCollector.getStorageUsagePercent(): Int        // 0-100
DeviceInfoCollector.getStorageModel(): String

// Rețea
DeviceInfoCollector.getNetworkInfo(context): List<InfoItem>

// Senzori
DeviceInfoCollector.getSensorInfo(context): List<InfoItem>
```

**Helper functions:**
```kotlin
DeviceInfoCollector.formatBytes(bytes: Long): String    // "X.X GB" / "X MB" / "X KB"
DeviceInfoCollector.formatUptime(millis: Long): String  // "Xh Ym Zs"
```

---

### `BenchmarkEngine.kt`

Singleton cu 5 funcții suspend pentru teste de performanță. Fiecare funcție acceptă un callback opțional de progres.

**Data class rezultat:**
```kotlin
data class BenchmarkResult(
    val score: Int,       // 0–10000
    val details: String,  // "1234 ms | X MFLOPS"
    val durationMs: Long
)
```

**Constante de referință (Snapdragon 865):**
```kotlin
REF_SINGLE_CORE_MS = 1800.0
REF_INTEGER_MS     = 1200.0
REF_MULTI_CORE_MS  = 400.0
REF_MEMORY_MS      = 1200.0
REF_STORAGE_MS     = 1800.0
MAX_SCORE          = 10_000
```

**API public:**
```kotlin
suspend fun BenchmarkEngine.runCpuSingleCore(onProgress: (Int) -> Unit = {}): BenchmarkResult
suspend fun BenchmarkEngine.runCpuInteger(onProgress: (Int) -> Unit = {}): BenchmarkResult
suspend fun BenchmarkEngine.runCpuMultiCore(onProgress: (Int) -> Unit = {}): BenchmarkResult
suspend fun BenchmarkEngine.runMemoryBenchmark(onProgress: (Int) -> Unit = {}): BenchmarkResult
suspend fun BenchmarkEngine.runStorageBenchmark(cacheDir: File, onProgress: (Int) -> Unit = {}): BenchmarkResult
```

---

### `StressTestEngine.kt`

Singleton care gestionează toți workerii de stress și monitorizarea în timp real.

**Enumerație tipuri:**
```kotlin
enum class StressType { CPU, MEMORY, MIXED, GPU, MIXED_ALL }
```

**Data class statistici:**
```kotlin
data class StressStats(
    val elapsedSeconds: Long,
    val cpuLoadPercent: Float,
    val temperatureCelsius: Float,
    val activeThreads: Int,
    val iterationsCompleted: Long,
    val iterationsPerSec: Long,
    val memoryAllocatedMB: Int
)
```

**API public:**
```kotlin
StressTestEngine.isRunning: AtomicBoolean
StressTestEngine.totalIterations: AtomicLong  // shared cu GpuStressRenderer

fun StressTestEngine.start(
    scope: CoroutineScope,
    type: StressType,
    threadCount: Int,
    durationSeconds: Int,             // 0 = infinit
    onStats: (StressStats) -> Unit,   // apelat la fiecare secundă
    onComplete: () -> Unit
)

fun StressTestEngine.stop()
```

**Comportament memory stress:**
- Alocă chunks de **4 MB** până la maxim **800 MB total**
- Fiecare chunk este scris și citit pentru verificare
- La OOM: șterge cel mai vechi chunk și reîncearcă
- Tracking thread-safe cu `synchronized(memChunks)`

---

### `DeviceFragment.kt`

Gestionează Tab "Dispozitiv". Structura internă:

```kotlin
onViewCreated()
    ├── loadDeviceInfo(view)        // apel inițial, populează toate cele 8 secțiuni
    └── startPeriodicRefresh(view) // coroutine loop cu delay(3000)
            ├── getCoreFrequencies()  // actualizează lista per-core
            ├── getMemoryInfo()       // actualizează card + progress bar
            └── getBatteryInfo()      // actualizează card + progress bar

onDestroyView()
    └── refreshJob?.cancel()       // oprire graceful a loop-ului
```

Fiecare secțiune de info este populată prin `populateSection(container, items)` care inflează dinamic `item_info_row.xml` pentru fiecare `InfoItem`.

---

### `BenchmarkFragment.kt`

Gestionează Tab "Benchmark". Orchestrează cele 5 teste secvențial:

```kotlin
runAllBenchmarks(view)
    ├── setStatus("CPU Single-Core", "Rulează...")
    ├── result1 = BenchmarkEngine.runCpuSingleCore { progress -> updateProgressBar(...) }
    ├── setStatus("CPU Integer", "Rulează...")
    ├── result2 = BenchmarkEngine.runCpuInteger { ... }
    ├── ...                                       // (4 mai)
    └── scor_total = (r1 + r2 + r3 + r4 + r5) / 5
        → afișează scor total + getRating(scor_total)
```

---

### `StressTestFragment.kt`

Gestionează Tab "Stress Test". Controlează vizibilitatea elementelor UI în funcție de `BuildConfig.IS_FREE`:

```kotlin
setupControls()
    ├── if (IS_FREE): ascunde Memory/Mixed/GPU/MixedAll radio buttons
    ├── if (IS_FREE): gpuSurface.visibility = GONE
    └── threadSlider.max = availableProcessors()

startStressTest()
    ├── if (GPU selected): startGpuSurface()
    └── StressTestEngine.start(...) { stats ->
            withContext(Main) { updateLiveStats(stats) }
        }

updateLiveStats(stats)
    ├── elapsed time display
    ├── cpuLoad cu color coding (verde/portocaliu/roșu)
    ├── temperature cu color coding
    ├── active threads
    ├── iterations per second
    └── memory allocated (MB)
```

---

## 8. Componente principale — Windows

Aplicația Windows (`ZF-Info64-Windows.py`) replică funcționalitățile Android folosind:

### Colectare date hardware

**WMI via PowerShell** (single query la startup, rezultat cache-iat):
```powershell
Get-WmiObject Win32_Processor              # Nume CPU, viteze, nuclee
Get-WmiObject Win32_DiskDrive              # Modele disk, capacitate
Get-WmiObject Win32_NetworkAdapter         # Adaptoare rețea active (NetConnectionStatus=2)
Get-WmiObject Win32_PhysicalMemory         # Module RAM: capacitate, tip, viteză, vendor
Get-WmiObject Win32_Battery                # Baterie (laptop): ciclu de viață
```

**Windows Registry** (direct via `winreg`, fără subprocess):
```python
winreg.OpenKey(HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
# → Citire CPU name instant
```

**psutil** (opțional, pentru date live):
- CPU usage %, temperaturi, utilizare memorie, throughput disk

### Aceeași paletă de culori ca Android

```python
BG      = "#0D1117"   # fundal principal
CARD    = "#1C2333"   # fundal card
CYAN    = "#00BCD4"
GREEN   = "#4CAF50"
ORANGE  = "#FF9800"
RED     = "#F44336"
PURPLE  = "#9C27B0"
YELLOW  = "#FFEB3B"
```

### Distribuție Windows

**Build MSI** cu PyInstaller:
```bash
python build_msi.py           # build ambele ediții
python build_msi_edition.py   # build ediție specifică
python setup_msi.py           # configurare WiX pentru MSI
```

Output: `dist/ZF-Info64.exe`, `dist/ZF-Info64-2.0-win64.msi`

---

## 9. GPU Stress Renderer

`GpuStressRenderer.kt` implementează `GLSurfaceView.Renderer` cu o tehnică de **FBO ping-pong** pentru a maximiza încărcarea GPU.

### Parametri de configurare

```kotlin
PASSES = 60              // number de render passes per frame
FBO_W  = 1920            // lățime FBO fixă (indiferent de rezoluția ecranului)
FBO_H  = 1080            // înălțime FBO fixă
```

### Arhitectura de rendering

```
onDrawFrame()
    ├── for pass in 0..59:
    │       ├── bind FBO[pass % 2]          // alternare ping-pong
    │       ├── sample texture[1 - pass%2]  // citire din pass anterior
    │       ├── render stress shader         // 80 iterații trig per pixel
    │       └── glViewport(0,0, FBO_W, FBO_H)
    ├── blit final la ecran (native resolution)
    └── StressTestEngine.reportGpuFrame()   // increment totalIterations
```

### Shader de stress (Fragment Shader)

```glsl
// 80 iterații per pixel la 1920×1080 = ~160M operații per pass
// 60 passes per frame = ~9.6 miliarde operații per frame
for (int i = 0; i < 80; i++) {
    v += sin(vUV.x * 19.0 + uTime * 1.1 + float(i) * 0.17);
    v += cos(length(vUV - 0.5) * 25.0 + uTime * 0.9);
    v += sqrt(abs(v) + 0.001);
    v -= floor(v);                           // fractal feedback
    v *= 1.0 - texture2D(uPrevious, vUV + sin(v)*0.003).r * 0.15;
}
```

### De ce FBO-uri fixe la 1920×1080?

FBO-urile sunt independente de rezoluția ecranului fizic pentru a asigura o **încărcare GPU consistentă** indiferent de dispozitiv. Un dispozitiv cu ecran 720p va rula exact același număr de operații GPU ca unul cu ecran 4K.

### Resurse OpenGL gestionate

| Resursă | Count | Alocat în |
|---|---|---|
| Shader programs | 2 (stress + blit) | `onSurfaceCreated` |
| FBOs | 2 | `onSurfaceCreated` |
| Texturi | 2 | `onSurfaceCreated` |
| VBO (quad vertices) | 1 | `onSurfaceCreated` |

Toate resursele sunt eliberate în `destroyGpuSurface()` apelat din `StressTestFragment.onDestroyView()`.

---

## 10. Permisiuni Android

Declarate în `AndroidManifest.xml`:

| Permisiune | Nivel | Utilizare |
|---|---|---|
| `READ_PHONE_STATE` | Dangerous | Identificare hardware dispozitiv |
| `ACCESS_NETWORK_STATE` | Normal | Status conectivitate rețea |
| `ACCESS_WIFI_STATE` | Normal | SSID WiFi, RSSI, link speed |
| `BATTERY_STATS` | Signature/System | Statistici baterie detaliate (cicluri) |
| `WAKE_LOCK` | Normal | Previne sleep în timpul stress test |
| `HIGH_SAMPLING_RATE_SENSORS` | Normal | Acces senzori cu rată > 200Hz |

> **Notă:** `BATTERY_STATS` este o permisiune de nivel `signatureOrSystem`. Pe dispozitivele non-root va fi ignorată de OS; aplicația degradează graceful la datele disponibile prin `BatteryManager` Intent standard.

---

## 11. Acces Sysfs (fără permisiuni manifest)

Aplicația citește direct fișiere din sistemul de fișiere virtual Linux. Aceste operațiuni nu necesită permisiuni declarate în manifest:

| Cale sysfs | Informație citită |
|---|---|
| `/proc/version` | Versiune kernel |
| `/proc/cpuinfo` | Model procesor, platform hardware |
| `/proc/stat` | Statistici CPU per-tick pentru calcul load |
| `/sys/devices/system/cpu/cpuN/cpufreq/cpuinfo_max_freq` | Frecvență maximă per core |
| `/sys/devices/system/cpu/cpuN/cpufreq/cpuinfo_min_freq` | Frecvență minimă per core |
| `/sys/devices/system/cpu/cpuN/cpufreq/scaling_cur_freq` | Frecvență curentă per core |
| `/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor` | CPU governor activ |
| `/sys/class/power_supply/*/cycle_count` | Cicluri baterie |
| `/sys/class/thermal/thermal_zone*/temp` | Temperaturi hardware |
| `/sys/class/block/mmcblk0/device/name` | Numele chipului eMMC |
| `/sys/class/block/mmcblk0/device/manfid` | ID producător eMMC |

> **Notă:** Accesul la aceste fișiere variază între producători și versiuni Android. Toate citirile sunt înconjurate de `try-catch`, cu valori fallback sensibile.

**Detecție temperatură** — logică de scalare automată:
```kotlin
// /sys/class/thermal/ poate returna:
//   - miligrade: 45000 → 45.0°C
//   - grade × 10: 450 → 45.0°C
//   - grade: 45 → 45.0°C
// DeviceInfoCollector detectează automat formatul
```

---

## 12. Build și instalare

### Prerequisite

- Android Studio Hedgehog (2023.1.1) sau mai nou
- Android SDK API 34 (Android 14)
- JDK 17 (inclus în Android Studio)
- Gradle 8.13 (wrapper inclus în repo)

### Build debug

```bash
# Windows PowerShell
.\gradlew assembleProDebug    # Ediție Pro debug
.\gradlew assembleFreeDebug   # Ediție Free debug

# Linux/macOS
./gradlew assembleProDebug
./gradlew assembleFreeDebug
```

**Output APK:**
```
app/build/outputs/apk/pro/debug/app-pro-debug.apk
app/build/outputs/apk/free/debug/app-free-debug.apk
```

### Build release (semnat)

```bash
.\gradlew assembleProRelease    # Ediție Pro release
.\gradlew assembleFreeRelease   # Ediție Free release
```

**Output APK:**
```
app/build/outputs/apk/pro/release/SysInfo.apk
app/build/outputs/apk/free/release/app-free-release.apk
```

### Instalare directă pe dispozitiv via ADB

```bash
# Instalare release Pro
adb install app/build/outputs/apk/pro/release/SysInfo.apk

# Instalare debug (fără dezinstalare prealabilă)
adb install -r app/build/outputs/apk/pro/debug/app-pro-debug.apk
```

### Build Windows (MSI)

```bash
cd ZF-Info64
pip install pyinstaller pillow psutil
python build_msi.py
# Output: dist/ZF-Info64.exe, dist/ZF-Info64-2.0-win64.msi
```

### Task-uri Gradle disponibile

```bash
.\gradlew tasks --all          # lista completă task-uri
.\gradlew lint                 # analiză statică cod
.\gradlew assembleDebug        # ambele flavors debug
.\gradlew assembleRelease      # ambele flavors release
.\gradlew clean                # curăță build artifacts
```

---

## 13. Signing / Keystore

Keystore-ul de release se află în rădăcina proiectului: `sysinfo-release.jks`

**Configurare în `app/build.gradle.kts`:**
```kotlin
signingConfigs {
    create("release") {
        storeFile = file("../sysinfo-release.jks")
        storePassword = "sysinfo123"
        keyAlias = "sysinfo"
        keyPassword = "sysinfo123"
    }
}
```

> **IMPORTANT:** Keystore-ul **NU trebuie** publicat sau încărcat pe un sistem public (GitHub, etc.). Pierderea lui face imposibilă actualizarea aplicației cu același `applicationId` pe Google Play.
>
> Aplicația Pro are `applicationId = "com.zfinfo64.app"` — orice actualizare viitoare pe Play Store trebuie semnată cu același keystore.

---

## 14. Dependențe

### Android

| Librărie | Versiune | Utilizare |
|---|---|---|
| `androidx.core:core-ktx` | 1.12.0 | Extensions Kotlin pentru Android |
| `androidx.appcompat:appcompat` | 1.6.1 | Compatibilitate backwards |
| `com.google.android.material` | 1.11.0 | Material Design 3 components |
| `androidx.constraintlayout:constraintlayout` | 2.1.4 | Layout flexibil cu constraints |
| `androidx.navigation:navigation-fragment-ktx` | 2.7.7 | Navigation Component (Fragment) |
| `androidx.navigation:navigation-ui-ktx` | 2.7.7 | Navigation UI + BottomNav integration |
| `androidx.lifecycle:lifecycle-viewmodel-ktx` | 2.7.0 | ViewModel + coroutines scope |
| `androidx.lifecycle:lifecycle-livedata-ktx` | 2.7.0 | LiveData + coroutines |
| `org.jetbrains.kotlinx:kotlinx-coroutines-android` | 1.7.3 | Coroutines Android dispatcher |
| `com.github.PhilJay:MPAndroidChart` | v3.1.0 | Grafice (JitPack) |
| `androidx.recyclerview:recyclerview` | 1.3.2 | Liste dinamice |
| `androidx.cardview:cardview` | 1.0.0 | Card UI components |

### Plugins Gradle

| Plugin | Versiune |
|---|---|
| Android Gradle Plugin | 8.13.2 |
| Kotlin Android | 1.9.22 |

### Repositories configurate

```kotlin
// settings.gradle.kts
repositories {
    google()
    mavenCentral()
    maven { url = uri("https://jitpack.io") }  // pentru MPAndroidChart
}
```

### Python (Windows app)

| Librărie | Obligatorie | Utilizare |
|---|---|---|
| `tkinter` | Da (stdlib) | UI principal |
| `subprocess` | Da (stdlib) | PowerShell queries |
| `winreg` | Da (stdlib Windows) | Registry CPU name |
| `psutil` | Opțional | CPU%, temperaturi live |
| `Pillow` | Opțional | Procesare imagini/logo |

---

## 15. Teme vizuale și stiluri

### Paletă de culori (Android `colors.xml`)

| Rol | Hex | Utilizare |
|---|---|---|
| `bg_primary` | `#0D1117` | Fundal principal aplicație |
| `bg_card` | `#161B22` | Fundal carduri normale |
| `bg_card_elevated` | `#1C2333` | Fundal carduri ridicate (stress test) |
| `accent_cyan` | `#00BCD4` | Scoruri benchmark, frecvențe, elemente principale |
| `accent_green` | `#4CAF50` | Status OK, CPU low, temp scăzută |
| `accent_orange` | `#FF9800` | Avertizări, CPU mediu, temp medie |
| `accent_red` | `#F44336` | Erori, CPU înalt, temp mare |
| `accent_purple` | `#9C27B0` | Memory benchmark |
| `accent_yellow` | `#FFEB3B` | Storage benchmark |
| `text_primary` | `#E6EDF3` | Text principal |
| `text_secondary` | `#8B949E` | Label-uri, text secundar |

### Stiluri definite (`themes.xml`)

| Style | Utilizare |
|---|---|
| `InfoCard` | Container card pentru secțiuni hardware |
| `SectionTitle` | Titlu secțiune cu icon |
| `InfoLabel` | Coloana label din `item_info_row.xml` |
| `InfoValue` | Coloana value din `item_info_row.xml` |
| `BenchScore` | Scor benchmark (24sp, bold, cyan, monospace) |

### Font

Toate textele numerice și tehnice folosesc **font monospace** (`fontFamily="monospace"`) pentru aliniere consistentă a cifrelor.

---

*Documentație generată pentru versiunea 2.0 — ZF-INFO64 Android + Windows*
