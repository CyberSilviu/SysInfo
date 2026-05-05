package com.sysinfo.app.ui.stresstest

import android.opengl.GLSurfaceView
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.google.android.material.chip.Chip
import com.sysinfo.app.BuildConfig
import com.sysinfo.app.R
import com.sysinfo.app.utils.StressTestEngine

class StressTestFragment : Fragment() {

    private val stressEngine = StressTestEngine()
    private var selectedDurationSeconds = 60
    private var selectedThreads = 4
    private var glSurfaceView: GLSurfaceView? = null
    private var gpuRenderer: GpuStressRenderer? = null
    private var gpuActive = false

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_stress_test, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setupControls(view)
    }

    override fun onResume() {
        super.onResume()
        // Only resume GL thread if renderer was already initialized
        if (gpuRenderer != null) glSurfaceView?.onResume()
    }

    override fun onPause() {
        super.onPause()
        // Only pause GL thread if renderer was already initialized
        if (gpuRenderer != null) glSurfaceView?.onPause()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        destroyGpuSurface()
        stressEngine.stop()
        glSurfaceView = null
    }

    private fun startGpuSurface(view: View) {
        val sv = view.findViewById<GLSurfaceView>(R.id.gpuSurface) ?: return
        // Make VISIBLE before setRenderer so EGL window surface exists when GL thread starts
        sv.visibility = View.VISIBLE
        if (gpuRenderer == null) {
            sv.setEGLContextClientVersion(2)
            val renderer = GpuStressRenderer(stressEngine.totalIterations)
            sv.setRenderer(renderer)
            sv.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
            glSurfaceView = sv
            gpuRenderer   = renderer
        } else {
            sv.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }
        gpuActive = true
    }

    private fun stopGpuSurface() {
        glSurfaceView?.renderMode = GLSurfaceView.RENDERMODE_WHEN_DIRTY
        glSurfaceView?.visibility = View.GONE
        gpuActive = false
    }

    private fun destroyGpuSurface() {
        glSurfaceView?.renderMode = GLSurfaceView.RENDERMODE_WHEN_DIRTY
        glSurfaceView?.visibility = View.GONE
        gpuActive    = false
        gpuRenderer  = null
    }

    private fun setupControls(view: View) {
        val btnStart = view.findViewById<MaterialButton>(R.id.btnStartStress)
        val tvThreadCount = view.findViewById<TextView>(R.id.tvThreadCount)
        val seekThreads = view.findViewById<SeekBar>(R.id.seekThreads)

        // Free edition: hide everything except CPU stress
        if (BuildConfig.IS_FREE) {
            view.findViewById<View>(R.id.rbMemoryStress).visibility  = View.GONE
            view.findViewById<View>(R.id.rbMixedStress).visibility   = View.GONE
            view.findViewById<View>(R.id.rbGpuStress).visibility     = View.GONE
            view.findViewById<View>(R.id.rbMixedAllStress).visibility = View.GONE
            view.findViewById<View>(R.id.gpuSurface).visibility      = View.GONE
        }

        // Set default and max thread count to number of CPU cores
        val defaultThreads = Runtime.getRuntime().availableProcessors()
        selectedThreads = defaultThreads
        seekThreads.max = defaultThreads
        seekThreads.progress = defaultThreads
        tvThreadCount.text = "$defaultThreads"

        // Thread count slider
        seekThreads.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                selectedThreads = progress.coerceAtLeast(1)
                tvThreadCount.text = "$selectedThreads"
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        // Duration chips
        val chip1min = view.findViewById<Chip>(R.id.chip1min)
        val chip5min = view.findViewById<Chip>(R.id.chip5min)
        val chip15min = view.findViewById<Chip>(R.id.chip15min)
        val chipInfinite = view.findViewById<Chip>(R.id.chipInfinite)

        val allChips = listOf(chip1min, chip5min, chip15min, chipInfinite)
        val durations = mapOf(chip1min to 60, chip5min to 300, chip15min to 900, chipInfinite to 0)

        for (chip in allChips) {
            chip.setOnClickListener {
                allChips.forEach { c -> c.isChecked = (c == chip) }
                selectedDurationSeconds = durations[chip] ?: 60
            }
        }

        // Start/Stop button
        btnStart.setOnClickListener {
            if (stressEngine.running) {
                stopStressTest(view)
            } else {
                startStressTest(view)
            }
        }
    }

    private fun startStressTest(view: View) {
        val btnStart = view.findViewById<MaterialButton>(R.id.btnStartStress)
        val tvStatus = view.findViewById<TextView>(R.id.tvStressStatus)
        val tvLog = view.findViewById<TextView>(R.id.tvStressLog)
        val rgType = view.findViewById<RadioGroup>(R.id.rgStressType)

        // Determine stress type
        val stressType = when (rgType.checkedRadioButtonId) {
            R.id.rbCpuStress      -> StressTestEngine.StressType.CPU
            R.id.rbMemoryStress   -> StressTestEngine.StressType.MEMORY
            R.id.rbMixedStress    -> StressTestEngine.StressType.MIXED
            R.id.rbGpuStress      -> StressTestEngine.StressType.GPU
            R.id.rbMixedAllStress -> StressTestEngine.StressType.MIXED_ALL
            else                  -> StressTestEngine.StressType.CPU
        }

        // Update UI
        btnStart.text = getString(R.string.btn_stop_stress)
        btnStart.setBackgroundColor(resources.getColor(R.color.accent_red, null))
        tvStatus.text = getString(R.string.stress_status_running)
        tvStatus.setTextColor(resources.getColor(R.color.accent_green, null))

        val durationText = if (selectedDurationSeconds > 0) "${selectedDurationSeconds}s" else "∞"
        tvLog.append("▶ Start ${stressType.name} • ${selectedThreads} threads • $durationText\n")

        // Start GPU surface when needed
        if (stressType == StressTestEngine.StressType.GPU ||
            stressType == StressTestEngine.StressType.MIXED_ALL) {
            startGpuSurface(view)
        }

        // Start engine
        stressEngine.start(
            scope = viewLifecycleOwner.lifecycleScope,
            type = stressType,
            threadCount = selectedThreads,
            durationSeconds = selectedDurationSeconds,
            onStats = { stats ->
                updateLiveStats(view, stats)
            },
            onComplete = { summary ->
                tvLog.append("✓ $summary\n\n")
                stopGpuSurface()
                resetButton(view)
            }
        )
    }

    private fun stopStressTest(view: View) {
        stressEngine.stop()
        stopGpuSurface()
        val tvLog = view.findViewById<TextView>(R.id.tvStressLog)
        tvLog.append("■ Test oprit manual.\n\n")
        resetButton(view)
    }

    private fun resetButton(view: View) {
        val btnStart = view.findViewById<MaterialButton>(R.id.btnStartStress)
        val tvStatus = view.findViewById<TextView>(R.id.tvStressStatus)

        btnStart.text = getString(R.string.btn_start_stress)
        btnStart.setBackgroundColor(resources.getColor(R.color.accent_green, null))
        tvStatus.text = getString(R.string.stress_status_done)
        tvStatus.setTextColor(resources.getColor(R.color.text_secondary, null))
    }

    private fun updateLiveStats(view: View, stats: StressTestEngine.StressStats) {
        // Elapsed time
        val h = stats.elapsedSeconds / 3600
        val m = (stats.elapsedSeconds % 3600) / 60
        val s = stats.elapsedSeconds % 60
        view.findViewById<TextView>(R.id.tvElapsedTime).text =
            String.format("%02d:%02d:%02d", h, m, s)

        // CPU Load (real, from /proc/stat)
        val tvCpuLoad = view.findViewById<TextView>(R.id.tvCpuLoad)
        tvCpuLoad.text = "${stats.cpuLoadPercent}%"
        tvCpuLoad.setTextColor(resources.getColor(when {
            stats.cpuLoadPercent > 90 -> R.color.accent_red
            stats.cpuLoadPercent > 70 -> R.color.accent_orange
            else                      -> R.color.accent_green
        }, null))

        // Temperature
        val tvTemp = view.findViewById<TextView>(R.id.tvTemperature)
        if (stats.temperatureCelsius > 0) {
            tvTemp.text = "${String.format("%.1f", stats.temperatureCelsius)}°C"
            tvTemp.setTextColor(resources.getColor(when {
                stats.temperatureCelsius > 80 -> R.color.accent_red
                stats.temperatureCelsius > 60 -> R.color.accent_orange
                else                          -> R.color.accent_green
            }, null))
        } else {
            tvTemp.text = "--°C"
        }

        // Active threads
        view.findViewById<TextView>(R.id.tvActiveThreads).text = "${stats.activeThreads}"

        // Iterations/sec
        val ips = stats.iterationsPerSec
        view.findViewById<TextView>(R.id.tvIterPerSec).text = when {
            ips >= 1_000_000 -> "${String.format("%.1f", ips / 1_000_000.0)}M"
            ips >= 1_000     -> "${String.format("%.1f", ips / 1_000.0)}K"
            else             -> "$ips"
        }

        // RAM allocated
        view.findViewById<TextView>(R.id.tvRamAllocated).text = "${stats.memoryAllocatedMB} MB"

        // Total iterations
        val total = stats.iterationsCompleted
        view.findViewById<TextView>(R.id.tvTotalIter).text = when {
            total >= 1_000_000_000 -> "${String.format("%.1f", total / 1_000_000_000.0)}G"
            total >= 1_000_000     -> "${String.format("%.1f", total / 1_000_000.0)}M"
            total >= 1_000         -> "${String.format("%.1f", total / 1_000.0)}K"
            else                   -> "$total"
        }
    }
}
