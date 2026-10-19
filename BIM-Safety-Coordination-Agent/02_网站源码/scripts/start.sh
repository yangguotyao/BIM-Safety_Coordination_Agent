#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGE_ROOT="$(cd "$SOURCE_DIR/.." && pwd)"
BACKEND_DIR="$SOURCE_DIR/backend"
FRONTEND_DIR="$SOURCE_DIR/frontend"
DATA_ROOT="${DATA_ROOT:-$PACKAGE_ROOT/01_资料与依据}"
RUNTIME_DIR="${RUNTIME_DIR:-$BACKEND_DIR/runtime}"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export DATA_ROOT RUNTIME_DIR PORT HOST

mkdir -p "$RUNTIME_DIR"

if [ ! -d "$DATA_ROOT" ]; then
  echo "✗ 资料目录不存在：$DATA_ROOT"
  echo "  请确认交付包完整，或设置 DATA_ROOT 指向 01_资料与依据。"
  exit 1
fi

PORT_BUSY=0
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    PORT_BUSY=1
    echo "✗ 端口 $PORT 已被占用："
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | sed -n '2,4p'
  fi
else
  PORT_BUSY=$("$PYTHON_BIN" -c '
import socket, sys
port = int(sys.argv[1])
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", port))
except Exception:
    print(0)
else:
    print(1)
finally:
    s.close()
' "$PORT")
fi
if [ "$PORT_BUSY" = "1" ]; then
  echo "  可设置 PORT=8001 后重试。"
  exit 1
fi

cd "$BACKEND_DIR"
if [ ! -x ".venv/bin/python" ]; then
  echo "· 创建后端虚拟环境（复用系统已安装包）"
  "$PYTHON_BIN" -m venv --system-site-packages .venv
fi

if ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import fastapi, pydantic, uvicorn, langgraph, ifcopenshell
PY
then
  echo "· 安装后端依赖（需要网络）"
  .venv/bin/python -m pip install --no-cache-dir -r requirements.txt
fi

if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
  echo "· 未发现前端构建产物，尝试构建"
  if command -v npm >/dev/null 2>&1; then
    (cd "$FRONTEND_DIR" && npm_config_cache="$SOURCE_DIR/.npm-cache" npm install --no-audit --no-fund && npm run build)
  else
    echo "✗ 前端 dist 缺失且未找到 npm；请使用源码中的 dist 或安装 Node.js。"
    exit 1
  fi
fi

if [ -f "$BACKEND_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.env"
  set +a
fi

DISPLAY_HOST="$HOST"
if [ "$HOST" = "0.0.0.0" ]; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')"
  DISPLAY_HOST="${LAN_IP:-127.0.0.1}"
fi

echo ""
echo "  BIM 施工安全协同平台"
echo "  ─────────────────────────────────────────"
echo "  本机      http://127.0.0.1:$PORT"
if [ "$HOST" = "0.0.0.0" ]; then
  echo "  局域网    http://$DISPLAY_HOST:$PORT"
  echo "  绑定      $HOST:${PORT}（同一 Wi-Fi 的设备可访问）"
else
  echo "  地址      http://$HOST:${PORT}（仅本机）"
fi
echo "  API 文档  http://$DISPLAY_HOST:$PORT/api/docs"
echo "  资料根目录 $DATA_ROOT"
echo "  运行目录   $RUNTIME_DIR"
echo "  模式      ${DEMO_MODE:-true} (DEMO_MODE)"
echo "  ─────────────────────────────────────────"
echo "  停止：Ctrl+C"
echo ""

exec .venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
