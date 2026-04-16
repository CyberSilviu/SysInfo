package com.sysinfo.app.utils

import kotlinx.coroutines.*
import java.io.File
import java.io.RandomAccessFile
import kotlin.math.*
import kotlin.system.measureTimeMillis

/**
 * Benchmark engine — 5 hardware performance tests.
 * Scores normalized to a Snapdragon 865 reference device (max 10,000 pts/test).
 */
object BenchmarkEngine {

    // Reference times on a mid-high-range device (Snapdragon 865 class)
    private const val REF_SINGLE_CORE_MS  = 1800.0   // single-core FP
    private const val REF_INTEGER_MS      = 1200.0   // integer / logic ops
    private const val REF_MULTI_CORE_MS   = 400.0    // multi-core FP
    private const val REF_MEMORY_MS       = 1200.0   // memory bandwidth
    private const val REF_STORAGE_MS      = 1800.0   // storage I/O
    private const val MAX_SCORE           = 10_000

    data class BenchmarkResult(
        val score: Int,
        val details: String,
        val durationMs: Long
    )

    // ==================== CPU SINGLE-CORE (floating point) ====================

    suspend fun runCpuSingleCore(onProgress: (Int) -> Unit): BenchmarkResult =
        withContext(Dispatchers.Default) {
            onProgress(5)
            val iterations = 60_000_000
            var result = 0.0
            val elapsed = measureTimeMillis {
                for (i in 0 until iterations) {
                    result += sin(i.toDouble()) * cos(i.toDouble()) + sqrt(i.toDouble() + 1.0)
                    if (i % (iterations / 19) == 0) {
                        onProgress(5 + (i.toFloat() / iterations * 90).toInt())
                    }
                }
            }
            onProgress(100)
            val score = ((REF_SINGLE_CORE_MS / elapsed) * 5000).toInt().coerceIn(1, MAX_SCORE)
            BenchmarkResult(
                score = score,
                details = "$iterations iterații • ${elapsed}ms",
                durationMs = elapsed
            )
        }

    // ==================== CPU INTEGER (bit-ops, hashing) ====================

    suspend fun runCpuInteger(onProgress: (Int) -> Unit): BenchmarkResult =
        withContext(Dispatchers.Default) {
            onProgress(5)
            val iterations = 80_000_000
            var acc = 0L
            val elapsed = measureTimeMillis {
                for (i in 0 until iterations) {
                    // Integer-heavy: multiply, xor, shift, modulo
                    acc = (acc * 6364136223846793005L + 1442695040888963407L) xor (i.toLong() shl 3)
                    acc = acc.rotateLeft(13) xor (acc ushr 7)
                    if (i % (iterations / 19) == 0) {
                        onProgress(5 + (i.toFloat() / iterations * 90).toInt())
                    }
                }
            }
            onProgress(100)
            val score = ((REF_INTEGER_MS / elapsed) * 5000).toInt().coerceIn(1, MAX_SCORE)
            val mops = iterations / (elapsed / 1000.0) / 1_000_000
            BenchmarkResult(
                score = score,
                details = "${String.format("%.0f", mops)} Mops/s • ${elapsed}ms",
                durationMs = elapsed
            )
        }

    // ==================== CPU MULTI-CORE ====================

    suspend fun runCpuMultiCore(onProgress: (Int) -> Unit): BenchmarkResult =
        withContext(Dispatchers.Default) {
            onProgress(5)
            val numCores = Runtime.getRuntime().availableProcessors()
            val iterationsPerCore = 60_000_000 / numCores
            val progressCounter = java.util.concurrent.atomic.AtomicInteger(0)

            val elapsed = measureTimeMillis {
                val jobs = (0 until numCores).map {
                    async {
                        var result = 0.0
                        for (i in 0 until iterationsPerCore) {
                            result += sin(i.toDouble()) * cos(i.toDouble()) + sqrt(i.toDouble() + 1.0)
                            if (i % (iterationsPerCore / 10) == 0) {
                                val total = progressCounter.incrementAndGet()
                                onProgress(5 + (total.toFloat() / (numCores * 10) * 90).toInt())
                            }
                        }
                        result
                    }
                }
                jobs.awaitAll()
            }

            onProgress(100)
            val score = ((REF_MULTI_CORE_MS / elapsed) * 5000 * numCores / 4)
                .toInt().coerceIn(1, MAX_SCORE)
            BenchmarkResult(
                score = score,
                details = "$numCores nuclee • ${elapsed}ms",
                durationMs = elapsed
            )
        }

