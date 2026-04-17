package com.sysinfo.app.utils

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.Sensor
import android.hardware.SensorManager
import android.hardware.display.DisplayManager
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.util.DisplayMetrics
import android.view.Display
import android.view.WindowManager
import java.io.BufferedReader
import java.io.File
import java.io.FileReader
import java.io.RandomAccessFile
import java.net.Inet4Address
import java.net.NetworkInterface

data class InfoItem(val label: String, val value: String)

object DeviceInfoCollector {

    // ==================== SYSTEM ====================

    fun getSystemInfo(context: Context): List<InfoItem> {
        return listOf(
            InfoItem("Producător", Build.MANUFACTURER.uppercase()),
            InfoItem("Model", Build.MODEL),
            InfoItem("Dispozitiv", Build.DEVICE),
            InfoItem("Brand", Build.BRAND.uppercase()),
            InfoItem("Produs", Build.PRODUCT),
            InfoItem("Android", "${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"),
            InfoItem("Patch securitate", Build.VERSION.SECURITY_PATCH ?: "N/A"),
            InfoItem("Build", Build.DISPLAY),
            InfoItem("Bootloader", Build.BOOTLOADER),
            InfoItem("Hardware", Build.HARDWARE),
            InfoItem("Board", Build.BOARD),
            InfoItem("Fingerprint", Build.FINGERPRINT),
            InfoItem("Kernel", System.getProperty("os.version") ?: "N/A"),
            InfoItem("Arhitectură", Build.SUPPORTED_ABIS.joinToString(", ")),
            InfoItem("Uptime", formatUptime(android.os.SystemClock.elapsedRealtime()))
        )
    }

    // ==================== CPU ====================

    fun getCpuInfo(): List<InfoItem> {
        val items = mutableListOf<InfoItem>()

        // SoC commercial name — API 31+ then fallback
        val socName = getSocName()
        items.add(InfoItem("SoC / Chipset", socName))

        // Read /proc/cpuinfo for processor model
        try {
            val cpuInfo = File("/proc/cpuinfo").readText()
            val processorName = cpuInfo.lines()
                .firstOrNull { it.startsWith("Hardware") || it.startsWith("model name") }
                ?.substringAfter(":")?.trim()
            if (!processorName.isNullOrEmpty() && processorName != socName) {
                items.add(InfoItem("Procesor", processorName))
            }
        } catch (_: Exception) {}

        val numCores = Runtime.getRuntime().availableProcessors()
        items.add(InfoItem("Nuclee", "$numCores"))

        // CPU Frequencies
        try {
            val maxFreq = readCpuFreqFile("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
            val minFreq = readCpuFreqFile("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq")
            val curFreq = readCpuFreqFile("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")

            if (maxFreq > 0) items.add(InfoItem("Frecvență max", "${maxFreq / 1000} MHz"))
            if (minFreq > 0) items.add(InfoItem("Frecvență min", "${minFreq / 1000} MHz"))
            if (curFreq > 0) items.add(InfoItem("Frecvență curentă", "${curFreq / 1000} MHz"))
        } catch (_: Exception) {}

        // CPU Governor
        try {
            val governor = File("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").readText().trim()
            items.add(InfoItem("Governor", governor))
        } catch (_: Exception) {}

        items.add(InfoItem("ABI-uri suportate", Build.SUPPORTED_ABIS.joinToString(", ")))

        return items
    }

    fun getSocName(): String {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val soc = Build.SOC_MODEL
            if (soc != Build.UNKNOWN && soc.isNotBlank()) return soc
        }
        try {
            val cpuInfo = File("/proc/cpuinfo").readText()
            val hardware = cpuInfo.lines()
                .firstOrNull { it.startsWith("Hardware") }
                ?.substringAfter(":")?.trim()
            if (!hardware.isNullOrEmpty()) return hardware
        } catch (_: Exception) {}
        return Build.HARDWARE
    }

