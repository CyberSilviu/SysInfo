package com.sysinfo.app.ui.stresstest

import android.opengl.GLES20
import android.opengl.GLSurfaceView
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.util.concurrent.atomic.AtomicLong
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

class GpuStressRenderer(private val frameCounter: AtomicLong) : GLSurfaceView.Renderer {

    companion object {
        private const val PASSES  = 60      // must be even
        private const val FBO_W   = 1920    // fixed large FBO — forces real GPU work
        private const val FBO_H   = 1080    // regardless of surface size
    }

    private var stressProg  = 0
    private var blitProg    = 0
    private val fboIds      = IntArray(2)
    private val texIds      = IntArray(2)
    private var fboReady    = false
    private var vertexBuf: FloatBuffer? = null
    private var surfW       = 1
    private var surfH       = 1
    private var startTime   = System.nanoTime()

    // Uniform locations — stress program
    private var sPos  = -1
    private var sTime = -1
    private var sPrev = -1
    // Uniform locations — blit program
    private var bPos  = -1
    private var bTex  = -1

    private val quadVerts = floatArrayOf(
        -1f, -1f,   1f, -1f,   -1f,  1f,
         1f, -1f,   1f,  1f,   -1f,  1f
    )

    private val vertSrc = """
        attribute vec2 aPos;
        varying vec2 vUV;
        void main() {
            vUV = aPos * 0.5 + 0.5;
            gl_Position = vec4(aPos, 0.0, 1.0);
        }
    """.trimIndent()

    // 80 heavy iterations per pixel; reads from previous-pass texture for dependency chain
    private val stressFragSrc = """
        precision highp float;
        uniform float uTime;
        uniform sampler2D uPrev;
        varying vec2 vUV;
        void main() {
            vec4 seed = texture2D(uPrev, vUV);
            float v = seed.r * 2.0 - 1.0;
            float w = seed.g * 2.0 - 1.0;
            float s = seed.b * 2.0 - 1.0;
            float q = seed.a * 2.0 - 1.0;
            for (int i = 0; i < 80; i++) {
                float fi = float(i) * 0.09;
                v += sin(vUV.x * 19.0 + uTime * 1.1 + fi)
                   * cos(vUV.y * 17.0 - uTime * 1.3 + fi);
                w += cos(length(vUV - vec2(0.5)) * 25.0 - uTime * 2.0 + fi * 0.5);
                s += sin(vUV.x * vUV.y * 13.0 + uTime * 0.8 + fi)
                   + cos(vUV.x * 7.0  - vUV.y * 11.0 + uTime * 1.5 + fi);
                q += sin(v * 0.3 + w * 0.2 - s * 0.1 + uTime * 0.6 + fi);
            }
            gl_FragColor = vec4(
                fract(abs(v) * 0.1 + 0.5),
                fract(abs(w) * 0.1 + 0.5),
                fract(abs(s) * 0.1 + 0.5),
                fract(abs(q) * 0.1 + 0.5)
            );
        }
    """.trimIndent()

    private val blitFragSrc = """
        precision mediump float;
        uniform sampler2D uTex;
        varying vec2 vUV;
        void main() {
            gl_FragColor = texture2D(uTex, vUV);
        }
    """.trimIndent()

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        startTime = System.nanoTime()

        stressProg = buildProgram(vertSrc, stressFragSrc).also {
            if (it == 0) return
            sPos  = GLES20.glGetAttribLocation(it,  "aPos")
            sTime = GLES20.glGetUniformLocation(it, "uTime")
            sPrev = GLES20.glGetUniformLocation(it, "uPrev")
        }

        blitProg = buildProgram(vertSrc, blitFragSrc).also {
            if (it == 0) return
            bPos = GLES20.glGetAttribLocation(it,  "aPos")
            bTex = GLES20.glGetUniformLocation(it, "uTex")
        }

        val bb = ByteBuffer.allocateDirect(quadVerts.size * 4)
        bb.order(ByteOrder.nativeOrder())
        vertexBuf = bb.asFloatBuffer().apply { put(quadVerts); position(0) }

