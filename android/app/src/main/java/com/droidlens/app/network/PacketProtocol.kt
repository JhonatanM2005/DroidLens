package com.droidlens.app.network

import com.droidlens.app.camera.StreamMode
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Protocolo binario de empaquetado APCM v2 para transmisión USB multiplexada.
 * Cabecera fija de 21 bytes (Big-Endian):
 *   [0..3]   MAGIC        -> 4 bytes: 'APCM'
 *   [4]      PACKET_TYPE  -> uint8 (1: VIDEO, 2: AUDIO, 3: CONTROL_MODE)
 *   [5..8]   SEQ_ID       -> uint32 (Int) big-endian
 *   [9..16]  TIMESTAMP_MS -> uint64 (Long) big-endian
 *   [17..20] LENGTH       -> uint32 (Int) big-endian
 * Cuerpo:
 *   [21..N]  PAYLOAD      -> bytes JPEG, chunk PCM 16-bit o byte de modo
 */
object PacketProtocol {
    val MAGIC = byteArrayOf('A'.code.toByte(), 'P'.code.toByte(), 'C'.code.toByte(), 'M'.code.toByte())
    const val HEADER_SIZE = 21

    const val TYPE_VIDEO: Byte = 1
    const val TYPE_AUDIO: Byte = 2
    const val TYPE_CONTROL_MODE: Byte = 3

    data class Header(
        val packetType: Byte,
        val seqId: Int,
        val timestampMs: Long,
        val payloadLength: Int
    )

    /**
     * Construye los 21 bytes de la cabecera APCM v2 especificando el tipo de paquete.
     */
    fun createHeader(packetType: Byte, seqId: Int, timestampMs: Long, payloadLength: Int): ByteArray {
        val buffer = ByteBuffer.allocate(HEADER_SIZE).order(ByteOrder.BIG_ENDIAN)
        buffer.put(MAGIC)
        buffer.put(packetType)
        buffer.putInt(seqId)
        buffer.putLong(timestampMs)
        buffer.putInt(payloadLength)
        return buffer.array()
    }

    /**
     * Sobrecarga para tramas de vídeo por defecto.
     */
    fun createHeader(frameId: Int, timestampMs: Long, payloadLength: Int): ByteArray {
        return createHeader(TYPE_VIDEO, frameId, timestampMs, payloadLength)
    }

    /**
     * Empaqueta frame completo (cabecera + payload) en un solo array.
     */
    fun packFrame(
        frameId: Int,
        timestampMs: Long,
        payloadData: ByteArray,
        packetType: Byte = TYPE_VIDEO
    ): ByteArray {
        val totalSize = HEADER_SIZE + payloadData.size
        val buffer = ByteBuffer.allocate(totalSize).order(ByteOrder.BIG_ENDIAN)
        buffer.put(MAGIC)
        buffer.put(packetType)
        buffer.putInt(frameId)
        buffer.putLong(timestampMs)
        buffer.putInt(payloadData.size)
        buffer.put(payloadData)
        return buffer.array()
    }

    /**
     * Empaqueta un comando bidireccional de cambio de modo (22 bytes totales).
     */
    fun packControlMode(
        mode: StreamMode,
        seqId: Int = 0,
        timestampMs: Long = System.currentTimeMillis()
    ): ByteArray {
        return packFrame(seqId, timestampMs, byteArrayOf(mode.code), TYPE_CONTROL_MODE)
    }

    /**
     * Parsea una cabecera de 21 bytes o retorna null si MAGIC o tipo son inválidos.
     */
    fun parseHeader(headerBytes: ByteArray): Header? {
        if (headerBytes.size < HEADER_SIZE) return null
        val buf = ByteBuffer.wrap(headerBytes, 0, HEADER_SIZE).order(ByteOrder.BIG_ENDIAN)
        val magic = ByteArray(4)
        buf.get(magic)
        if (!magic.contentEquals(MAGIC)) return null

        val packetType = buf.get()
        if (packetType != TYPE_VIDEO && packetType != TYPE_AUDIO && packetType != TYPE_CONTROL_MODE) {
            return null
        }

        val seqId = buf.int
        val timestampMs = buf.long
        val payloadLength = buf.int
        return Header(packetType, seqId, timestampMs, payloadLength)
    }
}