    fun getCoreFrequencies(): List<Pair<Int, Long>> {
        val frequencies = mutableListOf<Pair<Int, Long>>()
        val numCores = Runtime.getRuntime().availableProcessors()
        for (i in 0 until numCores) {
            try {
                val freq = readCpuFreqFile("/sys/devices/system/cpu/cpu$i/cpufreq/scaling_cur_freq")
                frequencies.add(Pair(i, freq))
            } catch (_: Exception) {
                frequencies.add(Pair(i, 0L))
            }
        }
        return frequencies
    }

    fun getCpuMaxFreq(): Long {
        return try {
            readCpuFreqFile("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
        } catch (_: Exception) { 1L }
    }

    // ==================== MEMORY ====================

    fun getMemoryInfo(context: Context): List<InfoItem> {
        val actManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        actManager.getMemoryInfo(memInfo)

        val totalMB = memInfo.totalMem / (1024 * 1024)
        val availMB = memInfo.availMem / (1024 * 1024)
        val usedMB = totalMB - availMB
        val usagePercent = ((usedMB.toFloat() / totalMB) * 100).toInt()

        return listOf(
            InfoItem("Total RAM", formatBytes(memInfo.totalMem)),
            InfoItem("Disponibil", formatBytes(memInfo.availMem)),
            InfoItem("Utilizat", formatBytes(memInfo.totalMem - memInfo.availMem)),
            InfoItem("Utilizare", "$usagePercent%"),
            InfoItem("Threshold low mem", formatBytes(memInfo.threshold)),
            InfoItem("Low memory", if (memInfo.lowMemory) "DA" else "NU")
        )
    }

    fun getMemoryUsagePercent(context: Context): Int {
        val actManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        actManager.getMemoryInfo(memInfo)
        val totalMB = memInfo.totalMem / (1024 * 1024)
        val availMB = memInfo.availMem / (1024 * 1024)
        val usedMB = totalMB - availMB
        return ((usedMB.toFloat() / totalMB) * 100).toInt()
    }

    // ==================== DISPLAY ====================

    fun getDisplayInfo(context: Context): List<InfoItem> {
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val display = wm.defaultDisplay
        val metrics = DisplayMetrics()

        @Suppress("DEPRECATION")
        display.getRealMetrics(metrics)

        val widthPixels  = metrics.widthPixels
        val heightPixels = metrics.heightPixels
        val density      = metrics.density
        val densityDpi   = metrics.densityDpi
        val xdpi         = metrics.xdpi
        val ydpi         = metrics.ydpi

        val widthInches    = widthPixels / xdpi
        val heightInches   = heightPixels / ydpi
        val diagonalInches = Math.sqrt((widthInches * widthInches + heightInches * heightInches).toDouble())

        @Suppress("DEPRECATION")
        val refreshRate = display.refreshRate

        val panelType = getDisplayPanelType(context)

        return listOf(
            InfoItem("Tip panou", panelType),
            InfoItem("Rezoluție", "${widthPixels} × ${heightPixels} px"),
            InfoItem("Densitate", "${densityDpi} dpi (${getDensityBucket(density)})"),
            InfoItem("Diagonală", String.format("%.1f\"", diagonalInches)),
            InfoItem("Rată reîmprospătare", "${refreshRate.toInt()} Hz"),
            InfoItem("Scală densitate", "${density}x"),
            InfoItem("xDPI / yDPI", "${String.format("%.1f", xdpi)} / ${String.format("%.1f", ydpi)}")
        )
    }

    fun getDisplayPanelType(context: Context): String {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
            @Suppress("DEPRECATION")
            val hdrCaps = wm.defaultDisplay.hdrCapabilities
            val types = hdrCaps?.supportedHdrTypes ?: intArrayOf()
            if (Display.HdrCapabilities.HDR_TYPE_HDR10_PLUS in types) return "AMOLED / Super AMOLED (HDR10+)"
            if (Display.HdrCapabilities.HDR_TYPE_DOLBY_VISION in types) return "OLED / AMOLED (Dolby Vision)"
            if (Display.HdrCapabilities.HDR_TYPE_HDR10 in types) return "OLED / AMOLED (HDR10)"
        }
        // Fallback heuristic: high-end Samsung → AMOLED, others → LCD/IPS
        val manufacturer = Build.MANUFACTURER.lowercase()
        if (manufacturer == "samsung") {
            val model = Build.MODEL.uppercase()
            val amoledSeries = listOf("S2","S3","S4","S5","S6","S7","S8","S9",
                "S10","S20","S21","S22","S23","S24","NOTE","FOLD","FLIP","Z FOLD","Z FLIP")
            if (amoledSeries.any { model.contains(it) }) return "Super AMOLED (estimat)"
        }
        return "LCD / IPS (estimat)"
    }

