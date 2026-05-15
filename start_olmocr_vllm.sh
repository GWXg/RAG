#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/lrn/MUL_RAG"
MODEL_DIR="${OLMOCR_MODEL_DIR:-$ROOT_DIR/MUL_rag/olmocr/olmOCR-2-7B-1025-FP8}"
ENV_NAME="${OLMOCR_ENV_NAME:-olmocr}"
HOST="${OLMOCR_HOST:-127.0.0.1}"
PORT="${OLMOCR_PORT:-8005}"
SERVED_MODEL_NAME="${OLMOCR_MODEL:-olmocr}"
MAX_MODEL_LEN="${OLMOCR_MAX_MODEL_LEN:-16384}"
GPU_MEMORY_UTILIZATION="${OLMOCR_GPU_MEMORY_UTILIZATION:-0.8}"

LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/olmocr_vllm.log"
PID_FILE="$LOG_DIR/olmocr_vllm.pid"

mkdir -p "$LOG_DIR"

if ! command -v conda >/dev/null 2>&1; then
  echo "未找到 conda，请先确保 conda 已安装并可用。"
  exit 1
fi

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "未找到 conda 环境: $ENV_NAME"
  echo "请先安装 OLMOCR vLLM 依赖，或设置 OLMOCR_ENV_NAME 指向可用环境。"
  exit 1
fi

if [ ! -d "$MODEL_DIR" ]; then
  echo "未找到 OLMOCR 模型目录: $MODEL_DIR"
  exit 1
fi

if curl -fsS "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then
  echo "OLMOCR vLLM 服务已在运行: http://$HOST:$PORT/v1"
  exit 0
fi

echo "启动 OLMOCR vLLM 服务..."
echo "模型目录: $MODEL_DIR"
echo "服务地址: http://$HOST:$PORT/v1"
echo "日志文件: $LOG_FILE"

nohup setsid env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
  conda run --no-capture-output -n "$ENV_NAME" \
  vllm serve "$MODEL_DIR" \
    --host "$HOST" \
    --port "$PORT" \
    --served-model-name "$SERVED_MODEL_NAME" \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  >"$LOG_FILE" 2>&1 < /dev/null &

echo $! >"$PID_FILE"

for _ in $(seq 1 120); do
  if curl -fsS "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then
    echo "OLMOCR vLLM 服务启动成功: http://$HOST:$PORT/v1"
    exit 0
  fi
  sleep 2
done

echo "OLMOCR vLLM 服务启动超时，请查看日志: $LOG_FILE"
exit 1
