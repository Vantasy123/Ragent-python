#!/bin/bash

echo "========================================="
echo "  Ragent-Python Docker 部署状态监控"
echo "========================================="
echo ""

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker Desktop"
    exit 1
fi

echo "✅ Docker 正在运行"
echo ""

# 显示容器状态
echo "📊 容器状态:"
echo "-----------------------------------------"
docker-compose ps

echo ""
echo "🔍 服务健康检查:"
echo "-----------------------------------------"

# 检查 PostgreSQL
if docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
    echo "✅ PostgreSQL: 正常"
else
    echo "⏳ PostgreSQL: 启动中..."
fi

# 检查 Backend API
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✅ Backend API: 正常"
else
    echo "⏳ Backend API: 启动中..."
fi

# 检查 Frontend
if curl -s http://localhost:80 > /dev/null 2>&1; then
    echo "✅ Frontend: 正常"
else
    echo "⏳ Frontend: 启动中..."
fi

echo ""
echo "🌐 访问地址:"
echo "-----------------------------------------"
echo "  前端界面: http://localhost"
echo "  API 文档: http://localhost:8000/docs"
echo "  健康检查: http://localhost:8000/api/health"
echo ""

echo "📝 常用命令:"
echo "-----------------------------------------"
echo "  查看日志:   docker-compose logs -f"
echo "  停止服务:   docker-compose down"
echo "  重启服务:   docker-compose restart"
echo "  查看状态:   docker-compose ps"
echo ""
