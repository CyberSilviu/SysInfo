package com.sysinfo.app.utils

import kotlinx.coroutines.*
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.*

/**
 * Stress test engine — CPU / Memory / Mixed.
 * Reports real CPU usage via /proc/stat sampling and iterations/second.
 */
class StressTestEngine {

    enum class StressType { CPU, MEMORY, MIXED, GPU, MIXED_ALL }

    data class StressStats(
        val elapsedSeconds: Int,
        val cpuLoadPercent: Int,
        val temperatureCelsius: Float,
        val activeThreads: Int,
        val iterationsCompleted: Long,
        val iterationsPerSec: Long,
        val memoryAllocatedMB: Int
    )

    private val isRunning         = AtomicBoolean(false)
    private val activeThreadCount = AtomicInteger(0)
    val totalIterations           = AtomicLong(0)   // public so GLSurfaceView can increment it
    private var stressJob: Job?   = null

    fun reportGpuFrame() { totalIterations.incrementAndGet() }

    // CPU stat snapshot for delta calculations
    private data class CpuStat(val idle: Long, val total: Long)

    val running: Boolean get() = isRunning.get()

    fun start(
        scope: CoroutineScope,
        type: StressType,
        threadCount: Int,
        durationSeconds: Int,
        onStats: (StressStats) -> Unit,
        onComplete: (String) -> Unit
    ) {
        if (isRunning.get()) return
        isRunning.set(true)
        activeThreadCount.set(0)
        totalIterations.set(0)

        stressJob = scope.launch(Dispatchers.Default) {
            val startTime  = System.currentTimeMillis()
            val memChunks  = mutableListOf<ByteArray>()
            var prevStat   = readCpuStat()
            var prevIter   = 0L

            // Launch workers
            val workers = (0 until threadCount).map { idx ->
                async {
                    activeThreadCount.incrementAndGet()
                    try {
                        when (type) {
                            StressType.CPU       -> cpuWorker()
                            StressType.MEMORY    -> memoryWorker(memChunks)
                            StressType.GPU       -> gpuWorker()
                            StressType.MIXED     ->
                                if (idx % 2 == 0) cpuWorker() else memoryWorker(memChunks)
                            StressType.MIXED_ALL -> when (idx % 3) {
                                0    -> cpuWorker()
                                1    -> memoryWorker(memChunks)
                                else -> gpuWorker()
                            }
                        }
                    } finally {
                        activeThreadCount.decrementAndGet()
                    }
                }
            }

            // Monitor loop — fires every second
            val monitorJob = launch {
                while (isActive && isRunning.get()) {
                    delay(1000)
                    val elapsed = ((System.currentTimeMillis() - startTime) / 1000).toInt()

                    // Real CPU usage from /proc/stat
                    val curStat  = readCpuStat()
                    val cpuLoad  = calculateCpuLoad(prevStat, curStat)
                    prevStat     = curStat

                    val temp    = DeviceInfoCollector.getCpuTemperature()
                    val curIter = totalIterations.get()
                    val ips     = curIter - prevIter
                    prevIter    = curIter

                    val allocMB = synchronized(memChunks) {
                        memChunks.sumOf { it.size } / (1024 * 1024)
                    }

                    withContext(Dispatchers.Main) {
                        onStats(StressStats(
                            elapsedSeconds       = elapsed,
                            cpuLoadPercent       = cpuLoad,
                            temperatureCelsius   = temp,
                            activeThreads        = activeThreadCount.get(),
                            iterationsCompleted  = curIter,
                            iterationsPerSec     = ips,
                            memoryAllocatedMB    = allocMB
                        ))
                    }

                    if (durationSeconds > 0 && elapsed >= durationSeconds) {
                        isRunning.set(false)
                        break
                    }
                }
            }

            monitorJob.join()
            isRunning.set(false)
            workers.forEach { it.cancel() }
            synchronized(memChunks) { memChunks.clear() }
            System.gc()

            val totalTime = ((System.currentTimeMillis() - startTime) / 1000).toInt()
            val summary = "Test finalizat: ${totalTime}s\n" +
                          "Iterații: ${totalIterations.get()}\n" +
                          "Thread-uri: $threadCount\n" +
                          "Tip: ${type.name}"

            withContext(Dispatchers.Main) { onComplete(summary) }
        }
    }

