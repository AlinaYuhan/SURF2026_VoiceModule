"""手动测试机器人 TTS：从笔记本 WSL2 调用机器人内置 TtsMaker 播报语音。"""
import sys
import os

# 禁用 CycloneDDS 组播，改用单播直连机器人，避免 WSL2 组播不稳定导致卡死
os.environ["CYCLONEDDS_URI"] = (
    "<CycloneDDS><Domain><General><AllowMulticast>false</AllowMulticast></General>"
    "<Discovery><Peers><Peer address=\"192.168.123.164\"/></Peers></Discovery>"
    "</Domain></CycloneDDS>"
)

SDK_PATH = "/mnt/e/Education/Research/SURF2026_RobotAgent/code/qwen_ros_node_edg_tts/third_party/unitree_sdk2_python"
sys.path.insert(0, SDK_PATH)

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

NETWORK_INTERFACE = "eth1"  # WSL2 连接机器人的网卡

import time

print("正在初始化 DDS 通道...", flush=True)
ChannelFactoryInitialize(0, NETWORK_INTERFACE)
print("DDS 通道初始化完成", flush=True)
client = AudioClient()
client.Init()
client.SetTimeout(10.0)

print("轮询等待 AudioService 就绪...")
for i in range(20):
    code, vol = client.GetVolume()
    if code == 0:
        print(f"AudioService 就绪，当前音量: {vol}")
        break
    print(f"  [{i+1}/20] GetVolume 返回 {code}，继续等待...")
    time.sleep(1.0)
else:
    print("AudioService 20秒内未就绪，退出")
    sys.exit(1)

print("等待'调试模式'播报完毕（2秒）...")
time.sleep(2)

text = "你好，语音链路测试成功"
print(f"发送 TTS: {text}")
ret = client.TtsMaker(text, 0)
print(f"TtsMaker 返回码: {ret}  (0=成功)")
