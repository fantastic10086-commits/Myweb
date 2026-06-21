#!/bin/bash
# PI Management System — One-click startup
PORT=5001
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_ROOT"

# Kill existing process on port (if lsof or fuser available)
PID=$(lsof -ti :$PORT 2>/dev/null || fuser $PORT/tcp 2>/dev/null | awk '{print $1}')
if [ -n "$PID" ]; then
    kill -9 $PID 2>/dev/null && sleep 1
    echo "Killed PID $PID on port $PORT"
fi

echo "Starting Flask on port $PORT ..."
nohup python3 -m flask run --host=0.0.0.0 --port=$PORT > pi_manager.log 2>&1 &
echo $! > pi_manager.pid

sleep 2
echo "Server PID: $(cat pi_manager.pid)"
echo "Access at http://<NAS_IP>:$PORT"
echo "Logs: tail -f $APP_ROOT/pi_manager.log"
