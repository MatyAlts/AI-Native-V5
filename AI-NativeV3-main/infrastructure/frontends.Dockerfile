# Multi-stage build de los 3 frontends + Nginx que los sirve.
#
# Stage 1: instala pnpm + dependencies del monorepo, buildea los 3 frontends
# Vite. Output: apps/web-{admin,teacher,student}/dist/.
#
# Stage 2: nginx:alpine sirviendo los 3 dist/ en paths separados, con proxy
# /api/ -> api-gateway:8000.
#
# Build context: root del repo (..). El compose pasa context: ../ para que
# el COPY pueda acceder al monorepo entero (workspace pnpm necesita lockfile
# y todos los packages/* compartidos).

# ─────────────────────────────────────────────────────────────────────
# Stage 1: builder
# ─────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

# pnpm via corepack (incluido en Node 20).
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

WORKDIR /repo

# Copia mínima para resolver dependencies (mejor cache layer).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/web-admin/package.json   apps/web-admin/package.json
COPY apps/web-teacher/package.json apps/web-teacher/package.json
COPY apps/web-student/package.json apps/web-student/package.json
COPY packages/ui/package.json           packages/ui/package.json
COPY packages/auth-client/package.json  packages/auth-client/package.json
COPY packages/contracts/package.json    packages/contracts/package.json
COPY packages/ctr-client/package.json   packages/ctr-client/package.json
COPY packages/observability/package.json packages/observability/package.json
COPY packages/platform-ops/package.json  packages/platform-ops/package.json
COPY packages/test-utils/package.json    packages/test-utils/package.json

# Instala todas las deps del workspace (frozen lockfile = reproducible).
RUN pnpm install --frozen-lockfile

# Ahora sí copia el código source de apps y packages necesarios.
COPY packages/ packages/
COPY apps/web-admin/   apps/web-admin/
COPY apps/web-teacher/ apps/web-teacher/
COPY apps/web-student/ apps/web-student/

# Build de los 3 frontends. Cada uno produce apps/<name>/dist/.
RUN pnpm --filter @platform/web-admin   build \
 && pnpm --filter @platform/web-teacher build \
 && pnpm --filter @platform/web-student build

# ─────────────────────────────────────────────────────────────────────
# Stage 2: runtime nginx
# ─────────────────────────────────────────────────────────────────────
FROM nginx:alpine

# Quita config default y mete la nuestra.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY infrastructure/nginx-frontends.conf /etc/nginx/conf.d/frontends.conf

# Copia los 3 builds a paths separados dentro de /usr/share/nginx/html.
COPY --from=builder /repo/apps/web-admin/dist/   /usr/share/nginx/html/admin/
COPY --from=builder /repo/apps/web-teacher/dist/ /usr/share/nginx/html/teacher/
COPY --from=builder /repo/apps/web-student/dist/ /usr/share/nginx/html/student/


# nginx:alpine ya tiene CMD por default: nginx -g 'daemon off;'.
