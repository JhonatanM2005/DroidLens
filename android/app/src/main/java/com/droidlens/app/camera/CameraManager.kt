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
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

enum class VideoProfile(
    val title: String,
    val width: Int,
    val height: Int,
    val targetFps: Int,
    val jpegQuality: Int
) {
    LOW_POWER("480p Ahorro", 854, 480, 24, 50),
    HD_720P("720p HD", 1280, 720, 30, 65),
    FULL_HD_1080P("1080p FHD", 1920, 1080, 30, 75)
}

class CameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner
) {

    interface FrameListener {
        fun onFrameCaptured(jpegBytes: ByteArray)
    }

    interface CameraErrorListener {
        fun onCameraError(message: String, throwable: Throwable?)
    }

    var frameListener: FrameListener? = null
    var errorListener: CameraErrorListener? = null

    private var cameraProvider: ProcessCameraProvider? = null
    private var camera: Camera? = null
    private var preview: Preview? = null
    private var imageAnalysis: ImageAnalysis? = null
    private var currentPreviewView: PreviewView? = null

    private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    private var lensFacing: Int = CameraSelector.LENS_FACING_BACK
    var currentProfile: VideoProfile = VideoProfile.HD_720P
        private set

    private var isTorchEnabled: Boolean = false

    // Estado único y seguro para hilos del streaming
    val isStreamingActive = AtomicBoolean(false)

    fun startCamera(onResult: ((Boolean) -> Unit)? = null) {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener({
            try {
                cameraProvider = cameraProviderFuture.get()
                val success = bindCameraUseCases()
                onResult?.invoke(success)
            } catch (e: Exception) {
                Log.e(TAG, "Error obteniendo ProcessCameraProvider: ${e.message}", e)
                errorListener?.onCameraError("No se pudo iniciar el proveedor de cámara: ${e.message}", e)
                onResult?.invoke(false)
            }
        }, ContextCompat.getMainExecutor(context))
    }

    fun attachPreview(previewView: PreviewView) {
        currentPreviewView = previewView
        preview?.setSurfaceProvider(previewView.surfaceProvider)
    }

    fun detachPreview() {
        currentPreviewView = null
        preview?.setSurfaceProvider(null)
    }

    fun bindCameraUseCases(): Boolean {
        val provider = cameraProvider ?: return false
        provider.unbindAll()

        val cameraSelector = CameraSelector.Builder()
            .requireLensFacing(lensFacing)
            .build()

        val targetSize = Size(currentProfile.width, currentProfile.height)

        val resolutionSelector = ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
            .setResolutionStrategy(
                ResolutionStrategy(targetSize, ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
            )
            .build()

        // 1. Caso de uso: Preview en pantalla en 16:9
        preview = Preview.Builder()
            .setResolutionSelector(resolutionSelector)
            .build()
            .also { p ->
                currentPreviewView?.let { pv ->
                    p.setSurfaceProvider(pv.surfaceProvider)
                }
            }

        // 2. Caso de uso: Análisis de imagen y captura en 16:9
        imageAnalysis = ImageAnalysis.Builder()
            .setResolutionSelector(resolutionSelector)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also {
                it.setAnalyzer(cameraExecutor) { imageProxy ->
                    try {
                        // Pausa de conversión de imagen si no se está transmitiendo
                        if (!isStreamingActive.get()) {
                            return@setAnalyzer
                        }

                        val jpeg = ImageConverter.imageProxyToJpeg(imageProxy, quality = currentProfile.jpegQuality)
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

        return try {
            val useCases = mutableListOf<UseCase>(imageAnalysis!!)
            preview?.let { useCases.add(it) }

            camera = provider.bindToLifecycle(
                lifecycleOwner,
                cameraSelector,
                *useCases.toTypedArray()
            )

            // Restaurar estado de linterna si el hardware lo soporta
            if (lensFacing == CameraSelector.LENS_FACING_BACK && hasFlashUnit()) {
                camera?.cameraControl?.enableTorch(isTorchEnabled)
            } else {
                isTorchEnabled = false
            }
            true
        } catch (exc: Exception) {
            Log.e(TAG, "Fallo al enlazar casos de uso de CameraX: ${exc.message}", exc)
            camera = null
            errorListener?.onCameraError("Cámara no disponible o en uso por otra aplicación: ${exc.message}", exc)
            false
        }
    }

    fun hasFlashUnit(): Boolean {
        return camera?.cameraInfo?.hasFlashUnit() == true
    }

    fun switchCamera(): Int {
        lensFacing = if (lensFacing == CameraSelector.LENS_FACING_BACK) {
            CameraSelector.LENS_FACING_FRONT
        } else {
            CameraSelector.LENS_FACING_BACK
        }
        isTorchEnabled = false
        bindCameraUseCases()
        return lensFacing
    }

    fun getLensFacing(): Int = lensFacing

    fun toggleTorch(): Boolean {
        if (!hasFlashUnit()) {
            isTorchEnabled = false
            return false
        }
        isTorchEnabled = !isTorchEnabled
        try {
            camera?.cameraControl?.enableTorch(isTorchEnabled)
        } catch (e: Exception) {
            Log.w(TAG, "No se pudo cambiar estado de linterna: ${e.message}")
            isTorchEnabled = false
        }
        return isTorchEnabled
    }

    fun setProfile(profile: VideoProfile): Boolean {
        if (currentProfile == profile) return true
        currentProfile = profile
        return bindCameraUseCases()
    }

    fun setLinearZoom(zoom: Float) {
        try {
            camera?.cameraControl?.setLinearZoom(zoom.coerceIn(0f, 1f))
        } catch (e: Exception) {
            Log.w(TAG, "Error aplicando zoom lineal: ${e.message}")
        }
    }

    fun focusOnPoint(x: Float, y: Float) {
        val pv = currentPreviewView ?: return
        val factory = pv.meteringPointFactory
        val point = factory.createPoint(x, y)
        val action = FocusMeteringAction.Builder(point, FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE)
            .setAutoCancelDuration(3, TimeUnit.SECONDS)
            .build()
        try {
            camera?.cameraControl?.startFocusAndMetering(action)
        } catch (e: Exception) {
            Log.w(TAG, "Error aplicando autoenfoque: ${e.message}")
        }
    }

    fun stop() {
        cameraProvider?.unbindAll()
        cameraExecutor.shutdown()
        camera = null
        preview = null
        imageAnalysis = null
    }

    companion object {
        private const val TAG = "DroidLens.CameraManager"
    }
}
