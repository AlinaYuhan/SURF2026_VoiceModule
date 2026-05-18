#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${WORKSPACE_ROOT}"

set -a
source "${WORKSPACE_ROOT}/config/default.env"
set +a

MODE="${SURF_QWEN_MODE}"
WAKE_WORDS="${SURF_QWEN_WAKE_WORDS}"

usage() {
  cat <<'EOF'
Usage: run_pipeline.sh [--mode listen|wake] [--wake-word WORD]

Starts:
  SURF voice-pipeline.service
  qwen-server.service
  qwen-ros-node.service with QWEN_AUTOSTART_ASR_BRIDGE=0
  qwen-audio-player.service
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --mode=*)
      MODE="${1#*=}"
      shift
      ;;
    --wake-word|--wake-words)
      WAKE_WORDS="${2:-}"
      shift 2
      ;;
    --wake-word=*|--wake-words=*)
      WAKE_WORDS="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${MODE}" != "listen" && "${MODE}" != "wake" ]]; then
  echo "Invalid --mode value: ${MODE}" >&2
  usage >&2
  exit 1
fi

test -f "${WORKSPACE_ROOT}/surf_voice_runtime.py"
test -f "${WORKSPACE_ROOT}/surf_ros_bridge.py"
test -d "${QWEN_ROOT}/third_party/unitree_sdk2_python"
test -f "${WORKSPACE_ROOT}/qwen_server.py"
test -f "${WORKSPACE_ROOT}/qwen_surf_context_node.py"
test -f "${WORKSPACE_ROOT}/unitree_audio_player.py"

set +u
source /opt/ros/jazzy/setup.bash
set -u

systemctl --user stop \
  voice-pipeline.service \
  surf-voice-runtime.service \
  surf-ros-bridge.service \
  qwen-asr-bridge.service \
  qwen-server.service \
  qwen-ros-node.service \
  qwen-audio-player.service \
  surf-qwen-server.service \
  surf-qwen-node.service \
  surf-qwen-audio-player.service >/dev/null 2>&1 || true

pkill -f 'asr_dds_to_ros_bridge.py --network' >/dev/null 2>&1 || true

systemd-run --user --unit=surf-ros-bridge --same-dir --collect \
  "${WORKSPACE_ROOT}/scripts/run_surf_ros_bridge.sh" >/dev/null

systemd-run --user --unit=surf-voice-runtime --same-dir --collect \
  "${WORKSPACE_ROOT}/scripts/run_surf_voice_runtime.sh" >/dev/null

export QWEN_AUTOSTART_ASR_BRIDGE=0
export QWEN_ALWAYS_LISTEN=1
if [[ "${MODE}" == "wake" ]]; then
  export QWEN_ALWAYS_LISTEN=0
fi
if [[ -n "${WAKE_WORDS}" ]]; then
  export QWEN_WAKE_WORDS="${WAKE_WORDS}"
fi

SYSTEMD_ENV=(
  --setenv=QWEN_AUTOSTART_ASR_BRIDGE=0
  --setenv=QWEN_ALWAYS_LISTEN="${QWEN_ALWAYS_LISTEN}"
  --setenv=PYTHONPATH="${WORKSPACE_ROOT}:${QWEN_ROOT}/third_party/unitree_sdk2_python:${PYTHONPATH:-}"
)
if [[ -n "${WAKE_WORDS}" ]]; then
  SYSTEMD_ENV+=(--setenv=QWEN_WAKE_WORDS="${WAKE_WORDS}")
fi

systemd-run --user --unit=surf-qwen-server --same-dir --collect "${SYSTEMD_ENV[@]}" \
  "${WORKSPACE_ROOT}/scripts/run_qwen_server.sh" >/dev/null

echo "Waiting for Qwen server health..."
for _ in $(seq 1 120); do
  if env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
      NO_PROXY=127.0.0.1,localhost \
      curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

systemd-run --user --unit=surf-qwen-node --same-dir --collect "${SYSTEMD_ENV[@]}" \
  "${WORKSPACE_ROOT}/scripts/run_surf_context_node.sh" >/dev/null

systemd-run --user --unit=surf-qwen-audio-player --same-dir --collect "${SYSTEMD_ENV[@]}" \
  "${WORKSPACE_ROOT}/scripts/run_audio_player.sh" >/dev/null

echo "Integrated pipeline started."
echo "SURF publishes /audio_msg; qwen consumes /audio_msg."
echo "Mode: ${MODE}"
if [[ -n "${WAKE_WORDS}" ]]; then
  echo "Wake words: ${WAKE_WORDS}"
fi
echo "Qwen DDS ASR bridge: disabled"
echo "Logs:"
echo "  journalctl --user -u surf-voice-runtime -f"
echo "  journalctl --user -u surf-ros-bridge -f"
echo "  journalctl --user -u surf-qwen-node -f"
echo "  journalctl --user -u surf-qwen-server -f"
echo "  journalctl --user -u surf-qwen-audio-player -f"
