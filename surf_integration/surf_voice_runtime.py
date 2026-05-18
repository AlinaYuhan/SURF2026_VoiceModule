from __future__ import annotations

import json
import logging
import os
import socket
import time

import numpy as np

from asr.asr_engine import ASREngine
from audio.audio_bus import AudioBus
from audio.mic_capture import MicCapture
from config.voice_config import CONFIG
from vad.vad_engine import VADEngine
from voice_id.speaker_database import SpeakerDatabase
from voice_id.voiceprint_recognizer import VoiceprintRecognizer
from wake_word.chinese_wake_word_detector import ChineseWakeWordDetector
from wake_word.wake_word_detector import WakeWordDetector
from wake_word.wakeup_dispatcher import WakeupDispatcher


logging.basicConfig(level=logging.INFO, format="[surf_voice_runtime] %(message)s")
logger = logging.getLogger(__name__)


class UdpEventSink:
    def __init__(self) -> None:
        self._addr = (
            os.environ.get("SURF_BRIDGE_HOST", "127.0.0.1"),
            int(os.environ.get("SURF_BRIDGE_PORT", "18765")),
        )
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def publish(self, topic: str, msg_type: str, data) -> None:
        payload = {
            "topic": topic,
            "type": msg_type,
            "data": data,
            "time": time.time(),
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._sock.sendto(raw, self._addr)


class SurfVoiceRuntime:
    def __init__(self) -> None:
        self._sink = UdpEventSink()
        self._bus = AudioBus()
        self._vad = VADEngine()
        self._dispatch = WakeupDispatcher()
        self._dispatch.register(self._on_wake)
        if CONFIG.wake_word_lang == "zh":
            self._wakeword = ChineseWakeWordDetector(on_detected=self._dispatch.on_detection)
        else:
            self._wakeword = WakeWordDetector(on_detected=self._dispatch.on_detection)
        self._asr = ASREngine(on_result=self._on_asr)
        self._vprint = VoiceprintRecognizer(on_embedding=self._on_embedding)
        self._speaker_db = SpeakerDatabase()
        self._current_speaker = ""

        if CONFIG.audio_source == "robot":
            from audio.robot_mic_capture import RobotMicCapture

            self._mic = RobotMicCapture(bus=self._bus)
        else:
            self._mic = MicCapture(bus=self._bus)

        self._bus.register(self._vad.process_frame)
        self._bus.register(self._wakeword.push_audio)
        self._bus.register(self._asr.push_audio)
        self._bus.register(self._vprint.push_audio)
        self._vad.register(self._on_vad)

        self._asr_deadline = 0.0
        self._vad_holdoff_until = 0.0

    def start(self) -> None:
        self._wakeword.start()
        self._mic.start()
        logger.info("ready, listening via %s", CONFIG.audio_source)

    def stop(self) -> None:
        self._mic.stop()
        self._wakeword.stop()

    def spin(self) -> None:
        while True:
            if self._asr_deadline and time.monotonic() > self._asr_deadline:
                self._asr_deadline = 0.0
                self._asr.stop_and_transcribe()
            time.sleep(0.1)

    def _on_wake(self, word: str) -> None:
        logger.info("wake: %s", word)
        self._sink.publish("/wake_word_event", "string", word)
        bus_snapshot = self._bus.get_buffer()
        self._asr.start_recording(initial_audio=b"".join(bus_snapshot[-15:]))
        self._vprint.start_capture(initial_audio=b"".join(bus_snapshot))
        self._asr_deadline = time.monotonic() + CONFIG.asr_window_sec
        self._vad_holdoff_until = time.monotonic() + CONFIG.vad_holdoff_sec

    def _on_vad(self, is_speech: bool) -> None:
        logger.info("vad: %s", is_speech)
        self._sink.publish("/vad_state", "bool", is_speech)
        if not is_speech and time.monotonic() > self._vad_holdoff_until:
            self._asr.stop_and_transcribe()

    def _on_asr(self, text: str) -> None:
        logger.info("asr: %s speaker=%s", text, self._current_speaker)
        self._sink.publish(
            "/audio_msg",
            "string",
            json.dumps({"text": text, "speaker": self._current_speaker}, ensure_ascii=False),
        )

    def _on_embedding(self, embedding: np.ndarray) -> None:
        self._current_speaker = self._speaker_db.identify(embedding)
        logger.info("speaker: %s", self._current_speaker)
        self._sink.publish(
            "/speaker_id",
            "string",
            json.dumps({"speaker": self._current_speaker}, ensure_ascii=False),
        )


def main() -> None:
    runtime = SurfVoiceRuntime()
    runtime.start()
    try:
        runtime.spin()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
