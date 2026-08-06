# syntax=docker/dockerfile:1

# ---- frontend build stage ----
# 构建 SPA 产物（dist），随后拷入运行阶段由 FastAPI StaticFiles 托管（§12）。
FROM node:22-slim AS frontend

WORKDIR /app/frontend
ENV CI=true
RUN corepack enable

# 先装依赖（利用层缓存）：仅拷贝清单与锁文件。
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# 再拷源码并构建（tsc -b && vite build，产物在 dist/，资源为相对路径）。
COPY frontend/ ./
RUN pnpm build

# ---- python build stage ----
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv build --wheel --out-dir /dist

# ---- runtime stage ----
FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

# 前端产物：单镜像同时提供 API 与 UI（BIREC_STATIC_DIR 指向静态目录）。
COPY --from=frontend /app/frontend/dist /app/static

# BIREC_OUT_DIR/BIREC_LOG_DIR 走不通（Application 用 model_construct 绕过环境变量），
# 故路径必须经 CMD 显式传入，落到卷挂载点，否则录像写进容器临时目录、重启即丢。
WORKDIR /app
ENV BIREC_STATIC_DIR=/app/static
VOLUME ["/rec", "/root/.birec", "/var/log/birec"]

EXPOSE 2233
ENTRYPOINT ["birec"]
CMD ["--host", "0.0.0.0", "--port", "2233", \
     "--config", "/root/.birec/settings.toml", \
     "--output", "/rec", \
     "--log-dir", "/var/log/birec"]
