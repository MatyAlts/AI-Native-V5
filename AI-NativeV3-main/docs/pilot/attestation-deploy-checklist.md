# Checklist de deploy — `integrity-attestation-service` en VPS institucional UNSL

**Audiencia**: Director de informática UNSL.
**Doctorando**: Alberto Alejandro Cortez (cortezalberto@gmail.com).
**Fecha del checklist**: 2026-04-27.
**Referencias**: [ADR-021](../adr/021-external-integrity-attestation.md), [`reglas.md` RN-128](../../reglas.md), [`docs/pilot/auditabilidad-externa.md`](auditabilidad-externa.md).

---

## ⚠ Precondición crítica del rol

**El doctorando NO debe tener acceso a la clave privada Ed25519 institucional**, en ningún momento. La separación de control es exactamente lo que defiende la propiedad académica de "registro externo independiente" del piloto. El doctorando solo recibe la **clave pública** después del Paso 1.

Si en algún momento la clave privada pasa por las manos del doctorando (por error o conveniencia), la propiedad se debilita y debe documentarse explícitamente como limitación en la tesis.

---

## Pre-requisitos del VPS

- [ ] Linux Ubuntu 22.04+ (o equivalente).
- [ ] Acceso SSH para administrador institucional.
- [ ] Python 3.12+ instalado.
- [ ] `uv` (Python package manager) instalado (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
- [ ] Git instalado.
- [ ] Acceso de **lectura** al repositorio del piloto (clonar el código del `integrity-attestation-service`).
- [ ] Redis disponible — puede ser:
   - **Recomendado**: instancia Redis dedicada del VPS institucional (no compartir con el cluster del piloto).
   - **Alternativa**: instancia Redis del piloto (requiere coordinación de network access).
- [ ] IP pública del `ctr-service` del piloto identificada (para IP allowlist del Paso 5).
- [ ] Hostname público para el servicio: sugerencia `attestation.unsl.edu.ar` o subdominio institucional.

---

## Paso 1 — Generar el keypair Ed25519 institucional

**EJECUTA EN EL VPS, NO EN LA MÁQUINA DEL DOCTORANDO.**

```bash
# Crear directorio con permisos restrictivos
sudo mkdir -p /etc/attestation
sudo chmod 0700 /etc/attestation

# Generar el keypair (corrida única)
sudo python3 <<'PYEOF'
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

priv = Ed25519PrivateKey.generate()
pub = priv.public_key()

priv_pem = priv.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
pub_pem = pub.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

with open("/etc/attestation/private.pem", "wb") as f:
    f.write(priv_pem)
with open("/etc/attestation/public.pem", "wb") as f:
    f.write(pub_pem)

# Computar el pubkey_id (hash de la pubkey raw)
import hashlib
raw_pub = pub.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
pubkey_id = hashlib.sha256(raw_pub).hexdigest()[:12]
print(f"Pubkey ID: {pubkey_id}")
PYEOF

# Permisos restrictivos
sudo chmod 0600 /etc/attestation/private.pem
sudo chmod 0644 /etc/attestation/public.pem
# Crear usuario dedicado del servicio (si no existe)
sudo useradd -r -s /bin/false attestation-svc 2>/dev/null || true
sudo chown attestation-svc:attestation-svc /etc/attestation/private.pem
```

- [ ] Keypair generado en `/etc/attestation/`.
- [ ] Permisos `0600` en la privada (solo el usuario del servicio puede leerla).
- [ ] **Pubkey ID anotado** (12 hex chars, ej. `a1b2c3d4e5f6`). Lo necesitás para verificar el failsafe.

---

## Paso 2 — Distribuir la pubkey al doctorando

- [ ] Copiar `public.pem` y enviar al doctorando por canal institucional (email, sftp, etc.):
  ```bash
  cat /etc/attestation/public.pem
  ```
- [ ] El doctorando hace commit en `docs/pilot/attestation-pubkey.pem` del repositorio del piloto.
- [ ] **NO enviar la clave privada bajo ningún concepto.** Si por error se transmitió, regenerar el keypair desde cero (vuelve al Paso 1).

---

## Paso 3 — Clonar el código del servicio en el VPS

```bash
sudo mkdir -p /opt/attestation
sudo chown attestation-svc:attestation-svc /opt/attestation
cd /opt/attestation

# Clonar el repositorio del piloto (read-only)
sudo -u attestation-svc git clone --depth 1 \
    https://github.com/<org>/<repo-piloto>.git src

cd src/apps/integrity-attestation-service
sudo -u attestation-svc uv sync --all-packages
```

---

## Paso 4 — Configurar env vars de producción

Crear `/etc/attestation/env`:

```bash
# Modo producción — el failsafe rechaza arrancar si detecta dev key
ENVIRONMENT=production

# Paths a las claves generadas en Paso 1
ATTESTATION_PRIVATE_KEY_PATH=/etc/attestation/private.pem
ATTESTATION_PUBLIC_KEY_PATH=/etc/attestation/public.pem

# Directorio del journal JSONL (rotación diaria automática)
ATTESTATION_LOG_DIR=/var/lib/attestation/logs

# Redis del VPS institucional (puerto 6379, DB 0)
REDIS_URL=redis://127.0.0.1:6379/0

# Observabilidad (opcional pero recomendado)
OTEL_ENDPOINT=http://<grafana-otel-collector>:4317

# Puerto del servicio
SERVICE_PORT=8012
```

Crear directorio del journal:
```bash
sudo mkdir -p /var/lib/attestation/logs
sudo chown -R attestation-svc:attestation-svc /var/lib/attestation
sudo chmod 0755 /var/lib/attestation/logs
```

- [ ] `/etc/attestation/env` creado.
- [ ] `/var/lib/attestation/logs` creado con permisos correctos.

---

## Paso 5 — Levantar el servicio (systemd)

**Importante**: el consumer del JSONL asume **single-consumer**. NO levantes múltiples workers ni configures réplicas. Sin file lock explícito, dos consumers concurrentes generan duplicados en el journal.

`/etc/systemd/system/attestation.service`:

```ini
[Unit]
Description=Integrity Attestation Service (ADR-021)
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=attestation-svc
Group=attestation-svc
WorkingDirectory=/opt/attestation/src/apps/integrity-attestation-service
EnvironmentFile=/etc/attestation/env

# IMPORTANTE: --workers 1 (CRITICO — ver ADR-021)
ExecStart=/opt/attestation/src/.venv/bin/uvicorn integrity_attestation_service.main:app --host 0.0.0.0 --port 8012 --workers 1

# Worker del consumer del stream Redis (proceso aparte, single-consumer)
# (Opcional: correr como segundo systemd unit si se prefiere separación)

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Worker del consumer** (segundo unit recomendado para separación):

`/etc/systemd/system/attestation-consumer.service`:

```ini
[Unit]
Description=Attestation Consumer Worker (ADR-021)
After=attestation.service redis.service
Requires=redis.service

[Service]
Type=simple
User=attestation-svc
Group=attestation-svc
WorkingDirectory=/opt/attestation/src/apps/integrity-attestation-service
EnvironmentFile=/etc/attestation/env
ExecStart=/opt/attestation/src/.venv/bin/python -m integrity_attestation_service.workers.attestation_consumer

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable attestation.service attestation-consumer.service
sudo systemctl start attestation.service attestation-consumer.service
sudo systemctl status attestation.service
```

- [ ] Servicio HTTP corriendo en :8012.
- [ ] Worker consumer corriendo (proceso separado, un único consumer).
- [ ] Logs muestran `attestation_keys_loaded environment=production pubkey_id=<el del Paso 1>`.
- [ ] **Failsafe activo**: si por error se setea la dev key del repo en `ATTESTATION_PRIVATE_KEY_PATH`, el servicio rechaza arrancar con `DevKeyInProductionError`.

---

## Paso 6 — Reverse proxy + IP allowlist

El **POST a `/api/v1/attestations`** debe estar restringido al `ctr-service` del piloto. Los **GETs** son públicos para auditores.

`nginx` config sugerida (`/etc/nginx/sites-available/attestation`):

```nginx
server {
    listen 80;
    listen 443 ssl;
    server_name attestation.unsl.edu.ar;

    # SSL — Let's Encrypt o cert institucional
    ssl_certificate /etc/letsencrypt/live/attestation.unsl.edu.ar/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/attestation.unsl.edu.ar/privkey.pem;

    # GETs públicos (auditores descargan JSONL + pubkey)
    location /api/v1/attestations/pubkey {
        proxy_pass http://127.0.0.1:8012;
        allow all;
    }
    location ~ ^/api/v1/attestations/[0-9]{4}-[0-9]{2}-[0-9]{2}$ {
        proxy_pass http://127.0.0.1:8012;
        allow all;
    }
    location /health {
        proxy_pass http://127.0.0.1:8012;
        allow all;
    }

    # POST restricto al ctr-service del piloto
    location /api/v1/attestations {
        # Reemplazar <CTR_SERVICE_IP> con la IP pública del cluster del piloto
        allow <CTR_SERVICE_IP>;
        deny all;
        proxy_pass http://127.0.0.1:8012;
    }
}
```

- [ ] Reverse proxy configurado con allowlist.
- [ ] SSL configurado (Let's Encrypt o cert institucional).
- [ ] IP del `ctr-service` del piloto agregada al allowlist.

---

## Paso 7 — Smoke test

Desde el VPS (interno):
```bash
curl http://127.0.0.1:8012/health
# → {"service":"integrity-attestation-service","status":"ready",...}

curl http://127.0.0.1:8012/api/v1/attestations/pubkey
# → -----BEGIN PUBLIC KEY-----... + header X-Signer-Pubkey-Id: <pubkey_id>
```

Desde Internet (público):
```bash
curl https://attestation.unsl.edu.ar/api/v1/attestations/pubkey
# → mismo PEM, mismo pubkey_id
```

Test de IP allowlist:
```bash
# Desde una IP NO autorizada — debe devolver 403
curl -X POST https://attestation.unsl.edu.ar/api/v1/attestations -H "Content-Type: application/json" -d '{}'
# → 403 Forbidden (nginx)
```

- [ ] `/health` responde 200.
- [ ] `/api/v1/attestations/pubkey` devuelve la pubkey con `X-Signer-Pubkey-Id` matcheando el del Paso 1.
- [ ] `POST` desde IP no autorizada devuelve 403.
- [ ] Logs del servicio muestran requests entrantes.

---

## Paso 8 — Configurar el `ctr-service` del piloto

Desde el cluster del piloto, setear la env var del `ctr-service`:

```bash
# Apuntar al Redis del VPS institucional (no al Redis del piloto)
ATTESTATION_REDIS_URL=redis://attestation.unsl.edu.ar:6379/0
```

(O configurar conectividad de red entre el ctr-service del piloto y el Redis institucional vía VPN/private network.)

Si se prefiere que el ctr-service emita por HTTP en lugar de Redis (alternativa de implementación), eso requiere ajuste de código — actualmente emite XADD al stream Redis. Coordinar con el doctorando.

- [ ] `ctr-service` configurado para usar el Redis del VPS institucional.
- [ ] Smoke test end-to-end: cerrar un episodio en el piloto, esperar ~10 segundos, verificar que aparece una línea nueva en `/var/lib/attestation/logs/attestations-YYYY-MM-DD.jsonl` del VPS.

---

## Paso 9 — Monitoreo + backup

- [ ] **Backup nightly** del directorio `/var/lib/attestation/logs/` a otro VPS o storage. Si UNSL pierde el JSONL, se pierde toda la evidencia externa del período. Sugerencia: rsync nightly a `backup-attestation.unsl.edu.ar` o storage S3.
- [ ] **Métrica Grafana**: `attestation_pending_count` (eventos en stream Redis sin consumir). Alerta si supera 0 por más de 24 horas (SLO confirmado en ADR-021).
  - Esta métrica todavía NO está implementada en el servicio (declarada como agenda futura). Si no está disponible, monitorear vía:
    ```bash
    redis-cli XLEN attestation.requests  # debería ser ~0 en estado normal
    ```
- [ ] **Logs estructurados** propagándose a Loki/Grafana institucional para audit trail.

---

## Paso 10 — Verificación criptográfica end-to-end (con el doctorando)

Cuando todo esté arriba:

1. El **doctorando** descarga el JSONL del primer día con attestations:
   ```bash
   curl https://attestation.unsl.edu.ar/api/v1/attestations/2026-XX-XX > attestations-2026-XX-XX.jsonl
   ```

2. Corre la verificación con la pubkey commiteada en el repo:
   ```bash
   uv run python scripts/verify-attestations.py \
       --jsonl-dir ./ \
       --pubkey-pem docs/pilot/attestation-pubkey.pem \
       --verbose
   ```

3. Resultado esperado: **exit 0**, todas las firmas válidas, `pubkey_id` matchea el del Paso 1.

- [ ] Verificación criptográfica exitosa.
- [ ] La pubkey del repo (`docs/pilot/attestation-pubkey.pem`) coincide bit-a-bit con la del endpoint público.

---

## Si algo falla — runbook rápido

| Síntoma | Causa probable | Fix |
|---|---|---|
| Servicio no arranca, log dice `DevKeyInProductionError` | `ATTESTATION_PRIVATE_KEY_PATH` apunta a la dev key del repo | Setear el path correcto en `/etc/attestation/env` (Paso 4). |
| `/api/v1/attestations/pubkey` devuelve 503 | Las keys no se cargaron al startup | Verificar permisos de `/etc/attestation/private.pem` (debe leerlo `attestation-svc`). |
| POST devuelve 403 desde el ctr-service | IP del ctr-service no está en el nginx allowlist | Agregar IP en `/etc/nginx/sites-available/attestation` y `nginx -s reload`. |
| Episodios cerrándose pero no aparecen attestations en el JSONL | Worker consumer caído, o no llega el XADD al Redis | Verificar `systemctl status attestation-consumer.service` + `redis-cli XLEN attestation.requests`. |
| Verificación del doctorando falla con "FIRMA INVALIDA" | La pubkey del repo no coincide con la activa | Re-distribuir la pubkey del Paso 2; re-committear; o verificar si hubo rotación de claves no documentada. |

---

## Contacto

- **Doctorando**: Alberto Cortez — cortezalberto@gmail.com
- **Repositorio**: `<URL>`
- **ADR de referencia**: [ADR-021](../adr/021-external-integrity-attestation.md)
