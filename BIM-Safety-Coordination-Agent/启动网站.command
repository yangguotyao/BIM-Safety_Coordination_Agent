#!/bin/bash
cd "$(dirname "$0")" || exit 1
RUNTIME="02_网站源码/backend/runtime"
PID_FILE="$RUNTIME/server.pid"
URL="http://127.0.0.1:8000"
mkdir -p "$RUNTIME"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "服务已在运行（PID $(cat "$PID_FILE")）。"
  open "$URL"
  exit 0
fi

if curl -sf --max-time 2 "$URL/api/health" >/dev/null 2>&1; then
  echo "端口 8000 已有服务在运行。"
  open "$URL"
  exit 0
fi

echo "正在启动 BIM 施工安全协同平台…"
echo "首次启动会安装后端依赖，可能需要 1–3 分钟。"
nohup 02_网站源码/scripts/start.sh > "$RUNTIME/server.log" 2>&1 &
echo $! > "$PID_FILE"

for i in $(seq 1 120); do
  if curl -sf --max-time 1 "$URL/api/health" >/dev/null 2>&1; then
    echo "启动成功：$URL"
    open "$URL"
    exit 0
  fi
  sleep 1
done

echo "启动超时。请查看日志：$RUNTIME/server.log"
tail -30 "$RUNTIME/server.log"
read -r -p "按回车关闭窗口…" _
exit 1
