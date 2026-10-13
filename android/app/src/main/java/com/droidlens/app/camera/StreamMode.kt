package com.droidlens.app.camera

/**
 * Modos de operación bidireccionales sincronizados entre Android y PC.
 */
enum class StreamMode(val code: Byte, val title: String) {
    VIDEO_ONLY(1, "Solo Cámara"),
    AUDIO_ONLY(2, "Solo Micrófono"),
    AUDIO_VIDEO(3, "Cámara + Micrófono");

    fun next(): StreamMode = when (this) {
        AUDIO_VIDEO -> VIDEO_ONLY
        VIDEO_ONLY -> AUDIO_ONLY
        AUDIO_ONLY -> AUDIO_VIDEO
    }

    companion object {
        fun fromCode(code: Byte): StreamMode? = entries.find { it.code == code }
    }
}
