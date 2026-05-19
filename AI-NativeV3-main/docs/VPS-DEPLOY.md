# VPS Deploy — guía paso a paso

Cómo levantar la stack AI-Native N4 en un VPS UNSL para piloto-2 ampliado.

Esta guía asume que **todavía no hay VPS provisionado** y arrancás validando todo el flujo de manera local con `docker-compose.prod.yml`. Cuando tengas VPS, los pasos son idénticos — solo cambian los DNS/hostname/TLS.

---

## TL;DR (validación local rápida)

```bash
cd AI-NativeV3-main

# 1. Crear .env.prod desde el template
cp infrastructure/env.prod.example infrastructure/.env.prod
# Editar infrastructure/.env.prod — generar passwords con `openssl rand -base64 32`

# 2. Levantar la stack prod-like
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod up -d

# 3. Esperar healthchecks (~60s) y migrar
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  exec api-gateway bash scripts/migrate-all.sh

# 4. Seed Casbin (RBAC)
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  exec academic-service uv run python -m academic_service.seeds.casbin_policies

# 5. Validar
docker compose -f infrastructure/docker-compose.prod.yml ps
bash scripts/check-health.sh
make test-rls

# 6. UI accesible en:
#   - http://localhost:8000 (api-gateway — backend)
#   - http://localhost:3000 (Grafana — observabilidad, admin/CAMBIAR)
#   - http://localhost:8180 (Keycloak admin — para configurar realm UNSL)
```

Si todo arranca limpio, podés replicarlo en VPS UNSL — solo necesitás cambiar `KEYCLOAK_HOSTNAME`, `CORS_ORIGINS`, `JWT_ISSUER`, `JWT_JWKS_URI`, y poner un reverse proxy TLS al frente.

---

## 1. Prerrequisitos

### Software requerido

| Herramienta | Versión mínima | Comando para verificar |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose plugin | v2.20+ | `docker compose version` |
| `openssl` | cualquiera moderna | `openssl version` |
| `curl` | cualquiera moderna | `curl --version` |
| `bash` | 4+ | `bash --version` |

### Recursos mínimos del host

- **RAM**: 6 GB libres (postgres + keycloak + 10 servicios Python + observabilidad)
- **Disco**: 20 GB libres (volúmenes de pg_data + minio_data + prom_data crecen con uso real)
- **CPU**: 2 cores mínimo, 4 recomendado para piloto-2 con ~100 alumnos concurrentes

### Configuración del kernel (VPS Linux)

```bash
# Aumentar max file descriptors (Postgres + Redis los necesitan)
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# Postgres recomienda esto para evitar OOM kills:
sudo sysctl -w vm.overcommit_memory=1
echo "vm.overcommit_memory=1" | sudo tee -a /etc/sysctl.conf
```

---

## 2. Bootstrap inicial (primera vez)

### Paso 1 — Clonar el repo en el VPS

```bash
ssh ops@vps-unsl
sudo mkdir -p /opt/platform
sudo chown ops:ops /opt/platform
cd /opt/platform
git clone https://github.com/<org>/<repo>.git ai-native-n4
cd ai-native-n4/AI-NativeV3-main
```

### Paso 2 — Generar `.env.prod`

```bash
cp infrastructure/env.prod.example infrastructure/.env.prod
chmod 600 infrastructure/.env.prod  # solo el owner puede leer
```

Editar `infrastructure/.env.prod` y generar TODAS las passwords con:

```bash
openssl rand -base64 32
```

Variables que **DEBEN** cambiar (sin valores reales el compose no arranca):

| Variable | Cómo generar |
|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -base64 32` |
| `ACADEMIC_DB_PASSWORD` | `openssl rand -base64 32` |
| `CTR_DB_PASSWORD` | `openssl rand -base64 32` |
| `CLASSIFIER_DB_PASSWORD` | `openssl rand -base64 32` |
| `CONTENT_DB_PASSWORD` | `openssl rand -base64 32` |
| `KEYCLOAK_DB_PASSWORD` | `openssl rand -base64 32` |
| `KEYCLOAK_ADMIN_PASSWORD` | password fuerte (lo usás en consola admin) |
| `REDIS_PASSWORD` | `openssl rand -base64 32` |
| `MINIO_ROOT_PASSWORD` | `openssl rand -base64 32` |
| `BYOK_MASTER_KEY` | `openssl rand -base64 32` — **si la perdés, todas las keys BYOK del tenant quedan inservibles** |
| `GRAFANA_ADMIN_PASSWORD` | password fuerte |
| `CORS_ORIGINS` | lista separada por coma de los dominios reales del piloto |
| `JWT_ISSUER` + `JWT_JWKS_URI` | URLs del Keycloak |

### Paso 3 — Arrancar la stack

```bash
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  build  # ~5-8 min la primera vez

docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  up -d
```

### Paso 4 — Esperar healthchecks

```bash
# Esperar a que Postgres + Keycloak estén ready (~60-90s)
docker compose -f infrastructure/docker-compose.prod.yml ps
# Todos los containers deben estar (healthy) o (running)

# Verificar Postgres
docker exec platform-prod-postgres pg_isready -U postgres
# debe responder: "/var/run/postgresql:5432 - accepting connections"
```

### Paso 5 — Aplicar migraciones

```bash
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  exec api-gateway bash scripts/migrate-all.sh
```

Esto corre Alembic upgrade head sobre las 4 bases. **Si falla con permission denied**, el `alembic/env.py` está usando `academic_user` que no es owner — workaround documentado en CLAUDE.md (override con `ACADEMIC_DB_URL` apuntando a `postgres:$POSTGRES_PASSWORD`).

### Paso 6 — Seed Casbin (RBAC policies)

```bash
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  exec academic-service uv run python -m academic_service.seeds.casbin_policies
```

Esto carga las 205 policies Casbin (los 4 roles × N entidades).

### Paso 7 — Configurar Keycloak realm (única acción manual)

1. Abrir consola admin: `http://localhost:8180` (o `https://keycloak.tu-dominio.unsl.edu.ar`)
2. Login con `KEYCLOAK_ADMIN_USER` / `KEYCLOAK_ADMIN_PASSWORD`
3. Importar realm desde `infrastructure/keycloak/realm-templates/demo_uni-realm.json` (ya montado en `/opt/keycloak/data/import` adentro del container)
4. Crear usuarios iniciales (al menos 1 superadmin, 1 docente, 1 alumno para validar el flujo)
5. **(Para VPS real con LDAP UNSL)**: configurar User Federation contra el LDAP institucional. Coordinación con DI UNSL — ver `docs/research/plan-b2-jwt-comisiones-activas.md`.

### Paso 8 — Validación end-to-end

```bash
# Health checks
bash scripts/check-health.sh
# Esperado: 10/10 OK (el undécimo, integrity-attestation, no corre acá)

# RLS aplicado en las 4 bases
make test-rls

# Smoke tests E2E
make test-smoke
# Esperado: 33 tests pasando contra el stack real
```

Si todo pasa, el piloto-2 está deployable.

---

## 3. Operación día a día

### Levantar / apagar la stack

```bash
# Apagar (preserva volúmenes)
docker compose -f infrastructure/docker-compose.prod.yml down

# Apagar destruyendo volúmenes (DESTRUCTIVO — pierde toda la data)
docker compose -f infrastructure/docker-compose.prod.yml down -v

# Reiniciar un servicio sin tocar los demás
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  restart tutor-service

# Ver logs de un servicio
docker compose -f infrastructure/docker-compose.prod.yml logs -f tutor-service

# Ver logs de los últimos 100 events
docker compose -f infrastructure/docker-compose.prod.yml logs --tail=100 ctr-service
```

### Aplicar actualizaciones de código

```bash
cd /opt/platform/ai-native-n4
git pull origin main

cd AI-NativeV3-main

# Rebuild solo los servicios que cambiaron
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  build tutor-service classifier-service

# Aplicar migraciones nuevas
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  exec api-gateway bash scripts/migrate-all.sh

# Restart con la imagen nueva
docker compose -f infrastructure/docker-compose.prod.yml \
  --env-file infrastructure/.env.prod \
  up -d --no-deps tutor-service classifier-service
```

### Inspeccionar la base de datos

```bash
# Conectar a Postgres como root
docker exec -it platform-prod-postgres psql -U postgres -d academic_main

# Conectar como user de la base (con RLS aplicado)
docker exec -it platform-prod-postgres psql -U academic_user -d academic_main
# password: el de ACADEMIC_DB_PASSWORD
```

---

## 4. Reverse proxy TLS (en VPS real)

El compose prod expone el api-gateway en `0.0.0.0:8000` y Grafana en `127.0.0.1:3000`. **Para piloto-2 con datos reales de alumnos, NUNCA exponer api-gateway sin TLS**. Poné un reverse proxy delante (nginx, Caddy, Traefik).

### Ejemplo nginx (sin certbot — Let's Encrypt manual):

```nginx
server {
    listen 443 ssl http2;
    server_name platform.tu-dominio.unsl.edu.ar;

    ssl_certificate /etc/letsencrypt/live/platform.tu-dominio.unsl.edu.ar/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/platform.tu-dominio.unsl.edu.ar/privkey.pem;

    # Frontends servidos como estáticos (build de pnpm) o detrás de Vite preview
    location /admin/  { proxy_pass http://localhost:5173/; }
    location /teacher/ { proxy_pass http://localhost:5174/; }
    location /student/ { proxy_pass http://localhost:5175/; }

    # API
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";  # para SSE del tutor
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;  # SSE necesita streaming, no buffering
        proxy_read_timeout 300s;
    }
}
```

