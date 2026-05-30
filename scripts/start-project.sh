#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-ops}"
BUILD_FLAG="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.ops.yml)
PROFILE_ARGS=()
SERVICES=()

init_config_file() {
  local target="$1"
  local example="$2"
  if [[ ! -f "${target}" && -f "${example}" ]]; then
    cp "${example}" "${target}"
    echo "已从示例生成配置：${target}，请按个人环境修改后再用于生产。"
  fi
}

init_config_file ".env" ".env.example"
init_config_file "config/servers.yml" "config/servers.example.yml"
init_config_file "config/monitoring.yml" "config/monitoring.example.yml"

case "${MODE}" in
  full|ops)
    PROFILE_ARGS=(--profile full)
    ;;
  backend|ops-backend)
    SERVICES=(mysql rustfs etcd milvus redis ragent-api ops-test-service)
    ;;
  monitoring)
    COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.monitoring.yml)
    PROFILE_ARGS=(--profile full)
    ;;
  monitoring-backend)
    COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.monitoring.yml)
    SERVICES=(mysql rustfs etcd milvus redis ragent-api ops-test-service prometheus alertmanager grafana node-exporter cadvisor redis-exporter mysqld-exporter blackbox-exporter)
    ;;
  *)
    echo "未知模式：${MODE}" >&2
    echo "可选：ops | ops-backend | monitoring | monitoring-backend" >&2
    exit 1
    ;;
esac

ARGS=("${COMPOSE_FILES[@]}" "${PROFILE_ARGS[@]}" up -d)
if [[ "${BUILD_FLAG}" == "--build" || "${BUILD_FLAG}" == "-Build" ]]; then
  ARGS+=(--build)
fi
ARGS+=("${SERVICES[@]}")

docker compose "${ARGS[@]}"

echo "后端健康检查：http://localhost:8000/api/health"
if [[ "${MODE}" == "ops" || "${MODE}" == "full" || "${MODE}" == "monitoring" ]]; then
  echo "前端入口：http://localhost/"
fi
if [[ "${MODE}" == monitoring* ]]; then
  echo "Prometheus：http://localhost:9090/"
  echo "Alertmanager：http://localhost:9093/"
  echo "Grafana：http://localhost:3001/  admin/admin"
fi