    // ==================== MEMORY BANDWIDTH ====================

    suspend fun runMemoryBenchmark(onProgress: (Int) -> Unit): BenchmarkResult =
        withContext(Dispatchers.Default) {
            onProgress(5)
            val arraySize = 16_000_000   // 64 MB as int array
            val passes    = 4

            val elapsed = measureTimeMillis {
                val array = IntArray(arraySize)

                // Sequential write
                for (pass in 0 until passes) {
                    for (i in array.indices) array[i] = i * 2654435761.toInt() + pass
                    onProgress(5 + (pass + 1) * 8)
                }

                // Sequential read + sum
                var sum = 0L
                for (pass in 0 until passes) {
                    for (i in array.indices) sum += array[i]
                    onProgress(37 + (pass + 1) * 8)
                }

                // Random-access (cache-miss simulation)
                val rng = java.util.Random(0xDEADBEEF)
                for (pass in 0 until passes) {
                    for (i in 0 until arraySize / 8) {
                        val idx = (rng.nextInt() and 0x7FFFFFFF) % arraySize
                        array[idx] = array[idx] xor i
                    }
                    onProgress(69 + (pass + 1) * 7)
                }
            }

            onProgress(100)
            val score = ((REF_MEMORY_MS / elapsed) * 5000).toInt().coerceIn(1, MAX_SCORE)
            // bytes moved: (write + read + random) × passes × 4 bytes
            val bytesMoved = arraySize.toLong() * passes * 4 * 2 + (arraySize.toLong() / 8) * passes * 4
            val bandwidthMBps = bytesMoved / (elapsed / 1000.0) / (1024 * 1024)
            BenchmarkResult(
                score = score,
                details = "${String.format("%.0f", bandwidthMBps)} MB/s • ${elapsed}ms",
                durationMs = elapsed
            )
        }

    // ==================== STORAGE I/O ====================

    suspend fun runStorageBenchmark(
        cacheDir: File,
        onProgress: (Int) -> Unit
    ): BenchmarkResult = withContext(Dispatchers.IO) {
        onProgress(5)
        val testFile  = File(cacheDir, "bench_io_test.tmp")
        val blockSize = 4096
        val totalBlocks = 4096  // 16 MB total
        val buffer = ByteArray(blockSize) { (it % 256).toByte() }

        val elapsed = measureTimeMillis {
            try {
                RandomAccessFile(testFile, "rw").use { raf ->
                    for (i in 0 until totalBlocks) {
                        raf.write(buffer)
                        if (i % (totalBlocks / 10) == 0)
                            onProgress(5 + (i.toFloat() / totalBlocks * 45).toInt())
                    }
                    raf.fd.sync()
                }
            } catch (_: Exception) {}
            onProgress(50)
            try {
                RandomAccessFile(testFile, "r").use { raf ->
                    val readBuf = ByteArray(blockSize)
                    var read = 0
                    while (read < totalBlocks) {
                        raf.read(readBuf)
                        read++
                        if (read % (totalBlocks / 10) == 0)
                            onProgress(50 + (read.toFloat() / totalBlocks * 45).toInt())
                    }
                }
            } catch (_: Exception) {}
        }

        testFile.delete()
        onProgress(100)

        val score = ((REF_STORAGE_MS / elapsed) * 5000).toInt().coerceIn(1, MAX_SCORE)
        val totalBytes = blockSize.toLong() * totalBlocks * 2
        val throughputMBps = totalBytes / (elapsed / 1000.0) / (1024 * 1024)
        BenchmarkResult(
            score = score,
            details = "${String.format("%.0f", throughputMBps)} MB/s • ${elapsed}ms",
            durationMs = elapsed
        )
    }
}
