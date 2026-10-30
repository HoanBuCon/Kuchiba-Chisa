FROM node:20-alpine AS base
WORKDIR /app
ENV NODE_ENV=production

FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund

FROM base AS runtime
COPY --from=deps /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src
COPY scripts ./scripts
USER node
CMD ["node", "src/index.js"]
