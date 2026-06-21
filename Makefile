.PHONY: deploy up down logs clean sync-deps

# ── 依赖同步 ─────────────────────────────────────────────────────────────────

sync-deps:  ## 宿主机预构建 .venv（首次/依赖变更后执行一次，3 分钟）
	@echo "==> 在宿主机同步依赖（走腾讯云镜像）..."
	UV_LINK_MODE=copy uv sync --frozen --no-install-project --no-dev
	@echo "==> .venv 已就绪，现在 docker build 将直接 COPY 进镜像"

# ── 部署 ─────────────────────────────────────────────────────────────────────

deploy: sync-deps  ## 一键构建并启动（先 sync .venv，再 docker build）
	docker compose up --build -d
	@echo "────────────────────────────────────────────────────────"
	@echo "  TruthSeeker 已启动！"
	@echo "  访问地址: http://localhost"
	@echo "  API 文档: http://localhost/docs"
	@echo "  查看日志: make logs"
	@echo "  停止服务: make down"
	@echo "────────────────────────────────────────────────────────"

up:  ## 启动服务（增量构建）
	docker compose up -d

down:  ## 停止所有服务
	docker compose down

logs:  ## 跟踪所有服务日志
	docker compose logs -f

clean:  ## 停止并删除数据卷
	docker compose down -v
