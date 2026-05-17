# SURF2026 Voice Module

Unitree G1 机器人语音处理模块，负责中文/英文唤醒词识别、语音活动检测（VAD）、语音转文字（ASR）、声纹识别和 ROS2 集成。

[English below](#english)

---

## 目录

- [模块结构](#模块结构)
- [Pipeline](#pipeline)
- [环境](#环境)
- [依赖安装](#依赖安装)
- [快速开始](#快速开始)
- [模块详解](#模块详解)
- [ROS2 接口](#ros2-接口)
- [配置参考](#配置参考)
- [测试](#测试)
- [XJTLU RAG 问答系统](#xjtlu-rag-问答系统)
- [目录结构](#目录结构)

---

## 模块结构

```
SURF2026_VoiceModule/
├── config/
│   └── voice_config.py              # 统一配置（所有环境变量）
│
├── audio/
│   ├── audio_bus.py                 # 线程安全 PCM 广播总线，1 秒滚动缓冲
│   ├── mic_capture.py               # sounddevice USB 麦克风采集
│   ├── robot_mic_capture.py         # UDP 多播接收机器人麦克风（G1）
│   └── audio_preprocessor.py        # 噪声抑制（noisereduce）
│
├── wake_word/
│   ├── wake_word_detector.py        # openWakeWord 英文唤醒词检测
│   ├── chinese_wake_word_detector.py # sherpa-onnx 中文唤醒词检测
│   └── wakeup_dispatcher.py         # 唤醒词去重分发（500ms 窗口）
│
├── vad/
│   └── vad_engine.py                # webrtcvad 帧级 VAD，30 帧确认窗口
│
├── asr/
│   └── asr_engine.py                # FunASR paraformer-zh 语音转文字
│
├── voice_id/
│   ├── voiceprint_recognizer.py     # pyannote.audio 说话人声纹提取
│   └── speaker_database.py          # 滚动说话人注册，余弦相似度匹配
│
├── ros_nodes/
│   └── voice_pipeline_node.py       # ROS2 主节点，串联全部子系统
│
├── tts_relay/
│   ├── tts_relay_server.py          # Jetson TCP 中继 → 机器人 TTS
│   └── run_tts_relay.sh             # 启动脚本
│
├── xjtlu-rag-system/               # 西浦智能问答系统（RAG）
│   ├── app.py                       # FastAPI 主应用
│   ├── chat_engine.py               # 对话引擎（身份、记忆、RAG）
│   ├── vector_store.py              # SQLite 向量检索
│   ├── memory_store.py              # SQLite 会话记忆
│   ├── ingest.py                    # 知识库向量化脚本
│   ├── knowledge_extract.py          # 知识提取器
│   ├── ollama_client.py             # 模型客户端（DeepSeek + Ollama）
│   ├── ros_bridge.py                # ROS2 桥接（订阅 /audio_msg，发布 /xjtlu_reply）
│   ├── requirements.txt             # FastAPI 依赖
│   └── .env                         # API 配置（DeepSeek + Ollama）
│
├── models/kws/
│   ├── tokens.txt                  # sherpa-onnx 音素词表（229 tokens）
│   └── keywords.txt                 # 中文唤醒词音素序列配置
│
├── tests/                          # 68 个单元测试，覆盖全部模块
│   ├── conftest.py                 # pytest fixtures（正弦波/静音 PCM 生成器）
│   ├── test_audio_bus.py
│   ├── test_mic_capture.py
│   ├── test_audio_preprocessor.py
│   ├── test_wakeup_dispatcher.py
│   ├── test_wake_word_detector.py
│   ├── test_chinese_wake_word_detector.py
│   ├── test_vad_engine.py
│   ├── test_asr_engine.py
│   ├── test_voice_pipeline_node.py
│   ├── test_voiceprint_recognizer.py
│   └── test_speaker_database.py
│
├── docs/
│   ├── architecture.md              # 架构文档
│   └── plans/                      # 设计方案记录
│       ├── 2026-04-30-voice-module.md
│       ├── 2026-05-12-chinese-wake-word.md
│       └── chunk2-design.md
│
├── standalone_test.py              # 本地冒烟测试（无需 ROS2）
├── run_node.sh                     # WSL2 启动脚本
├── run_tests.sh                    # pytest 运行脚本
├── pytest.ini                      # pytest 配置
├── .gitattributes                  # 行尾符 + 二进制文件配置
├── .gitignore
└── requirements.txt                # 语音模块 Python 依赖
```

---

## Pipeline

### 语音处理主流程

```
┌─────────────────────────────────────────────────────────────────────┐
│  音频采集                                                         │
│  ┌──────────────────┐    ┌──────────────────────┐                  │
│  │  MicCapture      │    │  RobotMicCapture     │                  │
│  │  (USB 麦克风)    │    │  (UDP 多播 239.168.  │                  │
│  │  WSL2 PulseAudio │    │  123.161:5555)       │                  │
│  └────────┬─────────┘    └──────────┬───────────┘                  │
│           │                          │                               │
│           └────────────┬─────────────┘                              │
│                        ▼                                             │
│              ┌─────────────────┐                                     │
│              │   AudioBus      │   ← 线程安全 PCM 广播总线，         │
│              │  (1s 滚动缓冲)  │     持有者注册回调                 │
│              └────────┬────────┘                                     │
│         ┌────────────┼────────────┐                                  │
│         ▼            ▼            ▼                                  │
│  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────┐       │
│  │中文唤醒词检测│ │ 英文唤醒词│ │   VAD   │ │   ASR (FunASR)  │       │
│  │sherpa-onnx│ │openWakeWord│ │webrtcvad│ │  paraformer-zh  │       │
│  └─────┬──────┘ └────┬─────┘ └────┬────┘ └────────┬────────┘       │
│        │              │             │               │                │
│        └──────────┬──┴─────────────┘               │                │
│                   ▼                                  ▼                │
│         ┌──────────────────┐               ┌───────────────┐          │
│         │WakeupDispatcher │               │VAD 静音触发 / │          │
│         │(500ms 去重)     │               │ASR 超时触发   │          │
│         └────────┬────────┘               └───────┬───────┘          │
│                  ▼                                  ▼                │
│         ┌──────────────────────────────────────────────┐             │
│         │         voice_pipeline_node (ROS2)            │             │
│         │  /wake_word_event → 开始录音 → /audio_msg   │             │
│         │                         ↓                     │             │
│         │              voiceprint_recognizer           │             │
│         │              (pyannote 声纹) → /speaker_id  │             │
│         └──────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ xjtlu-rag-system │
                    │  (FastAPI + RAG) │
                    │ /audio_msg 订阅  │
                    │ /xjtlu_reply 发布│
                    └──────────────────┘
```

### 唤醒后时序

```
唤醒词检测到 ("你好小G")
    │
    ▼
1. 发送 /wake_word_event（唤醒词名称）
    │
    ├──► ASREngine.start_recording()
    │    从 AudioBus 回溯 300ms（pre-wake 音频）
    │
    ├──► VoiceprintRecognizer.start_capture()
    │    收集 3.5s 音频提取声纹
    │
    └──► 启动 1s VAD 静默抑制窗口
              │
              ▼
VAD 检测到静音 / ASR 超时（8s）
    │
    ▼
ASREngine.stop_and_transcribe()
    │
    ▼
/audio_msg 发布 {"text": "...", "speaker": "user-1"}
    │
    ▼
声纹提取完成 → /speaker_id 发布说话人标签
    │
    ▼
ros_bridge 接收 /audio_msg → XJTLU RAG → /xjtlu_reply
```

---

## 环境

### 目标硬件

| 组件 | 设备 | 系统 |
|------|------|------|
| 语音管道 | Jetson Orin NX（WSL2 Ubuntu 24.04） | ROS2 Jazzy |
| 麦克风 | Unitree G1 机器人内置麦克风阵列 | UDP 多播 |
| 本地测试 | Windows PC（WSL2） | Python 3.11+ |

### 环境依赖

- **Python**：3.10+
- **ROS2**：Jazzy
- **音频后端**：WSL2 下使用 PulseAudio（`/mnt/wslg/PulseServer`），或 Linux 原生 ALSA/PulseAudio
- **Conda 环境**：`conda activate voice`

### 模型下载

首次运行前需下载模型文件（首次 import 时自动下载，也可手动预热）：

```bash
# ASR 模型（FunASR paraformer-zh，约 200MB）
python -c "from funasr import AutoModel; AutoModel(model='paraformer-zh')"

# 声纹模型（pyannote wespeaker-voxceleb，约 80MB）
python -c "from pyannote.audio import Model; Model.from_pretrained('pyannote/wespeaker-voxceleb-resnet34-LM')"

# 中文唤醒词模型（sherpa-onnx，已在 models/kws/）
# 需提前准备好 .onnx 文件和 keywords.txt
```

> **注意**：在无网络的实验室环境中，提前在有网环境下运行上述命令缓存模型，然后设置 `HF_HUB_OFFLINE=1`（FunASR 用 `MODELSCOPE_SDK` 同理）。

---

## 依赖安装

### 步骤 1：创建 Conda 环境

```bash
conda create -n voice python=3.11 -y
conda activate voice
```

### 步骤 2：安装 Python 依赖

```bash
pip install -r requirements.txt
```

**requirements.txt 内容：**

```
openwakeword
webrtcvad-wheels
sounddevice
soundfile
pyroomacoustics
numpy
scipy
```

> 如果 `webrtcvad-wheels` 安装失败（Windows），改用 `pip install webrtcvad` 或手动编译。

### 步骤 3：安装 ROS2 Jazzy（WSL2）

参考 [ROS2 官方安装指南](https://docs.ros.org/en/jazzy/Installation.html)：

```bash
# 添加 ROS2 apt 源
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository universe
sudo apt install -y curl
curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | sudo apt-key add -
sudo sh -c 'echo "deb [arch=$(dpkg --print-architecture)] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) main" > /etc/apt/sources.list.d/ros2.list'

sudo apt update
sudo apt install -y ros-jazzy-ros-base # 最小安装
sudo apt install -y python3-colcon-common-extensions
```

### 步骤 4：配置环境变量

```bash
# 在 ~/.bashrc 中添加（参考 run_node.sh）
export VOICE_ASR_MODEL=$HOME/.cache/modelscope/hub/models/iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
export HF_HUB_OFFLINE=1
export ROS_DOMAIN_ID=42
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><AllowMulticast>false</AllowMulticast></General><Discovery><Peers><Peer address="192.168.123.164"/></Peers></Discovery></Domain></CycloneDDS>'
export VOICE_AUDIO_SOURCE=robot
```

### 步骤 5：配置中文唤醒词

确保 `models/kws/` 目录下有：

```
models/kws/
├── tokens.txt       # 音素词表（229 tokens）
└── keywords.txt     # 唤醒词音素序列，例如：
                     # 你好@小G@nǐ_hǎo@xiǎo_G
```

> **中文唤醒词训练**：需要用 [sherpa-onnx 训练工具](https://k2-fsa.github.io/sherpa/onnx/keyword spotting/index.html) 训练自定义唤醒词模型，将生成的 `.onnx` 文件放入 `models/kws/`。

---

## 快速开始

### 本地冒烟测试（无需 ROS2）

在 Windows WSL2 中测试完整语音管道：

```bash
conda activate voice
PULSE_SERVER=unix:/mnt/wslg/PulseServer python standalone_test.py
```

预期输出：

```
初始化模型中，请稍候...
监听中...  唤醒词: 「你好小G」 / 「hey jarvis」
说唤醒词后说指令，停顿后自动转写。按 Ctrl+C 退出。

[唤醒 #1] 检测到: '你好小G'  →  开始录音（最长 8s）
[VAD]  说话中...
[ASR #1]  西浦有哪些专业
[声纹 #1] 用户1（已知说话人：）
```

### 启动 ROS2 主节点

```bash
bash run_node.sh
```

此脚本会：

- Source `/opt/ros/jazzy/setup.bash`
- 设置 `PYTHONPATH` 包含项目根目录
- 配置 CycloneDDS 单播到机器人 IP（`192.168.123.164`）
- 设置 `VOICE_AUDIO_SOURCE=robot`（使用 UDP 多播麦克风）

### 运行测试

```bash
# 方式 A：使用脚本（自动过滤 ROS2 PYTHONPATH）
bash run_tests.sh

# 方式 B：直接 pytest
pytest tests/ -v

# 方式 C：运行特定模块测试
pytest tests/test_vad_engine.py -v
pytest tests/test_asr_engine.py -v
```

### 启动 XJTLU RAG 系统

```bash
cd xjtlu-rag-system
cp .env.example .env
# 编辑 .env 填入 DeepSeek API Key
python ingest.py --reset    # 首次运行需构建向量索引
./start.ps1                 # Windows，或：
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

---

## 模块详解

### audio/ — 音频采集与总线

| 文件 | 职责 |
|------|------|
| `audio_bus.py` | 线程安全 PCM 广播总线。持有 `deque` 滚动缓冲，生产者 `push()`，消费者注册回调。消费者异常被捕获隔离，不影响总线。 |
| `mic_capture.py` | `sounddevice.InputStream` 采集 USB 麦克风（float32），转换为 int16 PCM，帧对齐后推入 AudioBus。 |
| `robot_mic_capture.py` | UDP 多播接收 G1 机器人麦克风数据，加入组播 `239.168.123.161:5555`。与 `MicCapture` 接口完全一致。 |
| `audio_preprocessor.py` | ABC 接口 + `NoiseReduceProcessor` 实现，使用 `noisereduce` 稳态降噪（适合空调/风扇背景）。`stationary=True` 模式。 |

**音频规格**：16kHz、单声道、16-bit PCM、20ms 帧（320 字节/帧）。

### wake_word/ — 唤醒词检测

| 文件 | 引擎 | 语言 | 帧大小 |
|------|------|------|--------|
| `wake_word_detector.py` | openWakeWord (ONNX) | 英文 | 80ms / 1280 采样 |
| `chinese_wake_word_detector.py` | sherpa-onnx KeywordSpotter | 中文 | 200ms / 3200 采样 |
| `wakeup_dispatcher.py` | — | 去重分发 | — |

**去重逻辑**：`WakeupDispatcher` 维护每个唤醒词的最近触发时间，同一唤醒词在 0.5s 内重复触发会被抑制。不同唤醒词独立计时。

### vad/ — 语音活动检测

`vad_engine.py` 使用 **webrtcvad**， aggressiveness 默认为 2。

关键特性：**30 帧确认窗口**——需要连续 30 个静音帧（约 600ms）才认为语音结束。这防止了语句间短暂停顿导致的误触发。

### asr/ — 语音识别

`asr_engine.py` 使用 **FunASR paraformer-zh**。

状态机：

```
IDLE ──start_recording()──► RECORDING ──stop_and_transcribe()──► IDLE
                                 │
                         push_audio() 持续追加 PCM
```

- **回溯音频**：`start_recording()` 从 AudioBus 尾部取 15 帧（300ms）作为 pre-wake 音频，确保唤醒词后第一个字不被截断
- **推理在锁外**：`stop_and_transcribe()` 先复制 buffer、释放锁，再调用模型，避免长时持锁阻塞音频流
- **超时保护**：8s 无声自动触发转写

### voice_id/ — 声纹识别

| 文件 | 职责 |
|------|------|
| `voiceprint_recognizer.py` | pyannote/wespeaker-voxceleb-resnet34-LM，3.5s 音频窗口提取 256 维说话人向量，后台线程推理 |
| `speaker_database.py` | 滚动说话人注册，余弦相似度 ≥ 0.50 判定为已知用户，否则注册为"用户 N" |

### ros_nodes/ — ROS2 主节点

`voice_pipeline_node.py` 是整个管道中枢：

- 统一管理所有组件生命周期
- 响应 `WakeWord` 事件触发 ASR 录音
- 管理 VAD 静默抑制窗口（唤醒后 1s）
- 发布 `/audio_msg`（JSON：`{"text": "...", "speaker": "user-1"}`）
- 发布 `/speaker_id`（JSON：`{"speaker": "用户1", "similarity": 0.72}`）
- 模型在 `rclpy.init()` **之前**加载，避免 CycloneDDS 与 ModelScope/HuggingFace 网络冲突

### tts_relay/ — TTS 中继

`ts_relay_server.py` 是一个 TCP 服务器（端口 9999），接收文本后调用 Unitree SDK2 的 `AudioClient.TtsMaker()` 串行合成语音。配置了 CycloneDDS 单播指向机器人音频服务 IP。

---

## ROS2 接口

### 发布话题（voice_pipeline_node）

| 话题 | 类型 | 说明 |
|------|------|------|
| `/audio_msg` | `std_msgs/String` | JSON：`{"text": "...", "speaker": "user-1"}` |
| `/wake_word_event` | `std_msgs/String` | 检测到的唤醒词名称 |
| `/vad_state` | `std_msgs/Bool` | 当前是否为语音活动状态 |
| `/speaker_id` | `std_msgs/String` | JSON：`{"speaker": "用户1", "similarity": 0.72}` |
| `/voice_direction` | `std_msgs/Float32` | 声源方位角 0–360°（规划中） |

### 订阅话题（xjtlu-rag-system/ros_bridge.py）

| 话题 | 说明 |
|------|------|
| `/audio_msg` | 接收 ASR 转写的文本，调用 RAG 问答 |
| `/wake_word_event` | 触发回复"我在" |
| `/xjtlu_reply` | 发布 RAG 回答（text 或 JSON 格式） |

---

## 配置参考

所有配置通过环境变量注入，由 `config/voice_config.py` 统一管理。

### 音频配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `VOICE_SAMPLE_RATE` | `16000` | 采样率 |
| `VOICE_CHANNELS` | `1` | 声道数 |
| `VOICE_FRAME_MS` | `20` | VAD 帧长（毫秒） |
| `VOICE_BUS_BUFFER_SEC` | `1.0` | AudioBus 滚动缓冲时长 |
| `VOICE_MIC_DEVICE` | `None` | sounddevice 设备索引 |

### 音频源

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `VOICE_AUDIO_SOURCE` | `local` | `local`=USB 麦克风，`robot`=UDP 多播 |
| `VOICE_ROBOT_MIC_GROUP` | `239.168.123.161` | 多播组地址 |
| `VOICE_ROBOT_MIC_PORT` | `5555` | 多播端口 |
| `VOICE_ROBOT_MIC_IF` | `192.168.123.225` | WSL2 多播出口 IP |

### 唤醒词

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `VOICE_WAKE_WORDS` | `hey jarvis,alexa` | 英文唤醒词（逗号分隔） |
| `VOICE_WAKE_THRESHOLD` | `0.5` | 英文唤醒词检测阈值 |
| `VOICE_WAKE_WORD_LANG` | `zh` | `zh`=中文，`en`=英文 |
| `VOICE_KWS_MODEL_DIR` | `./models/kws` | sherpa-onnx 模型目录 |
| `VOICE_WAKEUP_DEDUP_SEC` | `0.5` | 去重窗口（秒） |

### VAD

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `VOICE_VAD_SILENCE_FRAMES` | `30` | 静音确认帧数（约 600ms） |
| `VOICE_VAD_HOLDOFF_SEC` | `1.0` | 唤醒后静默抑制时长 |

### ASR

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `VOICE_ASR_MODEL` | `paraformer-zh` | FunASR 模型名 |
| `VOICE_ASR_WINDOW_SEC` | `8.0` | 最大录音时长 |

### 声纹识别

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `VOICE_VOICEPRINT_SEC` | `3.5` | 声纹采集时长（秒） |
| `VOICE_VOICEPRINT_MODEL` | `pyannote/wespeaker-voxceleb-resnet34-LM` | 声纹模型 |
| `VOICE_SPEAKER_SIM_THRESHOLD` | `0.50` | 余弦相似度阈值 |
| `VOICE_SPEAKER_MAX_HISTORY` | `20` | 说话人历史记录上限 |

### ROS2

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ROS_DOMAIN_ID` | `42` | ROS2 域 ID |
| `VOICE_ROS_AUDIO_TOPIC` | `/audio_msg` | ASR 结果话题 |
| `VOICE_ROS_WAKE_TOPIC` | `/wake_word_event` | 唤醒事件话题 |
| `VOICE_ROS_VAD_TOPIC` | `/vad_state` | VAD 状态话题 |
| `VOICE_ROS_SPEAKER_TOPIC` | `/speaker_id` | 说话人话题 |

---

## 测试

### 测试覆盖

| 模块 | 测试文件 | 测试数 |
|------|----------|--------|
| AudioBus | `test_audio_bus.py` | 6 |
| MicCapture | `test_mic_capture.py` | 4 |
| AudioPreprocessor | `test_audio_preprocessor.py` | 3 |
| WakeupDispatcher | `test_wakeup_dispatcher.py` | 6 |
| WakeWordDetector | `test_wake_word_detector.py` | 5 |
| ChineseWakeWordDetector | `test_chinese_wake_word_detector.py` | 5 |
| VADEngine | `test_vad_engine.py` | 9 |
| ASREngine | `test_asr_engine.py` | 7 |
| VoicePipelineNode | `test_voice_pipeline_node.py` | 7 |
| VoiceprintRecognizer | `test_voiceprint_recognizer.py` | 7 |
| SpeakerDatabase | `test_speaker_database.py` | 9 |
| **总计** | **11 个文件** | **68** |

### 测试原则

- 所有重型模型（openWakeWord、FunASR、sherpa-onnx、pyannote）使用 `unittest.mock.patch` mock，不实际加载
- 音频数据使用 `conftest.py` 中的 `make_sine_wave()` / `make_silence()` fixtures 生成
- 测试隔离：每个测试独立，不共享状态

---

## XJTLU RAG 问答系统

位于 `xjtlu-rag-system/` 子目录，是西浦智能问答的核心——基于本地知识库的 RAG 系统。

### 技术架构

| 功能 | 服务提供者 | 说明 |
|------|-----------|------|
| 对话生成 | DeepSeek API | `deepseek-v4-pro` 模型 |
| 向量嵌入 | Ollama（本地） | `nomic-embed-text` 模型 |

### RAG Pipeline

```
用户消息 → 身份推断 → 画像提取 → 闲聊检测
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
             RAG 向量检索      FAQ 关键词直查     专业库直查
                    │                 │                 │
                    └─────────────────┼─────────────────┘
                                      ▼
                               Prompt 组装
                                      │
                                      ▼
                               DeepSeek API
                                      │
                                      ▼
                               答案截断（100字）
                                      │
                                      ▼
                               返回 JSON
```

### 快速启动

```bash
cd xjtlu-rag-system

# 安装依赖
pip install -r requirements.txt  # fastapi, uvicorn, httpx, numpy, pydantic

# 配置（复制并编辑 .env）
cp .env.example .env
# 填入 DEEPSEEK_API_KEY 等配置

# 构建向量索引（首次）
python ingest.py --reset

# 启动服务
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 对话接口，返回答案、身份、画像、来源 |
| `/health` | GET | 健康检查 |
| `/profile/{session_id}` | GET | 获取会话记忆 |
| `/docs` | GET | Swagger API 文档 |

---

## 目录结构（完整）

```
SURF2026_VoiceModule/
├── audio/
│   ├── audio_bus.py              ✅ 线程安全 PCM 广播总线
│   ├── mic_capture.py            ✅ USB 麦克风采集
│   ├── robot_mic_capture.py      ✅ UDP 多播机器人麦克风
│   └── audio_preprocessor.py     ✅ 噪声抑制
├── wake_word/
│   ├── wake_word_detector.py     ✅ openWakeWord 英文唤醒词
│   ├── chinese_wake_word_detector.py  ✅ sherpa-onnx 中文唤醒词
│   └── wakeup_dispatcher.py      ✅ 去重分发
├── vad/
│   └── vad_engine.py             ✅ webrtcvad + 确认窗口
├── asr/
│   └── asr_engine.py             ✅ FunASR 语音转文字
├── voice_id/
│   ├── voiceprint_recognizer.py  ✅ pyannote 声纹提取
│   └── speaker_database.py       ✅ 说话人注册
├── ros_nodes/
│   └── voice_pipeline_node.py    ✅ ROS2 主节点
├── tts_relay/
│   ├── tts_relay_server.py       ✅ TCP TTS 中继
│   └── run_tts_relay.sh          ✅ 启动脚本
├── xjtlu-rag-system/            ✅ RAG 问答系统
├── models/kws/                  ✅ sherpa-onnx 中文唤醒词配置
├── config/
│   └── voice_config.py           ✅ 统一配置管理
├── tests/                       ✅ 68 个单元测试
├── docs/                        ✅ 架构文档 + 设计方案
├── standalone_test.py           ✅ 本地冒烟测试
├── run_node.sh                  ✅ WSL2 启动脚本
├── run_tests.sh                 ✅ pytest 运行脚本
├── pytest.ini                   ✅ pytest 配置
├── .gitattributes               ✅ 行尾符配置
├── requirements.txt             ✅ 语音模块依赖
└── README.md                    ✅ 本文档
```

---

## English

### Overview

SURF2026 Voice Module for the Unitree G1 robot. Handles Chinese/English wake word detection, voice activity detection (VAD), automatic speech recognition (ASR), speaker identification, and ROS2 integration.

### Quick Start

```bash
# Local smoke test (no ROS2 required)
conda activate voice
PULSE_SERVER=unix:/mnt/wslg/PulseServer python standalone_test.py

# ROS2 main node (WSL2)
bash run_node.sh

# Tests
pytest tests/ -v
```

### Architecture

```
Mic/UDP Multicast → AudioBus → WakeWord(VAD→ sherpa-onnx/openWakeWord)
                                   → VAD (webrtcvad)
                                   → ASR (FunASR paraformer-zh) → /audio_msg
                                   → Voiceprint (pyannote) → /speaker_id
                                                           ↓
                                              xjtlu-rag-system (FastAPI + DeepSeek)
                                                           ↓
                                              /xjtlu_reply
```

### License

MIT License
