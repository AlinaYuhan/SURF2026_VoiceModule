#!/usr/bin/env bash
set -euo pipefail

systemctl --user stop \
  voice-pipeline.service \
  surf-voice-runtime.service \
  surf-ros-bridge.service \
  demo-asr-bridge.service \
  demo-server.service \
  demo-ros-node.service \
  demo-audio-player.service \
  surf-demo-ollama.service \
  surf-demo-rag.service \
  surf-demo-server.service \
  surf-demo-node.service \
  surf-demo-audio-player.service >/dev/null 2>&1 || true

pkill -f 'asr_dds_to_ros_bridge.py --network' >/dev/null 2>&1 || true

echo "Stopped SURF -> Demo integrated pipeline services."
