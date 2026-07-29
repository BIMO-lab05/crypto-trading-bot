# Phase 14 CR-01 fix: multi-stage build (was single-stage `COPY dist`).
#
# The previous single-stage Dockerfile assumed the host had run `npm run
# build` before `docker compose build`. In CI (fresh checkout) `dist/` is
# gitignored and absent, so the COPY either failed or silently picked up
# a stale BuildKit layer. This multi-stage variant produces `dist/` inside
# the build image, removing the dependency on host-side artifacts.
#
# Stage 1: build the production bundle with the same Node version the CI
# `Setup Node` step uses (20). Stage 2: serve via nginx:alpine as before.

# ---------------- Build stage ----------------
FROM node:20-alpine AS build

WORKDIR /app

# Copy lockfile + package.json first so layer cache is reused on src-only edits.
COPY package.json package-lock.json ./
# Prefer the reproducible ci install; fall back to npm install when the lock
# file is momentarily out of sync with package.json (the fallback updates the
# lock inside the image layer only). Added 2026-07-29 alongside the
# eslint-plugin-react-hooks devDependency, whose lock entry appears after the
# next host `npm install`.
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

# Copy the rest of the frontend source and produce dist/.
COPY . .
RUN npm run build

# ---------------- Runtime stage ----------------
FROM nginx:alpine

# Remove default nginx configuration
RUN rm -rf /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the bundle produced in the build stage. No host-side dist/ required.
COPY --from=build /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
