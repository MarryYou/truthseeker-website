# 阶段 1: 安装依赖
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json yarn.lock ./
# 腾讯云 npm 镜像（容器内不继承宿主机 yarn 配置）
RUN yarn config set registry https://mirrors.cloud.tencent.com/npm/ && \
    yarn install --frozen-lockfile

# 阶段 2: 构建
FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
# 精确复制源码（不依赖 .dockerignore，避免 .env 等敏感文件意外进镜像）
COPY next.config.ts tsconfig.json postcss.config.mjs eslint.config.mjs package.json ./
COPY src/ ./src/
COPY public/ ./public/
# 注：前端源码不直接引用 LOGTO_* 环境变量，Logto OIDC 全由后端处理
# 构建时无需注入 Logto 凭据；运行时环境变量通过 docker-compose 注入
RUN yarn build

# 阶段 3: 运行
FROM node:22-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Next.js standalone 模式需要的权限
RUN groupadd --system --gid 1001 nodejs
RUN useradd --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]

# ── 阶段 4: 开发（基于 deps，源码由 volume 挂载，CMD 由 override 覆盖） ─
FROM deps AS dev
ENV NODE_ENV=development
# 注：实际 CMD 在 docker-compose.override.yml 中设为 "yarn dev"
