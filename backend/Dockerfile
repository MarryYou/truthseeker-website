# syntax=docker/dockerfile:1
# ── 宿主机预构建 .venv，Docker build 纯 COPY，零网络下载 ────────
# 前置步骤（在 CVM 上跑一次，3 分钟）：
#   uv sync --frozen --no-install-project --no-dev
# 然后正常 docker compose build，每次秒过
FROM python:3.14-slim

# apt 源加速
ARG APT_MIRROR=mirrors.cloud.tencent.com
RUN sed -i "s/deb.debian.org/${APT_MIRROR}/g" /etc/apt/sources.list.d/debian.sources && \
    sed -i "s/security.debian.org/${APT_MIRROR}/g" /etc/apt/sources.list.d/debian.sources

# 创建非 root 用户
RUN groupadd --system --gid 1000 app && \
    useradd --system --uid 1000 --gid app --home-dir /app app

WORKDIR /app

# 直接复制宿主机预构建的完整虚拟环境（不再在容器内 uv sync）
COPY --chown=app:app .venv /app/.venv

# 修正 shebang：uv 创建的脚本写死了宿主机路径（如 /home/ubuntu/.../）
# 容器内 .venv 在 /app/.venv，需要把所有脚本第一行的 Python 路径改过来
RUN find /app/.venv/bin -type f -exec sh -c \
    'head -1 "$1" 2>/dev/null | grep -q "^#!/" && sed -i "1s|^#!/.*\.venv/bin/python[0-9.]*|#!/app/.venv/bin/python|" "$1"' _ {} \; && \
    rm -f /app/.venv/bin/python /app/.venv/bin/python3 /app/.venv/bin/python3.14 && \
    ln -s /usr/local/bin/python3 /app/.venv/bin/python && \
    ln -s /usr/local/bin/python3 /app/.venv/bin/python3 && \
    ln -s /usr/local/bin/python3 /app/.venv/bin/python3.14

# 清理缓存文件（减少攻击面）
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
