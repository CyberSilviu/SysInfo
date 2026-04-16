package com.sysinfo.app.ui.benchmark

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ProgressBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.sysinfo.app.R
import com.sysinfo.app.utils.BenchmarkEngine
import kotlinx.coroutines.launch

class BenchmarkFragment : Fragment() {

    private var isRunning = false

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? = inflater.inflate(R.layout.fragment_benchmark, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        view.findViewById<MaterialButton>(R.id.btnRunAll).setOnClickListener {
            if (!isRunning) runAllBenchmarks(view)
        }
    }

    private fun runAllBenchmarks(view: View) {
        isRunning = true
        val btnRunAll = view.findViewById<MaterialButton>(R.id.btnRunAll)
        btnRunAll.isEnabled = false
        btnRunAll.text = "Rulează..."

        // Reset all scores
        listOf(R.id.tvTotalScore, R.id.tvScoreSingle, R.id.tvScoreInteger,
               R.id.tvScoreMulti, R.id.tvScoreMemory, R.id.tvScoreStorage)
            .forEach { view.findViewById<TextView>(it).text = "..." }
        view.findViewById<TextView>(R.id.tvScoreRating).text = "Rulează toate testele..."
        listOf(R.id.progressSingle, R.id.progressInteger, R.id.progressMulti,
               R.id.progressMemory, R.id.progressStorage)
            .forEach { view.findViewById<ProgressBar>(it).progress = 0 }

        viewLifecycleOwner.lifecycleScope.launch {
            var totalScore = 0

            // 1. CPU Single-Core
            setStatus(view, R.id.tvStatusSingle, "Rulează...", R.color.accent_green)
            val single = BenchmarkEngine.runCpuSingleCore { p ->
                view.findViewById<ProgressBar>(R.id.progressSingle).progress = p
            }
            view.findViewById<TextView>(R.id.tvScoreSingle).text = "${single.score}"
            setStatus(view, R.id.tvStatusSingle, single.details, R.color.text_secondary)
            totalScore += single.score

            // 2. CPU Integer
            setStatus(view, R.id.tvStatusInteger, "Rulează...", R.color.accent_cyan)
            val integer = BenchmarkEngine.runCpuInteger { p ->
                view.findViewById<ProgressBar>(R.id.progressInteger).progress = p
            }
            view.findViewById<TextView>(R.id.tvScoreInteger).text = "${integer.score}"
            setStatus(view, R.id.tvStatusInteger, integer.details, R.color.text_secondary)
            totalScore += integer.score

            // 3. CPU Multi-Core
            setStatus(view, R.id.tvStatusMulti, "Rulează...", R.color.accent_orange)
            val multi = BenchmarkEngine.runCpuMultiCore { p ->
                view.findViewById<ProgressBar>(R.id.progressMulti).progress = p
            }
            view.findViewById<TextView>(R.id.tvScoreMulti).text = "${multi.score}"
            setStatus(view, R.id.tvStatusMulti, multi.details, R.color.text_secondary)
            totalScore += multi.score

            // 4. Memory
            setStatus(view, R.id.tvStatusMemory, "Rulează...", R.color.accent_purple)
            val memory = BenchmarkEngine.runMemoryBenchmark { p ->
                view.findViewById<ProgressBar>(R.id.progressMemory).progress = p
            }
            view.findViewById<TextView>(R.id.tvScoreMemory).text = "${memory.score}"
            setStatus(view, R.id.tvStatusMemory, memory.details, R.color.text_secondary)
            totalScore += memory.score

            // 5. Storage I/O
            setStatus(view, R.id.tvStatusStorage, "Rulează...", R.color.accent_yellow)
            val storage = BenchmarkEngine.runStorageBenchmark(requireContext().cacheDir) { p ->
                view.findViewById<ProgressBar>(R.id.progressStorage).progress = p
            }
            view.findViewById<TextView>(R.id.tvScoreStorage).text = "${storage.score}"
            setStatus(view, R.id.tvStatusStorage, storage.details, R.color.text_secondary)
            totalScore += storage.score

            // Total (average of 5)
            val avg = totalScore / 5
            view.findViewById<TextView>(R.id.tvTotalScore).text = "$avg"
            view.findViewById<TextView>(R.id.tvScoreRating).text = getRating(avg)

            btnRunAll.isEnabled = true
            btnRunAll.text = getString(R.string.btn_run_all)
            isRunning = false
        }
    }

    private fun setStatus(view: View, id: Int, text: String, colorRes: Int) {
        val tv = view.findViewById<TextView>(id)
        tv.text = text
        tv.setTextColor(resources.getColor(colorRes, null))
    }

    private fun getRating(score: Int): String = when {
        score >= 8000 -> "Flagship — performanță excelentă"
        score >= 6000 -> "High-end — performanță foarte bună"
        score >= 4000 -> "Mid-range — performanță bună"
        score >= 2000 -> "Entry-level — performanță medie"
        else          -> "Low-end — performanță scăzută"
    }
}
