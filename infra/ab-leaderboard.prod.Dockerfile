# syntax=docker/dockerfile:1.7
# Production image for ab-leaderboard.
# Stage 1 builds the Vite SPA. Stage 2 serves the static bundle via nginx.

############################
# Stage 1: builder
############################
FROM node:20-alpine AS builder

# Bake API base into the static bundle. Vite inlines VITE_*/import.meta.env
# at build time, so this is the canonical handoff.
ARG AB_API_BASE_URL=/api/v1

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    CI=true

RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /app

# Workspace manifest, then the package itself.
COPY pnpm-workspace.yaml ./
COPY packages/ab-leaderboard/package.json packages/ab-leaderboard/pnpm-lock.yaml* packages/ab-leaderboard/

WORKDIR /app/packages/ab-leaderboard

# No lockfile is committed for the SPA right now (workspace pnpm-lock at root
# is empty for this package), so we deliberately allow resolution.
RUN pnpm install --frozen-lockfile=false

# Bring in the rest of the source AFTER deps cache layer.
COPY packages/ab-leaderboard/ ./

# Write the API base into .env.production so Vite picks it up.
RUN printf 'VITE_AB_API_BASE_URL=%s\n' "${AB_API_BASE_URL}" > .env.production \
    && printf 'AB_API_BASE_URL=%s\n' "${AB_API_BASE_URL}" >> .env.production

RUN pnpm build

############################
# Stage 2: runtime
############################
FROM nginx:1.27-alpine AS runtime

# Drop the default config; we ship our own SPA-aware one.
RUN rm -f /etc/nginx/conf.d/default.conf

COPY infra/nginx-spa.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/packages/ab-leaderboard/dist /usr/share/nginx/html

# wget is part of the busybox-alpine base, so the healthcheck has no extra deps.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O - http://localhost/ >/dev/null 2>&1 || exit 1

EXPOSE 80

# nginx official image already runs the master as root and workers as nginx user.
CMD ["nginx", "-g", "daemon off;"]
