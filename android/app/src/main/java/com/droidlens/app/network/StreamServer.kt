package com.droidlens.app.network

import android.util.Log
import kotlinx.coroutines.*
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
    private val isSending = AtomicBoolean(false)

    private var frameIdCounter = AtomicInteger(0)
    private var serverScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

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
                            outputStream = client.getOutputStream()
                            isClientConnected.set(true)
                        }

                        val addr = client.remoteSocketAddress.toString()
                        Log.i(TAG, "Cliente conectado desde $addr")
                        withContext(Dispatchers.Main) {
                            callback?.onClientConnected(addr)
                        }

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

    fun sendFrame(jpegBytes: ByteArray) {
        if (!isClientConnected.get() || outputStream == null) return

        // Si el socket aún está enviando el fotograma previo, descartar este para mantener latencia cero
        if (!isSending.compareAndSet(false, true)) {
            return
        }

        serverScope.launch {
            try {
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
                Log.w(TAG, "Error enviando frame, cliente desconectado: ${e.message}")
                handleClientDisconnected()
            } finally {
                isSending.set(false)
            }
        }
    }

    private fun handleClientDisconnected() {
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
