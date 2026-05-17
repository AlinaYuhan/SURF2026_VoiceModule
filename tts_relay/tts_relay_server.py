"""TTS relay service — run on Jetson (192.168.123.164).

Listens on TCP :9999. Each connection sends UTF-8 text; the server
queues it and calls AudioClient.TtsMaker() serially so the robot
never tries to speak two sentences at once.

Send a line of text:
    echo "你好" | nc 192.168.123.164 9999

Python caller:
    import socket
    with socket.create_connection(("192.168.123.164", 9999), timeout=5) as s:
        s.sendall("你好".encode())
        s.shutdown(socket.SHUT_WR)
        s.recv(16)  # b"OK\n"
"""
import os
import queue
import socket
import sys
import threading
import time

# Must be set before importing the SDK — configures CycloneDDS to use
# unicast on eth0 so it can reach the embedded audio service at .161.
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

_tts_queue: "queue.Queue[str]" = queue.Queue()


def _tts_worker(client: AudioClient) -> None:
    while True:
        text = _tts_queue.get()
        print(f"[TTS] {text!r}", flush=True)
        ret = client.TtsMaker(text, 0)
        if ret != 0:
            print(f"[TTS] 警告：TtsMaker 返回 {ret}", flush=True)


def _handle_conn(conn: socket.socket, addr) -> None:
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
