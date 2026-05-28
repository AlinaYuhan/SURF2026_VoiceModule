"""逐步诊断 TTS 链路，找到卡死位置。"""
import sys, os

# ── STEP 1: 最早的 print，确认 Python 本身正常
print("[STEP 1] Python 启动正常", flush=True)

# ── STEP 2: 设置 CYCLONEDDS_URI（必须在 import SDK 之前）
os.environ["CYCLONEDDS_URI"] = (
    "<CycloneDDS><Domain><General>"
    "<AllowMulticast>false</AllowMulticast>"
    "<NetworkInterfaceAddress>eth1</NetworkInterfaceAddress>"
    "</General>"
    "<Discovery><Peers>"
    "<Peer address=\"192.168.123.161\"/>"
    "<Peer address=\"192.168.123.164\"/>"
    "</Peers></Discovery>"
    "</Domain></CycloneDDS>"
)
print("[STEP 2] CYCLONEDDS_URI 已设置", flush=True)

# ── STEP 3: 加 SDK 路径
SDK_PATH = "/mnt/e/Education/Research/SURF2026_RobotAgent/code/qwen_ros_node_edg_tts/third_party/unitree_sdk2_python"
sys.path.insert(0, SDK_PATH)
print(f"[STEP 3] SDK_PATH 已加入 sys.path: {SDK_PATH}", flush=True)

# ── STEP 4: import ChannelFactoryInitialize（可能在这里卡住）
print("[STEP 4] 正在 import ChannelFactoryInitialize ...", flush=True)
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
print("[STEP 4] import 完成", flush=True)

# ── STEP 5: import AudioClient
print("[STEP 5] 正在 import AudioClient ...", flush=True)
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
print("[STEP 5] import 完成", flush=True)

# ── STEP 6: ChannelFactoryInitialize（可能在这里卡住）
import time
print("[STEP 6] 调用 ChannelFactoryInitialize(0, 'eth1') ...", flush=True)
ChannelFactoryInitialize(0, "eth1")
print("[STEP 6] ChannelFactoryInitialize 返回", flush=True)

# ── STEP 7: 创建 AudioClient 并 Init
print("[STEP 7] 创建 AudioClient ...", flush=True)
client = AudioClient()
client.Init()
client.SetTimeout(10.0)
print("[STEP 7] AudioClient 初始化完成", flush=True)

# ── STEP 8: 轮询 GetVolume 等待服务就绪
print("[STEP 8] 轮询 GetVolume，等待 AudioService 就绪（最多 30 秒）...", flush=True)
for i in range(30):
    code, vol = client.GetVolume()
    print(f"  [{i+1}/30] GetVolume 返回 code={code}, vol={vol}", flush=True)
    if code == 0:
        print(f"[STEP 8] AudioService 就绪，音量={vol}", flush=True)
        break
    time.sleep(1.0)
else:
    print("[STEP 8] 30 秒内 AudioService 未就绪，退出", flush=True)
    sys.exit(1)

# ── STEP 9: 等调试模式播完
print("[STEP 9] 等 3 秒让调试模式播完 ...", flush=True)
time.sleep(3)

# ── STEP 10: 发送 TTS
text = "你好，语音链路测试成功"
print(f"[STEP 10] 调用 TtsMaker: {text!r} ...", flush=True)
ret = client.TtsMaker(text, 0)
print(f"[STEP 10] TtsMaker 返回码: {ret}  (0=成功)", flush=True)
