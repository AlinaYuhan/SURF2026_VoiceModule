#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${WORKSPACE_ROOT}"

set -a
source "${WORKSPACE_ROOT}/config/default.env"
set +a

export DEMO_RUNTIME_DIR="${WORKSPACE_ROOT}/runtime"
export PYTHONPATH="${WORKSPACE_ROOT}:${QWEN_ROOT}/third_party/unitree_sdk2_python:${PYTHONPATH:-}"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"
mkdir -p "${DEMO_RUNTIME_DIR}"

exec "${QWEN_PYTHON}" -m uvicorn demo_server:app --host "${DEMO_SERVER_HOST}" --port "${DEMO_SERVER_PORT}"
