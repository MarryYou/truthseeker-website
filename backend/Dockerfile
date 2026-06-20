# ── 阶段 1: 安装依赖 ──────────────────────────────────────────
FROM python:3.14-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev && \
    pip uninstall -y uv && \
    rm -rf /root/.cache /tmp/*

# ── 阶段 2: 运行 ──────────────────────────────────────────────
FROM python:3.14-slim

# 创建非 root 用户
RUN groupadd --system --gid 1000 app && \
    useradd --system --uid 1000 --gid app --home-dir /app app

WORKDIR /app

# 复制虚拟环境并清理缓存文件（减少攻击面）
COPY --from=builder --chown=app:app /app/.venv /app/.venv
RUN find /app/.venv -type f \( -name '*.pyc' -o -name '*.whl' \) -delete && \
    rm -rf /app/.venv/cache /root/.cache /tmp/*
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 复制源码
COPY --chown=app:app backend/ /app/backend/

USER app

CMD ["uvicorn", "backend.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
