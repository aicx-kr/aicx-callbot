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
# next.config.js 의 rewrites BACKEND_URL (server-side, SSR / API proxy) 만 빌드 시 박는다.
# 클라이언트 측은 backendWsUrl() 이 same-origin 으로 동작 — NEXT_PUBLIC_BACKEND_URL 굳이 안 박음.
# 박으면 그 값이 우선해 deploy URL 미스매치 (예: ws://localhost:8080) 위험 (PR #16 fallback 무력화).
ARG BACKEND_URL=http://localhost:8080
ENV BACKEND_URL=$BACKEND_URL
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
