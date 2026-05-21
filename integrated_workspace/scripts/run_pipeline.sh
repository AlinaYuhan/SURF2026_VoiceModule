#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${WORKSPACE_ROOT}"

set -a
source "${WORKSPACE_ROOT}/config/default.env"
set +a

MODE="${SURF_DEMO_MODE}"
WAKE_WORDS="${SURF_DEMO_WAKE_WORDS}"
LOCAL_CURL_ENV=(
  env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy
  NO_PROXY=127.0.0.1,localhost
)
PIPELINE_UNITS=(
  surf-ros-bridge.service
  surf-voice-runtime.service
  surf-demo-ollama.service
  surf-demo-rag.service
  surf-demo-server.service
  surf-demo-node.service
  surf-demo-audio-player.service
)

usage() {
  cat <<'EOF'
Usage: run_pipeline.sh [--mode listen|wake] [--wake-word WORD]

Starts:
  SURF voice-pipeline.service
  demo-server.service
  demo-ros-node.service with QWEN_AUTOSTART_ASR_BRIDGE=0
  demo-audio-player.service

If DEMO_REPLY_BACKEND=rag, also starts Ollama and the XJTLU RAG server.
EOF
}

log_unit_tail() {
  local unit="$1"
  echo "Recent logs for ${unit}:" >&2
  journalctl --user -u "${unit}" -n 80 --no-pager >&2 || true
}

unit_is_running() {
  local unit="$1"
  systemctl --user is-active --quiet "${unit}"
}

resolve_unitree_availability() {
  case "${UNITREE_ENABLE}" in
    1|true|TRUE|yes|YES|on|ON)
      ;;
    *)
      export UNITREE_ENABLE=0
      export QWEN_ACTION_EXECUTE=0
      echo "Unitree DDS disabled by UNITREE_ENABLE=0."
      return 0
      ;;
  esac

  if ip -o link show "${UNITREE_NETWORK_INTERFACE}" 2>/dev/null | grep -q "LOWER_UP"; then
    export UNITREE_ENABLE=1
    return 0
  fi

  echo "Unitree DDS disabled: ${UNITREE_NETWORK_INTERFACE} is not connected or not active."
  echo "Core voice/RAG/DeepSeek pipeline will still start; G1 audio, lights, and action execution are disabled."
  export UNITREE_ENABLE=0
  export QWEN_ACTION_EXECUTE=0
}

fail_if_unit_stopped() {
  local unit="$1"
  if ! systemctl --user show "${unit}" --property=ActiveState --value >/dev/null 2>&1; then
    echo "${unit} disappeared during startup." >&2
    log_unit_tail "${unit}"
    exit 1
  fi
  local state
  state="$(systemctl --user show "${unit}" --property=ActiveState --value 2>/dev/null || true)"
  if [[ "${state}" == "failed" || "${state}" == "inactive" ]]; then
    echo "${unit} is ${state} during startup." >&2
    log_unit_tail "${unit}"
    exit 1
  fi
}

wait_unit_running() {
  local unit="$1"
  local attempts="${2:-20}"

  for _ in $(seq 1 "${attempts}"); do
    if systemctl --user is-active --quiet "${unit}"; then
      local substate
      substate="$(systemctl --user show "${unit}" --property=SubState --value 2>/dev/null || true)"
      if [[ "${substate}" == "running" ]]; then
        return 0
      fi
    fi
    fail_if_unit_stopped "${unit}"
    sleep 0.5
  done

  echo "${unit} did not reach running state." >&2
  systemctl --user status "${unit}" --no-pager >&2 || true
  log_unit_tail "${unit}"
  exit 1
}

wait_http_health() {
  local name="$1"
  local url="$2"
  local unit="$3"
  local attempts="${4:-120}"

  echo "Waiting for ${name} health..."
  for _ in $(seq 1 "${attempts}"); do
    if "${LOCAL_CURL_ENV[@]}" curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    fail_if_unit_stopped "${unit}"
    sleep 1
  done

  echo "${name} did not become healthy: ${url}" >&2
  systemctl --user status "${unit}" --no-pager >&2 || true
  log_unit_tail "${unit}"
  exit 1
}

