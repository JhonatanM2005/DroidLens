package com.droidlens.app.network

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import java.io.BufferedOutputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class StreamServer(private val port: Int = 8080) {

    interface ServerCallback {
        fun onClientConnected(clientAddress: String)
        fun onClientDisconnected()
        fun onFpsUpdated(fps: Float)
        fun onError(message: String)
    }

    var callback: ServerCallback? = null

    private var serverSocket: ServerSocket? = null
    private var clientSocket: Socket? = null
    private var outputStream: OutputStream? = null

    private val isRunning = AtomicBoolean(false)
    private val isClientConnected = AtomicBoolean(false)

    // Canal CONFLATED: la estructura óptima para baja latencia (siempre conserva el frame más reciente y descarta los viejos en 0ns)
    private val frameChannel = Channel<ByteArray>(Channel.CONFLATED)

    private var frameIdCounter = AtomicInteger(0)
    private var serverScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var senderJob: Job? = null

    // Métricas de FPS
    private var framesSentCount = 0
    private var lastFpsTimestamp = System.currentTimeMillis()

    fun start() {
        if (isRunning.getAndSet(true)) return

        serverScope.launch {
            try {
                serverSocket = ServerSocket().apply {
                    reuseAddress = true
                    bind(InetSocketAddress("0.0.0.0", port))
                }
                Log.i(TAG, "Servidor de streaming iniciado en puerto $port")

                while (isRunning.get()) {
                    try {
                        val client = serverSocket?.accept() ?: break
                        client.tcpNoDelay = true
                        client.sendBufferSize = 512 * 1024

                        synchronized(this@StreamServer) {
                            clientSocket?.close()
                            clientSocket = client
                            outputStream = BufferedOutputStream(client.getOutputStream(), 128 * 1024)
                            isClientConnected.set(true)
                        }

                        val addr = client.remoteSocketAddress.toString()
                        Log.i(TAG, "Cliente conectado desde $addr")
                        withContext(Dispatchers.Main) {
                            callback?.onClientConnected(addr)
                        }

                        // Iniciar bucle de envío dedicado de alta velocidad
                        startSenderLoop()

                    } catch (e: Exception) {
                        if (isRunning.get()) {
                            Log.w(TAG, "Error aceptando conexion: ${e.message}")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error fatal iniciando ServerSocket: ${e.message}")
                withContext(Dispatchers.Main) {
                    callback?.onError("No se pudo iniciar el servidor en el puerto $port: ${e.message}")
                }
            }
        }
    }

    private fun startSenderLoop() {
        senderJob?.cancel()
        senderJob = serverScope.launch {
            while (isActive && isClientConnected.get()) {
                try {
                    val jpegBytes = frameChannel.receive()
                    val frameId = frameIdCounter.incrementAndGet()
                    val timestamp = System.currentTimeMillis()
                    val packet = PacketProtocol.packFrame(frameId, timestamp, jpegBytes)

                    synchronized(this@StreamServer) {
                        outputStream?.write(packet)
                        outputStream?.flush()
                    }

                    // Cálculo de FPS
                    framesSentCount++
                    val now = System.currentTimeMillis()
                    if (now - lastFpsTimestamp >= 1000L) {
                        val fps = (framesSentCount * 1000f) / (now - lastFpsTimestamp)
                        framesSentCount = 0
                        lastFpsTimestamp = now
                        withContext(Dispatchers.Main) {
                            callback?.onFpsUpdated(fps)
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Error en bucle de envio: ${e.message}")
                    handleClientDisconnected()
                    break
                }
            }
        }
    }

    fun sendFrame(jpegBytes: ByteArray) {
        if (!isClientConnected.get()) return
        // trySend es no bloqueante y aprovecha Channel.CONFLATED para mantener latencia cero
        frameChannel.trySend(jpegBytes)
    }

    private fun handleClientDisconnected() {
        senderJob?.cancel()
        senderJob = null
        synchronized(this) {
            isClientConnected.set(false)
            try {
                outputStream?.close()
                clientSocket?.close()
            } catch (ignored: Exception) {}
            outputStream = null
            clientSocket = null
        }
        serverScope.launch(Dispatchers.Main) {
            callback?.onClientDisconnected()
        }
    }

    fun stop() {
        isRunning.set(false)
        handleClientDisconnected()
        try {
            serverSocket?.close()
        } catch (ignored: Exception) {}
        serverSocket = null
        serverScope.cancel()
        serverScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
        Log.i(TAG, "Servidor de streaming detenido")
    }

    companion object {
        private const val TAG = "DroidLens.StreamServer"
    }
}
