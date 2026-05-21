#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tail_pipeline_logs.sh [all|core|voice|rag|demo|audio]

Groups:
  all    all integrated pipeline services
  core   SURF voice, RAG, demo node, demo server, audio player
  voice  SURF voice runtime and UDP ROS bridge
  rag    Ollama and XJTLU RAG server
  demo   demo server and demo ROS context node
  audio  Unitree audio player
EOF
}

GROUP="${1:-all}"

case "${GROUP}" in
  all)
    UNITS=(
      surf-voice-runtime
      surf-ros-bridge
      surf-demo-ollama
      surf-demo-rag
      surf-demo-server
      surf-demo-node
      surf-demo-audio-player
    )
    ;;
  core)
    UNITS=(
      surf-voice-runtime
      surf-demo-rag
      surf-demo-server
      surf-demo-node
      surf-demo-audio-player
    )
    ;;
  voice)
    UNITS=(surf-voice-runtime surf-ros-bridge)
    ;;
  rag)
    UNITS=(surf-demo-ollama surf-demo-rag)
    ;;
  demo)
    UNITS=(surf-demo-server surf-demo-node)
    ;;
  audio)
    UNITS=(surf-demo-audio-player)
    ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  *)
    echo "Unknown log group: ${GROUP}" >&2
    usage >&2
    exit 1
    ;;
esac

ARGS=(--user -f -n 80 --no-pager)
for unit in "${UNITS[@]}"; do
  ARGS+=(-u "${unit}")
done

echo "Following logs for: ${UNITS[*]}"
exec journalctl "${ARGS[@]}"
