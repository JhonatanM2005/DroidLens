package com.droidlens.app.network

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Protocolo binario de empaquetado APCM para transmisión USB de ultra baja latencia.
 * Cabecera fija de 20 bytes:
 *   [0..3]   MAGIC        -> 4 bytes: 'APCM'
 *   [4..7]   FRAME_ID     -> uint32 (Int) big-endian
 *   [8..15]  TIMESTAMP_MS -> uint64 (Long) big-endian
 *   [16..19] LENGTH       -> uint32 (Int) big-endian
 * Cuerpo:
 *   [20..N]  PAYLOAD      -> bytes JPEG de la imagen
 */
object PacketProtocol {
    val MAGIC = byteArrayOf('A'.code.toByte(), 'P'.code.toByte(), 'C'.code.toByte(), 'M'.code.toByte())
    const val HEADER_SIZE = 20

    fun packFrame(frameId: Int, timestampMs: Long, jpegData: ByteArray): ByteArray {
        val totalSize = HEADER_SIZE + jpegData.size
        val buffer = ByteBuffer.allocate(totalSize).order(ByteOrder.BIG_ENDIAN)

        buffer.put(MAGIC)
        buffer.putInt(frameId)
        buffer.putLong(timestampMs)
        buffer.putInt(jpegData.size)
        buffer.put(jpegData)

        return buffer.array()
    }
}
