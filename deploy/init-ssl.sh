#!/bin/bash
# ── SSL 占位证书生成 ──────────────────────────────────────────────────────────
# 让 nginx 能直接用 HTTPS 启动（自签名占位），后续用 certbot 替换为真证书。
# 用法: ./deploy/init-ssl.sh <你的域名>
# 示例: ./deploy/init-ssl.sh truthseeker.example.com
set -euo pipefail

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    echo "用法: $0 <你的域名>"
    echo "示例: $0 truthseeker.example.com"
    exit 1
fi

CERT_DIR="./certbot/conf/live/truthseeker"
WWW_DIR="./certbot/www/.well-known/acme-challenge"

echo "==> 创建目录结构..."
mkdir -p "$CERT_DIR"
mkdir -p "$WWW_DIR"

echo "==> 生成自签名占位证书（域名: $DOMAIN）..."
openssl req -x509 -nodes -days 90 \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN"

echo ""
echo "  ✓ 占位证书已生成: $CERT_DIR/"
echo "  现在可以启动服务: make deploy"
echo ""
echo "  获取真实 Let's Encrypt 证书:"
echo "    1. 确保域名 $DOMAIN 已解析到本机"
echo "    2. 运行: ./deploy/get-cert.sh $DOMAIN"
