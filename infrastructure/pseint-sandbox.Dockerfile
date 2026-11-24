# Imagen del sandbox de PSeInt (HU-030, ADR-064).
#
# Trae el MISMO interprete que corre en el navegador (`packages/pseint`),
# empaquetado en un unico `/opt/pseint/run.js`. El runner del execution-service
# la usa SOLO para la correccion con IA: corre
#   docker run ... -e SRC=<fuente> <imagen> sh -c "node /opt/pseint/run.js"
# con la entrada por stdin y las mismas banderas que Java y Python
# (`--network=none`, `--read-only`, `--cap-drop=ALL`, usuario no root).
# Codigos de salida: 0 bien, 101 error de sintaxis ("no compila"), 1 error de
# ejecucion o limite de pasos.
#
# La publica en GHCR `.github/workflows/pseint-sandbox.yml`. En produccion se
# configura por DIGEST en `PSEINT_IMAGE` (control C1); es opcional (N06).
#
# Build context: raiz del repo.
#   docker build -f infrastructure/pseint-sandbox.Dockerfile -t pseint-sandbox .

# ─────────────────────────────────────────────────────────────────────
# Stage 1: empaquetar el interprete. El paquete no tiene dependencias de
# runtime: alcanza con esbuild (misma version y mismas opciones que el script
# `build` de packages/pseint/package.json), sin instalar el workspace entero.
# ─────────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS builder

WORKDIR /build
RUN npm install --no-save --no-audit --no-fund esbuild@0.25.12
COPY packages/pseint/src ./src
RUN npx esbuild src/cli.ts --bundle --platform=node --format=esm --target=node22 --outfile=/out/run.js \
 && printf '{"type":"module"}\n' > /out/package.json

# ─────────────────────────────────────────────────────────────────────
# Stage 2: solo Node y el bundle. Base por digest (control C1 del ADR-060):
# un tag mutable cambiaria el runtime bajo los pies.
# ─────────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392

COPY --from=builder /out/run.js /opt/pseint/run.js
COPY --from=builder /out/package.json /opt/pseint/package.json

# No corre como root. El runner igual fuerza `--user=65534:65534` (nobody).
USER node
WORKDIR /work
CMD ["node", "/opt/pseint/run.js"]
