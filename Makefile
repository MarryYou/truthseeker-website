.PHONY: deploy up down logs clean

# ── 部署 ─────────────────────────────────────────────────────────────────────

deploy:  ## 一键构建并启动（Nginx 入口 :80，无需宿主机依赖）
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
