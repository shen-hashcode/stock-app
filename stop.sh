#!/bin/bash

cd "$(dirname "$0")/backend"

PID_FILE="app.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "[错误] 未找到 PID 文件，服务可能未启动"
    exit 1
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    rm -f "$PID_FILE"
    echo "服务已停止，PID: $PID"
else
    rm -f "$PID_FILE"
    echo "服务未在运行（进程已不存在），已清理 PID 文件"
fi