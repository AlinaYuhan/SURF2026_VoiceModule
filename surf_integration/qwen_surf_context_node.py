from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

import requests
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from project_config import CONFIG


HTTP_SESSION = requests.Session()
HTTP_SESSION.trust_env = False


@dataclass
class SurfContext:
    wake_word: str = ""
    wake_time: float = 0.0
    vad_is_speech: bool = False
    vad_time: float = 0.0
    speaker: str = ""
    speaker_time: float = 0.0


class QwenSurfContextNode(Node):
    """Consume SURF context topics and run the qwen reply/TTS/action backend."""

    def __init__(self) -> None:
        super().__init__("qwen_surf_context_node")
        self.force_always_listen = CONFIG.always_listen
        self.awaiting_command_after_wake = False
        self.surf_context = SurfContext()
        self.status: dict[str, Any] = {
            "pipeline": "surf_qwen_workspace",
            "reply_backend": os.environ.get("QWEN_REPLY_BACKEND", "local"),
            "action_execute": CONFIG.action_execute,
            "action_release_after_sec": CONFIG.action_release_after_sec,
            "last_error": "",
            "latency": {},
        }
        self._status_lock = threading.Lock()
        self._action_lock = threading.Lock()

        self.create_subscription(String, CONFIG.ros_audio_topic, self.on_audio_msg, 10)
        self.create_subscription(String, CONFIG.surf_wake_topic, self.on_wake, 10)
        self.create_subscription(Bool, CONFIG.surf_vad_topic, self.on_vad, 10)
        self.create_subscription(String, CONFIG.surf_speaker_topic, self.on_speaker, 10)

        CONFIG.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._update_status(
            service_state="ready",
            qwen_server_url=CONFIG.qwen_server_url,
            action_backend=CONFIG.action_backend,
            action_keyword_first=CONFIG.action_keyword_first,
        )
        self.get_logger().info("Qwen SURF context node ready.")
        self.get_logger().info(f"SURF ASR topic: {CONFIG.ros_audio_topic}")
        self.get_logger().info(f"SURF wake topic: {CONFIG.surf_wake_topic}")
        self.get_logger().info(f"SURF VAD topic: {CONFIG.surf_vad_topic}")
        self.get_logger().info(f"SURF speaker topic: {CONFIG.surf_speaker_topic}")
        self.get_logger().info(f"Qwen server: {CONFIG.qwen_server_url}")
        self.get_logger().info(
            "Reply action bridge: "
            f"enabled={CONFIG.action_enable}, execute={CONFIG.action_execute}, "
            f"backend={CONFIG.action_backend}, network={CONFIG.unitree_network_interface}"
        )
        self.get_logger().info(
            "Qwen wake filter: "
            + ("disabled; SURF wake-word gates ASR." if self.force_always_listen else "enabled as a second filter.")
        )

    def on_wake(self, msg: String) -> None:
        self.surf_context.wake_word = msg.data
        self.surf_context.wake_time = time.time()
        self._write_status()
        self._update_status(last_wake=msg.data, last_wake_time=self.surf_context.wake_time)
        self.get_logger().info(f"SURF wake detected: {msg.data}")

    def on_vad(self, msg: Bool) -> None:
        self.surf_context.vad_is_speech = bool(msg.data)
        self.surf_context.vad_time = time.time()
        self._write_status()
        self.get_logger().debug(f"SURF VAD: {self.surf_context.vad_is_speech}")

    def on_speaker(self, msg: String) -> None:
        speaker = ""
        try:
            payload = json.loads(msg.data)
            speaker = str(payload.get("speaker", "")).strip()
        except Exception:
            speaker = msg.data.strip()

        if speaker:
            self.surf_context.speaker = speaker
            self.surf_context.speaker_time = time.time()
            self._write_status()
            self._update_status(last_speaker=speaker, last_speaker_time=self.surf_context.speaker_time)
            self.get_logger().info(f"SURF speaker: {speaker}")

    def on_audio_msg(self, msg: String) -> None:
        received_at = time.time()
        raw = msg.data
        speaker_from_audio = ""
        confidence: float | None = None
        try:
            data = json.loads(raw)
            user_text = str(data.get("text", "")).strip()
            speaker_from_audio = str(data.get("speaker", "")).strip()
            if "confidence" in data:
                confidence = float(data.get("confidence", 0.0))
        except Exception:
            user_text = raw.strip()

        if speaker_from_audio:
            self.surf_context.speaker = speaker_from_audio
            self.surf_context.speaker_time = time.time()

        if not user_text:
            return

        ignore_reason = self._asr_ignore_reason(user_text, confidence)
        if ignore_reason:
            self.get_logger().warn(f"Ignoring ASR text: reason={ignore_reason}, text={user_text}")
            self._update_status(
                last_ignored_asr=user_text,
                last_ignored_asr_reason=ignore_reason,
                last_error=f"ignored_asr:{ignore_reason}",
                updated_at=time.time(),
            )
            return

        self.get_logger().info(
            f"SURF ASR text: {user_text}"
            + (f" speaker={self.surf_context.speaker}" if self.surf_context.speaker else "")
        )
        self._update_status(
            last_asr=user_text,
            last_asr_time=received_at,
            last_audio_confidence=confidence,
            last_error="",
            latency={
                **self.status.get("latency", {}),
                "wake_to_asr_ms": self._elapsed_ms(self.surf_context.wake_time, received_at),
            },
        )

        if not self.force_always_listen:
            command_text = self.strip_wake_word(user_text)
            if command_text is None:
                if not self.awaiting_command_after_wake:
                    self.get_logger().info("Second qwen wake filter did not match; ignoring ASR text.")
                    return
                command_text = user_text.strip()
                self.awaiting_command_after_wake = False
            elif not command_text:
                self.awaiting_command_after_wake = True
                self.get_logger().info("Second qwen wake filter matched. Waiting for next command.")
                return
            user_text = command_text

        qwen_text = self._build_qwen_text(user_text)
        qwen_started_at = time.time()
        reply = self._request_qwen(qwen_text)
        qwen_finished_at = time.time()
        if not reply:
            self._update_status(last_error="qwen_request_failed", updated_at=time.time())
            return

        self.get_logger().info(f"Qwen reply: {reply}")
        self._update_status(
            last_reply=reply,
            last_reply_time=qwen_finished_at,
            latency={
                **self.status.get("latency", {}),
                "qwen_ms": self._elapsed_ms(qwen_started_at, qwen_finished_at),
                "wake_to_reply_ms": self._elapsed_ms(self.surf_context.wake_time, qwen_finished_at),
            },
        )

        action_thread = threading.Thread(target=self.run_reply_action, args=(reply, user_text), daemon=True)
        action_thread.start()

        tts_started_at = time.time()
        if not self._convert_tts_to_wav():
            self._update_status(last_error="tts_wav_failed", updated_at=time.time())
            action_thread.join(timeout=0)
            return
        self._update_status(
            last_tts_wav=str(CONFIG.tts_wav_path),
            last_tts_time=time.time(),
            latency={
                **self.status.get("latency", {}),
                "tts_convert_ms": self._elapsed_ms(tts_started_at, time.time()),
            },
        )

    @staticmethod
    def strip_wake_word(text: str) -> str | None:
        lowered_text = text.lower()
        for wake_word in CONFIG.wake_words:
            index = lowered_text.find(wake_word.lower())
            if index < 0:
                continue
            prefix = text[:index]
            suffix = text[index + len(wake_word):]
            return (prefix + suffix).strip("，,。.!！?？ ")

        compact_text = text.replace(" ", "")
        for wake_word in CONFIG.wake_words:
            compact_wake = wake_word.replace(" ", "")
            index = compact_text.lower().find(compact_wake.lower())
            if index < 0:
                continue
            prefix = compact_text[:index]
            suffix = compact_text[index + len(compact_wake):]
            return (prefix + suffix).strip("，,。.!！?？ ")

        return None

    @staticmethod
    def _elapsed_ms(start: float, end: float) -> int | None:
        if not start:
            return None
        return int((end - start) * 1000)

    def _asr_ignore_reason(self, text: str, confidence: float | None) -> str:
        if not CONFIG.filter_bad_asr:
            return ""
        stripped = text.strip()
        if not stripped:
            return "empty"
        if confidence is not None and confidence < CONFIG.min_audio_confidence:
            return f"low_confidence_{confidence:.2f}"
        meaningful = re.sub(r"[\s，。！？、,.!?;:：；'\"“”‘’\-()（）\[\]{}]", "", stripped)
        if len(meaningful) < CONFIG.min_asr_chars:
            return "too_short"
        if not re.search(r"[\u3040-\u30ff\u4e00-\u9fffA-Za-z0-9]", meaningful):
            return "punctuation_only"
        lowered = stripped.lower()
        english_tokens = re.findall(r"[a-z]+", lowered)
        if english_tokens and not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", stripped):
            token_set = set(english_tokens)
            filler_tokens = {"the", "oe", "uh", "um", "er", "ah"}
            if token_set <= filler_tokens:
                return "english_filler"
        return ""

    def _build_qwen_text(self, user_text: str) -> str:
        if not CONFIG.include_speaker_context or not self.surf_context.speaker:
            return user_text

        return (
            f"系统上下文：当前说话人是{self.surf_context.speaker}。"
            "除非用户询问身份或上下文，否则不要在回复中复述这句系统上下文。"
            f"\n用户说：{user_text}"
        )

    def _request_qwen(self, text: str) -> str:
        try:
            response = HTTP_SESSION.get(
                CONFIG.qwen_server_url,
                params={"text": text},
                timeout=CONFIG.request_timeout_sec,
            )
            response.raise_for_status()
            result = response.json()
        except Exception as exc:
            self.get_logger().error(f"Qwen request failed: {exc}")
            return ""

        reply = str(result.get("reply", "")).strip()
        if not reply:
            self.get_logger().error("Empty reply from Qwen")
        return reply

    def _convert_tts_to_wav(self) -> bool:
        if not CONFIG.tts_mp3_path.exists():
            self.get_logger().error(f"{CONFIG.tts_mp3_path} not found; Qwen server did not generate it")
            return False

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(CONFIG.tts_mp3_path),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(CONFIG.tts_wav_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            self.get_logger().error(f"ffmpeg conversion failed: {exc}")
            return False

        if not CONFIG.tts_wav_path.exists():
            self.get_logger().error(f"{CONFIG.tts_wav_path} not generated")
            return False

        self.get_logger().info(f"TTS wav generated successfully: {CONFIG.tts_wav_path}")
        return True

    def run_reply_action(self, reply: str, user_text: str = "") -> None:
        if not CONFIG.action_enable:
            return
        if not self._action_lock.acquire(blocking=False):
            self.get_logger().warn("Skipping reply action because another action is still running.")
            self._update_status(last_error="action_busy", updated_at=time.time())
            return

        try:
            self._run_reply_action_locked(reply, user_text)
        finally:
            self._action_lock.release()

    def _run_reply_action_locked(self, reply: str, user_text: str = "") -> None:
        started_at = time.time()
        payload: dict[str, Any] | None = None
        command = self._action_command(reply, CONFIG.action_backend)

        if CONFIG.action_keyword_first and user_text:
            user_payload = self._run_action_classifier(user_text, "keyword")
            if user_payload:
                user_classification = user_payload.get("classification", {})
                if self._int_or_default(user_classification.get("action_id"), -1) >= 0:
                    payload = user_payload
                    command = self._action_command(user_text, "keyword")

        if payload is None:
            payload = self._run_action_classifier(reply, CONFIG.action_backend)

        if payload is None:
            self._update_status(last_error="action_classifier_failed", updated_at=time.time())
            return

        classification = payload.get("classification", {})
        execution = payload.get("execution", {})
        self._log_action_result(classification, execution, started_at, command, reply)

    def _log_action_result(
        self,
        classification: dict[str, Any],
        execution: dict[str, Any],
        started_at: float,
        command: list[str],
        reply: str,
    ) -> None:
        if (
            CONFIG.action_keyword_first
            and CONFIG.action_backend != "keyword"
            and classification.get("label") == "无动作"
            and classification.get("backend") == "qwen"
        ):
            keyword_payload = self._run_action_classifier(reply, "keyword")
            if keyword_payload:
                keyword_classification = keyword_payload.get("classification", {})
                keyword_execution = keyword_payload.get("execution", {})
                if self._int_or_default(keyword_classification.get("action_id"), -1) >= 0:
                    classification = keyword_classification
                    execution = keyword_execution

        self.get_logger().info(
            "Reply action: "
            f"{classification.get('label')} / {classification.get('official_name')} "
            f"id={classification.get('action_id')} "
            f"score={classification.get('score')} "
            f"backend={classification.get('backend')} "
            f"executed={execution.get('executed')} "
            f"reason={execution.get('reason')}"
        )
        self._update_status(
            last_action=classification.get("label"),
            last_action_id=classification.get("action_id"),
            last_action_score=classification.get("score"),
            last_action_backend=classification.get("backend"),
            last_action_executed=execution.get("executed"),
            last_action_reason=execution.get("reason"),
            last_action_time=time.time(),
            latency={
                **self.status.get("latency", {}),
                "action_ms": self._elapsed_ms(started_at, time.time()),
            },
        )

        if (
            CONFIG.action_auto_release
            and CONFIG.action_execute
            and execution.get("reason") == "arm_holding_release_required"
        ):
            self.get_logger().warn("Arm is holding; running release action 99 and retrying once.")
            if self.release_arm():
                self.retry_reply_action(command)
            return

        if (
            CONFIG.action_execute
            and CONFIG.action_release_after_sec > 0
            and execution.get("executed")
            and self._int_or_default(classification.get("action_id"), -1) not in (-1, 99)
        ):
            self.get_logger().info(
                f"Action completed; releasing arm in {CONFIG.action_release_after_sec:.1f}s."
            )
            time.sleep(CONFIG.action_release_after_sec)
            self.release_arm()

    @staticmethod
    def _int_or_default(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _action_command(self, reply: str, backend: str) -> list[str]:
        command = [
            CONFIG.action_python,
            str(CONFIG.action_script),
            reply,
            "--backend",
            backend,
            "--threshold",
            str(CONFIG.action_threshold),
            "--network",
            CONFIG.unitree_network_interface,
            "--runner",
            str(CONFIG.action_runner),
        ]
        if backend == "qwen" and not CONFIG.action_keyword_first:
            command.append("--no-keyword-first")
        if CONFIG.action_execute:
            command.append("--execute")
        return command

    def _run_action_classifier(self, reply: str, backend: str) -> dict[str, Any] | None:
        try:
            completed = subprocess.run(
                self._action_command(reply, backend),
                check=False,
                text=True,
                capture_output=True,
                timeout=90,
                env=self.action_env(),
            )
        except Exception as exc:
            self.get_logger().warn(f"{backend} action classifier failed: {exc}")
            return None
        try:
            return json.loads(completed.stdout)
        except Exception:
            self.get_logger().warn(f"{backend} action classifier returned non-JSON: {completed.stdout.strip()}")
            return None

    @staticmethod
    def action_env() -> dict[str, str]:
        env = os.environ.copy()
        env["NO_PROXY"] = "127.0.0.1,localhost," + env.get("NO_PROXY", "")
        env["no_proxy"] = "127.0.0.1,localhost," + env.get("no_proxy", "")
        sdk_root = CONFIG.action_runner.parent.parent.parent
        unitree_lib_dir = sdk_root / "thirdparty" / "lib" / os.uname().machine
        if unitree_lib_dir.is_dir():
            existing = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = str(unitree_lib_dir) + (f":{existing}" if existing else "")
        return env

    def release_arm(self) -> bool:
        try:
            completed = subprocess.run(
                [
                    str(CONFIG.action_runner),
                    "--network",
                    CONFIG.unitree_network_interface,
                    "--id",
                    "99",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=20,
                env=self.action_env(),
            )
        except Exception as exc:
            self.get_logger().error(f"Release arm action failed: {exc}")
            return False

        if completed.stdout:
            self.get_logger().info(f"Release arm stdout: {completed.stdout.strip()}")
        if completed.stderr:
            self.get_logger().warn(f"Release arm stderr: {completed.stderr.strip()}")
        ok = completed.returncode == 0
        self._update_status(last_release_arm_ok=ok, last_release_arm_time=time.time())
        return ok

    def retry_reply_action(self, command: list[str]) -> None:
        try:
            completed = subprocess.run(
                command,
                check=False,
                text=True,
                capture_output=True,
                timeout=90,
                env=self.action_env(),
            )
        except Exception as exc:
            self.get_logger().error(f"Reply action retry failed: {exc}")
            return

        try:
            payload = json.loads(completed.stdout)
        except Exception:
            self.get_logger().error(f"Reply action retry returned non-JSON output: {completed.stdout.strip()}")
            return

        classification = payload.get("classification", {})
        execution = payload.get("execution", {})
        self.get_logger().info(
            "Reply action retry: "
            f"{classification.get('label')} id={classification.get('action_id')} "
            f"executed={execution.get('executed')} reason={execution.get('reason')}"
        )

    def _write_status(self) -> None:
        if not CONFIG.write_context_status:
            return
        status_path = CONFIG.runtime_dir / "surf_context_status.json"
        payload: dict[str, Any] = asdict(self.surf_context)
        payload["updated_at"] = time.time()
        try:
            status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.get_logger().warn(f"Failed to write context status: {exc}")

    def _update_status(self, **updates: Any) -> None:
        if not CONFIG.write_context_status:
            return
        status_path = CONFIG.runtime_dir / "status.json"
        with self._status_lock:
            latency = updates.pop("latency", None)
            self.status.update(updates)
            if latency is not None:
                self.status["latency"] = latency
            self.status["surf_context"] = asdict(self.surf_context)
            self.status["updated_at"] = time.time()
            payload = json.dumps(self.status, ensure_ascii=False, indent=2)
        try:
            status_path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            self.get_logger().warn(f"Failed to write pipeline status: {exc}")


def main() -> None:
    rclpy.init()
    node = QwenSurfContextNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
