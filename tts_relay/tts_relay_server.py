"""TTS relay service — run on Jetson (192.168.123.164).

Listens on TCP :9999. Each connection sends UTF-8 text; the server
maps it to a pre-generated WAV file and plays via AudioClient.PlayStream().

Supported phrases:
  "我在"     → assets/wake_ack_zh.wav
  "I'm here" → assets/wake_ack_en.wav

Send a line of text:
    echo "我在" | nc 192.168.123.164 9999
"""
import os
import pathlib
import queue
import socket
import sys
import threading
import time
import wave

os.environ["CYCLONEDDS_URI"] = (
    "<CycloneDDS><Domain><General>"
    "<AllowMulticast>false</AllowMulticast>"
    "<NetworkInterfaceAddress>eth0</NetworkInterfaceAddress>"
    "</General>"
    "<Discovery><Peers>"
    "<Peer address=\"192.168.123.161\"/>"
    "</Peers></Discovery>"
    "</Domain></CycloneDDS>"
)

SDK_PATH = "/home/unitree/unitree_sdk2_python"
sys.path.insert(0, SDK_PATH)

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

HOST = "0.0.0.0"
PORT = 9999
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"
CHUNK_BYTES = 96000  # 3 s @ 16kHz mono 16-bit

AUDIO_MAP = {
    "我在": "wake_ack_zh.wav",
    "I'm here": "wake_ack_en.wav",
}

_tts_queue: "queue.Queue[str]" = queue.Queue()


def _read_pcm(path: pathlib.Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        print(
            f"[relay] WAV: {wf.getnchannels()}ch {wf.getframerate()}Hz "
            f"{wf.getsampwidth()*8}bit",
            flush=True,
        )
        return wf.readframes(wf.getnframes())


def _play(client: AudioClient, pcm: bytes) -> None:
    stream_id = str(int(time.time() * 1000))
    offset = 0
    idx = 0
    while offset < len(pcm):
        chunk = pcm[offset : offset + CHUNK_BYTES]
        ret, _ = client.PlayStream("tts", stream_id, chunk)
        if ret != 0:
            print(f"[relay] PlayStream chunk {idx} error: {ret}", flush=True)
            break
        print(f"[relay] chunk {idx} sent ({len(chunk)} bytes)", flush=True)
        offset += CHUNK_BYTES
        idx += 1
        if offset < len(pcm):
            time.sleep(1.0)


def _tts_worker(client: AudioClient) -> None:
    while True:
        text = _tts_queue.get()
        wav_name = AUDIO_MAP.get(text)
        if wav_name is None:
            print(f"[relay] 未知文本: {text!r}", flush=True)
            continue
        wav_path = ASSETS_DIR / wav_name
        if not wav_path.exists():
            print(f"[relay] 文件不存在: {wav_path}", flush=True)
            continue
        print(f"[relay] → {wav_name}", flush=True)
        try:
            pcm = _read_pcm(wav_path)
            _play(client, pcm)
        except Exception as e:
            print(f"[relay] 播放失败: {e}", flush=True)


def _handle_conn(conn: socket.socket, _addr) -> None:
    with conn:
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        text = b"".join(chunks).decode("utf-8").strip()
        if text:
            _tts_queue.put(text)
            conn.sendall(b"OK\n")


def _wait_for_audio_service(client: AudioClient, timeout_sec: int = 20) -> bool:
    for i in range(timeout_sec):
        code, vol = client.GetVolume()
        if code == 0:
            print(f"[relay] AudioService 就绪，音量={vol}", flush=True)
            return True
        print(f"[relay] 等待 AudioService [{i+1}/{timeout_sec}]...", flush=True)
        time.sleep(1.0)
    return False


def main() -> None:
    print("[relay] 初始化 DDS (domain=0, if=eth0)...", flush=True)
    ChannelFactoryInitialize(0, "eth0")

    client = AudioClient()
    client.Init()
    client.SetTimeout(10.0)

    if not _wait_for_audio_service(client):
        print("[relay] AudioService 未就绪，退出", flush=True)
        sys.exit(1)

    threading.Thread(target=_tts_worker, args=(client,), daemon=True).start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(5)
        print(f"[relay] 监听 {HOST}:{PORT}，等待文本输入...", flush=True)
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=_handle_conn, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
