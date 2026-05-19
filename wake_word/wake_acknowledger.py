from __future__ import annotations

import logging
import os
import socket
import threading

logger = logging.getLogger(__name__)

_RELAY_HOST = os.environ.get("WAKE_ACK_RELAY_HOST", "")
_RELAY_PORT = int(os.environ.get("WAKE_ACK_RELAY_PORT", "9999"))


class WakeAcknowledger:
    """唤醒词确认音，通过 Jetson TTS relay 让机器人开口说话。

    需要 WAKE_ACK_RELAY_HOST 指向 tts_relay_server 的 IP。
    未设置时静默（不播本地音频，避免干扰麦克风）。
    """

    def __init__(
        self,
        relay_host: str = _RELAY_HOST,
        relay_port: int = _RELAY_PORT,
    ) -> None:
        self._relay = (relay_host, relay_port) if relay_host else None
        if self._relay:
            logger.info("wake ack relay: %s:%d", relay_host, relay_port)
        else:
            logger.info("wake ack relay not configured, running silent")

    def ack(self, word: str) -> None:
        if not self._relay:
            return
        text = "我在" if "你好小浦" in word else "I'm here"
        threading.Thread(target=self._send, args=(text,), daemon=True).start()

    def _send(self, text: str) -> None:
        try:
            with socket.create_connection(self._relay, timeout=3) as sock:
                sock.sendall((text + "\n").encode("utf-8"))
        except Exception:
            logger.exception("wake ack relay failed")
