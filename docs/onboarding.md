# Onboarding — setup local

Guía para poner el monorepo funcionando en tu máquina desde cero, en menos de 30 minutos.

## Requisitos

Instalar una sola vez:

| Herramienta | Versión | Cómo |
|---|---|---|
| Python | 3.12.x | [python.org](https://www.python.org/downloads/) o pyenv |
| uv | ≥0.5 | `pip install uv` o `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20 LTS | [nodejs.org](https://nodejs.org/) o nvm |
| pnpm | ≥9.12 | `npm i -g pnpm` o `corepack enable` |
| Docker | ≥24 | [docker.com](https://docs.docker.com/get-docker/) |
| Docker Compose | ≥2.20 | Incluido en Docker Desktop |
| Git | ≥2.40 | Seguramente ya lo tenés |

Verificar con `make check-tools`.

## Paso 1 — Clonar y preparar el entorno

```bash
git clone <repo-url> platform
cd platform
cp .env.example .env
# Editar .env si hace falta (API keys de Anthropic/OpenAI para F3+)
```

## Paso 2 — Levantar infraestructura

```bash
make dev-bootstrap
```

Esto levanta en Docker:

- **PostgreSQL 16** con pgvector en `localhost:5432` (usuario root: `postgres`/`postgres`)
- **Keycloak 25** en http://localhost:8180 (admin: `admin`/`admin`)
- **Redis 7** en `localhost:6379`
- **MinIO** en http://localhost:9001 (`minioadmin`/`minioadmin`)
- **Grafana** en http://localhost:3000 (`admin`/`admin`)
- **Jaeger UI** en http://localhost:16686
- **Prometheus** en http://localhost:9090

El realm `demo_uni` se importa automáticamente con tres usuarios de prueba:

| Usuario | Password | Rol |
|---|---|---|
| `admin@demo-uni.edu` | `admin123` | docente_admin |
| `docente@demo-uni.edu` | `docente123` | docente |
| `estudiante@demo-uni.edu` | `estudiante123` | estudiante |

## Paso 3 — Instalar dependencias

```bash
make install
```

Esto corre `uv sync --all-packages` (12 servicios Python + 2 packages Python) y `pnpm install` (3 frontends + 3 packages TS). La primera vez tarda 3-5 minutos.

## Paso 4 — Aplicar migraciones

```bash
make migrate
```

En F0 esto es no-op (las migraciones llegan en F1). El comando debe pasar sin errores.

## Paso 5 — Arrancar los servicios

```bash
make dev
```

Arranca los 12 servicios Python con hot-reload y los 3 frontends con Vite HMR, todos en paralelo.

Verificar que responden con:

```bash
make check-health
```

Output esperado:

```
──── Backend services ────
  ✓ api-gateway (:8000)
  ✓ identity-service (:8001)
  ...
──── Frontends ────
  ✓ web-admin (:5173)
  ✓ web-teacher (:5174)
  ✓ web-student (:5175)

Todos los backends OK
```

## Paso 6 — Probar un login end-to-end

1. Abrir http://localhost:5173 (web-admin).
2. Click "Login".
3. Keycloak redirige al form de demo_uni.
4. Login con `admin@demo-uni.edu` / `admin123`.
5. Volvés al web-admin autenticado. El JWT trae `tenant_id=00000000-0000-0000-0000-000000000001`.

> **F0 nota**: en el esqueleto actual el frontend solo muestra el estado del `/api/`; el flujo de login completo se completa en F1.

## Comandos útiles del día a día

```bash
# Ver logs de un servicio específico
docker logs -f platform-keycloak

# Reiniciar solo un servicio Python
cd apps/academic-service && uv run uvicorn academic_service.main:app --reload --port 8002

# Ejecutar tests de un paquete
cd packages/contracts && uv run pytest

# Crear una nueva migración
make migrate-new SERVICE=academic-service NAME=agregar_tabla_carreras

# Verificar RLS (debería pasar 100% en CI)
make check-rls

# Limpiar todo y empezar de cero
make clean && make dev-bootstrap && make install
```

## Trabajar en una feature

```bash
git checkout -b feat/mi-feature
# ... código ...
make lint-fix        # autofix de formato/lint
make typecheck       # mypy + tsc
make test            # suite completa
git commit -m "feat: descripción"
git push
```

El PR dispara el workflow de CI que debe quedar todo verde antes de merge.

## Si algo falla

### "Port already in use"

Algún servicio ya ocupa el puerto. `docker ps` o `lsof -i :5432`. Parar el conflictivo o cambiar `docker-compose.dev.yml`.

### Keycloak no importa el realm

Mirar `docker logs platform-keycloak`. Común: JSON mal formado o que el realm ya existe (borrar volumen con `docker compose down -v`).

### `uv sync` falla con error de pgvector

Algunas dependencias Python requieren headers del sistema. En Ubuntu/Debian:
```bash
sudo apt install build-essential libpq-dev python3.12-dev
```

### Tests fallan por timeout de testcontainers

Testcontainers baja imágenes la primera vez. Si tenés internet lento, pre-pulleá:
```bash
docker pull pgvector/pgvector:pg16
docker pull redis:7-alpine
```

### Memoria insuficiente

Todo el stack local consume ~4 GB RAM. Si tenés 8 GB, cerrá Chrome antes. Si tenés 16 GB estás cómodo. Para máquinas chicas, comentar los servicios de observabilidad en `docker-compose.dev.yml`.

## Siguientes pasos

Para entender qué se construye en cada fase y trabajar sobre funcionalidad real, leer:

- [`docs/plan-detallado-fases.md`](./plan-detallado-fases.md) — plan de 16 meses con desglose semanal
- [`docs/architecture.md`](./architecture.md) — arquitectura general de la plataforma
- [`docs/adr/`](./adr/) — decisiones arquitectónicas
