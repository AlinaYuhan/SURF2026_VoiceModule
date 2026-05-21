# SURF Demo Clean Workspace

Integrated workspace for the SURF voice module, XJTLU RAG, TTS playback, and
Unitree G1 action execution.

## Pipeline

```text
SURF voice runtime
  -> /audio_msg
  -> demo_surf_context_node.py
  -> demo_server.py
  -> XJTLU RAG / DeepSeek / Ollama embedding
  -> Edge TTS wav
  -> action classifier
  -> Unitree action runner
```

## Current Runtime Behavior

Voice timing:

```text
wake word -> wake ack "我在" -> record command -> 1.5s silence -> ASR -> Demo
```

The ASR hard deadline is only a no-speech fallback. Once speech is detected by
VAD or speaker embedding, the deadline is cancelled and VAD controls the end of
recording.

Light states:

```text
standby                 -> blue
wake / waiting command  -> red
ASR accepted / thinking -> green
reply playback          -> blue
playback finished       -> blue
```

## Main Commands

Start the full pipeline:

```bash
cd /home/louisxx/surf_demo_clean_workspace
./scripts/run_pipeline.sh --mode wake
```

Stop the pipeline:

```bash
./scripts/stop_pipeline.sh
```

Check configuration and syntax:

```bash
./scripts/check_pipeline.sh
```

Clean generated local files:

```bash
./scripts/clean_workspace.sh
./scripts/clean_workspace.sh --runtime
./scripts/clean_workspace.sh --logs
```

Follow logs:

```bash
./scripts/tail_pipeline_logs.sh all
./scripts/tail_pipeline_logs.sh rag
./scripts/tail_pipeline_logs.sh demo
./scripts/tail_pipeline_logs.sh voice
```

Monitor ASR topic:

```bash
./scripts/monitor_audio_msg.sh
```

## Current Backend

The default configured backend is RAG:

```text
DEMO_REPLY_BACKEND=rag
CHAT_PROVIDER=openai
CHAT_MODEL=deepseek-v4-pro
EMBED_PROVIDER=ollama
EMBED_MODEL=nomic-embed-text
```

Switch reply backend:

```bash
./scripts/env_set.sh DEMO_REPLY_BACKEND rag
./scripts/env_set.sh DEMO_REPLY_BACKEND local
./scripts/env_set.sh DEMO_REPLY_BACKEND dashscope
```

## Important Paths

```text
config/default.env             Runtime configuration and API keys
xjtlu-rag-system/              XJTLU RAG service and knowledge index
runtime/                       Generated status and TTS files
logs/                          Per-session pipeline archives
scripts/                       Startup, stop, check, and log scripts
PROJECT_CLEANUP.md             What is source vs generated output
CHANGELOG_20260521.md          Archived update summary for 2026-05-21
```

## External Dependencies

This workspace expects these existing local dependencies:

```text
SURF_ROOT=/home/louisxx/SURF2026_VoiceModule-main
QWEN_ROOT=/home/louisxx/qwen_ros_node_edg_tts
OLLAMA_BIN=/home/louisxx/.local/ollama/bin/ollama
QWEN_PYTHON=/home/louisxx/miniconda3/envs/qwen/bin/python
VOICE_PYTHON from SURF_ROOT/config/default.env
Unitree action classifier package under /home/louisxx/unitree_g1_action_classifier_package
```

`nomic-embed-text` must exist in Ollama:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 /home/louisxx/.local/ollama/bin/ollama list
```

## Notes

`config/default.env` contains local API keys. Do not publish this workspace as a
public repository unless those values are removed or replaced.
