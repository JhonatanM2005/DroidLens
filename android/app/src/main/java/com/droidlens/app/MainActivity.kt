package com.droidlens.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.droidlens.app.camera.CameraManager
import com.droidlens.app.databinding.ActivityMainBinding
import com.droidlens.app.network.StreamServer

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var cameraManager: CameraManager
    private lateinit var streamServer: StreamServer

    private var isStreaming = false
    private var is720p = true
    private var isDarkModeActive = false

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            initCamera()
        } else {
            Toast.makeText(this, R.string.camera_permission_required, Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Mantener la pantalla encendida durante videollamadas
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        initServer()
        setupUI()

        if (allPermissionsGranted()) {
            initCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun allPermissionsGranted() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.CAMERA
    ) == PackageManager.PERMISSION_GRANTED

    private fun initCamera() {
        cameraManager = CameraManager(this, this, binding.previewView)
        cameraManager.frameListener = object : CameraManager.FrameListener {
            override fun onFrameCaptured(jpegBytes: ByteArray) {
                if (isStreaming) {
                    streamServer.sendFrame(jpegBytes)
                }
            }
        }
        cameraManager.startCamera {
            // Iniciar streaming automáticamente al arrancar
            startStreaming()
        }
    }

    private fun initServer() {
        streamServer = StreamServer(port = 8080)
        streamServer.callback = object : StreamServer.ServerCallback {
            override fun onClientConnected(clientAddress: String) {
                binding.tvStatus.text = "PC Conectada"
                binding.tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.status_green))
            }

            override fun onClientDisconnected() {
                binding.tvStatus.text = "Esperando USB :8080"
                binding.tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.secondary))
            }

            override fun onFpsUpdated(fps: Float) {
                binding.tvFps.text = String.format("%.1f FPS", fps)
            }

            override fun onError(message: String) {
                Toast.makeText(this@MainActivity, message, Toast.LENGTH_SHORT).show()
            }
        }
        streamServer.start()
    }

    private fun setupUI() {
        binding.btnToggleStream.setOnClickListener {
            if (isStreaming) {
                stopStreaming()
            } else {
                startStreaming()
            }
        }

        binding.btnSwitchCamera.setOnClickListener {
            cameraManager.switchCamera()
        }

        binding.btnFlash.setOnClickListener {
            val enabled = cameraManager.toggleTorch()
            binding.btnFlash.text = if (enabled) "Flash ON" else "Flash"
        }

        binding.btnResolution.setOnClickListener {
            is720p = !is720p
            if (is720p) {
                cameraManager.setResolution(1280, 720)
                binding.btnResolution.text = "720p"
            } else {
                cameraManager.setResolution(1920, 1080)
                binding.btnResolution.text = "1080p"
            }
        }

        // Modo pantalla apagada para evitar calentamiento de pantalla en llamadas largas
        binding.btnDarkMode.setOnClickListener {
            enableDarkMode(true)
        }

        binding.blackoutOverlay.setOnClickListener {
            enableDarkMode(false)
        }
    }

    private fun enableDarkMode(enable: Boolean) {
        isDarkModeActive = enable
        binding.blackoutOverlay.visibility = if (enable) View.VISIBLE else View.GONE
        val lp = window.attributes
        lp.screenBrightness = if (enable) 0.01f else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
        window.attributes = lp
    }

    private fun startStreaming() {
        isStreaming = true
        binding.btnToggleStream.text = getString(R.string.stop_streaming)
        binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.status_red))
    }

    private fun stopStreaming() {
        isStreaming = false
        binding.btnToggleStream.text = getString(R.string.start_streaming)
        binding.btnToggleStream.setBackgroundColor(ContextCompat.getColor(this, R.color.primary))
        binding.tvFps.text = "0.0 FPS"
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::cameraManager.isInitialized) {
            cameraManager.stop()
        }
        if (::streamServer.isInitialized) {
            streamServer.stop()
        }
    }
}
