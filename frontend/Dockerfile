# --- Build stage --------------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /app
# corepack reads the pnpm version from package.json (packageManager)
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Git-SHA baked into the SPA at build time (CI passes GIT_SHA); nuxt exposes it
# via runtimeConfig.public.gitSha. Empty in local dev.
ARG GIT_SHA=""
ENV GIT_SHA=$GIT_SHA
RUN pnpm generate

# --- Runtime: static SPA via nginx (unprivileged, port 8080) -------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/.output/public /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
