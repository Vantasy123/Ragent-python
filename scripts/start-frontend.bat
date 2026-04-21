@echo off
echo ========================================
echo   Ragent Python Frontend 启动脚本
echo ========================================
echo.

cd frontend

REM 检查 node_modules 是否存在
if not exist "node_modules\" (
    echo [1/2] 安装依赖...
    call npm install
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    echo [成功] 依赖安装完成
    echo.
)

echo [2/2] 启动开发服务器...
echo.
echo 前端地址: http://localhost:5173
echo 后端代理: http://localhost:8000
echo.
echo 按 Ctrl+C 停止服务器
echo.

call npm run dev
