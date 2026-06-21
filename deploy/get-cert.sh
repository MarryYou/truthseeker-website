#!/bin/bash
# ── 获取 Let's Encrypt 真实 SSL 证书 ──────────────────────────────────────────
# 前置条件:
#   1. 已运行 ./deploy/init-ssl.sh <域名>
#   2. nginx 正在运行 (docker compose up -d nginx)
#   3. 域名已解析到本机
# 用法: ./deploy/get-cert.sh <你的域名>
set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    echo "用法: $0 <你的域名>"
    exit 1
fi

EMAIL="${CERTBOT_EMAIL:-admin@${DOMAIN}}"

echo "==> 检查 nginx 是否运行..."
if ! docker compose ps nginx | grep -q "Up"; then
    echo "  nginx 未运行，正在启动..."
    docker compose up -d nginx
    sleep 3
fi

echo "==> 申请 Let's Encrypt 证书（域名: $DOMAIN）..."
docker compose run --rm certbot \
    certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --cert-name truthseeker \
    -d "$DOMAIN"

echo "==> 重载 nginx 以加载新证书..."
docker compose exec nginx nginx -s reload 2>/dev/null || docker compose restart nginx

echo ""
echo "  ✓ SSL 证书已就绪！"
echo "  访问: https://$DOMAIN"
echo "  certbot 容器每 12 小时自动检查续期"
echo "  手动续期测试: docker compose run --rm certbot renew --dry-run"
