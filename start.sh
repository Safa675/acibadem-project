#!/usr/bin/env bash
# start.sh — Launch both FastAPI backend and Next.js frontend
# Usage: ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  İLAY — AI Clinical Risk Intelligence${NC}"
echo -e "${CYAN}  ACUHIT 2026 — Acıbadem University${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID 2>/dev/null
    wait $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}Done.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ── Backend (FastAPI) ─────────────────────────────────────────────────────
echo -e "${GREEN}[1/2]${NC} Starting FastAPI backend on :8000..."

cd "$SCRIPT_DIR"

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to be ready
echo -e "${YELLOW}      Waiting for backend to initialize (loading pipeline)...${NC}"
for i in $(seq 1 120); do
    if curl -s http://localhost:8000/api/patients > /dev/null 2>&1; then
        echo -e "${GREEN}      Backend ready!${NC}"
        break
    fi
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "\033[0;31m      Backend failed to start. Check logs above.${NC}"
        exit 1
    fi
    sleep 2
done

# ── Frontend (Next.js) ────────────────────────────────────────────────────
echo -e "${GREEN}[2/2]${NC} Starting Next.js frontend on :3000..."

cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Backend:  ${NC}http://localhost:8000"
echo -e "${GREEN}  Frontend: ${NC}http://localhost:3000"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  Press Ctrl+C to stop both servers${NC}"
echo ""

wait
