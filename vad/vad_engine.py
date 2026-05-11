from __future__ import annotations

import logging
from typing import Callable

import webrtcvad

from config.voice_config import CONFIG

logger = logging.getLogger(__name__)

VADCallback = Callable[[bool], None]


class VADEngine:
    """Frame-level voice activity detector backed by webrtcvad.

    Accepts exactly CONFIG.frame_bytes of raw 16-bit mono PCM per call.
    Fires registered callbacks with True (speech) or False (silence) on
    each frame, but only when state changes (rising/falling edge).
    """

    def __init__(self, aggressiveness: int = 2) -> None:
        if not 0 <= aggressiveness <= 3:
            raise ValueError(f"aggressiveness must be 0-3, got {aggressiveness}")
        self._vad = webrtcvad.Vad(aggressiveness)
        self._callbacks: list[VADCallback] = []
        self._is_speech: bool = False

    def register(self, callback: VADCallback) -> None:
        self._callbacks.append(callback)

    def unregister(self, callback: VADCallback) -> None:
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def process_frame(self, frame: bytes) -> bool:
        """Process one PCM frame; return True if speech detected."""
        if len(frame) != CONFIG.frame_bytes:
            raise ValueError(
                f"Expected {CONFIG.frame_bytes} bytes, got {len(frame)}"
            )
        is_speech = self._vad.is_speech(frame, CONFIG.sample_rate)
        if is_speech != self._is_speech:
            self._is_speech = is_speech
            self._notify(is_speech)
        return is_speech

    def _notify(self, state: bool) -> None:
        for cb in list(self._callbacks):
            try:
                cb(state)
            except Exception:
                logger.exception("VADEngine callback %r raised", cb)
