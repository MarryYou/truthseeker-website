# ⚠️ 本文件仅供本地开发调试（Development）使用。
# 生产环境/Docker 容器中已通过 uvicorn 命令直接启动，无需此入口。
from __future__ import annotations
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
