# XJTLU 智能助手 - 本地 RAG 知识库系统

基于西交利物浦大学知识库的本地检索增强生成(RAG)系统，支持连接远程 Qwen3VL-4B 大模型。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端浏览器                               │
│                    http://localhost:8000                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI 服务 (本机)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │   前端 UI    │  │  Chat API    │  │  向量检索引擎    │    │
│  └──────────────┘  └──────┬───────┘  └────────┬─────────┘    │
│                            │                    │               │
│  ┌─────────────────────────┴────────────────────┴───────────┐  │
│  │                    Chat Engine                          │  │
│  │  • 身份管理  • 记忆存储  • RAG 检索  • 提示词组装       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │ xjtlu_knowledge │  │   rag_index.db  │  │chat_memory.db │  │
│  │     .db         │  │   (向量索引)    │  │  (会话记忆)   │  │
│  │   (原始知识)     │  └─────────────────┘  └───────────────┘  │
│  └─────────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘
              │                              ▲
              │ HTTP POST /v1/chat           │ HTTP POST /v1/embeddings
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    远程服务器 (Qwen3VL-4B)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              OpenAI 兼容 API 接口                          │   │
│  │  • /v1/chat/completions  (对话生成)                       │   │
│  │  • /v1/embeddings         (向量嵌入)                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────┐  ┌────────────────────────────────────┐   │
│  │  Qwen3VL-4B     │  │         bge-m3 (或其他)            │   │
│  │  (对话模型)     │  │           (Embedding)              │   │
│  └─────────────────┘  └────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 功能特性

- **智能问答**: 基于 XJTLU 知识库的精准回答
- **身份切换**: 招生顾问 / 学术导师 / 校园助手 三种身份
- **会话记忆**: 自动记住用户偏好和对话上下文
- **闲聊融合**: 闲聊不强制引用知识库，自然流畅
- **参考来源**: 回答附带知识库来源链接
- **远程部署**: 支持连接远程服务器的大模型

## 目录结构

```
xjtlu-rag/
├── app.py                 # FastAPI 主应用
├── chat_engine.py         # 对话引擎（身份、记忆、RAG）
├── vector_store.py        # 向量存储与检索
├── memory_store.py        # 会话记忆存储
├── ingest.py              # 知识库向量化脚本
├── knowledge_extract.py   # 知识提取器
├── ollama_client.py       # 模型客户端
├── rag_config.py          # 配置文件加载
├── test_connection.py     # 连接测试工具
├── .env                   # 环境配置
├── .env.example           # 配置模板
├── requirements.txt       # Python 依赖
├── xjtlu_knowledge.db     # 原始知识库 (需自行复制)
├── rag_index.db           # 向量索引数据库
├── chat_memory.db         # 会话记忆数据库
├── start.ps1              # Windows 一键启动
├── start.bat              # Windows 启动（备用）
└── static/               # 前端静态文件
    ├── index.html
    ├── main.js
    └── style.css
```

---

## 快速开始

### 步骤 1: 准备工作

#### 1.1 安装 Python

确保安装了 Python 3.11 或更高版本：

```powershell
python --version
```

