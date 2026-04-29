# 多阶段构建：先安装 Python 依赖，再复制到运行镜像。
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装编译型依赖，主要用于部分 Python 包构建 wheel。
RUN apt-get update -o Acquire::Retries=3 && apt-get install -y --fix-missing \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Docker CLI 单独取自官方镜像，供 ops profile 下的运维 Agent 使用。
FROM docker:27-cli AS docker-cli

FROM python:3.11-slim

WORKDIR /app

# curl 用于健康检查。
RUN apt-get update -o Acquire::Retries=3 && apt-get install -y --fix-missing \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .

# 默认使用非 root 用户运行；ops profile 如需 Docker socket 权限由 compose override 处理。
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
