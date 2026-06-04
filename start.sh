#!/bin/bash

cd "$(dirname "$0")/backend"

if [ ! -f ".env" ]; then
    echo "[警告] 未找到 .env 文件，请先配置环境变量"
    exit 1
fi

echo "========================================"
echo "  智能选股助手 - 启动后端服务"
echo "  地址: http://localhost:8000"
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo

python3 main.py
