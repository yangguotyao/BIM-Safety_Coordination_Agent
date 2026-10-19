#!/bin/bash
cd "$(dirname "$0")" || exit 1
RUNTIME="02_网站源码/backend/runtime"
PID_FILE="$RUNTIME/server.pid"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"
if [ -z "$LAN_IP" ]; then
  echo "未检测到局域网 IP。请确认已连接 Wi-Fi/热点，或运行 ipconfig getifaddr en0 查看。"
  read -r -p "按回车关闭窗口…" _
  exit 1
fi
URL="http://$LAN_IP:8000"
mkdir -p "$RUNTIME"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "服务已在运行（PID $(cat "$PID_FILE")）。"
  echo "局域网地址：$URL"
  open "$URL"
  exit 0
fi

if curl -sf --max-time 2 "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
  BIND="$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | tail -1)"
  echo "端口 8000 已有服务在运行。"
  if echo "$BIND" | grep -q "127.0.0.1:8000"; then
    echo "但该服务只绑定了 127.0.0.1，局域网设备无法访问。"
    echo "请先双击“停止网站.command”，再运行本脚本。"
    read -r -p "按回车关闭窗口…" _
    exit 1
  fi
  echo "局域网地址：$URL"
  open "$URL"
  exit 0
fi

echo "正在以局域网模式启动 BIM 施工安全协同平台…"
echo "本机：http://127.0.0.1:8000"
echo "局域网：$URL"
echo "请确保对方与你在同一 Wi-Fi/热点，且路由器未开启 AP 隔离。"
echo "首次启动会安装后端依赖，可能需要 1–3 分钟。"
HOST=0.0.0.0 nohup 02_网站源码/scripts/start.sh > "$RUNTIME/server.log" 2>&1 &
echo $! > "$PID_FILE"

for i in $(seq 1 120); do
  if curl -sf --max-time 1 "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
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
