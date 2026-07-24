# syntax=docker/dockerfile:1

# ---- build stage ----
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

ENV BIREC_OUT_DIR=/rec \
    BIREC_LOG_DIR=/var/log/birec
VOLUME ["/rec", "/root/.birec", "/var/log/birec"]

EXPOSE 2233
ENTRYPOINT ["birec"]
CMD ["--host", "0.0.0.0", "--port", "2233"]
