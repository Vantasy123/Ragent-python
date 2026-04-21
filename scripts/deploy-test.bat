@echo off
REM Docker 部署测试脚本 (Windows)

echo =========================================
echo   Ragent-Python Docker 部署测试
echo =========================================
echo.

REM 检查 Docker 是否安装
echo [1/7] 检查 Docker 环境...
where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] Docker 未安装，请先安装 Docker
    pause
    exit /b 1
)

where docker-compose >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] Docker Compose 未安装，请先安装 Docker Compose
    pause
    exit /b 1
)

echo [成功] Docker 环境检查通过
echo.

REM 停止并清理旧容器
echo [2/7] 清理旧容器...
docker-compose down -v 2>nul
echo [成功] 清理完成
echo.

REM 构建镜像
echo [3/7] 构建 Docker 镜像...
docker-compose build --no-cache
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 镜像构建失败
    pause
    exit /b 1
)
echo [成功] 镜像构建完成
echo.

REM 启动服务
echo [4/7] 启动服务...
docker-compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 服务启动失败
    pause
    exit /b 1
)
echo [成功] 服务启动完成
echo.

REM 等待服务就绪
echo [5/7] 等待服务就绪...
set max_attempts=30
set attempt=1

:wait_loop
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/api/health >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [成功] 服务已就绪 (%attempt%/%max_attempts%)
    goto wait_done
)

set /a attempt+=1
if %attempt% LEQ %max_attempts% (
    echo|set /p=.
    goto wait_loop
)

echo.
echo [错误] 服务启动超时
docker-compose logs ragent-api
pause
exit /b 1

:wait_done
echo.

REM 运行健康检查
echo [6/7] 运行健康检查...
curl -s http://localhost:8000/api/health | findstr "ok" >nul
if %ERRORLEVEL% EQU 0 (
    echo [成功] API 健康检查通过
) else (
    echo [错误] API 健康检查失败
    pause
    exit /b 1
)

docker-compose exec -T postgres pg_isready >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [成功] 数据库连接正常
) else (
    echo [错误] 数据库连接失败
    pause
    exit /b 1
)
echo.

REM 显示服务状态
echo [7/7] 服务状态:
docker-compose ps
echo.

echo =========================================
echo   部署成功！
echo =========================================
echo.
echo 📊 API 文档: http://localhost:8000/docs
echo 💚 健康检查: http://localhost:8000/api/health
echo.
echo 常用命令:
echo   查看日志:     docker-compose logs -f
echo   停止服务:     docker-compose down
echo   重启服务:     docker-compose restart
echo   进入容器:     docker-compose exec ragent-api bash
echo.

pause
