package com.droidlens.app.camera

import android.content.Context
import android.util.Log
import android.util.Size
import androidx.camera.core.*
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.droidlens.app.util.ImageConverter
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class CameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView
) {

    interface FrameListener {
        fun onFrameCaptured(jpegBytes: ByteArray)
    }

    var frameListener: FrameListener? = null

    private var cameraProvider: ProcessCameraProvider? = null
    private var camera: Camera? = null
    private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    private var lensFacing: Int = CameraSelector.LENS_FACING_BACK
    private var targetResolution: Size = Size(1280, 720)
    private var isTorchEnabled: Boolean = false

    fun startCamera(onReady: (() -> Unit)? = null) {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener({
            cameraProvider = cameraProviderFuture.get()
            bindCameraUseCases()
            onReady?.invoke()
        }, ContextCompat.getMainExecutor(context))
    }

    private fun bindCameraUseCases() {
        val provider = cameraProvider ?: return
        provider.unbindAll()

        val cameraSelector = CameraSelector.Builder()
            .requireLensFacing(lensFacing)
            .build()

        // Forzar estrictamente relación de aspecto 16:9 en hardware y resolución objetivo
        val resolutionSelector = ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
            .setResolutionStrategy(
                ResolutionStrategy(targetResolution, ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
            )
            .build()

        // 1. Caso de uso: Preview en pantalla en 16:9
        val preview = Preview.Builder()
            .setResolutionSelector(resolutionSelector)
            .build()
            .also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

        // 2. Caso de uso: Análisis de imagen y captura en 16:9
        val imageAnalysis = ImageAnalysis.Builder()
            .setResolutionSelector(resolutionSelector)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also {
                it.setAnalyzer(cameraExecutor) { imageProxy ->
                    try {
                        // Calidad 65: óptima para 30+ FPS continuos, reduce peso a ~50KB por frame
                        val jpeg = ImageConverter.imageProxyToJpeg(imageProxy, quality = 65)
                        if (jpeg != null) {
                            frameListener?.onFrameCaptured(jpeg)
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Error procesando frame de camara: ${e.message}")
                    } finally {
                        imageProxy.close()
                    }
                }
            }

        try {
            camera = provider.bindToLifecycle(
                lifecycleOwner,
                cameraSelector,
                preview,
                imageAnalysis
            )
            // Restaurar estado de linterna si aplica
            if (lensFacing == CameraSelector.LENS_FACING_BACK) {
                camera?.cameraControl?.enableTorch(isTorchEnabled)
            }
        } catch (exc: Exception) {
            Log.e(TAG, "Fallo al enlazar casos de uso de CameraX: ${exc.message}", exc)
        }
    }

    fun switchCamera() {
        lensFacing = if (lensFacing == CameraSelector.LENS_FACING_BACK) {
            CameraSelector.LENS_FACING_FRONT
        } else {
            CameraSelector.LENS_FACING_BACK
        }
        isTorchEnabled = false
        bindCameraUseCases()
    }

    fun toggleTorch(): Boolean {
        if (lensFacing == CameraSelector.LENS_FACING_FRONT) {
            return false // Cámaras frontales no suelen tener flash físico
        }
        isTorchEnabled = !isTorchEnabled
        camera?.cameraControl?.enableTorch(isTorchEnabled)
        return isTorchEnabled
    }

    fun setResolution(width: Int, height: Int) {
        targetResolution = Size(width, height)
        bindCameraUseCases()
    }

    fun stop() {
        cameraProvider?.unbindAll()
        cameraExecutor.shutdown()
    }

    companion object {
        private const val TAG = "DroidLens.CameraManager"
    }
}
