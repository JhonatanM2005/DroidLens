package com.droidlens.app.service

import android.Manifest
import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import com.droidlens.app.MainActivity
import com.droidlens.app.R
import com.droidlens.app.audio.AudioCaptureManager
import com.droidlens.app.camera.CameraManager
import com.droidlens.app.camera.StreamMode
import com.droidlens.app.network.StreamServer
import java.util.concurrent.atomic.AtomicBoolean

class CamStreamService : LifecycleService() {

    inner class StreamBinder : Binder() {
        fun getService(): CamStreamService = this@CamStreamService
    }

    private val binder = StreamBinder()
    private var wakeLock: PowerManager.WakeLock? = null

    lateinit var cameraManager: CameraManager
        private set
    lateinit var audioCaptureManager: AudioCaptureManager
        private set
    lateinit var streamServer: StreamServer
        private set

    val isStreaming = AtomicBoolean(false)
    var currentMode: StreamMode = StreamMode.AUDIO_VIDEO
        private set

    // Callbacks para la actividad si está enlazada
    var onStatusChanged: ((Boolean, String) -> Unit)? = null
    var onFpsUpdated: ((Float) -> Unit)? = null
    var onClientStateChanged: ((Boolean, String) -> Unit)? = null
    var onModeChanged: ((StreamMode) -> Unit)? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()

        // 1. Inicializar servidor en 127.0.0.1
        streamServer = StreamServer(bindHost = "127.0.0.1", port = 8080)
        streamServer.callback = object : StreamServer.ServerCallback {
            override fun onClientConnected(clientAddress: String) {
                onClientStateChanged?.invoke(true, clientAddress)
                streamServer.sendControlMode(currentMode)
                updateNotification("PC conectada ($clientAddress) — ${currentMode.title}")
            }

            override fun onClientDisconnected() {
                onClientStateChanged?.invoke(false, "")
                if (isStreaming.get()) {
                    updateNotification("Esperando USB (:8080)")
                }
            }

            override fun onFpsUpdated(fps: Float) {
                onFpsUpdated?.invoke(fps)
            }

            override fun onRemoteModeChanged(mode: StreamMode) {
                setStreamMode(mode, notifyRemote = false)
            }

            override fun onError(message: String) {
                // Informar error
            }
        }
        streamServer.start()

        // 2. Inicializar CameraManager vinculado al ciclo de vida del Servicio
        cameraManager = CameraManager(this, this)
        cameraManager.frameListener = object : CameraManager.FrameListener {
            override fun onFrameCaptured(jpegBytes: ByteArray) {
                if (isStreaming.get() && currentMode != StreamMode.AUDIO_ONLY) {
                    streamServer.sendFrame(jpegBytes)
                }
            }
        }
        cameraManager.startCamera()

