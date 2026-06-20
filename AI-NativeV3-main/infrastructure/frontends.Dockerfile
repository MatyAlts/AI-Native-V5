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

# URL base consumida por los bundles Vite en build-time.
# Si queda vacia, los frontends mantienen requests relativas `/api/*`
# (que nginx frontends proxea a api-gateway:8000).
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL

ARG VITE_CLERK_PUBLISHABLE_KEY=
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY

# pnpm via corepack (incluido en Node 20).
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

WORKDIR /repo

# Copia mínima para resolver dependencies (mejor cache layer).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/web-admin/package.json   apps/web-admin/package.json
COPY apps/web-teacher/package.json apps/web-teacher/package.json
COPY apps/web-student/package.json apps/web-student/package.json
# Solo los 4 packages que SON Node (tienen package.json). Los otros
# packages del workspace (observability, platform-ops, test-utils,
# contracts/src/python) son Python puro y no tienen package.json.
COPY packages/ui/package.json           packages/ui/package.json
COPY packages/auth-client/package.json  packages/auth-client/package.json
COPY packages/contracts/package.json    packages/contracts/package.json
COPY packages/ctr-client/package.json   packages/ctr-client/package.json

# Instala todas las deps del workspace (frozen lockfile = reproducible).
RUN pnpm install --frozen-lockfile

# Cache-bust: en el deploy managed (EasyPanel) la cache de build a veces NO se
# invalida aunque el código source cambie, sirviendo un bundle viejo (gotcha
# 2026-06-16: el checkbox permite_pausa no aparecía en prod pese a estar en
# main). Bumpear este valor rompe la cache desde acá y fuerza recompilar los 3
# frontends con el código actual.
ARG FRONTEND_CACHEBUST=20260620-2
RUN echo "frontend cachebust: $FRONTEND_CACHEBUST"

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

# Cache-bust del stage runtime. BuildKit cacheaba los `COPY --from=builder
# dist/` de abajo AUNQUE el builder recompilara (bug multi-stage 2026-06-16:
# el `pnpm build` corría 87s pero el COPY del dist salía CACHED → servía el
# bundle viejo). Re-declarar el ARG acá invalida el stage 2 y fuerza re-copiar
# los `dist/` recién compilados. Bumpear el valor en un rebuild futuro.
ARG FRONTEND_CACHEBUST=20260620-2
RUN echo "stage2 cachebust: $FRONTEND_CACHEBUST"

# Quita config default y mete la nuestra.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY infrastructure/nginx-frontends.conf /etc/nginx/conf.d/frontends.conf
# Credenciales Basic Auth del panel admin / fallback de /api/ sin Bearer.
# DEV/TEST: admin/admin. Reemplazar por un secreto real (o gestionarlo vía
# volumen/secret del orquestador) antes de exponer datos reales del piloto.
COPY infrastructure/htpasswd /etc/nginx/.htpasswd

# Copia los 3 builds a paths separados dentro de /usr/share/nginx/html.
COPY --from=builder /repo/apps/web-admin/dist/   /usr/share/nginx/html/admin/
COPY --from=builder /repo/apps/web-teacher/dist/ /usr/share/nginx/html/teacher/
COPY --from=builder /repo/apps/web-student/dist/ /usr/share/nginx/html/student/


# nginx:alpine ya tiene CMD por default: nginx -g 'daemon off;'.
