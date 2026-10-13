package com.droidlens.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.droidlens.app.camera.StreamMode
import com.droidlens.app.camera.VideoProfile
import com.droidlens.app.databinding.ActivityMainBinding
import com.droidlens.app.service.CamStreamService

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: SharedPreferences
    private lateinit var scaleGestureDetector: ScaleGestureDetector

    private var streamService: CamStreamService? = null
    private var isBound = false
    private var isDarkModeActive = false

    private val requestMediaPermissionsLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val cameraGranted = permissions[Manifest.permission.CAMERA] == true || hasCameraPermission()
        if (cameraGranted) {
            bindStreamService()
        } else {
            Toast.makeText(this, R.string.camera_permission_required, Toast.LENGTH_LONG).show()
            binding.tvStatus.text = "Permiso de cámara denegado"
            binding.tvStatus.setTextColor(ContextCompat.getColor(this, R.color.status_red))
        }
    }

    private val requestNotificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> }

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            val localBinder = binder as? CamStreamService.StreamBinder
            streamService = localBinder?.getService()
            isBound = true

            streamService?.let { service ->
                // Acoplar vista previa
                service.cameraManager.attachPreview(binding.previewView)

                // Restaurar perfil guardado si aplica
                val savedProfileName = prefs.getString(KEY_VIDEO_PROFILE, VideoProfile.HD_720P.name)
                val initialProfile = try {
                    VideoProfile.valueOf(savedProfileName ?: VideoProfile.HD_720P.name)
                } catch (e: Exception) {
                    VideoProfile.HD_720P
                }
                service.cameraManager.setProfile(initialProfile)
                binding.btnResolution.text = initialProfile.title

                // Restaurar modo de transmisión guardado
                val savedModeName = prefs.getString(KEY_STREAM_MODE, StreamMode.AUDIO_VIDEO.name)
                val initialMode = try {
                    StreamMode.valueOf(savedModeName ?: StreamMode.AUDIO_VIDEO.name)
                } catch (e: Exception) {
                    StreamMode.AUDIO_VIDEO
                }

                // Vincular callbacks de estado
                service.onStatusChanged = { streaming, _ ->
                    runOnUiThread {
                        updateStreamingUI(streaming)
                    }
                }

                service.onFpsUpdated = { fps ->
                    runOnUiThread {
                        binding.tvFps.text = String.format("%.1f FPS", fps)
                    }
                }

                service.onClientStateChanged = { connected, _ ->
                    runOnUiThread {
                        if (connected) {
                            binding.tvStatus.text = "PC Conectada"
                            binding.tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.status_green))
                        } else {
                            binding.tvStatus.text = "Esperando USB :8080"
                            binding.tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.secondary))
                        }
                    }
                }

                service.onModeChanged = { activeMode ->
                    runOnUiThread {
                        binding.btnStreamMode.text = "Modo: ${activeMode.title}"
                        prefs.edit().putString(KEY_STREAM_MODE, activeMode.name).apply()
                    }
                }

                service.cameraManager.errorListener = object : com.droidlens.app.camera.CameraManager.CameraErrorListener {
                    override fun onCameraError(message: String, throwable: Throwable?) {
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, message, Toast.LENGTH_LONG).show()
                            binding.tvStatus.text = "Error de cámara"
                            binding.tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.status_red))
                        }
                    }
                }

                service.setStreamMode(initialMode, notifyRemote = false)
                updateStreamingUI(service.isStreaming.get())
                updateFlashButtonState()

                // Si no estaba transmitiendo, iniciar sesión automáticamente
                if (!service.isStreaming.get()) {
                    service.startStreamingSession()
                }
            }
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            streamService = null
            isBound = false
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        setupUI()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
                requestNotificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        if (hasCameraPermission() && hasAudioPermission()) {
            bindStreamService()
        } else {
            requestMediaPermissionsLauncher.launch(
                arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
            )
        }
    }

    private fun hasCameraPermission() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.CAMERA
    ) == PackageManager.PERMISSION_GRANTED

    private fun hasAudioPermission() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.RECORD_AUDIO
    ) == PackageManager.PERMISSION_GRANTED

    private fun bindStreamService() {
        val intent = Intent(this, CamStreamService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupUI() {
        binding.btnStreamMode.setOnClickListener {
            val service = streamService ?: return@setOnClickListener
            val targetMode = service.currentMode.next()
            if (targetMode != StreamMode.VIDEO_ONLY && !hasAudioPermission()) {
                Toast.makeText(
                    this,
                    "Permiso de micrófono requerido; usando Solo Cámara",
                    Toast.LENGTH_SHORT
                ).show()
            }
            val applied = service.setStreamMode(targetMode, notifyRemote = true)
            binding.btnStreamMode.text = "Modo: ${applied.title}"
            prefs.edit().putString(KEY_STREAM_MODE, applied.name).apply()
        }

        binding.btnToggleStream.setOnClickListener {
            val service = streamService ?: return@setOnClickListener
            if (service.isStreaming.get()) {
                service.stopStreamingSession()
            } else {
                service.startStreamingSession()
            }
        }

        binding.btnSwitchCamera.setOnClickListener {
            val service = streamService ?: return@setOnClickListener
            service.cameraManager.switchCamera()
            updateFlashButtonState()
        }

        binding.btnFlash.setOnClickListener {
            val service = streamService ?: return@setOnClickListener
            val enabled = service.cameraManager.toggleTorch()
            binding.btnFlash.text = if (enabled) "Flash ON" else "Flash"
        }

        binding.btnResolution.setOnClickListener {
            val service = streamService ?: return@setOnClickListener
            val nextProfile = when (service.cameraManager.currentProfile) {
                VideoProfile.HD_720P -> VideoProfile.FULL_HD_1080P
                VideoProfile.FULL_HD_1080P -> VideoProfile.LOW_POWER
                VideoProfile.LOW_POWER -> VideoProfile.HD_720P
            }
            service.cameraManager.setProfile(nextProfile)
            binding.btnResolution.text = nextProfile.title
            prefs.edit().putString(KEY_VIDEO_PROFILE, nextProfile.name).apply()
            Toast.makeText(this, "Perfil móvil: ${nextProfile.title}", Toast.LENGTH_SHORT).show()
        }

        binding.btnDarkMode.setOnClickListener {
            enableDarkMode(true)
        }

        binding.blackoutOverlay.setOnClickListener {
            enableDarkMode(false)
        }

        scaleGestureDetector = ScaleGestureDetector(this, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            private var currentZoom = 0f
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                val service = streamService ?: return true
                currentZoom += (detector.scaleFactor - 1.0f) * 0.5f
                currentZoom = currentZoom.coerceIn(0f, 1f)
                service.cameraManager.setLinearZoom(currentZoom)
                return true
            }
        })

        binding.previewView.setOnTouchListener { _, event ->
            scaleGestureDetector.onTouchEvent(event)
            if (!scaleGestureDetector.isInProgress && event.action == MotionEvent.ACTION_UP) {
                streamService?.cameraManager?.focusOnPoint(event.x, event.y)
            }
            true
        }
    }

    private fun updateStreamingUI(isStreaming: Boolean) {
        if (isStreaming) {
            binding.btnToggleStream.text = getString(R.string.stop_streaming)
            binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.status_red))
        } else {
            binding.btnToggleStream.text = getString(R.string.start_streaming)
            binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.primary))
            binding.tvFps.text = "0.0 FPS"
        }
    }

    private fun updateFlashButtonState() {
        val service = streamService ?: return
        val hasFlash = service.cameraManager.hasFlashUnit()
        binding.btnFlash.isEnabled = hasFlash
        binding.btnFlash.alpha = if (hasFlash) 1.0f else 0.4f
        binding.btnFlash.text = "Flash"
    }

    private fun enableDarkMode(enable: Boolean) {
        isDarkModeActive = enable
        binding.blackoutOverlay.visibility = if (enable) View.VISIBLE else View.GONE
        binding.bottomControls.visibility = if (enable) View.GONE else View.VISIBLE
        binding.topBar.visibility = if (enable) View.GONE else View.VISIBLE

        val lp = window.attributes
        lp.screenBrightness = if (enable) 0.01f else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
        window.attributes = lp
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isBound) {
            streamService?.cameraManager?.detachPreview()
            unbindService(serviceConnection)
            isBound = false
        }
    }

    companion object {
        private const val PREFS_NAME = "droidlens_prefs"
        private const val KEY_VIDEO_PROFILE = "video_profile"
        private const val KEY_STREAM_MODE = "stream_mode"
    }
}
