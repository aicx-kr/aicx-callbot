FROM node:20-alpine AS base
WORKDIR /app
RUN corepack enable pnpm

# 1. 의존성 설치
FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# 2. 빌드 (Next.js standalone)
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.js 의 rewrites BACKEND_URL (server-side) +
# 클라이언트 코드의 NEXT_PUBLIC_BACKEND_URL (WebSocket 직접 호출) 둘 다 빌드 시 평가.
# → workflow build-args 로 환경별 backend URL 주입
ARG BACKEND_URL=http://localhost:8765
ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8765
ENV BACKEND_URL=$BACKEND_URL
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# 3. 런타임 (standalone server)
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Next.js standalone output — 자체 node_modules 포함된 최소 server
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
