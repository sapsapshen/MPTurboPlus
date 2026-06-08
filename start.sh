#!/usr/bin/env bash
# =============================================================================
# MoneyPrinterTurbo — 一键启动脚本 (Linux / macOS)
# 同时启动 API 服务 (后台) 和 WebUI (前台)，自动检测运行环境。
# =============================================================================
set -euo pipefail

CURRENT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
export PYTHONPATH="${CURRENT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

# ---------------------------------------------------------------------------
# 1. 可配置项
# ---------------------------------------------------------------------------
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8080}"
WEBUI_HOST="${MPT_WEBUI_HOST:-127.0.0.1}"
WEBUI_PORT="${MPT_WEBUI_PORT:-8501}"

# huggingface 镜像（国内用户可取消注释）
# export HF_ENDPOINT=https://hf-mirror.com

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo -e "${CYAN}======================================${NC}"
echo -e "${CYAN}  MoneyPrinterTurbo v1.2.9${NC}"
echo -e "${CYAN}======================================${NC}"
echo ""

# ---------------------------------------------------------------------------
# 2. 环境检测 & 启动方式选择
# ---------------------------------------------------------------------------
LAUNCHER=""

if [[ -x "$CURRENT_DIR/.venv/bin/python" ]]; then
    LAUNCHER="venv"
elif command -v uv &>/dev/null && [[ -f "$CURRENT_DIR/uv.lock" ]]; then
    LAUNCHER="uv"
elif command -v python3 &>/dev/null; then
    echo -e "${YELLOW}***** Warning: using system python3. Run 'uv sync' first for best results. *****${NC}"
    LAUNCHER="system"
else
    echo -e "${RED}***** ERROR: No usable Python environment found. *****${NC}"
    echo -e "${RED}***** Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh *****${NC}"
    echo -e "${RED}***** Then run: uv sync *****${NC}"
    exit 1
fi

echo -e "Launcher: ${GREEN}${LAUNCHER}${NC}"
echo ""

# ---------------------------------------------------------------------------
# 3. 端口探测 — 找一个可用的 WebUI 端口
# ---------------------------------------------------------------------------
find_available_port() {
    python3 - "$WEBUI_HOST" "$WEBUI_PORT" "$@" 2>/dev/null <<'PYEOF'
import os
import socket
import sys

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
preferred = int(sys.argv[2]) if len(sys.argv) > 2 else 8501
candidates = [preferred] + [p for p in range(8502, 8600) if p != preferred]

for port in candidates:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            continue
        print(port)
        sys.exit(0)

sys.exit(1)
PYEOF
}

# Use the appropriate Python for port probing
case "$LAUNCHER" in
    venv)   PORT_PROBE_PYTHON="$CURRENT_DIR/.venv/bin/python" ;;
    uv)     PORT_PROBE_PYTHON="uv run python" ;;
    system) PORT_PROBE_PYTHON="python3" ;;
esac

# Detect available WebUI port
SELECTED_WEBUI_PORT="$(find_available_port "$PORT_PROBE_PYTHON" 2>/dev/null)"
if [[ -z "$SELECTED_WEBUI_PORT" ]]; then
    echo -e "${RED}***** No available WebUI port found in 8501-8599 for ${WEBUI_HOST}. *****${NC}"
    exit 1
fi

if [[ "$SELECTED_WEBUI_PORT" != "$WEBUI_PORT" ]]; then
    echo -e "${YELLOW}***** Port ${WEBUI_PORT} is unavailable, using ${SELECTED_WEBUI_PORT} instead. *****${NC}"
fi
WEBUI_PORT="$SELECTED_WEBUI_PORT"

# Check if API port is already in use
API_ALREADY_RUNNING=false
if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', ${API_PORT}))
    s.close()
    exit(0)
except:
    s.close()
    exit(1)
" 2>/dev/null; then
    API_ALREADY_RUNNING=true
fi

# ---------------------------------------------------------------------------
# 4. 构建启动命令
# ---------------------------------------------------------------------------
case "$LAUNCHER" in
    venv)
        API_CMD=("$CURRENT_DIR/.venv/bin/python" "$CURRENT_DIR/main.py")
        WEBUI_CMD=("$CURRENT_DIR/.venv/bin/streamlit")
        ;;
    uv)
        API_CMD=(uv run python "$CURRENT_DIR/main.py")
        WEBUI_CMD=(uv run streamlit)
        ;;
    system)
        API_CMD=(python3 "$CURRENT_DIR/main.py")
        WEBUI_CMD=(streamlit)
        ;;
esac

# ---------------------------------------------------------------------------
# 5. 启动 API 服务 (后台)
# ---------------------------------------------------------------------------
API_PID=""
if $API_ALREADY_RUNNING; then
    echo -e "[API] Port ${API_PORT} is already in use — assuming API is already running."
else
    echo -e "[API] Starting API server on http://127.0.0.1:${API_PORT} ..."
    cd "$CURRENT_DIR"
    "${API_CMD[@]}" &
    API_PID=$!
    # 等待 API 就绪
    for i in $(seq 1 15); do
        if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', ${API_PORT}))
    s.close()
    exit(0)
except:
    s.close()
    exit(1)
" 2>/dev/null; then
            echo -e "[API] ${GREEN}Ready.${NC}"
            break
        fi
        sleep 1
    done
fi

# ---------------------------------------------------------------------------
# 6. 启动 WebUI (前台)
# ---------------------------------------------------------------------------
echo ""
echo -e "[WebUI] Starting WebUI on http://${WEBUI_HOST}:${WEBUI_PORT} ..."
echo -e "${CYAN}======================================${NC}"
echo -e "  API:    ${GREEN}http://127.0.0.1:${API_PORT}${NC}"
echo -e "  Docs:   ${GREEN}http://127.0.0.1:${API_PORT}/docs${NC}"
echo -e "  WebUI:  ${GREEN}http://${WEBUI_HOST}:${WEBUI_PORT}${NC}"
echo -e "${CYAN}======================================${NC}"
echo ""
echo "Press Ctrl+C to stop WebUI and API."

# Trap cleanup: kill API on exit
cleanup() {
    echo ""
    echo "***** Shutting down ... *****"
    if [[ -n "$API_PID" ]] && kill -0 "$API_PID" 2>/dev/null; then
        kill "$API_PID" 2>/dev/null
        echo "***** API server stopped. *****"
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

cd "$CURRENT_DIR"
"${WEBUI_CMD[@]}" run "$CURRENT_DIR/webui/Main.py" \
    --server.address="$WEBUI_HOST" \
    --server.port="$WEBUI_PORT" \
    --browser.serverAddress="$WEBUI_HOST" \
    --browser.gatherUsageStats=False \
    --server.enableCORS=True

cleanup