    // ==================== BATTERY ====================

    fun getBatteryInfo(context: Context): List<InfoItem> {
        val ifilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        val batteryStatus: Intent? = context.registerReceiver(null, ifilter)

        val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val batteryPct = if (level >= 0 && scale > 0) (level * 100 / scale) else -1

        val status = when (batteryStatus?.getIntExtra(BatteryManager.EXTRA_STATUS, -1)) {
            BatteryManager.BATTERY_STATUS_CHARGING     -> "Încarcă"
            BatteryManager.BATTERY_STATUS_DISCHARGING  -> "Descarcă"
            BatteryManager.BATTERY_STATUS_FULL         -> "Plin"
            BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "Nu încarcă"
            else                                       -> "Necunoscut"
        }

        val plugged = when (batteryStatus?.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1)) {
            BatteryManager.BATTERY_PLUGGED_AC       -> "AC"
            BatteryManager.BATTERY_PLUGGED_USB      -> "USB"
            BatteryManager.BATTERY_PLUGGED_WIRELESS -> "Wireless"
            else                                    -> "Deconectat"
        }

        val health = when (batteryStatus?.getIntExtra(BatteryManager.EXTRA_HEALTH, -1)) {
            BatteryManager.BATTERY_HEALTH_GOOD          -> "Bună"
            BatteryManager.BATTERY_HEALTH_OVERHEAT      -> "Supraîncălzit"
            BatteryManager.BATTERY_HEALTH_DEAD          -> "Mort"
            BatteryManager.BATTERY_HEALTH_OVER_VOLTAGE  -> "Supratensiune"
            BatteryManager.BATTERY_HEALTH_COLD          -> "Rece"
            else                                        -> "Necunoscută"
        }

