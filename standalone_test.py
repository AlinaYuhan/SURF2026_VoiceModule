"""
standalone_test.py — 本地 PC 冒烟测试，不依赖 ROS2。

用法（conda voice 环境，WSL2）：
    PULSE_SERVER=unix:/mnt/wslg/PulseServer python standalone_test.py

流程：说唤醒词（默认"你好小G"）→ 进入录音 → 说指令 → 停顿后自动转写 → 打印结果
按 Ctrl+C 退出。
"""
from __future__ import annotations

import os
import pathlib
import queue
import time

import numpy as np

# WSL2：让 sounddevice 通过 WSLg PulseAudio 访问 Windows 麦克风
if not os.environ.get("PULSE_SERVER"):
    os.environ["PULSE_SERVER"] = "unix:/mnt/wslg/PulseServer"

from asr.asr_engine import ASREngine
from audio.audio_bus import AudioBus
from audio.mic_capture import MicCapture
from config.voice_config import CONFIG
from vad.vad_engine import VADEngine
from voice_id.speaker_database import SpeakerDatabase
from voice_id.voiceprint_recognizer import VoiceprintRecognizer
from wake_word.chinese_wake_word_detector import ChineseWakeWordDetector
from wake_word.wakeup_dispatcher import WakeupDispatcher


# ── 状态 ──────────────────────────────────────────────────────────────────────

_recording = False
_asr_deadline: float = 0.0
_vad_holdoff_until: float = 0.0
_session_counter: int = 0
_current_asr_session: int = 0
_session_queue: queue.Queue[int] = queue.Queue()
_speaker_db = SpeakerDatabase()


# ── 回调 ──────────────────────────────────────────────────────────────────────

def on_wake(word: str) -> None:
    global _recording, _asr_deadline, _vad_holdoff_until, _session_counter, _current_asr_session
    _recording = True
    _asr_deadline = time.monotonic() + CONFIG.asr_window_sec
    _vad_holdoff_until = time.monotonic() + CONFIG.vad_holdoff_sec
    _session_counter += 1
    _current_asr_session = _session_counter
    _session_queue.put(_session_counter)
    print(f"\n[唤醒 #{_session_counter}] 检测到: {word!r}  →  开始录音（最长 {CONFIG.asr_window_sec}s）")
    bus_snapshot = bus.get_buffer()
    asr.start_recording(initial_audio=b"".join(bus_snapshot[-15:]))
    vprint.start_capture(initial_audio=b"".join(bus_snapshot))


def on_vad(is_speech: bool) -> None:
    global _recording
    state = "说话中..." if is_speech else "静音"
    print(f"[VAD]  {state}", end="\r")
    if not is_speech and _recording and time.monotonic() > _vad_holdoff_until:
        _recording = False
        print()
        asr.stop_and_transcribe()


def on_asr(text: str) -> None:
    print(f"[ASR #{_current_asr_session}]  {text}")


def on_embedding(embedding: np.ndarray) -> None:
    sid = _session_queue.get_nowait() if not _session_queue.empty() else "?"
    label = _speaker_db.identify(embedding)
    known = " / ".join(f"「{s}」" for s in _speaker_db.known_speakers)
    print(f"[声纹 #{sid}] {label}（已知说话人：{known}）")


# ── 组件初始化 ────────────────────────────────────────────────────────────────

print("初始化模型中，请稍候...")

bus    = AudioBus()
vad    = VADEngine()
disp   = WakeupDispatcher()
kws    = ChineseWakeWordDetector(on_detected=disp.on_detection)
asr    = ASREngine(on_result=on_asr)
vprint = VoiceprintRecognizer(on_embedding=on_embedding)
mic    = MicCapture(bus=bus)

disp.register(on_wake)
bus.register(vad.process_frame)
bus.register(kws.push_audio)
bus.register(asr.push_audio)
bus.register(vprint.push_audio)
vad.register(on_vad)

# ── 启动 ──────────────────────────────────────────────────────────────────────

kws.start()
mic.start()

keywords_file = pathlib.Path(CONFIG.kws_model_dir) / "keywords.txt"
wake_words = [
    line.split("@")[-1].strip()
    for line in keywords_file.read_text(encoding="utf-8").splitlines()
    if line.strip() and "@" in line
]
wake_str = " / ".join(f"「{w}」" for w in wake_words)
print(f"\n监听中...  唤醒词: {wake_str}")
print("说唤醒词后说指令，停顿后自动转写。按 Ctrl+C 退出。\n")

try:
    while True:
        # ASR 超时保护
        if _recording and _asr_deadline and time.monotonic() > _asr_deadline:
            _recording = False
            _asr_deadline = 0.0
            print("\n[超时] ASR 窗口到期，强制转写")
            asr.stop_and_transcribe()
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\n\n停止中...")
finally:
    mic.stop()
    kws.stop()
    print("已退出。")
