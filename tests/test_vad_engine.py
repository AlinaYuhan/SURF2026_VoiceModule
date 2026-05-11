from __future__ import annotations

import pytest

from config.voice_config import CONFIG
from vad.vad_engine import VADEngine


def test_process_frame_returns_bool(one_frame_pcm):
    engine = VADEngine()
    result = engine.process_frame(one_frame_pcm)
    assert isinstance(result, bool)


def test_wrong_frame_size_raises():
    engine = VADEngine()
    with pytest.raises(ValueError, match="Expected"):
        engine.process_frame(b"\x00" * (CONFIG.frame_bytes + 1))


def test_invalid_aggressiveness_raises():
    with pytest.raises(ValueError):
        VADEngine(aggressiveness=4)


def test_no_callback_when_no_state_change(silence_pcm):
    engine = VADEngine()
    events: list[bool] = []
    engine.register(events.append)

    silence_frame = silence_pcm[: CONFIG.frame_bytes]
    engine.process_frame(silence_frame)
    engine.process_frame(silence_frame)

    assert len(events) == 0


def test_callback_not_fired_on_repeated_same_state():
    engine = VADEngine()
    events: list[bool] = []
    engine.register(events.append)

    silence = b"\x00" * CONFIG.frame_bytes
    for _ in range(5):
        engine.process_frame(silence)

    assert len(events) == 0


def test_unregister_stops_callbacks():
    engine = VADEngine()
    events: list[bool] = []
    engine.register(events.append)
    engine.unregister(events.append)

    silence = b"\x00" * CONFIG.frame_bytes
    engine.process_frame(silence)
    assert events == []