        setupFBOs()
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        surfW = width; surfH = height
        // FBOs stay at fixed FBO_W × FBO_H — no resize needed
    }

    override fun onDrawFrame(gl: GL10?) {
        if (stressProg == 0 || blitProg == 0 || !fboReady) return
        val buf = vertexBuf ?: return

        val t = (System.nanoTime() - startTime) / 1_000_000_000f

        // ── 60 ping-pong stress passes at 1920×1080 ───────────────────────────
        GLES20.glViewport(0, 0, FBO_W, FBO_H)
        GLES20.glUseProgram(stressProg)
        GLES20.glUniform1f(sTime, t)
        GLES20.glEnableVertexAttribArray(sPos)
        GLES20.glVertexAttribPointer(sPos, 2, GLES20.GL_FLOAT, false, 0, buf)

        var cur = 0
        repeat(PASSES) {
            GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, fboIds[cur])
            GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, texIds[1 - cur])
            GLES20.glUniform1i(sPrev, 0)
            GLES20.glDrawArrays(GLES20.GL_TRIANGLES, 0, 6)
            cur = 1 - cur
        }
        // PASSES is even → last write was into fboIds[1], so final texture = texIds[1]
        GLES20.glDisableVertexAttribArray(sPos)

        // ── Blit final FBO texture to screen ──────────────────────────────────
        GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, 0)
        GLES20.glViewport(0, 0, surfW, surfH)
        GLES20.glUseProgram(blitProg)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, texIds[1])
        GLES20.glUniform1i(bTex, 0)
        GLES20.glEnableVertexAttribArray(bPos)
        GLES20.glVertexAttribPointer(bPos, 2, GLES20.GL_FLOAT, false, 0, buf)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLES, 0, 6)
        GLES20.glDisableVertexAttribArray(bPos)

        frameCounter.incrementAndGet()
    }

    // ── FBO setup at fixed 1920×1080 ─────────────────────────────────────────

    private fun setupFBOs() {
        if (fboReady) {
            GLES20.glDeleteFramebuffers(2, fboIds, 0)
            GLES20.glDeleteTextures(2, texIds, 0)
            fboReady = false
        }

        GLES20.glGenFramebuffers(2, fboIds, 0)
        GLES20.glGenTextures(2, texIds, 0)

        for (i in 0..1) {
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, texIds[i])
            GLES20.glTexImage2D(
                GLES20.GL_TEXTURE_2D, 0, GLES20.GL_RGBA,
                FBO_W, FBO_H, 0, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, null
            )
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)

            GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, fboIds[i])
            GLES20.glFramebufferTexture2D(
                GLES20.GL_FRAMEBUFFER, GLES20.GL_COLOR_ATTACHMENT0,
                GLES20.GL_TEXTURE_2D, texIds[i], 0
            )
            if (GLES20.glCheckFramebufferStatus(GLES20.GL_FRAMEBUFFER) != GLES20.GL_FRAMEBUFFER_COMPLETE) {
                GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, 0)
                return
            }
        }

        GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, 0)
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, 0)
        fboReady = true
    }

    // ── Shader helpers ────────────────────────────────────────────────────────

    private fun compileShader(type: Int, src: String): Int {
        val sh = GLES20.glCreateShader(type)
        if (sh == 0) return 0
        GLES20.glShaderSource(sh, src)
        GLES20.glCompileShader(sh)
        val st = IntArray(1)
        GLES20.glGetShaderiv(sh, GLES20.GL_COMPILE_STATUS, st, 0)
        if (st[0] == 0) { GLES20.glDeleteShader(sh); return 0 }
        return sh
    }

    private fun buildProgram(vs: String, fs: String): Int {
        val v = compileShader(GLES20.GL_VERTEX_SHADER,   vs); if (v == 0) return 0
        val f = compileShader(GLES20.GL_FRAGMENT_SHADER, fs)
        if (f == 0) { GLES20.glDeleteShader(v); return 0 }
        val p = GLES20.glCreateProgram()
        if (p == 0) { GLES20.glDeleteShader(v); GLES20.glDeleteShader(f); return 0 }
        GLES20.glAttachShader(p, v); GLES20.glAttachShader(p, f)
        GLES20.glLinkProgram(p)
        GLES20.glDeleteShader(v); GLES20.glDeleteShader(f)
        val st = IntArray(1)
        GLES20.glGetProgramiv(p, GLES20.GL_LINK_STATUS, st, 0)
        if (st[0] == 0) { GLES20.glDeleteProgram(p); return 0 }
        return p
    }
}
