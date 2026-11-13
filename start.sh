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
# 3. 端口探测 — 与 start.bat 共用 start_helper.py
# ---------------------------------------------------------------------------
# 使用当前启动器对应的 Python。只有 .venv / uv、没有系统 python3 时也能探测端口。
run_python() {
    case "$LAUNCHER" in
        venv)
            "$CURRENT_DIR/.venv/bin/python" "$@"
            ;;
        uv)
            uv run python "$@"
            ;;
        system)
            python3 "$@"
            ;;
        *)
            echo "unsupported launcher: $LAUNCHER" >&2
            return 1
            ;;
    esac
}

API_ALREADY_RUNNING=false
if run_python "$CURRENT_DIR/start_helper.py" check 127.0.0.1 "$API_PORT"; then
    API_ALREADY_RUNNING=true
fi

SELECTED_WEBUI_PORT="$(run_python "$CURRENT_DIR/start_helper.py" find "$WEBUI_HOST" "$WEBUI_PORT" 8599 || true)"
if [[ -z "$SELECTED_WEBUI_PORT" ]]; then
    echo -e "${RED}***** No available WebUI port found in ${WEBUI_PORT}-8599 for ${WEBUI_HOST}. *****${NC}"
    exit 1
fi

if [[ "$SELECTED_WEBUI_PORT" != "$WEBUI_PORT" ]]; then
    echo -e "${YELLOW}***** Port ${WEBUI_PORT} is unavailable, using ${SELECTED_WEBUI_PORT} instead. *****${NC}"
fi
WEBUI_PORT="$SELECTED_WEBUI_PORT"

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
    for _ in $(seq 1 15); do
        if run_python "$CURRENT_DIR/start_helper.py" check 127.0.0.1 "$API_PORT"; then
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
