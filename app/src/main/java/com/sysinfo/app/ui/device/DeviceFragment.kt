package com.sysinfo.app.ui.device

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.sysinfo.app.R
import com.sysinfo.app.utils.DeviceInfoCollector
import com.sysinfo.app.utils.InfoItem
import kotlinx.coroutines.*

class DeviceFragment : Fragment() {

    private var refreshJob: Job? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_device, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        loadDeviceInfo(view)
        startPeriodicRefresh(view)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        refreshJob?.cancel()
    }

    private fun loadDeviceInfo(view: View) {
        val ctx = requireContext()

        // System info
        populateSection(
            view.findViewById(R.id.systemInfoContainer),
            DeviceInfoCollector.getSystemInfo(ctx)
        )

        // CPU info
        populateSection(
            view.findViewById(R.id.cpuInfoContainer),
            DeviceInfoCollector.getCpuInfo()
        )

        // GPU info
        populateSection(
            view.findViewById(R.id.gpuInfoContainer),
            DeviceInfoCollector.getGpuInfo(ctx)
        )

        // Memory info
        populateSection(
            view.findViewById(R.id.memInfoContainer),
            DeviceInfoCollector.getMemoryInfo(ctx)
        )
        view.findViewById<ProgressBar>(R.id.memProgressBar).progress =
            DeviceInfoCollector.getMemoryUsagePercent(ctx)

        // Display info
        populateSection(
            view.findViewById(R.id.displayInfoContainer),
            DeviceInfoCollector.getDisplayInfo(ctx)
        )

        // Battery info
        populateSection(
            view.findViewById(R.id.batteryInfoContainer),
            DeviceInfoCollector.getBatteryInfo(ctx)
        )
        view.findViewById<ProgressBar>(R.id.batteryProgressBar).progress =
            DeviceInfoCollector.getBatteryLevel(ctx)

        // Storage info
        populateSection(
            view.findViewById(R.id.storageInfoContainer),
            DeviceInfoCollector.getStorageInfo()
        )
        view.findViewById<ProgressBar>(R.id.storageProgressBar).progress =
            DeviceInfoCollector.getStorageUsagePercent()

        // Sensors
        populateSection(
            view.findViewById(R.id.sensorsInfoContainer),
            DeviceInfoCollector.getSensorInfo(ctx)
        )
    }

    private fun startPeriodicRefresh(view: View) {
        refreshJob = viewLifecycleOwner.lifecycleScope.launch {
            while (isActive) {
                delay(3000) // Refresh every 3 seconds
                try {
                    val ctx = requireContext()

                    // Update CPU frequencies
                    val cpuFreqContainer = view.findViewById<LinearLayout>(R.id.cpuFreqContainer)
                    cpuFreqContainer.removeAllViews()
                    val freqs = DeviceInfoCollector.getCoreFrequencies()
                    val maxFreq = DeviceInfoCollector.getCpuMaxFreq()

                    for ((core, freq) in freqs) {
                        val row = LayoutInflater.from(ctx)
                            .inflate(R.layout.item_info_row, cpuFreqContainer, false)
                        row.findViewById<TextView>(R.id.tvLabel).text = "Core $core"
                        row.findViewById<TextView>(R.id.tvValue).apply {
                            text = if (freq > 0) "${freq / 1000} MHz" else "Offline"
                            setTextColor(
                                if (freq > 0)
                                    resources.getColor(R.color.accent_green, null)
                                else
                                    resources.getColor(R.color.text_tertiary, null)
                            )
                        }
                        cpuFreqContainer.addView(row)
                    }

                    // Update memory usage
                    view.findViewById<ProgressBar>(R.id.memProgressBar).progress =
                        DeviceInfoCollector.getMemoryUsagePercent(ctx)

                    // Update battery
                    view.findViewById<ProgressBar>(R.id.batteryProgressBar).progress =
                        DeviceInfoCollector.getBatteryLevel(ctx)

                } catch (_: Exception) {}
            }
        }
    }

    private fun populateSection(container: LinearLayout, items: List<InfoItem>) {
        container.removeAllViews()
        val inflater = LayoutInflater.from(requireContext())

        for (item in items) {
            val row = inflater.inflate(R.layout.item_info_row, container, false)
            row.findViewById<TextView>(R.id.tvLabel).text = item.label
            row.findViewById<TextView>(R.id.tvValue).text = item.value
            container.addView(row)
        }
    }
}
