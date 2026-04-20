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

    private var program   = 0
    private var posAttr   = -1
    private var timeUnif  = -1
    private var resUnif   = -1
    private var vertexBuf: FloatBuffer? = null
    private var startTime = System.nanoTime()
    private var surfW = 1; private var surfH = 1

    // Full-screen quad — two triangles
    private val quadVerts = floatArrayOf(
        -1f, -1f,   1f, -1f,   -1f,  1f,
         1f, -1f,   1f,  1f,   -1f,  1f
    )

    // Vertex shader — pass-through
    private val vertSrc = """
        attribute vec2 aPosition;
        void main() { gl_Position = vec4(aPosition, 0.0, 1.0); }
    """.trimIndent()

    // Fragment shader — 32 heavy trig iterations per pixel.
    // 32 is the sweet spot: GPU-bound on all devices, but won't blow the
    // instruction-count limit that crashes older Adreno / Mali drivers.
    private val fragSrc = """
        precision highp float;
        uniform float uTime;
        uniform vec2  uResolution;
        void main() {
            vec2 uv = gl_FragCoord.xy / uResolution;
            float v = 0.0;
            float w = 0.0;
            for (int i = 0; i < 32; i++) {
                float fi = float(i) * 0.15;
                v += sin(uv.x * 14.0 + uTime + fi) * cos(uv.y * 14.0 - uTime * 1.3 + fi);
                v += sin(uv.x * uv.y * 9.0  + uTime * 0.9 + fi);
                w += cos(length(uv - vec2(0.5)) * 20.0 - uTime * 2.0 + fi * 0.5);
            }
            float r = 0.5 + 0.5 * sin(v * 1.5 + uTime);
            float g = 0.5 + 0.5 * cos(w * 2.3 - uTime * 0.7);
            float b = 0.5 + 0.5 * sin((v + w) * 3.1 + uTime);
            gl_FragColor = vec4(r, g, b, 1.0);
        }
    """.trimIndent()

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        startTime = System.nanoTime()

        val vert = compileShader(GLES20.GL_VERTEX_SHADER,   vertSrc)
        val frag = compileShader(GLES20.GL_FRAGMENT_SHADER, fragSrc)
        if (vert == 0 || frag == 0) {
            if (vert != 0) GLES20.glDeleteShader(vert)
            if (frag != 0) GLES20.glDeleteShader(frag)
            return
        }

        val prog = GLES20.glCreateProgram()
        if (prog == 0) { GLES20.glDeleteShader(vert); GLES20.glDeleteShader(frag); return }

        GLES20.glAttachShader(prog, vert)
        GLES20.glAttachShader(prog, frag)
        GLES20.glLinkProgram(prog)
        GLES20.glDeleteShader(vert)
        GLES20.glDeleteShader(frag)

        val status = IntArray(1)
        GLES20.glGetProgramiv(prog, GLES20.GL_LINK_STATUS, status, 0)
        if (status[0] == 0) { GLES20.glDeleteProgram(prog); return }

        program  = prog
        posAttr  = GLES20.glGetAttribLocation(program, "aPosition")
        timeUnif = GLES20.glGetUniformLocation(program, "uTime")
        resUnif  = GLES20.glGetUniformLocation(program, "uResolution")

        val bb = ByteBuffer.allocateDirect(quadVerts.size * 4)
        bb.order(ByteOrder.nativeOrder())
        vertexBuf = bb.asFloatBuffer().apply { put(quadVerts); position(0) }
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
        surfW = width; surfH = height
    }

    override fun onDrawFrame(gl: GL10?) {
        // Guard: do nothing if setup failed
        if (program == 0 || posAttr < 0 || vertexBuf == null) return

        val t = (System.nanoTime() - startTime) / 1_000_000_000f

        GLES20.glUseProgram(program)
        GLES20.glUniform1f(timeUnif, t)
        GLES20.glUniform2f(resUnif, surfW.toFloat(), surfH.toFloat())

        val buf = vertexBuf ?: return
        GLES20.glEnableVertexAttribArray(posAttr)
        GLES20.glVertexAttribPointer(posAttr, 2, GLES20.GL_FLOAT, false, 0, buf)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLES, 0, 6)
        GLES20.glDisableVertexAttribArray(posAttr)

        frameCounter.incrementAndGet()
    }

    private fun compileShader(type: Int, src: String): Int {
        val shader = GLES20.glCreateShader(type)
        if (shader == 0) return 0
        GLES20.glShaderSource(shader, src)
        GLES20.glCompileShader(shader)
        val status = IntArray(1)
        GLES20.glGetShaderiv(shader, GLES20.GL_COMPILE_STATUS, status, 0)
        if (status[0] == 0) { GLES20.glDeleteShader(shader); return 0 }
        return shader
    }
}
