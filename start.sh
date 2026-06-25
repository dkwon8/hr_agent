#!/bin/bash

# HR Recruitment Agent — Start all services
# Usage: ./start.sh

echo "=========================================="
echo "  Red Hat — HR Recruitment Agent"
echo "=========================================="

# Activate Python virtual environment
source .venv/bin/activate

# Create logs directory
mkdir -p logs

# Kill any leftover processes on our ports
for port in 5001 8001 3000 8000; do
    pid=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        echo "Killing existing process on port $port (PID $pid)"
        kill $pid 2>/dev/null || true
        sleep 1
    fi
done

# Helper: wait for a port to be ready
wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=$3
    for i in $(seq 1 $max_wait); do
        if curl -s http://localhost:$port > /dev/null 2>&1; then
            echo "  $name is ready on :$port"
            return 0
        fi
        sleep 1
    done
    echo "  WARNING: $name did not start on :$port (check logs/$name.log)"
    return 0
}

# 1. Start MLflow (port 5001) — must be ready before other services
echo ""
echo "Starting MLflow server..."
mlflow server --port 5001 >> logs/mlflow.log 2>&1 &
MLFLOW_PID=$!
wait_for_port 5001 "mlflow" 15

# 2. Start Dashboard API (port 8001)
echo "Starting Dashboard API..."
python dashboard/api.py >> logs/api.log 2>&1 &
API_PID=$!
wait_for_port 8001 "api" 10

# 3. Start Dashboard frontend (port 3000)
echo "Starting Dashboard UI..."
(cd dashboard && npm run dev) >> logs/dashboard.log 2>&1 &
DASH_PID=$!
wait_for_port 3000 "dashboard" 15

# 4. Start Chainlit chat (port 8000)
echo "Starting Chainlit chat..."
chainlit run app.py >> logs/chainlit.log 2>&1 &
CHAT_PID=$!
wait_for_port 8000 "chainlit" 10

# Status summary
echo ""
echo "=========================================="
echo "  Services:"

check_service() {
    local port=$1
    local name=$2
    local url=$3
    if curl -s http://localhost:$port > /dev/null 2>&1; then
        echo "  [OK]   $name  $url"
    else
        echo "  [FAIL] $name  $url  (see logs/)"
    fi
}

check_service 5001 "MLflow    " "http://localhost:5001"
check_service 8001 "API       " "http://localhost:8001"
check_service 3000 "Dashboard " "http://localhost:3000"
check_service 8000 "Chat      " "http://localhost:8000"

echo ""
echo "  Logs:  tail -f logs/<service>.log"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop all services"

# Trap Ctrl+C to kill all background processes
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $MLFLOW_PID $API_PID $DASH_PID $CHAT_PID 2>/dev/null
    wait $MLFLOW_PID $API_PID $DASH_PID $CHAT_PID 2>/dev/null
    echo "Done."
    exit 0
}
trap cleanup INT TERM

# Wait for any process to exit
wait
