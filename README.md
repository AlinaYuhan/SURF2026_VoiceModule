# SURF2026 Voice Module

Unitree G1 语音处理模块，负责唤醒词识别、噪声滤波、人声方位识别。

## 模块结构

```
voice_module/
├── audio/          # 麦克风采集 + AudioBus
├── wake_word/      # 唤醒词检测 + 去重分发
├── vad/            # 语音活动检测
├── doa/            # 声源方位识别
├── asr/            # 语音识别
├── config/         # 统一配置
├── ros_nodes/      # ROS2 节点入口
└── scripts/        # 启动脚本
```

## Pipeline

```
G1 Mic → NS/AEC → AudioBus → Wake Word → VAD → ASR → /audio_msg → Qwen Pipeline
                           └─────────────────────────────────────→ /voice_direction
```

## 环境

Ubuntu 24.04 + ROS2 Jazzy + conda `voice` 环境

## 依赖安装

```bash
conda activate voice
pip install -r requirements.txt
```
