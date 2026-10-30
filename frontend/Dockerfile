# Production web edge: build the React SPA, then serve it with Caddy.
# The Caddyfile (HTTPS, /api proxy, SSE, headers) is mounted read-only by Compose.
FROM node:20-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Same-origin deployment: the SPA calls /api/v1 on its own origin.
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

FROM caddy:2.8-alpine AS runtime
COPY --from=build /web/dist /srv/web
