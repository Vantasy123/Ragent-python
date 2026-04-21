#!/bin/bash

echo "========================================"
echo "  Ragent Python Frontend 启动脚本"
echo "========================================"
echo ""

cd frontend

# 检查 node_modules 是否存在
if [ ! -d "node_modules" ]; then
    echo "[1/2] 安装依赖..."
    npm install
    if [ $? -ne 0 ]; then
        echo "[错误] 依赖安装失败"
        exit 1
    fi
    echo "[成功] 依赖安装完成"
    echo ""
fi

echo "[2/2] 启动开发服务器..."
echo ""
echo "前端地址: http://localhost:5173"
echo "后端代理: http://localhost:8000"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

npm run dev