---

## 5. Troubleshooting común

### "Service X exited with code 1"

```bash
docker compose -f infrastructure/docker-compose.prod.yml logs <service>
```

Causas frecuentes:

| Síntoma en logs | Causa probable | Fix |
|---|---|---|
| `psycopg.OperationalError: connection refused` | Postgres no levantó aún | Esperar healthcheck (~60s) |
| `permission denied for table` | Migration creó tabla como `postgres`, el user no es owner | Override env var con `postgres:$POSTGRES_PASSWORD` y re-run migrate |
| `JWT_ISSUER not set` o `JWT_JWKS_URI not set` | Variables faltantes en .env.prod | Setear las JWT_* en .env.prod |
| `DEV_TRUST_HEADERS=true` warning | Algo override el default — buscar | Confirmar que `.env.prod` NO tenga `DEV_TRUST_HEADERS=true` |
| `BYOK_MASTER_KEY too short` | No es base64 de 32 bytes | Regenerar con `openssl rand -base64 32` |

### `make test-rls` falla con "RLS not enforced"

Es porque la conexión usa user superusuario que bypasea RLS. Setear:

```bash
export CTR_STORE_URL_FOR_RLS_TESTS=postgresql+asyncpg://ctr_user:$CTR_DB_PASSWORD@localhost:5432/ctr_store
make test-rls
```

### Workers CTR no consumen el stream Redis

```bash
docker compose -f infrastructure/docker-compose.prod.yml logs ctr-service
# Buscar "consumer group not found" o "stream empty"

# Verificar XLEN del stream
docker exec platform-prod-redis redis-cli -a $REDIS_PASSWORD XLEN ctr.p0
# debería ser > 0 si hay episodios cerrados
```

---

## 6. Lo que falta cuando haya VPS real

1. **DNS + TLS**: certbot/Let's Encrypt para `platform.tu-dominio.unsl.edu.ar`, `keycloak.*`, `grafana.*`.
2. **Reverse proxy** (nginx/Caddy) con SSE-friendly config — ver §4.
3. **Backup automático**: ver `docs/pilot/runbook.md` sección "Backup" + el systemd timer en `infrastructure/systemd/`.
4. **Alertmanager → Email del equipo**: configurado en `infrastructure/observability/alertmanager.yml` con `ALERTS_*` env vars.
5. **Federation LDAP UNSL**: configurar User Federation en Keycloak contra el directorio institucional (coordinación con DI UNSL).
6. **Firewall del VPS**: cerrar todo excepto :443 (TLS), :22 (SSH desde IPs whitelisteadas). NO exponer :5432, :6379, :9000, :3000 externamente.

---

## 7. Diferencias con el compose `dev`

| Aspecto | `docker-compose.dev.yml` | `docker-compose.prod.yml` |
|---|---|---|
| Servicios Python | en host (`uv run`) | en containers (`build .`) |
| Passwords | hardcoded `admin/admin`, `postgres/postgres` | env vars desde `.env.prod` |
| `DEV_TRUST_HEADERS` | `true` (default) | **forzado `false`** |
| `CORS_ORIGINS` | `["*"]` | lista explícita |
| Bind ports | `0.0.0.0:*` (todos expuestos) | solo api-gateway + Grafana + Keycloak admin |
| Redis | sin auth | con `requirepass` |
| Grafana | admin/admin | env vars |

---

## 8. Cuando tengas el VPS UNSL real

Pasos concretos:

1. Reservar VPS (4 vCPU / 8 GB RAM / 80 GB disco mínimo para piloto-2)
2. SSH access para `ops` user con clave pública
3. Instalar Docker + Docker Compose plugin
4. Reservar dominios (`platform.tu-dominio.unsl.edu.ar`, `keycloak.*`, `grafana.*`)
5. Solicitar certificados TLS (Let's Encrypt o CA institucional UNSL)
6. Coordinar con DI UNSL: LDAP federation + claim `comisiones_activas` (ver A3 en `docs/research/plan-accion.md`)
7. Seguir esta guía desde §2 reemplazando `localhost` por los hostnames reales

---

## Referencias

- `infrastructure/docker-compose.prod.yml` — compose prod-like
- `infrastructure/env.prod.example` — template de `.env.prod`
- `docs/pilot/runbook.md` — incidentes y recovery
- `CLAUDE.md` — gotchas del piloto + invariantes críticas
- `docs/INFORME-PRE-PROD.md` — checklist completo pre-producción
