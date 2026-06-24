#!/bin/bash

# HR Recruitment Agent — Start all services
# Usage: ./start.sh

echo "=========================================="
echo "  Red Hat — HR Recruitment Agent"
echo "=========================================="

# Activate Python virtual environment
source .venv/bin/activate

# Start MLflow (port 5001)
echo "Starting MLflow server on :5001..."
mlflow server --port 5001 &> /dev/null &
MLFLOW_PID=$!

# Start Dashboard API (port 8001)
echo "Starting Dashboard API on :8001..."
python dashboard/api.py &> /dev/null &
API_PID=$!

# Start Dashboard frontend (port 3000)
echo "Starting Dashboard UI on :3000..."
(cd dashboard && npm run dev) &> /dev/null &
DASH_PID=$!

# Start Chainlit chat (port 8000)
echo "Starting Chainlit chat on :8000..."
chainlit run app.py &> /dev/null &
CHAT_PID=$!

sleep 3

echo ""
echo "=========================================="
echo "  All services running:"
echo "  Dashboard:  http://localhost:3000"
echo "  Chat:       http://localhost:8000"
echo "  API:        http://localhost:8001"
echo "  MLflow:     http://localhost:5001"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop all services"

# Trap Ctrl+C to kill all background processes
trap "echo ''; echo 'Shutting down...'; kill $MLFLOW_PID $API_PID $DASH_PID $CHAT_PID 2>/dev/null; echo 'Done.'; exit 0" INT

# Wait for any process to exit
wait
