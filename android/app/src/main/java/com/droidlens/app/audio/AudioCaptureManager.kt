package com.droidlens.app.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.Process
import android.util.Log
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Gestor de captura de micrófono de baja latencia (48 kHz, Mono, PCM 16-bit).
 * Emite bloques de 20 ms (1920 bytes) listos para empaquetarse en el protocolo APCM v2.
 */
class AudioCaptureManager(
    private val onAudioChunk: (ByteArray) -> Unit
) {
    private var audioRecord: AudioRecord? = null
    private var captureThread: Thread? = null
    private var noiseSuppressor: NoiseSuppressor? = null
    private var echoCanceler: AcousticEchoCanceler? = null

    val isCapturing = AtomicBoolean(false)

    @SuppressLint("MissingPermission")
    fun start(): Boolean {
        if (isCapturing.get()) return true

        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBuf <= 0) {
            Log.e(TAG, "Tamaño de buffer de AudioRecord inválido: $minBuf")
            return false
        }

        val bufferSize = maxOf(minBuf * 2, CHUNK_BYTES * 4)

        return try {
            val record = AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )

            if (record.state != AudioRecord.STATE_INITIALIZED) {
                record.release()
                Log.e(TAG, "AudioRecord no pudo inicializarse")
                return false
            }

            attachHardwareEffects(record.audioSessionId)

            record.startRecording()
            audioRecord = record
            isCapturing.set(true)

            captureThread = Thread({
                Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
                val chunkBuffer = ByteArray(CHUNK_BYTES)
                while (isCapturing.get()) {
                    var offset = 0
                    while (offset < CHUNK_BYTES && isCapturing.get()) {
                        val read = record.read(chunkBuffer, offset, CHUNK_BYTES - offset)
                        if (read > 0) {
                            offset += read
                        } else {
                            break
                        }
                    }
                    if (offset == CHUNK_BYTES && isCapturing.get()) {
                        onAudioChunk(chunkBuffer.copyOf())
                    }
                }
            }, "DroidLens-AudioCapture").apply {
                isDaemon = true
                start()
            }

            Log.i(TAG, "[OK] Captura de micrófono iniciada (48 kHz Mono PCM-16)")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error iniciando AudioCaptureManager: ${e.message}")
            stop()
            false
        }
    }

    private fun attachHardwareEffects(sessionId: Int) {
        try {
            if (NoiseSuppressor.isAvailable()) {
                noiseSuppressor = NoiseSuppressor.create(sessionId)?.apply { enabled = true }
            }
        } catch (ignored: Exception) {}

        try {
            if (AcousticEchoCanceler.isAvailable()) {
                echoCanceler = AcousticEchoCanceler.create(sessionId)?.apply { enabled = true }
            }
        } catch (ignored: Exception) {}
    }

    fun stop() {
        if (!isCapturing.getAndSet(false)) return

        try {
            captureThread?.join(300)
        } catch (ignored: Exception) {}
        captureThread = null

        try {
            noiseSuppressor?.release()
        } catch (ignored: Exception) {}
        noiseSuppressor = null

        try {
            echoCanceler?.release()
        } catch (ignored: Exception) {}
        echoCanceler = null

        try {
            audioRecord?.let { rec ->
                if (rec.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                    rec.stop()
                }
                rec.release()
            }
        } catch (ignored: Exception) {}
        audioRecord = null
        Log.i(TAG, "Captura de micrófono detenida")
    }

    companion object {
        private const val TAG = "DroidLens.AudioCapture"
        const val SAMPLE_RATE = 48000
        const val CHUNK_SAMPLES = 960 // 20 ms a 48 kHz
        const val CHUNK_BYTES = CHUNK_SAMPLES * 2 // 1920 bytes
    }
}
