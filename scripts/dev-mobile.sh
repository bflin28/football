#!/bin/bash
# dev-mobile.sh — Start both backend and frontend for mobile testing
# Usage: ./scripts/dev-mobile.sh

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "  Starting Mobile Dev Environment"
echo "========================================"

# Start Flask backend
echo ""
echo "[1/2] Starting Flask backend on 0.0.0.0:5000..."
cd "$ROOT_DIR/nfl-game-simulator/backend"
python app.py &
BACKEND_PID=$!
sleep 2

# Start Vite frontend
echo "[2/2] Starting Vite frontend on 0.0.0.0:5173..."
cd "$ROOT_DIR/nfl-game-simulator/frontend"
npx vite --host 0.0.0.0 &
FRONTEND_PID=$!
sleep 2

# Get local IP address
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ipconfig getifaddr en0 2>/dev/null || echo "localhost")

echo ""
echo "========================================"
echo "  Mobile Testing Ready!"
echo ""
echo "  Frontend: http://${LOCAL_IP}:5173"
echo "  Backend:  http://${LOCAL_IP}:5000"
echo ""
echo "  Open the Frontend URL on your phone"
echo "  (must be on the same Wi-Fi network)"
echo ""
echo "  Press Ctrl+C to stop both servers"
echo "========================================"
echo ""

# Cleanup both processes on exit
cleanup() {
    echo ""
    echo "Shutting down servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

# Wait for either process to exit
wait
