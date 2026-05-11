from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v is not None else default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v is not None else default


def _env_int_opt(name: str) -> int | None:
    v = os.environ.get(name)
    return int(v) if v is not None else None


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    v = os.environ.get(name)
    if not v:
        return default
    return tuple(s.strip() for s in v.split(",") if s.strip())


@dataclass(frozen=True)
class VoiceConfig:
    sample_rate: int            = _env_int("VOICE_SAMPLE_RATE", 16000)
    channels: int               = _env_int("VOICE_CHANNELS", 1)
    frame_ms: int               = _env_int("VOICE_FRAME_MS", 20)
    bus_buffer_sec: float       = _env_float("VOICE_BUS_BUFFER_SEC", 1.0)

    mic_device: int | None      = _env_int_opt("VOICE_MIC_DEVICE")

    wake_words: tuple[str, ...] = _env_list("VOICE_WAKE_WORDS", ("hey jarvis", "alexa"))
    wake_threshold: float       = _env_float("VOICE_WAKE_THRESHOLD", 0.5)
    wakeup_dedup_sec: float     = _env_float("VOICE_WAKEUP_DEDUP_SEC", 0.5)

    asr_model: str              = _env("VOICE_ASR_MODEL", "paraformer-zh")
    asr_window_sec: float       = _env_float("VOICE_ASR_WINDOW_SEC", 5.0)

    voiceprint_capture_sec: float = _env_float("VOICE_VOICEPRINT_SEC", 2.0)
    voiceprint_model: str         = _env("VOICE_VOICEPRINT_MODEL",
                                         "pyannote/wespeaker-voxceleb-resnet34-LM")

    ros_audio_topic: str        = _env("VOICE_ROS_AUDIO_TOPIC", "/audio_msg")
    ros_direction_topic: str    = _env("VOICE_ROS_DIRECTION_TOPIC", "/voice_direction")
    ros_wake_topic: str         = _env("VOICE_ROS_WAKE_TOPIC", "/wake_word_event")
    ros_vad_topic: str          = _env("VOICE_ROS_VAD_TOPIC", "/vad_state")
    ros_speaker_topic: str      = _env("VOICE_ROS_SPEAKER_TOPIC", "/speaker_id")

    @property
    def frame_bytes(self) -> int:
        """Exact PCM byte length for one VAD frame (16-bit mono)."""
        return int(self.sample_rate * self.frame_ms / 1000) * 2


CONFIG = VoiceConfig()
