#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/lrn/MUL_RAG"
LOG_DIR="$ROOT_DIR/logs"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

BACKEND_PORT="8002"
FRONTEND_PORT="8501"

stop_by_pid_file() {
  local name="$1"
  local pid_file="$2"

  if [ ! -f "$pid_file" ]; then
    echo "$name: 未找到 PID 文件，跳过。"
    return
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"

  if [ -z "$pid" ]; then
    echo "$name: PID 文件为空，移除。"
    rm -f "$pid_file"
    return
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "$name: 进程 $pid 不存在，移除 PID 文件。"
    rm -f "$pid_file"
    return
  fi

  echo "停止 $name (PID: $pid)..."
  kill "$pid" 2>/dev/null || true

  for _ in $(seq 1 10); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$name: 已停止。"
      rm -f "$pid_file"
      return
    fi
    sleep 1
  done

  echo "$name: 优雅停止超时，发送 SIGKILL。"
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
}

stop_by_port() {
  local name="$1"
  local port="$2"

  if ! command -v lsof >/dev/null 2>&1; then
    echo "$name: 系统未安装 lsof，跳过端口兜底检查。"
    return
  fi

  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"

  if [ -z "$pids" ]; then
    echo "$name: 端口 $port 未发现残留进程。"
    return
  fi

  echo "$name: 清理端口 $port 上的残留进程: $pids"
  kill $pids 2>/dev/null || true
}

stop_by_pid_file "后端" "$BACKEND_PID_FILE"
stop_by_pid_file "前端" "$FRONTEND_PID_FILE"

# 兜底：如果 PID 文件丢了，但端口上还有残留进程，则继续清理
stop_by_port "后端" "$BACKEND_PORT"
stop_by_port "前端" "$FRONTEND_PORT"

echo
echo "停止完成。"