    fun stop() {
        isRunning.set(false)
        stressJob?.cancel()
    }

    // ── Workers ──────────────────────────────────────────────────────────────

    private suspend fun cpuWorker() {
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_URGENT_AUDIO)
        var x = 1.0
        while (isRunning.get()) {
            repeat(1_000_000) { i ->
                x = sin(x) * cos(x) + sqrt(abs(x) + 1.0) + tan(x * 0.001)
                x = ln(abs(x) + 1.0) * exp(x * 0.0001) + x.pow(1.001)
                x += (i.toLong() xor 0xDEADBEEFL).toDouble() * 1e-20
            }
            totalIterations.addAndGet(1_000_000)
            yield()
        }
    }

    private suspend fun memoryWorker(chunks: MutableList<ByteArray>) {
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_URGENT_AUDIO)
        val chunkSize = 4 * 1024 * 1024  // 4 MB per chunk
        val maxChunks = 200              // up to ~800 MB pressure

        while (isRunning.get()) {
            try {
                val chunk = ByteArray(chunkSize)
                for (i in chunk.indices step 64) chunk[i] = (i % 256).toByte()

                synchronized(chunks) {
                    if (chunks.size >= maxChunks) chunks.removeAt(0)
                    chunks.add(chunk)
                }

                // Read-back verification
                var checksum = 0L
                for (i in chunk.indices step 64) checksum += chunk[i]

                totalIterations.addAndGet(chunkSize.toLong())
                delay(5)
            } catch (_: OutOfMemoryError) {
                synchronized(chunks) {
                    if (chunks.size > 8) repeat(chunks.size / 2) { chunks.removeAt(0) }
                }
                System.gc()
                delay(200)
            }
            yield()
        }
    }

    private suspend fun gpuWorker() {
        // Real GPU rendering is handled by GpuStressRenderer on the GL thread.
        // This coroutine just stays alive while the GLSurfaceView renders.
        while (isRunning.get()) { delay(200) }
    }

    // ── CPU stat helpers ─────────────────────────────────────────────────────

    private fun readCpuStat(): CpuStat {
        return try {
            val line = File("/proc/stat").bufferedReader().readLine() ?: return CpuStat(0, 1)
            val parts = line.trim().split("\\s+".toRegex())
            // fields: cpu user nice system idle iowait irq softirq steal guest guestNice
            if (parts.size < 5) return CpuStat(0, 1)
            val user    = parts[1].toLongOrNull() ?: 0L
            val nice    = parts[2].toLongOrNull() ?: 0L
            val system  = parts[3].toLongOrNull() ?: 0L
            val idle    = parts[4].toLongOrNull() ?: 0L
            val iowait  = if (parts.size > 5) parts[5].toLongOrNull() ?: 0L else 0L
            val irq     = if (parts.size > 6) parts[6].toLongOrNull() ?: 0L else 0L
            val softirq = if (parts.size > 7) parts[7].toLongOrNull() ?: 0L else 0L
            val total   = user + nice + system + idle + iowait + irq + softirq
            CpuStat(idle = idle + iowait, total = total)
        } catch (_: Exception) {
            CpuStat(0, 1)
        }
    }

    private fun calculateCpuLoad(prev: CpuStat, cur: CpuStat): Int {
        val totalDelta = cur.total - prev.total
        val idleDelta  = cur.idle  - prev.idle
        if (totalDelta <= 0) return 0
        return ((1.0 - idleDelta.toDouble() / totalDelta) * 100).toInt().coerceIn(0, 100)
    }
}
