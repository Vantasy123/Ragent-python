#!/bin/bash
# Docker 部署测试脚本

set -e  # 遇到错误立即退出

echo "========================================="
echo "  Ragent-Python Docker 部署测试"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker 是否安装
check_docker() {
    echo -e "${YELLOW}检查 Docker 环境...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker 未安装，请先安装 Docker${NC}"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ Docker Compose 未安装，请先安装 Docker Compose${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Docker 环境检查通过${NC}"
    echo ""
}

# 停止并清理旧容器
cleanup() {
    echo -e "${YELLOW}清理旧容器...${NC}"
    docker-compose down -v 2>/dev/null || true
    echo -e "${GREEN}✅ 清理完成${NC}"
    echo ""
}

# 构建镜像
build() {
    echo -e "${YELLOW}构建 Docker 镜像...${NC}"
    docker-compose build --no-cache
    echo -e "${GREEN}✅ 镜像构建完成${NC}"
    echo ""
}

# 启动服务
start() {
    echo -e "${YELLOW}启动服务...${NC}"
    docker-compose up -d
    echo -e "${GREEN}✅ 服务启动完成${NC}"
    echo ""
}

# 等待服务就绪
wait_for_service() {
    echo -e "${YELLOW}等待服务就绪...${NC}"
    
    max_attempts=30
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ 服务已就绪 (${attempt}/${max_attempts})${NC}"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo -e "\n${RED}❌ 服务启动超时${NC}"
    docker-compose logs ragent-api
    return 1
}

# 运行健康检查
health_check() {
    echo -e "${YELLOW}运行健康检查...${NC}"
    
    # API 健康检查
    response=$(curl -s http://localhost:8000/api/health)
    if echo "$response" | grep -q "ok"; then
        echo -e "${GREEN}✅ API 健康检查通过${NC}"
    else
        echo -e "${RED}❌ API 健康检查失败${NC}"
        return 1
    fi
    
    # 数据库连接检查
    if docker-compose exec -T postgres pg_isready > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 数据库连接正常${NC}"
    else
        echo -e "${RED}❌ 数据库连接失败${NC}"
        return 1
    fi
    
    echo ""
}

# 显示服务状态
show_status() {
    echo -e "${YELLOW}服务状态:${NC}"
    docker-compose ps
    echo ""
    
    echo -e "${YELLOW}资源使用:${NC}"
    docker stats --no-stream
    echo ""
}

# 显示访问信息
show_access_info() {
    echo "========================================="
    echo -e "${GREEN}  部署成功！${NC}"
    echo "========================================="
    echo ""
    echo "📊 API 文档: http://localhost:8000/docs"
    echo "💚 健康检查: http://localhost:8000/api/health"
    echo ""
    echo "常用命令:"
    echo "  查看日志:     docker-compose logs -f"
    echo "  停止服务:     docker-compose down"
    echo "  重启服务:     docker-compose restart"
    echo "  进入容器:     docker-compose exec ragent-api bash"
    echo ""
}

# 主流程
main() {
    check_docker
    cleanup
    build
    start
    wait_for_service
    health_check
    show_status
    show_access_info
}

# 执行主流程
main