        val technology  = batteryStatus?.getStringExtra(BatteryManager.EXTRA_TECHNOLOGY) ?: "N/A"
        val temperature = (batteryStatus?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) ?: 0) / 10f
        val voltage     = (batteryStatus?.getIntExtra(BatteryManager.EXTRA_VOLTAGE, 0) ?: 0) / 1000f
        val cycleCount  = getBatteryCycleCount(context)

        val items = mutableListOf(
            InfoItem("Nivel",       "$batteryPct%"),
            InfoItem("Status",      status),
            InfoItem("Alimentare",  plugged),
            InfoItem("Sănătate",    health),
            InfoItem("Tehnologie",  technology),
            InfoItem("Temperatură", "${temperature}°C"),
            InfoItem("Tensiune",    "${String.format("%.2f", voltage)} V")
        )
        if (cycleCount != "N/A") items.add(InfoItem("Cicluri încărcare", cycleCount))
        return items
    }

    fun getBatteryCycleCount(context: Context): String {
        // Try sysfs (works on many Android devices)
        val paths = listOf(
            "/sys/class/power_supply/battery/cycle_count",
            "/sys/class/power_supply/Battery/cycle_count",
            "/sys/class/power_supply/bms/cycle_count"
        )
        for (path in paths) {
            try {
                val count = File(path).readText().trim()
                if (count.isNotEmpty() && count != "0") return count
            } catch (_: Exception) {}
        }
        return "N/A"
    }

    fun getBatteryLevel(context: Context): Int {
        val ifilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        val batteryStatus: Intent? = context.registerReceiver(null, ifilter)
        val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        return if (level >= 0 && scale > 0) (level * 100 / scale) else 0
    }

    // ==================== STORAGE ====================

    fun getStorageInfo(): List<InfoItem> {
        val items = mutableListOf<InfoItem>()

        // Try to identify storage type/model
        val storageModel = getStorageModel()
        if (storageModel != "N/A") items.add(InfoItem("Model stocare", storageModel))

        val internalStat  = StatFs(Environment.getDataDirectory().path)
        val totalInternal = internalStat.totalBytes
        val freeInternal  = internalStat.availableBytes
        val usedInternal  = totalInternal - freeInternal
        val usagePercent  = ((usedInternal.toFloat() / totalInternal) * 100).toInt()

        items.addAll(listOf(
            InfoItem("Total intern",  formatBytes(totalInternal)),
            InfoItem("Utilizat",      formatBytes(usedInternal)),
            InfoItem("Disponibil",    formatBytes(freeInternal)),
            InfoItem("Utilizare",     "$usagePercent%")
        ))

        val externalDirs = Environment.getExternalStorageDirectory()
        if (externalDirs.exists()) {
            val extStat = StatFs(externalDirs.path)
            items.add(InfoItem("Extern total",      formatBytes(extStat.totalBytes)))
            items.add(InfoItem("Extern disponibil", formatBytes(extStat.availableBytes)))
        }

        return items
    }

    fun getStorageModel(): String {
        // eMMC name
        val emmcPaths = listOf(
            "/sys/block/mmcblk0/device/name",
            "/sys/class/block/mmcblk0/device/name"
        )
        for (path in emmcPaths) {
            try {
                val name = File(path).readText().trim()
                if (name.isNotEmpty()) {
                    val manfid = try { File("/sys/block/mmcblk0/device/manfid").readText().trim() } catch (_: Exception) { "" }
                    return if (manfid.isNotEmpty()) "eMMC $name ($manfid)" else "eMMC $name"
                }
            } catch (_: Exception) {}
        }
        // UFS detection
        if (File("/dev/block/sda").exists()) return "UFS (NVMe-class)"
        if (File("/dev/block/mmcblk0").exists()) return "eMMC"
        return "N/A"
    }

    fun getStorageUsagePercent(): Int {
        val stat = StatFs(Environment.getDataDirectory().path)
        val used = stat.totalBytes - stat.availableBytes
        return ((used.toFloat() / stat.totalBytes) * 100).toInt()
    }

    // ==================== NETWORK ====================

    fun getNetworkInfo(context: Context): List<InfoItem> {
        val items = mutableListOf<InfoItem>()
        try {
            @Suppress("DEPRECATION")
            val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            @Suppress("DEPRECATION")
            val wifiInfo = wm.connectionInfo
            if (wifiInfo != null && wifiInfo.networkId != -1) {
                val ssid = wifiInfo.ssid?.replace("\"", "") ?: "Wi-Fi conectat"
                items.add(InfoItem("Wi-Fi SSID", ssid))
                items.add(InfoItem("Frecvență",  "${wifiInfo.frequency} MHz"))
                items.add(InfoItem("RSSI",       "${wifiInfo.rssi} dBm"))
                items.add(InfoItem("Viteză link","${wifiInfo.linkSpeed} Mbps"))
            }
        } catch (_: Exception) {}

        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            for (iface in interfaces.asSequence()) {
                if (!iface.isUp || iface.isLoopback) continue
                for (addr in iface.inetAddresses.asSequence()) {
                    if (!addr.isLoopbackAddress && addr is Inet4Address) {
                        items.add(InfoItem("IP (${iface.name})", addr.hostAddress ?: "N/A"))
                    }
                }
            }
        } catch (_: Exception) {}

        return items
    }

    // ==================== SENSORS (essential only) ====================

    private val ESSENTIAL_SENSOR_TYPES = listOf(
        Sensor.TYPE_ACCELEROMETER,
        Sensor.TYPE_GYROSCOPE,
        Sensor.TYPE_MAGNETIC_FIELD,
        Sensor.TYPE_LIGHT,
        Sensor.TYPE_PROXIMITY
    )

    fun getSensorInfo(context: Context): List<InfoItem> {
        val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        return ESSENTIAL_SENSOR_TYPES.map { type ->
            val sensor = sensorManager.getDefaultSensor(type)
            val typeName = getSensorTypeName(type)
            if (sensor != null) {
                InfoItem(typeName, sensor.vendor.ifBlank { "Detectat" })
            } else {
                InfoItem(typeName, "Nedetectat")
            }
        }
    }

    // ==================== GPU (best-effort) ====================

    fun getGpuInfo(): List<InfoItem> {
        val items = mutableListOf<InfoItem>()
        try {
            val renderer = System.getProperty("ro.hardware.egl") ?: "N/A"
            items.add(InfoItem("EGL", renderer))
        } catch (_: Exception) {}
        items.add(InfoItem("OpenGL ES", getOpenGLVersion()))
        items.add(InfoItem("Vulkan",    getVulkanSupport()))
        return items
    }

    // ==================== TEMPERATURE ====================

    fun getCpuTemperature(): Float {
        val paths = listOf(
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/devices/virtual/thermal/thermal_zone0/temp",
            "/sys/class/hwmon/hwmon0/temp1_input"
        )
        for (path in paths) {
            try {
                val temp = File(path).readText().trim().toFloat()
                return if (temp > 1000) temp / 1000f else if (temp > 100) temp / 10f else temp
            } catch (_: Exception) {}
        }
        return -1f
    }

    // ==================== HELPERS ====================

    private fun readCpuFreqFile(path: String): Long {
        return try {
            RandomAccessFile(path, "r").use { it.readLine().trim().toLong() }
        } catch (_: Exception) { 0L }
    }

    private fun formatBytes(bytes: Long): String {
        val kb = bytes / 1024.0
        val mb = kb / 1024.0
        val gb = mb / 1024.0
        return when {
            gb >= 1.0 -> String.format("%.2f GB", gb)
            mb >= 1.0 -> String.format("%.1f MB", mb)
            else      -> String.format("%.0f KB", kb)
        }
    }

    private fun formatUptime(millis: Long): String {
        val seconds = millis / 1000
        val hours   = seconds / 3600
        val minutes = (seconds % 3600) / 60
        val secs    = seconds % 60
        return String.format("%dh %dm %ds", hours, minutes, secs)
    }

    private fun getDensityBucket(density: Float): String = when {
        density <= 0.75f -> "ldpi"
        density <= 1.0f  -> "mdpi"
        density <= 1.5f  -> "hdpi"
        density <= 2.0f  -> "xhdpi"
        density <= 3.0f  -> "xxhdpi"
        else             -> "xxxhdpi"
    }

    private fun getSensorTypeName(type: Int): String = when (type) {
        Sensor.TYPE_ACCELEROMETER       -> "Accelerometru"
        Sensor.TYPE_GYROSCOPE           -> "Giroscop"
        Sensor.TYPE_MAGNETIC_FIELD      -> "Magnetometru"
        Sensor.TYPE_LIGHT               -> "Lumină"
        Sensor.TYPE_PROXIMITY           -> "Proximitate"
        Sensor.TYPE_PRESSURE            -> "Presiune"
        Sensor.TYPE_AMBIENT_TEMPERATURE -> "Temperatură"
        Sensor.TYPE_GRAVITY             -> "Gravitate"
        Sensor.TYPE_LINEAR_ACCELERATION -> "Accel. liniară"
        Sensor.TYPE_ROTATION_VECTOR     -> "Rotație"
        Sensor.TYPE_STEP_COUNTER        -> "Numărător pași"
        Sensor.TYPE_STEP_DETECTOR       -> "Detector pași"
        Sensor.TYPE_HEART_RATE          -> "Puls"
        Sensor.TYPE_SIGNIFICANT_MOTION  -> "Mișcare semn."
        else                            -> "Senzor (tip $type)"
    }

    private fun getOpenGLVersion(): String {
        return "ES ${if (Build.VERSION.SDK_INT >= 21) "3.x" else "2.0"}"
    }

    private fun getVulkanSupport(): String {
        return if (Build.VERSION.SDK_INT >= 24) "Suportat (1.x)" else "Nesuportat"
    }
}
