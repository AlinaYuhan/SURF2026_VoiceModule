"""全链路 Pipeline 日志记录器。

每次唤醒生成一个 session，数据写入：
  logs/
  └── 20260520_210301_s001/
      ├── pipeline.log   时间戳 + 各阶段耗时
      └── audio.wav      本次录音原始音频
"""
from __future__ import annotations

import json
import logging
import os
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LOGS_DIR = Path(os.environ.get("PIPELINE_LOGS_DIR", "logs"))


@dataclass
class SessionLog:
    session_id: str
    session_dir: Path
    _events: list[dict] = field(default_factory=list, repr=False)
    _t0: float = field(default_factory=time.monotonic, repr=False)

    def record(self, stage: str, **kwargs) -> float:
        """记录一个阶段事件，返回距离 session 开始的秒数。"""
        elapsed = time.monotonic() - self._t0
        entry = {
            "time": datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_sec": round(elapsed, 3),
            "stage": stage,
            **kwargs,
        }
        self._events.append(entry)
        logger.info("[%s] %s  +%.3fs", self.session_id, stage, elapsed)
        return elapsed

    def record_duration(self, stage: str, start: float, **kwargs) -> float:
        """记录带耗时的阶段（传入开始时间戳）。"""
        duration = time.monotonic() - start
        return self.record(stage, duration_sec=round(duration, 3), **kwargs)

    def save_audio(self, pcm_frames: list[bytes], sample_rate: int = 16000) -> None:
        """把录音 PCM 帧列表保存为 WAV。"""
        wav_path = self.session_dir / "audio.wav"
        try:
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                for frame in pcm_frames:
                    wf.writeframes(frame)
            self.record("audio_saved", path=str(wav_path))
        except Exception as e:
            logger.warning("音频保存失败: %s", e)

    def flush(self) -> None:
        """把所有事件写入 pipeline.log。"""
        log_path = self.session_dir / "pipeline.log"
        with open(log_path, "w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")


class PipelineLogger:
    """管理多个 session 的生命周期。"""

    def __init__(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._current: SessionLog | None = None

    def start_session(self, wake_word: str) -> SessionLog:
        self._counter += 1
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"{ts}_s{self._counter:03d}"
        session_dir = LOGS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        self._current = SessionLog(session_id=session_id, session_dir=session_dir)
        self._current.record("wake", wake_word=wake_word)
        return self._current

    def end_session(self) -> None:
        if self._current:
            self._current.record("session_end")
            self._current.flush()
            self._current = None

    @property
    def current(self) -> SessionLog | None:
        return self._current
