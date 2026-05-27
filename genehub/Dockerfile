ARG NODE_IMAGE=node:22-alpine

FROM ${NODE_IMAGE} AS base
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /app

# --- Install dependencies ---
FROM base AS deps
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/types/package.json packages/types/
COPY packages/sdk/typescript/package.json packages/sdk/typescript/
COPY packages/registry/package.json packages/registry/
COPY packages/web/package.json packages/web/
RUN pnpm install --frozen-lockfile

# --- Build all packages ---
FROM base AS build
COPY --from=deps /app/ /app/
COPY tsconfig.base.json ./
COPY packages/types/ packages/types/
COPY packages/sdk/typescript/ packages/sdk/typescript/
COPY packages/registry/ packages/registry/
COPY packages/web/ packages/web/
RUN pnpm --filter @nodeskai/genehub-types build \
 && pnpm --filter @nodeskai/genehub-sdk build \
 && pnpm --filter @nodeskai/genehub-registry build \
 && pnpm --filter @nodeskai/genehub-web build

# --- Production image (zero dependencies, fully bundled) ---
FROM ${NODE_IMAGE}
WORKDIR /app

COPY --from=build /app/packages/registry/dist/ ./dist/
COPY --from=build /app/packages/registry/drizzle/ ./drizzle/
COPY --from=build /app/packages/web/dist ./public

ENV NODE_ENV=production
ENV PORT=3000
ENV PUBLIC_DIR=./public
ENV GENEHUB_MIGRATIONS_DIR=./drizzle
EXPOSE 3000

CMD ["node", "dist/index.js"]
