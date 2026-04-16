# SysInfo — Documentație

**Versiune:** 1.0
**Platform:** Android (minim API 26 / Android 8.0)
**Limbaj:** Kotlin
**Build tool:** Gradle 8.13

---

## Cuprins

1. [Descriere generală](#1-descriere-generală)
2. [Cerințe sistem](#2-cerințe-sistem)
3. [Structura proiectului](#3-structura-proiectului)
4. [Arhitectură](#4-arhitectură)
5. [Funcționalități](#5-funcționalități)
6. [Componente principale](#6-componente-principale)
7. [Permisiuni](#7-permisiuni)
8. [Build și instalare](#8-build-și-instalare)
9. [Dependențe](#9-dependențe)

---

## 1. Descriere generală

**SysInfo** este o aplicație Android de monitorizare și testare hardware. Oferă informații detaliate despre dispozitiv, teste de performanță (benchmark) și teste de stres configurabile — totul într-o interfață dark modernă bazată pe Material Design 3.

**Funcționalități principale:**
- 40+ parametri de informații hardware în timp real
- Benchmark cu 4 teste (CPU single-core, CPU multi-core, Memorie, Storage)
- Stress test configurable (CPU / Memorie / Mixed) cu monitoring live
- Actualizare automată a datelor la fiecare 3 secunde

---

## 2. Cerințe sistem

| Cerință | Valoare |
|---|---|
| Android minim | 8.0 Oreo (API 26) |
| Android target | 14 (API 34) |
| RAM recomandat | 2 GB+ |
| Spațiu stocare | ~5 MB |
| Orientare | Portrait only |

---

## 3. Structura proiectului

```
SysInfo/
├── app/
│   ├── src/main/
│   │   ├── java/com/sysinfo/app/
│   │   │   ├── MainActivity.kt
│   │   │   ├── ui/
│   │   │   │   ├── device/
│   │   │   │   │   └── DeviceFragment.kt
│   │   │   │   ├── benchmark/
│   │   │   │   │   └── BenchmarkFragment.kt
│   │   │   │   └── stresstest/
│   │   │   │       └── StressTestFragment.kt
│   │   │   └── utils/
│   │   │       ├── DeviceInfoCollector.kt
│   │   │       ├── BenchmarkEngine.kt
│   │   │       └── StressTestEngine.kt
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   │   ├── activity_main.xml
│   │   │   │   ├── fragment_device.xml
│   │   │   │   ├── fragment_benchmark.xml
│   │   │   │   ├── fragment_stress_test.xml
│   │   │   │   └── item_info_row.xml
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
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
├── local.properties
└── sysinfo-release.jks
```

---

## 4. Arhitectură

Aplicația folosește o arhitectură simplă bazată pe **Fragments** cu **Navigation Component**:

```
MainActivity
    └── NavHostFragment
            ├── DeviceFragment      ← Tab "Dispozitiv"
            ├── BenchmarkFragment   ← Tab "Benchmark"
            └── StressTestFragment  ← Tab "Stress Test"

Utils (singletons)
    ├── DeviceInfoCollector  ← Citire hardware/sistem
    ├── BenchmarkEngine      ← Logică teste performanță
    └── StressTestEngine     ← Logică stress test
```

**Patternuri utilizate:**
- **Singleton** pentru utilitare (`object` Kotlin)
- **Coroutines** (`lifecycleScope.launch`) pentru operații asincrone
- **ViewBinding** pentru accesul la views
- **LiveData / actualizare periodică** la 3 secunde în DeviceFragment

---

## 5. Funcționalități

### Tab 1 — Dispozitiv

Afișează informații hardware în timp real, organizate în 8 secțiuni:

| Secțiune | Informații afișate |
|---|---|
| **Sistem** | Producător, model, versiune Android, security patch, kernel, arhitectură ABI |
| **CPU** | Procesorul, număr nuclee, frecvențe (max / min / curent), CPU governor |
| **Frecvențe per core** | Frecvența fiecărui core, actualizată la 3s (verde = activ, gri = offline) |
| **Memorie** | RAM total, disponibil, utilizat, procent utilizare, threshold low memory |
| **Ecran** | Rezoluție (px), densitate DPI, diagonală (inch), rată reîmprospătare, xDPI/yDPI |
| **Baterie** | Nivel (%), status, tip alimentare, sănătate, tehnologie, temperatură, tensiune |
| **Stocare** | Intern: total/utilizat/disponibil; Extern: total/disponibil |
| **Senzori** | Listă completă cu tip și vendor (accelerometru, giroscop, lumină, etc.) |

### Tab 2 — Benchmark

Rulează 4 teste de performanță secvențiale și calculează un scor total (0–10.000 puncte):

| Test | Descriere | Metrică |
|---|---|---|
| **CPU Single-Core** | 50 milioane operații matematice (sin, cos, sqrt) pe 1 nucleu | ms, scor normalizat |
| **CPU Multi-Core** | Aceeași operație distribuită pe toate nucleele | ms, scor normalizat |
| **Memory** | Write/read secvențial + acces aleator pe 10M int-uri (5 passes) | MB/s, scor normalizat |
| **Storage I/O** | Write + read 8MB în director cache | MB/s, scor normalizat |

Scorurile sunt normalizate față de un dispozitiv de referință **Snapdragon 855** (scor maxim: 10.000).
**Scorul total** = media aritmetică a celor 4 teste.

### Tab 3 — Stress Test

Test de stres hardware configurable cu monitoring live:

**Tipuri de stress:**
- **CPU** — operații trigonometrice complexe pe toate nucleele
- **Memorie** — alocare / dealcare intensivă (chunks de 1MB, max 100MB/thread)
- **Mixed** — CPU + Memorie simultan

**Configurare:**
- Durată: 1 min / 5 min / 15 min / Infinit
- Thread-uri: slider 1–16 (implicit = numărul de nuclee)

**Monitorizare live:**
- Timp scurs (HH:MM:SS)
- CPU Load (%) — cu color coding (verde < 70%, portocaliu 70–90%, roșu > 90%)
- Temperatură CPU (°C)
- Thread-uri active
- Log operații

---

## 6. Componente principale

### `DeviceInfoCollector`

Singleton (`object`) care citește informații hardware din surse de sistem:

| Metodă | Sursă date |
|---|---|
| `getSystemInfo()` | `Build.*`, `/proc/version` |
| `getCpuInfo()` | `/proc/cpuinfo`, `/sys/devices/system/cpu/` |
| `getCoreFrequencies()` | `/sys/devices/system/cpu/cpuN/cpufreq/` |
| `getMemoryInfo()` | `ActivityManager.getMemoryInfo()` |
| `getDisplayInfo()` | `WindowManager`, `DisplayMetrics` |
| `getBatteryInfo()` | `BatteryManager` (Intent) |
| `getStorageInfo()` | `StatFs` |
| `getSensorInfo()` | `SensorManager` |
| `getCpuTemperature()` | `/sys/class/thermal/thermal_zone*/temp` |

### `BenchmarkEngine`

Singleton cu 4 metode de test, fiecare returnând un scor normalizat:

```kotlin
BenchmarkEngine.runCpuSingleCore()  // -> BenchmarkResult(score, details)
BenchmarkEngine.runCpuMultiCore()   // -> BenchmarkResult(score, details)
BenchmarkEngine.runMemoryBenchmark() // -> BenchmarkResult(score, details)
BenchmarkEngine.runStorageIO()      // -> BenchmarkResult(score, details)
```

Timpi de referință pentru normalizare:
- Single-core: 2.000 ms → scor 5.000
- Multi-core: 500 ms → scor 5.000
- Memory: 1.500 ms → scor 5.000
- Storage: 2.000 ms → scor 5.000

### `StressTestEngine`

Gestionează thread-urile de stress și monitorizarea:

```kotlin
StressTestEngine.start(type, threads, duration, onUpdate)
StressTestEngine.stop()
```

Callback `onUpdate` primește: `elapsed`, `cpuLoad`, `temperature`, `activeThreads`, `logMessage`.

---

## 7. Permisiuni

| Permisiune | Utilizare |
|---|---|
| `READ_PHONE_STATE` | Informații despre dispozitiv |
| `ACCESS_NETWORK_STATE` | Status rețea |
| `ACCESS_WIFI_STATE` | Status WiFi |
| `BATTERY_STATS` | Statistici baterie (system-level) |
| `WAKE_LOCK` | Previne sleep-ul în timpul stress test-ului |
| `HIGH_SAMPLING_RATE_SENSORS` | Acces senzori cu rată mare de eșantionare |

---

## 8. Build și instalare

### Prerequisite

- Android Studio Hedgehog sau mai nou
- Android SDK API 34
- JDK 17 (inclus în Android Studio)

### Build debug

```bash
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

### Build release (semnat)

Keystore-ul se află în rădăcina proiectului (`sysinfo-release.jks`), configurat în `app/build.gradle.kts`:

```bash
./gradlew assembleRelease
# APK: app/build/outputs/apk/release/SysInfo.apk
```

### Instalare directă pe dispozitiv

```bash
adb install app/build/outputs/apk/release/SysInfo.apk
```

> **Important:** Păstrează fișierul `sysinfo-release.jks` în siguranță. Este necesar pentru toate actualizările viitoare ale aplicației. Dacă se pierde, aplicația nu mai poate fi actualizată pe același `applicationId`.

---

## 9. Dependențe

| Librărie | Versiune | Utilizare |
|---|---|---|
| `androidx.core:core-ktx` | 1.12.0 | Extensions Kotlin pentru Android |
| `androidx.appcompat:appcompat` | 1.6.1 | Compatibilitate backwards |
| `com.google.android.material` | 1.11.0 | Material Design 3 components |
| `androidx.constraintlayout` | 2.1.4 | Layout flexibil |
| `androidx.navigation:navigation-fragment-ktx` | 2.7.7 | Navigation Component |
| `androidx.navigation:navigation-ui-ktx` | 2.7.7 | Navigation UI helpers |
| `androidx.lifecycle:lifecycle-viewmodel-ktx` | 2.7.0 | ViewModel + coroutines |
| `androidx.lifecycle:lifecycle-livedata-ktx` | 2.7.0 | LiveData + coroutines |
| `org.jetbrains.kotlinx:kotlinx-coroutines-android` | 1.7.3 | Coroutines Android |
| `com.github.PhilJay:MPAndroidChart` | v3.1.0 | Grafice și charts |
| `androidx.recyclerview:recyclerview` | 1.3.2 | Liste dinamice |
| `androidx.cardview:cardview` | 1.0.0 | Card UI components |
