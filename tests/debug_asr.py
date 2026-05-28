"""诊断脚本：录3秒机器人麦克风音频，直接跑FunASR，打印原始结果。"""
import os
import socket
import struct
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HUB_OFFLINE"] = "1"

GROUP_IP = "239.168.123.161"
PORT = 5555
LOCAL_IF = "192.168.123.225"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("", PORT))
mreq = struct.pack("4s4s", socket.inet_aton(GROUP_IP), socket.inet_aton(LOCAL_IF))
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
sock.settimeout(1.0)

print("录音3秒，请对着机器人说一句完整的中文话...")
chunks = []
t0 = time.time()
while time.time() - t0 < 3:
    try:
        data, _ = sock.recvfrom(8192)
        chunks.append(data)
    except socket.timeout:
        pass
sock.close()

audio_bytes = b"".join(chunks)
audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
rms = float(np.sqrt(np.mean(audio ** 2)) * 32768)
print(f"录到 {len(audio)} 样本，RMS={rms:.1f}")

from funasr import AutoModel  # noqa: E402

model = AutoModel(model="paraformer-zh", disable_update=True)
result = model.generate(input=audio, batch_size_s=300)
print(f"FunASR 原始结果: {result}")
