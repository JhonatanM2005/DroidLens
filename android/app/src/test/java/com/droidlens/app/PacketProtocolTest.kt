package com.droidlens.app

import com.droidlens.app.camera.StreamMode
import com.droidlens.app.camera.VideoProfile
import com.droidlens.app.network.PacketProtocol
import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class PacketProtocolTest {

    @Test
    fun testHeaderCreationSizeAndValues() {
        val frameId = 1234
        val timestampMs = 9876543210L
        val payloadLen = 65536

        val header = PacketProtocol.createHeader(frameId, timestampMs, payloadLen)
        assertEquals("Cabecera debe medir exactamente 21 bytes", 21, header.size)

        val buf = ByteBuffer.wrap(header).order(ByteOrder.BIG_ENDIAN)
        val magic = ByteArray(4)
        buf.get(magic)
        assertArrayEquals("MAGIC debe ser APCM", PacketProtocol.MAGIC, magic)

        val packetType = buf.get()
        val readFid = buf.int
        val readTs = buf.long
        val readLen = buf.int

        assertEquals("PacketType por defecto debe ser VIDEO", PacketProtocol.TYPE_VIDEO, packetType)
        assertEquals("Frame ID debe coincidir", frameId, readFid)
        assertEquals("Timestamp ms debe coincidir", timestampMs, readTs)
        assertEquals("Payload length debe coincidir", payloadLen, readLen)
    }

    @Test
    fun testHeaderV2AudioAndControlMode() {
        val header = PacketProtocol.createHeader(PacketProtocol.TYPE_AUDIO, 10, 5000L, 1920)
        assertEquals(21, header.size)
        val parsed = PacketProtocol.parseHeader(header)
        assertNotNull(parsed)
        assertEquals(PacketProtocol.TYPE_AUDIO, parsed!!.packetType)
        assertEquals(10, parsed.seqId)
        assertEquals(5000L, parsed.timestampMs)
        assertEquals(1920, parsed.payloadLength)

        val ctrl = PacketProtocol.packControlMode(StreamMode.AUDIO_ONLY, seqId = 2, timestampMs = 7000L)
        assertEquals(22, ctrl.size)
        val ctrlHeader = PacketProtocol.parseHeader(ctrl.sliceArray(0 until 21))
        assertNotNull(ctrlHeader)
        assertEquals(PacketProtocol.TYPE_CONTROL_MODE, ctrlHeader!!.packetType)
        assertEquals(1, ctrlHeader.payloadLength)
        assertEquals(StreamMode.AUDIO_ONLY, StreamMode.fromCode(ctrl[21]))
    }

    @Test
    fun testPackFrameBackwardCompatibility() {
        val frameId = 7
        val timestampMs = 123456789L
        val fakeJpeg = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte(), 0xD9.toByte())

        val packet = PacketProtocol.packFrame(frameId, timestampMs, fakeJpeg)
        assertEquals("Tamaño total debe ser 21 + 4 = 25", 25, packet.size)

        val headerBytes = packet.sliceArray(0 until 21)
        val payloadBytes = packet.sliceArray(21 until 25)

        assertEquals("Cabecera debe medir 21 bytes", 21, headerBytes.size)
        assertArrayEquals("Payload debe coincidir", fakeJpeg, payloadBytes)
    }

    @Test
    fun testVideoProfilesDimensions() {
        assertEquals(1280, VideoProfile.HD_720P.width)
        assertEquals(720, VideoProfile.HD_720P.height)
        assertEquals(30, VideoProfile.HD_720P.targetFps)

        assertEquals(1920, VideoProfile.FULL_HD_1080P.width)
        assertEquals(1080, VideoProfile.FULL_HD_1080P.height)

        assertEquals(854, VideoProfile.LOW_POWER.width)
        assertEquals(480, VideoProfile.LOW_POWER.height)
    }
}