start_unit() {
  local unit="$1"
  shift
  systemd-run --user --unit="${unit}" --same-dir --collect \
    --property=Restart=on-failure --property=RestartSec=2s \
    "$@" >/dev/null
  sleep 0.3
  fail_if_unit_stopped "${unit}.service"
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
test -f "${WORKSPACE_ROOT}/demo_server.py"
test -f "${WORKSPACE_ROOT}/demo_surf_context_node.py"
test -f "${WORKSPACE_ROOT}/unitree_audio_player.py"

set +u
source /opt/ros/jazzy/setup.bash
set -u

resolve_unitree_availability

systemctl --user stop \
  voice-pipeline.service \
  surf-voice-runtime.service \
  surf-ros-bridge.service \
  demo-asr-bridge.service \
  demo-server.service \
  demo-ros-node.service \
  demo-audio-player.service \
  ollama.service \
  surf-demo-ollama.service \
  surf-demo-server.service \
  surf-demo-rag.service \
  surf-demo-node.service \
  surf-demo-audio-player.service >/dev/null 2>&1 || true

for unit in "${PIPELINE_UNITS[@]}"; do
  if unit_is_running "${unit}"; then
    echo "Failed to stop previous ${unit}" >&2
    exit 1
  fi
done

pkill -f 'asr_dds_to_ros_bridge.py --network' >/dev/null 2>&1 || true

start_unit surf-ros-bridge "${WORKSPACE_ROOT}/scripts/run_surf_ros_bridge.sh"

start_unit surf-voice-runtime "${WORKSPACE_ROOT}/scripts/run_surf_voice_runtime.sh"

if [[ "${DEMO_REPLY_BACKEND}" == "rag" ]]; then
  test -f "${WORKSPACE_ROOT}/xjtlu-rag-system/app.py"
  test -f "${WORKSPACE_ROOT}/xjtlu-rag-system/rag_index.db"
  test -f "${WORKSPACE_ROOT}/xjtlu-rag-system/xjtlu_knowledge.db"
  test -x "${OLLAMA_BIN}"

  start_unit surf-demo-ollama "${WORKSPACE_ROOT}/scripts/run_ollama_server.sh"
  wait_http_health "Ollama" "${OLLAMA_BASE_URL}/api/tags" surf-demo-ollama.service

  start_unit surf-demo-rag "${WORKSPACE_ROOT}/scripts/run_rag_server.sh"
  wait_http_health "XJTLU RAG server" "http://${RAG_SERVER_HOST}:${RAG_SERVER_PORT}/health" surf-demo-rag.service
fi

export QWEN_AUTOSTART_ASR_BRIDGE=0
export DEMO_ALWAYS_LISTEN=1
if [[ "${MODE}" == "wake" ]]; then
  export DEMO_ALWAYS_LISTEN=0
fi
if [[ -n "${WAKE_WORDS}" ]]; then
  export DEMO_WAKE_WORDS="${WAKE_WORDS}"
fi

SYSTEMD_ENV=(
  --setenv=QWEN_AUTOSTART_ASR_BRIDGE=0
  --setenv=DEMO_ALWAYS_LISTEN="${DEMO_ALWAYS_LISTEN}"
  --setenv=UNITREE_DOMAIN_ID="${UNITREE_DOMAIN_ID}"
  --setenv=UNITREE_ENABLE="${UNITREE_ENABLE}"
  --setenv=UNITREE_NETWORK_INTERFACE="${UNITREE_NETWORK_INTERFACE}"
  --setenv=QWEN_ACTION_EXECUTE="${QWEN_ACTION_EXECUTE}"
  --setenv=PYTHONPATH="${WORKSPACE_ROOT}:${QWEN_ROOT}/third_party/unitree_sdk2_python:${PYTHONPATH:-}"
)
if [[ -n "${WAKE_WORDS}" ]]; then
  SYSTEMD_ENV+=(--setenv=DEMO_WAKE_WORDS="${WAKE_WORDS}")
fi

start_unit surf-demo-server "${SYSTEMD_ENV[@]}" "${WORKSPACE_ROOT}/scripts/run_demo_server.sh"
wait_http_health "Demo server" "http://127.0.0.1:${DEMO_SERVER_PORT}/health" surf-demo-server.service

start_unit surf-demo-node "${SYSTEMD_ENV[@]}" "${WORKSPACE_ROOT}/scripts/run_surf_context_node.sh"

start_unit surf-demo-audio-player "${SYSTEMD_ENV[@]}" "${WORKSPACE_ROOT}/scripts/run_audio_player.sh"
wait_unit_running surf-demo-audio-player.service

echo "Integrated pipeline started."
echo "SURF publishes /audio_msg; demo consumes /audio_msg."
echo "Mode: ${MODE}"
echo "Reply backend: ${DEMO_REPLY_BACKEND}"
if [[ -n "${WAKE_WORDS}" ]]; then
  echo "Wake words: ${WAKE_WORDS}"
fi
echo "Demo DDS ASR bridge: disabled"
echo "Logs:"
echo "  journalctl --user -u surf-voice-runtime -f"
echo "  journalctl --user -u surf-ros-bridge -f"
echo "  journalctl --user -u surf-demo-ollama -f"
echo "  journalctl --user -u surf-demo-rag -f"
echo "  journalctl --user -u surf-demo-node -f"
echo "  journalctl --user -u surf-demo-server -f"
echo "  journalctl --user -u surf-demo-audio-player -f"
