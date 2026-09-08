package com.droidlens.app.util

import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import androidx.camera.core.ImageProxy
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer

object ImageConverter {

    /**
     * Convierte un ImageProxy (YUV_420_888 de CameraX) a un ByteArray codificado en JPEG.
     */
    fun imageProxyToJpeg(image: ImageProxy, quality: Int = 80): ByteArray? {
        val yuvBytes = yuv420888ToNv21(image) ?: return null
        val outStream = ByteArrayOutputStream()
        val yuvImage = YuvImage(
            yuvBytes,
            ImageFormat.NV21,
            image.width,
            image.height,
            null
        )
        val success = yuvImage.compressToJpeg(
            Rect(0, 0, image.width, image.height),
            quality,
            outStream
        )
        return if (success) outStream.toByteArray() else null
    }

    private fun yuv420888ToNv21(image: ImageProxy): ByteArray? {
        val width = image.width
        val height = image.height
        val ySize = width * height
        val uvSize = width * height / 2
        val nv21 = ByteArray(ySize + uvSize)

        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]

        val yBuffer: ByteBuffer = yPlane.buffer
        val uBuffer: ByteBuffer = uPlane.buffer
        val vBuffer: ByteBuffer = vPlane.buffer

        val yRowStride = yPlane.rowStride
        val yPixelStride = yPlane.pixelStride

        var pos = 0

        // 1. Copiar plano Y
        if (yPixelStride == 1) {
            for (row in 0 until height) {
                yBuffer.position(row * yRowStride)
                yBuffer.get(nv21, pos, width)
                pos += width
            }
        } else {
            for (row in 0 until height) {
                yBuffer.position(row * yRowStride)
                for (col in 0 until width) {
                    nv21[pos++] = yBuffer.get(col * yPixelStride)
                }
            }
        }

        // 2. Intercalar planos V y U (NV21 espera [Y...][V, U, V, U...])
        val uvRowStride = vPlane.rowStride
        val uvPixelStride = vPlane.pixelStride
        val uvWidth = width / 2
        val uvHeight = height / 2

        for (row in 0 until uvHeight) {
            val vRowPos = row * uvRowStride
            val uRowPos = row * uPlane.rowStride
            for (col in 0 until uvWidth) {
                val vByte = vBuffer.get(vRowPos + col * uvPixelStride)
                val uByte = uBuffer.get(uRowPos + col * uPlane.pixelStride)
                nv21[pos++] = vByte
                nv21[pos++] = uByte
            }
        }

        return nv21
    }
}
