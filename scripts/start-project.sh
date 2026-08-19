#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
BUILD_FLAG="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

COMPOSE_FILES=(-f docker-compose.yml)
PROFILE_ARGS=()
SERVICES=()

init_config_file() {
  local target="$1"
  local example="$2"
  if [[ ! -f "${target}" && -f "${example}" ]]; then
    cp "${example}" "${target}"
    echo "已从示例生成配置：${target}，请填入大模型 API Key 后即可体验。"
  fi
}

init_config_file ".env" ".env.example"
init_config_file "config/servers.yml" "config/servers.example.yml"

case "${MODE}" in
  full)
    PROFILE_ARGS=(--profile full)
    ;;
  backend)
    SERVICES=(mysql rustfs etcd milvus redis ragent-api)
    ;;
  *)
    echo "未知模式：${MODE}" >&2
    echo "可选：full | backend" >&2
    exit 1
    ;;
esac

ARGS=("${COMPOSE_FILES[@]}" "${PROFILE_ARGS[@]}" up -d)
if [[ "${BUILD_FLAG}" == "--build" || "${BUILD_FLAG}" == "-Build" ]]; then
  ARGS+=(--build)
fi
ARGS+=("${SERVICES[@]}")

docker compose "${ARGS[@]}"

echo "========================================="
echo "  Ragent Job Agent Startup Complete"
echo "========================================="
echo "后端 API: http://localhost:8000/api/health"
echo "API 文档: http://localhost:8000/docs"
if [[ "${MODE}" == "full" ]]; then
  echo "前端控制台: http://localhost/"
  echo "求职对话台: http://localhost/chat"
  echo "智能体评测: http://localhost/admin/evaluations"
fi