        // 3. Inicializar AudioCaptureManager
        audioCaptureManager = AudioCaptureManager { pcmBytes ->
            if (isStreaming.get() && currentMode != StreamMode.VIDEO_ONLY) {
                streamServer.sendAudio(pcmBytes)
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        if (intent?.action == ACTION_STOP_STREAM) {
            stopStreamingSession()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent): IBinder {
        super.onBind(intent)
        return binder
    }

    private fun hasAudioPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * Cambia en caliente el modo de transmisión, encendiendo/apagando cámara y micrófono según corresponda.
     */
    fun setStreamMode(requestedMode: StreamMode, notifyRemote: Boolean = true): StreamMode {
        val effectiveMode = if (requestedMode != StreamMode.VIDEO_ONLY && !hasAudioPermission()) {
            StreamMode.VIDEO_ONLY
        } else {
            requestedMode
        }

        currentMode = effectiveMode
        if (isStreaming.get()) {
            applyModeToHardware(effectiveMode)
            updateNotification("Transmitiendo: ${effectiveMode.title}")
        }

        if (notifyRemote) {
            streamServer.sendControlMode(effectiveMode)
        }
        onModeChanged?.invoke(effectiveMode)
        return effectiveMode
    }

    private fun applyModeToHardware(mode: StreamMode) {
        when (mode) {
            StreamMode.VIDEO_ONLY -> {
                audioCaptureManager.stop()
                cameraManager.isStreamingActive.set(true)
                cameraManager.resumeCameraSensor()
            }
            StreamMode.AUDIO_ONLY -> {
                cameraManager.isStreamingActive.set(false)
                cameraManager.pauseCameraSensor()
                if (hasAudioPermission()) {
                    audioCaptureManager.start()
                }
            }
            StreamMode.AUDIO_VIDEO -> {
                cameraManager.isStreamingActive.set(true)
                cameraManager.resumeCameraSensor()
                if (hasAudioPermission()) {
                    audioCaptureManager.start()
                }
            }
        }
    }

    /**
     * Inicia formalmente la sesión de streaming, adquiere WakeLock y levanta ForegroundService.
     */
    fun startStreamingSession(): Boolean {
        if (isStreaming.getAndSet(true)) return true

        acquireWakeLock()

        if (currentMode != StreamMode.VIDEO_ONLY && !hasAudioPermission()) {
            currentMode = StreamMode.VIDEO_ONLY
        }

        val notification = buildNotification("Transmitiendo (${currentMode.title}) por USB (:8080)")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            var fgType = ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA
            if (hasAudioPermission()) {
                fgType = fgType or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            }
            startForeground(NOTIFICATION_ID, notification, fgType)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }

        applyModeToHardware(currentMode)
        streamServer.sendControlMode(currentMode)

        onStatusChanged?.invoke(true, "Transmitiendo a PC")
        onModeChanged?.invoke(currentMode)
        return true
    }

    /**
     * Detiene la sesión unificada de streaming, libera WakeLock y termina el ForegroundService.
     */
    fun stopStreamingSession() {
        if (!isStreaming.getAndSet(false)) return

        cameraManager.isStreamingActive.set(false)
        audioCaptureManager.stop()
        releaseWakeLock()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }

        onStatusChanged?.invoke(false, "Detenido")
        stopSelf()
    }

    private fun acquireWakeLock() {
        if (wakeLock == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "DroidLens:StreamingWakeLock").apply {
                setReferenceCounted(false)
                acquire(4 * 60 * 60 * 1000L)
            }
        }
    }

    private fun releaseWakeLock() {
        try {
            wakeLock?.let {
                if (it.isHeld) it.release()
            }
        } catch (ignored: Exception) {}
        wakeLock = null
    }

    private fun updateNotification(text: String) {
        if (!isStreaming.get()) return
        val nm = getSystemService(NotificationManager::class.java)
        nm?.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun buildNotification(contentText: String): Notification {
        val openAppIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingOpenIntent = PendingIntent.getActivity(
            this, 0, openAppIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, CamStreamService::class.java).apply {
            action = ACTION_STOP_STREAM
        }
        val pendingStopIntent = PendingIntent.getService(
            this, 1, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("DroidLens Activo (${currentMode.title})")
            .setContentText(contentText)
            .setSmallIcon(R.drawable.ic_camera)
            .setContentIntent(pendingOpenIntent)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Detener", pendingStopIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "DroidLens Transmisión",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Notificación persistente para mantener el streaming activo en segundo plano"
                setShowBadge(false)
            }
            val nm = getSystemService(NotificationManager::class.java)
            nm?.createNotificationChannel(channel)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        releaseWakeLock()
        if (::audioCaptureManager.isInitialized) {
            audioCaptureManager.stop()
        }
        if (::cameraManager.isInitialized) {
            cameraManager.stop()
        }
        if (::streamServer.isInitialized) {
            streamServer.stop()
        }
    }

    companion object {
        const val CHANNEL_ID = "droidlens_stream_channel"
        const val NOTIFICATION_ID = 1001
        const val ACTION_STOP_STREAM = "com.droidlens.app.ACTION_STOP_STREAM"
    }
}
