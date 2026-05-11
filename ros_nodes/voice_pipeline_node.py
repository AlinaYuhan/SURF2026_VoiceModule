from __future__ import annotations

import json
import logging
import time

import numpy as np
from rclpy.node import Node
from std_msgs.msg import Bool, Float32, String

from asr.asr_engine import ASREngine
from audio.audio_bus import AudioBus
from audio.mic_capture import MicCapture
from config.voice_config import CONFIG
from vad.vad_engine import VADEngine
from voice_id.voiceprint_recognizer import VoiceprintRecognizer
from wake_word.wake_word_detector import WakeWordDetector
from wake_word.wakeup_dispatcher import WakeupDispatcher

logger = logging.getLogger(__name__)


class VoicePipelineNode(Node):
    """ROS2 主节点，串联所有语音模块。

    状态机：
      IDLE ──唤醒词触发──► RECORDING
      RECORDING ──VAD静音/超时──► IDLE（触发转写）
    """

    def __init__(self) -> None:
        super().__init__("voice_pipeline")

        self._pub_audio   = self.create_publisher(String, CONFIG.ros_audio_topic, 10)
        self._pub_wake    = self.create_publisher(String, CONFIG.ros_wake_topic, 10)
        self._pub_vad     = self.create_publisher(Bool,   CONFIG.ros_vad_topic, 10)
        self._pub_speaker = self.create_publisher(String, CONFIG.ros_speaker_topic, 10)

        self._bus      = AudioBus()
        self._vad      = VADEngine()
        self._dispatch = WakeupDispatcher()
        self._dispatch.register(self._on_wake)
        self._wakeword = WakeWordDetector(on_detected=self._dispatch.on_detection)
        self._asr      = ASREngine(on_result=self._on_asr)
        self._vprint   = VoiceprintRecognizer(on_embedding=self._on_embedding)
        self._mic      = MicCapture(bus=self._bus)

        self._bus.register(self._vad.process_frame)
        self._bus.register(self._wakeword.push_audio)
        self._bus.register(self._asr.push_audio)
        self._bus.register(self._vprint.push_audio)
        self._vad.register(self._on_vad)

        self._asr_deadline: float = 0.0
        self._timer = self.create_timer(0.5, self._check_asr_timeout)

    def start(self) -> None:
        self._wakeword.start()
        self._mic.start()

    def stop(self) -> None:
        self._mic.stop()
        self._wakeword.stop()

    # ── 回调 ──────────────────────────────────────────────────────────────

    def _on_wake(self, word: str) -> None:
        self._pub_wake.publish(String(data=word))
        self._asr.start_recording()
        self._vprint.start_capture()
        self._asr_deadline = time.monotonic() + CONFIG.asr_window_sec

    def _on_vad(self, is_speech: bool) -> None:
        self._pub_vad.publish(Bool(data=is_speech))
        if not is_speech:
            # ASREngine 内部判断 _recording 状态，IDLE 时直接返回
            self._asr.stop_and_transcribe()

    def _on_asr(self, text: str) -> None:
        self._pub_audio.publish(String(data=json.dumps({"text": text})))

    def _on_embedding(self, embedding: np.ndarray) -> None:
        self._pub_speaker.publish(String(data=json.dumps({"embedding": embedding.tolist()})))

    def _check_asr_timeout(self) -> None:
        if self._asr_deadline and time.monotonic() > self._asr_deadline:
            self._asr_deadline = 0.0
            self._asr.stop_and_transcribe()


def main() -> None:
    import rclpy
    rclpy.init()
    node = VoicePipelineNode()
    node.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()
