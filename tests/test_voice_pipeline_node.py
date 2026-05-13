from __future__ import annotations

import json
import sys
import time
from unittest.mock import MagicMock, patch

import numpy as np

# ── Mock rclpy 和 std_msgs（conda voice 环境没有 ROS2）──────────────────

class _MockNode:
    """最小化 rclpy.node.Node 替身，供继承使用。"""
    def __init__(self, name: str):
        self._name = name
    def create_publisher(self, msg_type, topic, qos):
        return MagicMock()
    def create_timer(self, period, callback):
        return MagicMock()
    def get_logger(self):
        return MagicMock()
    def destroy_node(self):
        pass


class _MockString:
    def __init__(self, data=""):
        self.data = data

class _MockBool:
    def __init__(self, data=False):
        self.data = data

class _MockFloat32:
    def __init__(self, data=0.0):
        self.data = data


_rclpy_mock = MagicMock()
_rclpy_mock.node.Node = _MockNode
sys.modules.setdefault("rclpy", _rclpy_mock)
sys.modules.setdefault("rclpy.node", _rclpy_mock.node)

_std_msgs_mock = MagicMock()
_std_msgs_mock.msg.String  = _MockString
_std_msgs_mock.msg.Bool    = _MockBool
_std_msgs_mock.msg.Float32 = _MockFloat32
sys.modules.setdefault("std_msgs", _std_msgs_mock)
sys.modules.setdefault("std_msgs.msg", _std_msgs_mock.msg)

# ── 现在可以安全导入 ────────────────────────────────────────────────────

from ros_nodes.voice_pipeline_node import VoicePipelineNode  # noqa: E402


# ── 辅助函数 ────────────────────────────────────────────────────────────

def _make_node():
    """构建 VoicePipelineNode，mock 掉所有重型组件。"""
    with patch("ros_nodes.voice_pipeline_node.WakeWordDetector")        as MockWWD, \
         patch("ros_nodes.voice_pipeline_node.ChineseWakeWordDetector") as MockCWWD, \
         patch("ros_nodes.voice_pipeline_node.ASREngine")               as MockASR, \
         patch("ros_nodes.voice_pipeline_node.VoiceprintRecognizer")    as MockVPR, \
         patch("ros_nodes.voice_pipeline_node.MicCapture")              as MockMic, \
         patch("ros_nodes.voice_pipeline_node.WakeupDispatcher")        as MockDisp:
        node = VoicePipelineNode()
    return node


# ── 测试 ────────────────────────────────────────────────────────────────

def test_on_wake_starts_asr_and_voiceprint():
    node = _make_node()
    node._on_wake("hey_jarvis")
    node._asr.start_recording.assert_called_once()
    node._vprint.start_capture.assert_called_once()
    node._pub_wake.publish.assert_called_once()
    assert node._asr_deadline > 0


def test_on_vad_silence_stops_asr():
    node = _make_node()
    node._on_vad(False)
    node._asr.stop_and_transcribe.assert_called_once()


def test_on_asr_publishes_json():
    node = _make_node()
    node._current_speaker = "用户1"
    node._on_asr("你好世界")
    call_args = node._pub_audio.publish.call_args[0][0]
    payload = json.loads(call_args.data)
    assert payload == {"text": "你好世界", "speaker": "用户1"}


def test_on_embedding_identifies_and_publishes_speaker():
    node = _make_node()
    emb = np.ones(256, dtype=np.float32)
    node._on_embedding(emb)
    assert node._current_speaker == "用户1"
    call_args = node._pub_speaker.publish.call_args[0][0]
    payload = json.loads(call_args.data)
    assert payload == {"speaker": "用户1"}


def test_asr_timeout_triggers_stop():
    node = _make_node()
    node._asr_deadline = time.monotonic() - 1.0  # 已超时
    node._check_asr_timeout()
    node._asr.stop_and_transcribe.assert_called_once()
    assert node._asr_deadline == 0.0


def test_on_vad_silence_suppressed_during_holdoff():
    node = _make_node()
    node._on_wake("你好小浦")        # 触发 hold-off
    node._on_vad(False)              # hold-off 期内，不应触发转写
    node._asr.stop_and_transcribe.assert_not_called()


def test_on_vad_silence_triggers_after_holdoff():
    node = _make_node()
    node._vad_holdoff_until = time.monotonic() - 0.1  # hold-off 已过期
    node._on_vad(False)
    node._asr.stop_and_transcribe.assert_called_once()
