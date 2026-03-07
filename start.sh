#!/usr/bin/env bash
# start.sh — Launch both FastAPI backend and Next.js frontend
# Usage: ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
FRONTEND_LOCK_FILE="$FRONTEND_DIR/.next/dev/lock"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  İLAY — AI Clinical Risk Intelligence${NC}"
echo -e "${CYAN}  ACUHIT 2026 — Acıbadem University${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

OWN_BACKEND=0
OWN_FRONTEND=0
BACKEND_PID=""
FRONTEND_PID=""
FRONTEND_PORT=""
FRONTEND_REUSED=0
_CLEANUP_DONE=0

: "${ILAY_BACKEND_RELOAD:=0}"

is_port_in_use() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
        return $?
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -ltn "( sport = :$port )" | tail -n +2 | grep -q .
        return $?
    fi
    return 1
}

find_existing_next_dev_pid() {
    ps -eo pid,args | awk -v dir="$FRONTEND_DIR" '
        $0 ~ /node .*next dev/ && index($0, dir) > 0 { print $1; exit }
    '
}

port_for_pid() {
    local pid="$1"
    local port=""
    if [ -z "$pid" ]; then
        return 0
    fi

    if command -v lsof >/dev/null 2>&1; then
        port="$(lsof -nP -a -p "$pid" -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {split($9,a,":"); print a[length(a)]; exit}')"
    fi

    if [ -z "$port" ] && command -v ss >/dev/null 2>&1; then
        port="$(ss -ltnp 2>/dev/null | awk -v pid="$pid" '$0 ~ "pid=" pid "," {split($4,a,":"); print a[length(a)]; exit}')"
    fi

    if [ -n "$port" ]; then
        echo "$port"
    fi
}

detect_existing_frontend_port() {
    local pid="$1"
    local port=""
    local child=""

    port="$(port_for_pid "$pid")"
    if [ -n "$port" ]; then
        echo "$port"
        return 0
    fi

    while read -r child; do
        [ -z "$child" ] && continue
        port="$(port_for_pid "$child")"
        if [ -n "$port" ]; then
            echo "$port"
            return 0
        fi
    done < <(pgrep -P "$pid" 2>/dev/null || true)
}

pick_frontend_port() {
    local preferred="${1:-3000}"
    local port=""
    local max_port=3100

    if ! is_port_in_use "$preferred"; then
        echo "$preferred"
        return 0
    fi

    for port in $(seq $((preferred + 1)) "$max_port"); do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
    done

    return 1
}

cleanup() {
    if [ "$_CLEANUP_DONE" -eq 1 ]; then
        return
    fi
    _CLEANUP_DONE=1

    echo -e "\n${YELLOW}Shutting down...${NC}"

    if [ "$OWN_FRONTEND" -eq 1 ] && [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null || true
        wait "$FRONTEND_PID" 2>/dev/null || true
    fi

    if [ "$OWN_BACKEND" -eq 1 ] && [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi

    echo -e "${GREEN}Done.${NC}"
}

trap cleanup EXIT
trap 'exit 130' SIGINT
trap 'exit 143' SIGTERM

# ── Backend (FastAPI) ─────────────────────────────────────────────────────
echo -e "${GREEN}[1/2]${NC} Starting FastAPI backend on :8000..."
echo -e "${YELLOW}      NLP scores loaded from .cache/ (no model or API calls at startup)${NC}"
if [ "$ILAY_BACKEND_RELOAD" = "1" ]; then
    echo -e "${YELLOW}      Backend reload enabled (ILAY_BACKEND_RELOAD=1).${NC}"
else
    echo -e "${YELLOW}      Backend reload disabled by default (set ILAY_BACKEND_RELOAD=1 to enable).${NC}"
fi

cd "$SCRIPT_DIR"

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

BACKEND_CMD=(python3 -m uvicorn api:app --host 0.0.0.0 --port 8000)
if [ "$ILAY_BACKEND_RELOAD" = "1" ]; then
    BACKEND_CMD+=(--reload)
fi
"${BACKEND_CMD[@]}" &
BACKEND_PID=$!
OWN_BACKEND=1

# Wait for backend to be ready
echo -e "${YELLOW}      Waiting for backend to initialize (loading pipeline)...${NC}"
for i in $(seq 1 120); do
    if curl -s http://localhost:8000/api/patients > /dev/null 2>&1; then
        echo -e "${GREEN}      Backend ready!${NC}"
        break
    fi
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}      Backend failed to start. Check logs above.${NC}"
        exit 1
    fi
    sleep 2
done

# ── Frontend (Next.js) ────────────────────────────────────────────────────
echo -e "${GREEN}[2/2]${NC} Starting Next.js frontend..."

EXISTING_NEXT_PID="$(find_existing_next_dev_pid || true)"
if [ -n "$EXISTING_NEXT_PID" ]; then
    FRONTEND_REUSED=1
    FRONTEND_PORT="$(detect_existing_frontend_port "$EXISTING_NEXT_PID" || true)"
    if [ -z "$FRONTEND_PORT" ]; then
        FRONTEND_PORT=3000
    fi
    echo -e "${YELLOW}      Reusing existing Next.js dev server (PID $EXISTING_NEXT_PID) on :$FRONTEND_PORT${NC}"
else
    if [ -f "$FRONTEND_LOCK_FILE" ]; then
        echo -e "${YELLOW}      Removing stale Next.js lock file: $FRONTEND_LOCK_FILE${NC}"
        rm -f "$FRONTEND_LOCK_FILE"
    fi

    FRONTEND_PORT="$(pick_frontend_port 3000)" || {
        echo -e "${RED}      Could not find an available frontend port between 3000-3100.${NC}"
        exit 1
    }
    echo -e "${YELLOW}      Launching Next.js on :$FRONTEND_PORT${NC}"

    cd "$FRONTEND_DIR"
    npm run dev -- --port "$FRONTEND_PORT" &
    FRONTEND_PID=$!
    OWN_FRONTEND=1

    for i in $(seq 1 90); do
        if curl -s "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
            echo -e "${GREEN}      Frontend ready!${NC}"
            break
        fi
        if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
            echo -e "${RED}      Frontend failed to start. Check logs above.${NC}"
            exit 1
        fi
        sleep 1
    done
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Backend:  ${NC}http://localhost:8000"
echo -e "${GREEN}  Frontend: ${NC}http://localhost:${FRONTEND_PORT}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  Press Ctrl+C to stop both servers${NC}"
echo ""

if [ "$FRONTEND_REUSED" -eq 1 ]; then
    wait "$BACKEND_PID"
else
    wait
fi
