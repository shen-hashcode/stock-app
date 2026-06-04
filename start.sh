#!/bin/bash

cd "$(dirname "$0")/backend"

if [ ! -f ".env" ]; then
    echo "[警告] 未找到 .env 文件，请先配置环境变量"
    exit 1
fi

LOG_FILE="app.log"
PID_FILE="app.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[错误] 服务已在运行中，PID: $(cat "$PID_FILE")"
    exit 1
fi

nohup python3 main.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "智能选股助手已启动"
echo "  PID: $(cat "$PID_FILE")"
echo "  地址: http://localhost:8000"
echo "  日志: backend/$LOG_FILE"
echo "  停止: ./stop.sh"