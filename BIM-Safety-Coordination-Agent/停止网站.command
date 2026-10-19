#!/bin/bash
cd "$(dirname "$0")" || exit 1
PID_FILE="02_网站源码/backend/runtime/server.pid"
if [ ! -f "$PID_FILE" ]; then
  echo "未找到 PID 文件；如果服务仍在运行，请手动停止占用 8000 端口的进程。"
  read -r -p "按回车关闭窗口…" _
  exit 0
fi
PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null
  for i in $(seq 1 20); do
    if ! kill -0 "$PID" 2>/dev/null; then break; fi
    sleep 0.5
  done
  if kill -0 "$PID" 2>/dev/null; then kill -9 "$PID" 2>/dev/null; fi
  echo "服务已停止（PID $PID）。"
else
  echo "PID $PID 已不存在。"
fi
rm -f "$PID_FILE"
read -r -p "按回车关闭窗口…" _
