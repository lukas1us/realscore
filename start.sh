#!/usr/bin/env bash
# Start RealScore CZ – backend (FastAPI) + frontend (Streamlit)
# Usage: ./start.sh

set -e
cd "$(dirname "$0")"

# Load .env so DATABASE_URL etc. are available
if [ -f .env ]; then
    set -a; source .env; set +a
fi

# Prefer local venv if it exists
if [ -f .venv/bin/uvicorn ]; then
    UVICORN=".venv/bin/uvicorn"
    STREAMLIT=".venv/bin/streamlit"
else
    UVICORN="uvicorn"
    STREAMLIT="streamlit"
fi

# Colours for log prefixes
RED='\033[0;31m'
BLUE='\033[0;34m'
RESET='\033[0m'

# Kill both child processes on Ctrl+C / script exit
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "Zastavuji procesy..."
    [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
    wait 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# Start backend
$UVICORN backend.main:app --reload --host 0.0.0.0 --port 8000 2>&1 \
    | sed "s/^/$(printf "${RED}[backend] ${RESET}")/" &
BACKEND_PID=$!

# Give backend a moment to bind the port before starting frontend
sleep 1

# Start frontend
$STREAMLIT run frontend/app.py --server.port 8501 2>&1 \
    | sed "s/^/$(printf "${BLUE}[frontend]${RESET}")/" &
FRONTEND_PID=$!

echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:8501"
echo "Ctrl+C pro zastavení"
echo ""

wait
