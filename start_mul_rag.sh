#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$ROOT_DIR/MUL_rag/mul_rag"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_APP="$PROJECT_DIR/streamlit_app.py"
ENV_NAME="mul_rag"
MINERU_ENV_NAME="${MINERU_ENV_NAME:-mineru}"
MINERU_BIN="$HOME/anaconda3/envs/$MINERU_ENV_NAME/bin/mineru"
UNSTRUCTURED_LAYOUT_REPO_ID="${UNSTRUCTURED_LAYOUT_REPO_ID:-unstructuredio/yolo_x_layout}"
PRELOAD_UNSTRUCTURED_MODELS="${PRELOAD_UNSTRUCTURED_MODELS:-1}"
PRELOAD_TIMEOUT_SEC="${PRELOAD_TIMEOUT_SEC:-1800}"

if [ -z "${MINERU_CMD:-}" ] && [ -x "$MINERU_BIN" ]; then
  export MINERU_CMD="$MINERU_BIN"
fi
export MINERU_BACKEND="${MINERU_BACKEND:-pipeline}"
export MINERU_TIMEOUT="${MINERU_TIMEOUT:-3600}"
if [ -z "${MINERU_MODEL_SOURCE:-}" ] && [ -f "$HOME/mineru.json" ]; then
  export MINERU_MODEL_SOURCE="local"
fi

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8002"
FRONTEND_HOST="127.0.0.1"
FRONTEND_PORT="8501"

LOG_DIR="$ROOT_DIR/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

mkdir -p "$LOG_DIR"

if ! command -v conda >/dev/null 2>&1; then
  echo "未找到 conda，请先确保 conda 已安装并可用。"
  exit 1
fi

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "未找到 conda 环境: $ENV_NAME"
  exit 1
fi

if [ ! -f "$FRONTEND_APP" ]; then
  echo "未找到前端入口文件: $FRONTEND_APP"
  exit 1
fi

if [ ! -f "$BACKEND_DIR/app.py" ]; then
  echo "未找到后端入口文件: $BACKEND_DIR/app.py"
  exit 1
fi

check_http() {
  local url="$1"
  curl -fsS "$url" >/dev/null 2>&1
}

preload_unstructured_models() {
  if [ "$PRELOAD_UNSTRUCTURED_MODELS" = "0" ]; then
    echo "跳过基础解析模型预下载。"
    return
  fi

  echo "预下载基础解析模型: $UNSTRUCTURED_LAYOUT_REPO_ID"
  echo "说明: 首次下载约 200MB+，慢网环境可能需要几分钟。"

  local preload_cmd=(
    conda run --no-capture-output -n "$ENV_NAME" env
    HF_HUB_DISABLE_PROGRESS_BARS=0
    UNSTRUCTURED_LAYOUT_REPO_ID="$UNSTRUCTURED_LAYOUT_REPO_ID"
    python -
  )

  if command -v timeout >/dev/null 2>&1; then
    timeout "${PRELOAD_TIMEOUT_SEC}s" "${preload_cmd[@]}" <<'PY'
import os
from huggingface_hub import hf_hub_download

repo_id = os.getenv("UNSTRUCTURED_LAYOUT_REPO_ID", "unstructuredio/yolo_x_layout")
files = ["label_map.json", "yolox_l0.05.onnx"]

print(f"开始检查缓存: {repo_id}")
for name in files:
    try:
        cached = hf_hub_download(repo_id=repo_id, filename=name, local_files_only=True)
        size_mb = os.path.getsize(cached) / (1024 * 1024)
        print(f"缓存命中: {name} ({size_mb:.1f} MB)")
    except Exception:
        print(f"下载中: {name}")
        path = hf_hub_download(repo_id=repo_id, filename=name, local_files_only=False)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        print(f"下载完成: {name} ({size_mb:.1f} MB)")

print(f"基础解析模型已就绪: {repo_id}")
PY
  else
    "${preload_cmd[@]}" <<'PY'
import os
from huggingface_hub import hf_hub_download

repo_id = os.getenv("UNSTRUCTURED_LAYOUT_REPO_ID", "unstructuredio/yolo_x_layout")
files = ["label_map.json", "yolox_l0.05.onnx"]

print(f"开始检查缓存: {repo_id}")
for name in files:
    try:
        cached = hf_hub_download(repo_id=repo_id, filename=name, local_files_only=True)
        size_mb = os.path.getsize(cached) / (1024 * 1024)
        print(f"缓存命中: {name} ({size_mb:.1f} MB)")
    except Exception:
        print(f"下载中: {name}")
        path = hf_hub_download(repo_id=repo_id, filename=name, local_files_only=False)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        print(f"下载完成: {name} ({size_mb:.1f} MB)")

print(f"基础解析模型已就绪: {repo_id}")
PY
  fi
}

start_backend() {
  if check_http "http://$BACKEND_HOST:$BACKEND_PORT/api/v1/health"; then
    echo "后端已在运行: http://$BACKEND_HOST:$BACKEND_PORT"
    return
  fi

  echo "启动后端..."
  (
    cd "$BACKEND_DIR"
    nohup env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
      AUTO_DOWNLOAD_NLTK=False \
      MINERU_CMD="${MINERU_CMD:-mineru}" \
      MINERU_BACKEND="${MINERU_BACKEND:-pipeline}" \
      MINERU_METHOD="${MINERU_METHOD:-}" \
      MINERU_LANG="${MINERU_LANG:-}" \
      MINERU_TIMEOUT="${MINERU_TIMEOUT:-3600}" \
      MINERU_EXTRA_ARGS="${MINERU_EXTRA_ARGS:-}" \
      MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-}" \
      conda run -n "$ENV_NAME" \
      uvicorn app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
      >"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )

  for _ in $(seq 1 30); do
    if check_http "http://$BACKEND_HOST:$BACKEND_PORT/api/v1/health"; then
      echo "后端启动成功: http://$BACKEND_HOST:$BACKEND_PORT"
      return
    fi
    sleep 1
  done

  echo "后端启动失败，请查看日志: $BACKEND_LOG"
  exit 1
}

start_frontend() {
  if check_http "http://$FRONTEND_HOST:$FRONTEND_PORT"; then
    echo "前端已在运行: http://$FRONTEND_HOST:$FRONTEND_PORT"
    return
  fi

  echo "启动前端..."
  nohup env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
    AUTO_DOWNLOAD_NLTK=False \
    conda run -n "$ENV_NAME" \
    python -m streamlit run "$FRONTEND_APP" \
    --server.address "$FRONTEND_HOST" \
    --server.port "$FRONTEND_PORT" \
    >"$FRONTEND_LOG" 2>&1 &
  echo $! >"$FRONTEND_PID_FILE"

  for _ in $(seq 1 30); do
    if check_http "http://$FRONTEND_HOST:$FRONTEND_PORT"; then
      echo "前端启动成功: http://$FRONTEND_HOST:$FRONTEND_PORT"
      return
    fi
    sleep 1
  done

  echo "前端启动失败，请查看日志: $FRONTEND_LOG"
  exit 1
}

preload_unstructured_models
start_backend
start_frontend

echo
echo "启动完成:"
echo "后端:   http://$BACKEND_HOST:$BACKEND_PORT/api/v1/health"
echo "前端:   http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "日志目录: $LOG_DIR"
