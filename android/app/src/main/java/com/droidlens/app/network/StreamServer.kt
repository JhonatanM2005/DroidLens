package com.droidlens.app.network

import android.util.Log
import com.droidlens.app.camera.StreamMode
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import java.io.BufferedOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class StreamServer(
    val bindHost: String = "127.0.0.1",
    val port: Int = 8080
) {

    interface ServerCallback {
        fun onClientConnected(clientAddress: String)
        fun onClientDisconnected()
        fun onFpsUpdated(fps: Float)
        fun onRemoteModeChanged(mode: StreamMode)
        fun onError(message: String)
    }

    var callback: ServerCallback? = null

    private var serverSocket: ServerSocket? = null
    private var clientSocket: Socket? = null
    private var outputStream: OutputStream? = null
    private var inputStream: InputStream? = null

    private val isRunning = AtomicBoolean(false)
    val isClientConnected = AtomicBoolean(false)

    // Canal CONFLATED para vídeo: conserva siempre el frame más reciente y descarta los antiguos
    private val frameChannel = Channel<ByteArray>(Channel.CONFLATED)

    // Canal acotado para audio (~160 ms máx): evita acumular latencia de voz
    private val audioChannel = Channel<ByteArray>(
        capacity = 8,
        onBufferOverflow = BufferOverflow.DROP_OLDEST
    )

    private var frameIdCounter = AtomicInteger(0)
    private var audioSeqCounter = AtomicInteger(0)
    private var controlSeqCounter = AtomicInteger(0)

    private var serverScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var videoSenderJob: Job? = null
    private var audioSenderJob: Job? = null
    private var controlReaderJob: Job? = null

    // Métricas de FPS de transmisión
    private var framesSentCount = 0
    private var lastFpsTimestamp = System.currentTimeMillis()

    fun start() {
        if (isRunning.getAndSet(true)) return

        serverScope.launch {
            try {
                serverSocket = ServerSocket().apply {
                    reuseAddress = true
                    bind(InetSocketAddress(bindHost, port))
                }
                Log.i(TAG, "Servidor de streaming iniciado en $bindHost:$port")

                while (isRunning.get()) {
                    try {
                        val client = serverSocket?.accept() ?: break
                        client.tcpNoDelay = true
                        client.sendBufferSize = 512 * 1024

                        synchronized(this@StreamServer) {
                            clientSocket?.close()
                            clientSocket = client
                            outputStream = BufferedOutputStream(client.getOutputStream(), 128 * 1024)
                            inputStream = client.getInputStream()
                            isClientConnected.set(true)
                        }

                        val addr = client.remoteSocketAddress.toString()
                        Log.i(TAG, "Cliente conectado desde $addr")
                        withContext(Dispatchers.Main) {
                            callback?.onClientConnected(addr)
                        }

                        startClientLoops()

                    } catch (e: Exception) {
                        if (isRunning.get()) {
                            Log.w(TAG, "Error aceptando conexion: ${e.message}")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error fatal iniciando ServerSocket: ${e.message}")
                withContext(Dispatchers.Main) {
                    callback?.onError("No se pudo iniciar el servidor en $bindHost:$port: ${e.message}")
                }
            }
        }
    }

    private fun writePacketSynchronized(header: ByteArray, payload: ByteArray) {
        synchronized(this@StreamServer) {
            outputStream?.let { os ->
                os.write(header)
                os.write(payload)
                os.flush()
            }
        }
    }

    private fun startClientLoops() {
        videoSenderJob?.cancel()
        audioSenderJob?.cancel()
        controlReaderJob?.cancel()

        videoSenderJob = serverScope.launch {
            while (isActive && isClientConnected.get()) {
                try {
                    val jpegBytes = frameChannel.receive()
                    val frameId = frameIdCounter.incrementAndGet()
                    val timestamp = System.currentTimeMillis()
                    val header = PacketProtocol.createHeader(
                        PacketProtocol.TYPE_VIDEO,
                        frameId,
                        timestamp,
                        jpegBytes.size
                    )
                    writePacketSynchronized(header, jpegBytes)

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
                    Log.w(TAG, "Error en bucle de envio de video: ${e.message}")
                    handleClientDisconnected()
                    break
                }
            }
        }

        audioSenderJob = serverScope.launch {
            while (isActive && isClientConnected.get()) {
                try {
                    val pcmBytes = audioChannel.receive()
                    val seqId = audioSeqCounter.incrementAndGet()
                    val timestamp = System.currentTimeMillis()
                    val header = PacketProtocol.createHeader(
                        PacketProtocol.TYPE_AUDIO,
                        seqId,
                        timestamp,
                        pcmBytes.size
                    )
                    writePacketSynchronized(header, pcmBytes)
                } catch (e: Exception) {
                    Log.w(TAG, "Error en bucle de envio de audio: ${e.message}")
                    handleClientDisconnected()
                    break
                }
            }
        }

        controlReaderJob = serverScope.launch {
            val headerBuf = ByteArray(PacketProtocol.HEADER_SIZE)
            while (isActive && isClientConnected.get()) {
                try {
                    val ins = inputStream ?: break
                    if (!readExact(ins, headerBuf, PacketProtocol.HEADER_SIZE)) {
                        handleClientDisconnected()
                        break
                    }
                    val parsed = PacketProtocol.parseHeader(headerBuf) ?: continue
                    if (parsed.payloadLength <= 0 || parsed.payloadLength > 1024) continue
                    val payload = ByteArray(parsed.payloadLength)
                    if (!readExact(ins, payload, parsed.payloadLength)) {
                        handleClientDisconnected()
                        break
                    }
                    if (parsed.packetType == PacketProtocol.TYPE_CONTROL_MODE) {
                        val mode = StreamMode.fromCode(payload[0])
                        if (mode != null) {
                            withContext(Dispatchers.Main) {
                                callback?.onRemoteModeChanged(mode)
                            }
                        }
                    }
                } catch (e: Exception) {
                    break
                }
            }
        }
    }

    private fun readExact(ins: InputStream, dest: ByteArray, length: Int): Boolean {
        var offset = 0
        while (offset < length && isClientConnected.get()) {
            val r = ins.read(dest, offset, length - offset)
            if (r <= 0) return false
            offset += r
        }
        return offset == length
    }

    fun sendFrame(jpegBytes: ByteArray) {
        if (!isClientConnected.get()) return
        frameChannel.trySend(jpegBytes)
    }

    fun sendAudio(pcmBytes: ByteArray) {
        if (!isClientConnected.get()) return
        audioChannel.trySend(pcmBytes)
    }

    fun sendControlMode(mode: StreamMode) {
        if (!isClientConnected.get()) return
        serverScope.launch {
            try {
                val seqId = controlSeqCounter.incrementAndGet()
                val header = PacketProtocol.createHeader(
                    PacketProtocol.TYPE_CONTROL_MODE,
                    seqId,
                    System.currentTimeMillis(),
                    1
                )
                writePacketSynchronized(header, byteArrayOf(mode.code))
            } catch (e: Exception) {
                Log.w(TAG, "Error enviando CONTROL_MODE a PC: ${e.message}")
            }
        }
    }

    private fun handleClientDisconnected() {
        videoSenderJob?.cancel()
        audioSenderJob?.cancel()
        controlReaderJob?.cancel()
        videoSenderJob = null
        audioSenderJob = null
        controlReaderJob = null
        synchronized(this) {
            isClientConnected.set(false)
            try {
                inputStream?.close()
                outputStream?.close()
                clientSocket?.close()
            } catch (ignored: Exception) {}
            inputStream = null
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
