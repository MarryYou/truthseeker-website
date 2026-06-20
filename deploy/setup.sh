#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# TruthSeeker 部署脚本 — 用于 VPS 首次部署与更新
# 用法：
#   ./deploy/setup.sh              # 首次部署（交互式域名配置）
#   ./deploy/setup.sh --domain example.com  # 指定域名非交互部署
#   ./deploy/setup.sh --update              # 仅更新服务（不重设 SSL）
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# ── 颜色输出 ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${CYAN}══════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}══════════════════════════════════════════════════${NC}\n"; }


# ── 参数解析 ─────────────────────────────────────────────────────────────────
DOMAIN=""
UPDATE_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --update) UPDATE_ONLY=true; shift ;;
    *) log_error "未知参数: $1"; exit 1 ;;
  esac
done


# ── 1. 前置检查 ──────────────────────────────────────────────────────────────
log_step "前置检查"

# Docker
if ! command -v docker &>/dev/null; then
  log_error "Docker 未安装。请先安装 Docker：https://docs.docker.com/engine/install/"
  exit 1
fi
log_info "Docker $(docker --version)"

# Docker Compose
if ! docker compose version &>/dev/null; then
  log_error "Docker Compose v2 未安装。"
  exit 1
fi
log_info "Docker Compose $(docker compose version)"

# 项目目录结构
if [[ ! -f "docker-compose.yml" ]]; then
  log_error "请在项目根目录运行此脚本。"
  exit 1
fi


# ── 2. 环境变量配置 ─────────────────────────────────────────────────────────
log_step "环境变量配置"

if [[ ! -f ".env" ]]; then
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    log_info "已从 .env.example 创建 .env 文件"
  else
    log_error ".env.example 不存在，请手动创建 .env 文件"
    exit 1
  fi
fi

# 如果 JWT_SECRET_KEY 为空，自动生成
if grep -q "^JWT_SECRET_KEY=$" .env; then
  NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null || \
            openssl rand -base64 48 2>/dev/null || \
            head -c 64 /dev/urandom | base64)
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s/^JWT_SECRET_KEY=$/JWT_SECRET_KEY=$NEW_KEY/" .env
  else
    sed -i "s/^JWT_SECRET_KEY=$/JWT_SECRET_KEY=$NEW_KEY/" .env
  fi
  log_info "已自动生成 JWT_SECRET_KEY"
fi

# 如果 POSTGRES_PASSWORD 为空，自动生成
if grep -q "^POSTGRES_PASSWORD=$" .env; then
  PG_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))" 2>/dev/null || \
            openssl rand -base64 32 2>/dev/null || \
            head -c 32 /dev/urandom | base64)
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$PG_PASS/" .env
  else
    sed -i "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$PG_PASS/" .env
  fi
  log_info "已自动生成 POSTGRES_PASSWORD"
fi

# 加载环境变量
set -a && source .env && set +a
log_info ".env 文件已加载"


# ── 3. 首次域名配置与 SSL（非 --update 模式） ─────────────────────────────
if [[ "$UPDATE_ONLY" == "false" ]]; then

  # ── 3a. 域名 ────────────────────────────────────────────────────────────────
  log_step "域名配置"

  if [[ -z "$DOMAIN" ]]; then
    read -r -p "请输入部署域名（留空 = 仅 HTTP，无 SSL）: " DOMAIN
  fi

  if [[ -n "$DOMAIN" ]]; then
    log_info "域名: $DOMAIN"

    # 更新 nginx 配置中的 server_name
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "s/server_name _;/server_name $DOMAIN;/g" nginx/default.conf
    else
      sed -i "s/server_name _;/server_name $DOMAIN;/g" nginx/default.conf
    fi
    log_info "Nginx server_name 已更新为 $DOMAIN"

    # 更新 .env 中的 APP_URL
    if [[ "$(uname)" == "Darwin" ]]; then
      sed -i '' "s|^APP_URL=.*|APP_URL=https://$DOMAIN|" .env 2>/dev/null || \
        echo "APP_URL=https://$DOMAIN" >> .env
    else
      sed -i "s|^APP_URL=.*|APP_URL=https://$DOMAIN|" .env 2>/dev/null || \
        echo "APP_URL=https://$DOMAIN" >> .env
    fi
  fi

  # ── 3b. SSL 证书（如果有域名） ──────────────────────────────────────────────
  if [[ -n "$DOMAIN" ]]; then
    log_step "SSL 证书申请 (Let's Encrypt)"

    # 先让 Nginx 启动（仅 HTTP），为 ACME challenge 做准备
    log_info "启动 Nginx 以完成 ACME challenge..."
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d nginx
    sleep 3

    # 申请证书
    docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
      certbot certonly --webroot -w /var/www/certbot \
      -d "$DOMAIN" \
      --cert-name truthseeker \
      --agree-tos \
      --non-interactive \
      --register-unsafely-without-email 2>&1 || {
        log_warn "SSL 证书申请失败，将继续使用 HTTP。"
        log_warn "检查域名 DNS 是否正确指向本机 IP。"
        log_warn "稍后可手动重试: docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot certonly --webroot -w /var/www/certbot -d $DOMAIN --cert-name truthseeker"
      }

    if docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot certificates 2>&1 | grep -q "Certificate Name: truthseeker"; then
      log_info "SSL 证书申请成功！"
    fi
  else
    log_warn "未设置域名，将使用 HTTP 模式（仅端口 80）。"
    log_warn "如需 SSL，稍后可运行: ./deploy/setup.sh --domain yourdomain.com"
  fi
fi


# ── 4. 构建并启动 ────────────────────────────────────────────────────────────
log_step "构建 Docker 镜像"

export DOCKER_BUILDKIT=1
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
log_info "镜像构建完成"


log_step "启动服务"

# 先运行数据库迁移
log_info "执行数据库迁移..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrations 2>&1 || log_warn "数据库迁移失败，请检查日志"

# 启动生产栈（2 个 Worker）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=2
log_info "服务已启动"


# ── 5. 状态检查 ──────────────────────────────────────────────────────────────
log_step "服务状态检查"

sleep 5

echo ""
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
echo ""

# 健康检查
HEALTHY=true
for SERVICE in postgres redis backend frontend nginx; do
  STATUS=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format json "$SERVICE" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health','') if isinstance(d,dict) else '')" 2>/dev/null || echo "unknown")
  if [[ "$STATUS" != "healthy" ]]; then
    log_warn "$SERVICE 状态: $STATUS"
    HEALTHY=false
  fi
done

if [[ "$HEALTHY" == "true" ]]; then
  echo ""
  log_info "✅ 所有服务健康！"
  if [[ -n "${DOMAIN:-}" ]]; then
    log_info "   访问: https://$DOMAIN"
  else
    log_info "   访问: http://<服务器IP>"
  fi
  echo ""
  log_info "管理命令:"
  log_info "   查看日志:  docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f"
  log_info "   停止服务:  docker compose -f docker-compose.yml -f docker-compose.prod.yml down"
  log_info "   更新服务:  ./deploy/setup.sh --update"
  echo ""
else
  log_warn "部分服务尚未就绪，请检查日志：docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f"
fi
