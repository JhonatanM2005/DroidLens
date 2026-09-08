package com.droidlens.app.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import com.droidlens.app.MainActivity
import com.droidlens.app.R
import com.droidlens.app.camera.CameraManager
import com.droidlens.app.camera.VideoProfile
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
    lateinit var streamServer: StreamServer
        private set

    val isStreaming = AtomicBoolean(false)

    // Callbacks para la actividad si está enlazada
    var onStatusChanged: ((Boolean, String) -> Unit)? = null
    var onFpsUpdated: ((Float) -> Unit)? = null
    var onClientStateChanged: ((Boolean, String) -> Unit)? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()

        // 1. Inicializar servidor en 127.0.0.1
        streamServer = StreamServer(bindHost = "127.0.0.1", port = 8080)
        streamServer.callback = object : StreamServer.ServerCallback {
            override fun onClientConnected(clientAddress: String) {
                onClientStateChanged?.invoke(true, clientAddress)
                updateNotification("PC conectada ($clientAddress)")
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

            override fun onError(message: String) {
                // Informar error
            }
        }
        streamServer.start()

        // 2. Inicializar CameraManager vinculado al ciclo de vida del Servicio
        cameraManager = CameraManager(this, this)
        cameraManager.frameListener = object : CameraManager.FrameListener {
            override fun onFrameCaptured(jpegBytes: ByteArray) {
                if (isStreaming.get()) {
                    streamServer.sendFrame(jpegBytes)
                }
            }
        }
        cameraManager.startCamera()
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

    /**
     * Inicia formalmente la sesión de streaming, adquiere WakeLock y levanta ForegroundService.
     */
    fun startStreamingSession(): Boolean {
        if (isStreaming.getAndSet(true)) return true

        acquireWakeLock()
        cameraManager.isStreamingActive.set(true)

        val notification = buildNotification("Transmitiendo video a la PC por USB (:8080)")
        startForeground(NOTIFICATION_ID, notification)

        onStatusChanged?.invoke(true, "Transmitiendo a PC")
        return true
    }

    /**
     * Detiene la sesión unificada de streaming, libera WakeLock y termina el ForegroundService.
     */
    fun stopStreamingSession() {
        if (!isStreaming.getAndSet(false)) return

        cameraManager.isStreamingActive.set(false)
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
                acquire(4 * 60 * 60 * 1000L) // 4 horas máximo de protección
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
            .setContentTitle("DroidLens Webcam Activa")
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