如果没有，请从 [python.org](https://www.python.org/downloads/) 下载安装。

#### 1.2 准备知识库文件

将 `xjtlu_knowledge.db` 复制到项目目录：

```powershell
# 如果文件在其他位置
Copy-Item "D:\大学\xjtlu_knowledge(2).db" ".\xjtlu_knowledge.db"

# 或者直接在 Windows 资源管理器中复制粘贴
```

### 步骤 2: 配置连接

编辑 `.env` 文件，配置远程服务器地址：

```powershell
notepad .env
```

关键配置项：

```ini
# 远程服务器地址 (请修改为你的服务器 IP)
OPENAI_BASE_URL=http://你的服务器IP:8000/v1

# API 密钥 (大多数自建服务设置为 EMPTY)
OPENAI_API_KEY=EMPTY

# 对话模型名称 (根据你的服务器配置修改)
CHAT_MODEL=Qwen3VL-4B

# 向量化模型 (如果服务器有的话)
EMBED_MODEL=bge-m3
```

### 步骤 3: 测试连接

运行连接测试脚本，验证与远程服务器的通信：

```powershell
python test_connection.py
```

预期输出：
```
============================================================
  XJTLU RAG - 服务器连接测试
============================================================

[测试 1] 连接 Embedding 服务...
  URL: http://服务器IP:8000/v1/embeddings
  模型: bge-m3
  ✓ 连接成功! 向量维度: 1024

[测试 2] 连接 Chat 服务...
  URL: http://服务器IP:8000/v1/chat/completions
  模型: Qwen3VL-4B
  ✓ 连接成功!
  模型回复: 测试成功

[测试 3] 检查本地数据库...
  ✓ 知识库数据库存在: ./xjtlu_knowledge.db
  表: document_chunks, faq, programmes, school_info, departments, events
  ✓ 向量索引存在: ./rag_index.db
  索引块数: 1250

============================================================
  ✓ 所有测试通过!
============================================================
```

### 步骤 4: 构建向量索引

首次运行需要将知识库内容向量化：

```powershell
python ingest.py --reset
```

这个过程可能需要几分钟，取决于知识库大小。

### 步骤 5: 启动服务

#### 方式 A: 使用一键启动脚本 (推荐)

```powershell
.\start.ps1
```

#### 方式 B: 手动启动

```powershell
# 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 启动服务
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 步骤 6: 开始使用

浏览器打开: **http://127.0.0.1:8000**

或者使用 API：

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/chat `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{
    "session_id": "student-1",
    "message": "我叫张三，对计算机科学专业感兴趣，请作为招生顾问介绍一下"
  }'
```

---

## 服务器端部署指南

如果你的 Qwen3VL-4B 模型部署在另一台 Linux 服务器上，需要在该服务器上做以下配置：

### 服务器要求

- Linux 系统 (Ubuntu 20.04+ / CentOS 8+)
- NVIDIA GPU (建议 8GB+ 显存)
- Python 3.10+
- CUDA 11.8+ / 12.x

### 推荐部署方案

#### 方案 1: vLLM (推荐)

vLLM 提供高性能的 OpenAI 兼容 API：

```bash
# 安装 vLLM
pip install vllm

# 启动 Qwen3VL-4B 服务
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2-VL-7B-Instruct \
  --port 8000 \
  --gpu-memory-utilization 0.9 \
  --max-model-len 8192
```

如果用 Qwen3VL-4B：

```bash
# 使用 Qwen3VL-4B
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2-VL-4B-Instruct \
  --port 8000 \
  --gpu-memory-utilization 0.9
```

#### 方案 2: FastChat + vLLM/Transformers

```bash
# 安装 FastChat
pip install fschat

# 使用 Transformers 直接启动
python -m fastchat.serve.model_worker \
  --model-path Qwen/Qwen2-VL-4B-Instruct \
  --controller http://localhost:8001 \
  --worker http://localhost:8002 \
  --port 8002 \
  --gpu-memory-utilization 0.9

# 启动控制器
python -m fastchat.serve.controller --port 8001

# 启动 API 服务器
python -m fastchat.serve.api_server --controller http://localhost:8001 --port 8000
```

#### 方案 3: Ollama (简单但性能较低)

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型
ollama pull qwen2-vl-4b

# 启动服务
ollama serve
```

### Embedding 模型部署

如果服务器没有 Embedding 接口，可以：

#### 选项 A: 在同一服务器部署 bge-m3

```bash
# 使用 FastChat 部署
pip install fschat

python -m fastchat.serve.model_worker \
  --model-path BAAI/bge-m3 \
  --device cpu \
  --num-gpus 0 \
  --port 8001
```

#### 选项 B: 在本机使用 Ollama (推荐)

在本机 Windows 安装 Ollama：

1. 下载 [Ollama for Windows](https://ollama.com/download)
2. 安装并启动 Ollama
3. 下载 embedding 模型：

```powershell
ollama pull bge-m3
```

4. 修改 `.env`：

```ini
EMBED_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
EMBED_MODEL=bge-m3
```

---

## 服务器端部署 (Linux)

### 使用部署脚本一键部署

```bash
# 在服务器上执行
chmod +x deploy-server.sh
./deploy-server.sh
```

### 手动部署

```bash
# 1. 安装依赖
sudo apt update
sudo apt install -y python3-venv python3-pip curl

# 2. 创建目录
sudo mkdir -p /opt/xjtlu-rag
cd /opt/xjtlu-rag

# 3. 复制项目文件
# (使用 scp 或其他方式将项目文件复制到服务器)

# 4. 设置环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 5. 配置
cp .env.example .env
nano .env  # 修改服务器地址

# 6. 构建索引
python ingest.py --reset

# 7. 启动服务
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 使用 systemd 服务

```bash
# 复制服务文件
sudo cp xjtlu-rag.service /etc/systemd/system/

# 修改服务文件中的用户名
sudo nano /etc/systemd/system/xjtlu-rag.service

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable xjtlu-rag
sudo systemctl start xjtlu-rag

# 查看状态
sudo systemctl status xjtlu-rag

# 查看日志
sudo journalctl -u xjtlu-rag -f
```

### Nginx 反向代理 (可选)

```bash
# 安装 Nginx
sudo apt install -y nginx

# 复制配置
sudo cp nginx.conf.example /etc/nginx/sites-available/xjtlu-rag
sudo ln -s /etc/nginx/sites-available/xjtlu-rag /etc/nginx/sites-enabled/

# 测试并重载
sudo nginx -t
sudo systemctl reload nginx
```

---

## 使用指南

### 身份切换

系统支持三种身份，通过消息中包含关键词自动切换：

| 身份 | 切换关键词 | 回答特点 |
|------|-----------|---------|
| 校园助手 | (默认) | 自然、友好、简洁 |
| 招生顾问 | "招生顾问"、"招生"+"身份" | 清晰、谨慎、面向学生家长 |
| 学术导师 | "学术导师"、"导师"+"身份" | 专业、课程路径、学术发展 |

示例：
- "请作为招生顾问介绍一下 Applied Linguistics"
- "作为学术导师，给我一些选课建议"

### 用户画像

系统会自动记住以下信息：

- **姓名**: "我叫张三"
- **专业兴趣**: "我对计算机科学感兴趣"
- **语言偏好**: "以后用中文回答"

### 闲聊识别

以下情况不会强制走 RAG 检索：

- 短问候语（"你好"、"Hi"、"Hello"、"谢谢"）
- 简单感谢
- 一般性闲聊

---

## 配置参数说明

### 检索参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TOP_K` | 6 | 返回的相似文档数量 |
| `SIMILARITY_THRESHOLD` | 0.35 | 相似度阈值 (0-1) |

调整建议：
- 需要更精确回答 → 提高阈值到 0.45
- 需要更多参考 → 降低阈值到 0.25 或提高 TOP_K

### 模型参数

| 参数 | 说明 |
|------|------|
| `CHAT_MODEL` | 对话模型名称 |
| `EMBED_MODEL` | 向量模型名称 |
| `TEMPERATURE` | 生成温度 (在 ollama_client.py 中调整) |

---

## API 接口

### POST /chat

对话接口

```json
// 请求
{
  "session_id": "student-1",
  "message": "西浦有哪些专业？"
}

// 响应
{
  "answer": "西交利物浦大学提供以下专业...",
  "identity": "校园助手",
  "profile": {
    "name": "张三",
    "assistant_identity": "校园助手"
  },
  "sources": [
    {
      "title": "专业列表",
      "url": "https://...",
      "category": "programmes",
      "score": 0.8542
    }
  ]
}
```

### GET /health

健康检查

```json
{
  "status": "ok",
  "rag_db": "./rag_index.db",
  "memory_db": "./chat_memory.db",
  "embed_model": "bge-m3",
  "chat_model": "Qwen3VL-4B"
}
```

### GET /profile/{session_id}

获取会话记忆

---

## 常见问题

### Q: 提示 "连接失败" 怎么办？

1. 检查远程服务器是否启动
2. 确认 `.env` 中的 `OPENAI_BASE_URL` 地址正确
3. 检查服务器防火墙是否放行了端口 (默认 8000)
4. 运行 `python test_connection.py` 查看详细错误

### Q: 远程服务器没有 embedding 接口？

两个解决方案：
1. 在服务器上部署 bge-m3 embedding 服务
2. 在本机安装 Ollama，运行 `ollama pull bge-m3`，然后设置 `EMBED_PROVIDER=ollama`

### Q: 回答质量不好？

1. 检查知识库是否正确导入 (`python ingest.py --reset`)
2. 调整 `SIMILARITY_THRESHOLD` 参数
3. 调整 `TOP_K` 参数返回更多参考
4. 检查远程服务器的模型是否正确加载

### Q: 如何添加新知识？

1. 更新 `xjtlu_knowledge.db` 中的数据
2. 重新运行 `python ingest.py --reset`

---

## 技术栈

- **后端**: FastAPI + Uvicorn
- **向量存储**: SQLite + NumPy
- **会话记忆**: SQLite
- **前端**: 原生 HTML/CSS/JavaScript
- **模型**: OpenAI 兼容 API

---

## License

MIT License
