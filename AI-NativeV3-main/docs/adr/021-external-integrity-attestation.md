# ADR-021 — Registro externo auditable de integridad del CTR

- **Estado**: Aceptado (2026-04-27 — ver "Decisiones tomadas" al final)
- **Fecha**: 2026-04-27
- **Deciders**: Alberto Alejandro Cortez, director de tesis, **director de informática UNSL** (deciders adicionales por la responsabilidad institucional sobre la clave de firma)
- **Tags**: integridad, criptografía, tesis, piloto-UNSL, CTR, auditoría

## Contexto y problema

La tesis declara en la **Sección 7.3** que el hash de referencia del CTR completo (hash del último evento de un episodio cerrado) **se almacena en dos ubicaciones**: en la base de datos del sistema y en un **registro externo auditable**, "por ejemplo, un log append-only en otro servidor institucional". La duplicación es lo que permite **detectar manipulación del sistema mismo**: si alguien con acceso root recalcula los hashes en cadena de la DB, queda evidencia en el registro externo que no controla.

**Verificación empírica del audit (2026-04-27)**: el código no implementa esta propiedad.

- `EpisodioCerradoPayload` ([events.py:57-65](packages/contracts/src/platform_contracts/ctr/events.py#L57-L65)) emite `final_chain_hash` localmente, sin hook a sistema externo.
- `apps/ctr-service/src/ctr_service/workers/integrity_checker.py` existe pero opera **dentro** del sistema — verifica que la cadena local sea consistente, lo cual no detecta manipulación que recalcule cadenas.
- `infrastructure/docker-compose.dev.yml` no tiene servicio de attestation ni puerto reservado.
- Búsqueda exhaustiva de `attestation`, `external_audit`, `merkle` → resultados solo en comentarios pendientes y referencias al `audi1.md → G5`.

**Consecuencia**: la afirmación de la Sección 7.3 sobre auditabilidad externa es **aspiracional**. Como la auditabilidad es contribución (i)/(ii) declarada en el abstract, la omisión tensiona la promesa de la tesis.

Fuerzas en juego:

1. **Independencia institucional**: el registro externo debe vivir fuera del control operativo del equipo del piloto. Si lo controla el mismo doctorando, no es "externo".
2. **No bloquear al estudiante**: el cierre del episodio se confirma al frontend en el momento. La attestation es **eventualmente consistente** — si el registro externo está caído, el sistema sigue funcionando y la attestation queda en cola.
3. **Verificable por terceros**: cualquier auditor con la clave pública debe poder verificar la integridad del log sin cooperación del sistema.
4. **Reproducibilidad bit-a-bit** (CLAUDE.md): la firma debe operar sobre un **buffer canónico** documentado bit-exact. Cualquier ambigüedad rompe la propiedad.
5. **Costo del piloto**: VPS institucional separado vs. opciones más sofisticadas. La tesis se defiende con auditabilidad razonable, no con un sistema bancario internacional.
6. **Apetito por dependencias externas** (CLAUDE.md "default `LLM_PROVIDER=mock`"): el dev loop debe seguir funcionando sin red ni claves reales. Hay que prever modo dev con clave de juguete.

## Drivers de la decisión

- **D1** — Cumplir promesa Sección 7.3 con implementación honesta y verificable.
- **D2** — **NO bloquear el cierre de episodio**: la attestation es asíncrona, fire-and-retry. La invariante operativa "el estudiante ve cerrado en <500ms" se preserva.
- **D3** — **NO usar el mismo secreto que el equipo del doctorando ya posee**: la clave privada vive en infraestructura institucional separada. Idealmente ni el doctorando tiene acceso a ella.
- **D4** — Verificación pública por terceros: la clave pública se commitea al repo + se distribuye vía endpoint público.
- **D5** — Buffer de firma canónico, documentado bit-exact, testeable. Mismo nivel de cuidado que `chunks_used_hash` (RN-026) o `classifier_config_hash` (ADR-009).
- **D6** — Modo dev funciona sin clave real: clave de juguete commiteada para que `make dev` no requiera ceremonial.
- **D7** — No introducir dependencias exóticas (blockchain, smart contracts, sidecars) que el comité doctoral o un auditor de UNSL no entiendan.

## Opciones consideradas

### Opción A — Archivo `.jsonl` append-only firmado con Ed25519, en VPS institucional separado

Un servicio nuevo `integrity-attestation-service` (puerto :8012) que:
- Recibe attestation requests (`{episode_id, final_chain_hash, tenant_id, ts_closed, total_events}`).
- Firma con clave Ed25519 institucional.
- Appendea a `attestations-YYYY-MM-DD.jsonl` (rotación diaria).
- Expone clave pública vía `GET /api/v1/attestations/pubkey`.
- Expone log diario vía `GET /api/v1/attestations/{date}` para auditores.

**Deploy**: en VPS institucional separado del cluster del piloto. Si UNSL no tiene VPS, fallback a **bucket MinIO institucional con write-only IAM para el attestation service** (no append-en-cliente, sí PUT inmutable).

Ventajas:
- Implementación trivial (~400 LOC total).
- Verificable por cualquier auditor con la clave pública: dos archivos (JSONL + pubkey) y una herramienta CLI bastan.
- Ed25519 es estándar moderno (RFC 8032), soportado nativamente en `cryptography` de Python, claves de 32 bytes, firmas de 64 bytes.
- Independencia institucional respeta D3.
- Sin dependencia de blockchain ni terceros pagos.

Desventajas:
- Si la institución pierde el archivo JSONL (incendio del servidor), se pierde toda la evidencia. Mitigación: replicación nightly a otro VPS o storage. **Esto es responsabilidad institucional, no del piloto** — declarado como tal.
- Confianza centralizada en la institución. Pero la institución es justamente el árbitro académico que la tesis necesita; no hay paradoja.

### Opción B — Certificate Transparency-style log con sparse Merkle tree

Log append-only con árbol Merkle, permitiendo **proofs de inclusión** y **proofs de consistencia** entre versiones del log.

Ventajas:
- Garantía criptográfica más fuerte: un auditor puede verificar que un attestation "está en el log al tiempo T" sin descargarse todo el log.
- Adoptado por Google (CT logs para certificados TLS).

Desventajas que la descartan:
- Complejidad de Merkle tree, gestión de versiones del root, distribución de proofs. ~5-10x más LOC.
- Requiere herramientas que un comité doctoral no tiene (la Opción A se verifica con `python verify_attestations.py`, esta requiere bibliotecas Merkle).
- Sobredimensionada para el stakeholder real (tesis doctoral, no PKI internacional).

### Opción C — OpenTimestamps / blockchain público

Hash del attestation se commitea a Bitcoin via OpenTimestamps. Garantía: el commit existe en el blockchain antes del bloque N, por lo tanto la attestation existió antes del bloque N.

Ventajas:
- Garantía no-falsificable sin colaboración global del sistema bancario.
- Usado en aplicaciones legales (ej. notario digital).

Desventajas que la descartan:
- Latencia: cada commit espera ~10 minutos para aparecer en un bloque, ~1 hora para confirmación. Acumulable con batching (no firma cada attestation por separado), pero introduce complejidad operacional.
- Dependencia de bitcoind o servicio externo (calendar.opentimestamps.org). El dev loop pasaría a depender de red.
- "Blockchain" en una tesis sobre pedagogía universitaria es una bandera roja para el comité — preguntará por qué, y la respuesta no es satisfactoria.

### Opción D — Diferir / declarar como agenda futura

NO implementar nada para el piloto-1, mantener la tesis Sección 7.3 como aspiracional, declararlo como trabajo futuro del Capítulo 20.

Ventajas:
- Cero esfuerzo de implementación.

Desventajas que la descartan:
- La auditabilidad externa es contribución (i)/(ii) del abstract. **Omitirla del MVP defensivo es exactamente lo que el modelo híbrido busca evitar**: el `audi1.md` clasifica G5 como "antes de la defensa".
- Sin esto, en una pregunta directa del comité ("¿alguien con root podría manipular el CTR?"), la respuesta honesta es "sí, y no se detectaría". Defendible solo con un ADR redactado que explique por qué se difiere — pero el ADR redactado **es exactamente el que estamos escribiendo ahora**, lo cual sugiere que no se difiere.

## Decisión

**Opción A — Archivo JSONL firmado con Ed25519 + servicio dedicado en infraestructura institucional separada.**

### Schema del attestation (formato JSONL line)

Cada línea del archivo `attestations-YYYY-MM-DD.jsonl` es un objeto JSON con esta forma:

```json
{
  "episode_id": "<uuid>",
  "tenant_id": "<uuid>",
  "final_chain_hash": "<64-hex-chars>",
  "total_events": <int>,
  "ts_episode_closed": "<ISO-8601-UTC-Z>",
  "ts_attested": "<ISO-8601-UTC-Z>",
  "signer_pubkey_id": "<short-hex-id>",
  "signature": "<128-hex-chars>",
  "schema_version": "1.0.0"
}
```

### Buffer canónico de firma (bit-exact)

La firma se calcula sobre el buffer:

```
canonical = f"{episode_id}|{tenant_id}|{final_chain_hash}|{total_events}|{ts_episode_closed}|{schema_version}".encode("utf-8")
signature = ed25519_private_key.sign(canonical).hex()
```

Notas críticas (cualquier desviación rompe la verificación):

- Separador entre campos: `|` (pipe, U+007C). Sin espacios.
- Orden de campos: **fijo** (`episode_id, tenant_id, final_chain_hash, total_events, ts_episode_closed, schema_version`). NO se ordena alfabéticamente para evitar ambigüedad si se renombran campos.
- `episode_id` y `tenant_id`: lowercase UUID con dashes (`str(uuid)`, no `uuid.hex`).
- `final_chain_hash`: 64 hex chars lowercase, igual que en el evento `EpisodioCerrado`.
- `total_events`: integer decimal sin separadores.
- `ts_episode_closed`: ISO-8601 UTC con sufijo `Z` (no `+00:00`). Mismo formato que `event.ts.isoformat().replace("+00:00", "Z")` que ya usa el repo.
- `schema_version`: `"1.0.0"` literal. Si en el futuro se cambia el formato del buffer, **bumpea** y se documenta en ADR sucesor (no se modifica este).
- **Encoding**: UTF-8. ASCII puro en este caso pero declarado explícitamente.

`ts_attested` (timestamp del momento en que se firmó) **NO entra en el buffer** porque sería trivialmente atacable: el atacante podría re-firmar con un `ts_attested` distinto. La firma es sobre los datos del episodio, no sobre cuándo se firmaron.

### Algoritmo de firma

**Ed25519** (RFC 8032). Justificación:

| Criterio | Ed25519 | RSA-2048 | ECDSA-P256 | HMAC-SHA256 |
|---|---|---|---|---|
| Tamaño clave priv | 32 B | 256 B | 32 B | 32 B |
| Tamaño firma | 64 B | 256 B | 64-72 B | 32 B |
| Velocidad firma | 70k ops/s | 2k ops/s | 25k ops/s | 1M ops/s |
| Verificación pública | ✓ | ✓ | ✓ | ✗ (simétrico) |
| Determinístico | ✓ | ✓ | con cuidado | ✓ |
| Footguns | pocos | side-channels | many | n/a |
| Soporte `cryptography` py | nativo | nativo | nativo | nativo |

HMAC se descarta por D4 (verificación pública). RSA por tamaño y velocidad. ECDSA por footguns (Sony PS3 incident, etc.). Ed25519 es la elección por defecto razonable de 2026 para firma digital nueva.

### Identificación de la clave (`signer_pubkey_id`)

`signer_pubkey_id = sha256(public_key_bytes).hex()[:12]` (12 hex chars, ~48 bits — suficiente para discriminar entre varias claves en rotación, no es secreto).

Permite que en el futuro la institución rote la clave: log queda con el viejo `signer_pubkey_id`, el verificador busca la pubkey correspondiente en su llavero.

### Flujo end-to-end

```
1. tutor-service: emite EpisodioCerrado al CTR (sin cambios respecto a hoy).
2. ctr-service: consumer del stream ctr.pN. Después de persistir el evento en
   Postgres + actualizar Episode.closed_at, emite a stream Redis NUEVO
   `attestation.requests` el payload {episode_id, tenant_id, final_chain_hash,
   total_events, ts_episode_closed}.
3. integrity-attestation-service (worker dedicado, single-consumer del stream):
   - Lee del stream. XACK manual.
   - Calcula buffer canónico, firma con Ed25519.
   - Appendea al JSONL del día.
   - Si fallo de I/O: NO acka, evento queda en pending. Reintenta con backoff
     exponencial (1s, 5s, 30s, 5min, 30min, 6h). Después de 24h, alerta a
     Grafana via métrica `attestation_pending_count`.
4. Verificación (OFFLINE, por auditor):
   - `python scripts/verify-attestations.py --jsonl-dir <dir> --pubkey <pem>`
   - Recorre cada línea, recalcula buffer canónico, verifica firma. Reporta
     OK/FAIL por línea + total + duplicados (mismo episode_id en distintas
     fechas — no debería pasar pero el verificador lo detecta).
```

**Crítico** (D2): el cierre del episodio NO espera a la attestation. El frontend ve "episodio cerrado" antes de que se firme nada. La attestation es **eventualmente consistente**, con SLO 24h. Esto se documenta al docente y al estudiante en la guía operativa del piloto.

### Storage de la clave

| Ambiente | Privada | Pública |
|---|---|---|
| Dev (laptop) | `attestation-keys/dev-private.pem` (commiteada al repo, **no es secreto** — clave de juguete) | `attestation-keys/dev-public.pem` (commiteada) |
| Piloto UNSL | env var `ATTESTATION_PRIVATE_KEY_PEM` o path a archivo en filesystem del VPS institucional. Generada por el director de informática UNSL **sin participación del doctorando**. | Commit en `docs/pilot/attestation-pubkey.pem` + endpoint público |

La separación dev/piloto es la línea entre "sistema funciona end-to-end en cualquier laptop" y "auditabilidad institucional real". El dev key tiene el mismo formato y algoritmo, pero un valor conocido — útil para tests y nada más.

### Deploy

- **Dev local** (`make dev`): el integrity-attestation-service corre en el mismo `docker-compose.dev.yml`, puerto 8012. Usa la dev key. Logs van a `./attestations/` (gitignored). Permite que `make test` end-to-end funcione sin red.
- **Piloto UNSL**: deploy en **VPS institucional separado** del cluster del piloto, propiedad del director de informática UNSL. Si UNSL no provee VPS, fallback a **bucket MinIO institucional** con IAM `s3:PutObject` solo para el service y `s3:GetObject` solo para auditores listados.
- **Helm**: chart separado `infrastructure/helm/integrity-attestation/` (NO incluido en el chart unificado del piloto, justamente por D3). Values mínimos: `pubkey_id`, `private_key_secret_name`, `log_dir`.

### ⚠ CRÍTICO — `replicas: 1` para el consumer

El `attestation_consumer.py` asume **single-consumer** del stream `attestation.requests`. El JSONL append-only del journal NO usa file lock explícito — depende de la atomicidad de `O_APPEND` POSIX (writes < 4KB). Si se corren **2 réplicas concurrentes** del consumer, dos firmas pueden ser appendeadas en el mismo episodio, generando duplicados en el JSONL del día.

**Mitigación**: el deployment Helm/K8s DEBE configurar `replicas: 1` para el `attestation-consumer`. Esto va en `infrastructure/helm/integrity-attestation/values-prod.yaml` cuando se redacte. Si en algún momento se necesita escalado horizontal, el rediseño correcto es: agregar lock explícito (`filelock` package) o particionar por `episode_id` (mismo patrón que `partition_worker.py` del ctr-service).

**Documentado adicionalmente** en docstring de `attestation_consumer.py` y en `journal.py` como precondición de uso.

### Endpoints del integrity-attestation-service

```
POST /api/v1/attestations
GET  /api/v1/attestations/pubkey       (devuelve la pubkey en formato PEM)
GET  /api/v1/attestations/{date}       (devuelve JSONL del día YYYY-MM-DD; auth opcional)
GET  /healthz                          (sin auth, para k8s probes)
```

**El `POST /api/v1/attestations` NO se expone públicamente al api-gateway.** Solo el ctr-service (autenticado por mTLS o IP allowlist) puede emitirlo. Esto es un servicio de **infraestructura interna del piloto**, no un endpoint del producto.

`GET /attestations/{date}` puede ser público (auditor descarga el JSONL del día sin auth, lo que tiene es público anyway: hashes y firmas que no exponen contenido del CTR).

## Consecuencias

### Positivas

- **Cumple Sección 7.3** con implementación verificable en <1 semana de trabajo.
- **Auditable por terceros**: el comité doctoral puede correr `verify-attestations.py` con la clave pública y validar cualquier rango de fechas. **Sin** cooperación del sistema en tiempo real.
- **Separación de control**: la clave privada vive en infraestructura institucional separada, no en el repo del doctorando. Eso es lo que defiende la propiedad académica.
- **CTR-safe**: `EpisodioCerrado` no cambia su payload. La invariante de reproducibilidad bit-a-bit de RN-034 / RN-036 / RN-039 / RN-040 queda intacta. La attestation es un side-channel que NO modifica eventos del CTR.
- **Operacionalmente robusto**: si el attestation service cae 6h, el cierre de episodio no se afecta. Reintento con backoff. Pendientes alarman después de 24h.
- **Verificable bit-exact**: el buffer canónico está documentado en este ADR; cualquier reimplementación en otro lenguaje (ej. un auditor que prefiera Go o Rust) puede reproducir las firmas.

### Negativas / trade-offs

- **Servicio nuevo + infraestructura nueva**: ~400 LOC del servicio + cliente/worker en ctr-service + helm + tool CLI = ~600-800 LOC totales. No trivial.
- **Dependencia institucional UNSL**: si UNSL no provee VPS o bucket separado, fallback a MinIO compartido reduce la propiedad de "registro externo independiente". **Aceptable para piloto-1, declarado como tal**. La opción C (blockchain) sería el escape si UNSL no coopera, pero se descarta por las razones de arriba.
- **Single point of trust en la institución**: si UNSL pierde el JSONL (catástrofe del VPS), se pierde toda evidencia. Mitigación: replicación nightly a otro VPS, responsabilidad institucional. **No es responsabilidad del doctorando**.
- **Velocidad de attestation**: si el integrity-attestation-service procesa con la dev key (latencia ~1ms) o con HSM (latencia ~10ms por firma), no es bottleneck. Pero si la clave vive en un HSM remoto con 100ms RTT, hay que dimensionar el throughput. Para el piloto UNSL (5 comisiones × ~30 episodios = 150 episodios/semana, ~1 attestation/hora pico), está sobredimensionado por órdenes de magnitud.
- **El verificador CLI vive en `scripts/`**, no en una herramienta separada distribuida. Para piloto-1 alcanza; producción podría querer una librería separada.

### Neutras

- **Casbin**: el integrity-attestation-service NO usa Casbin internamente (no hay autorización por rol — solo el ctr-service emite, todos pueden leer). Su autorización es a nivel red (IP allowlist).
- **`make dev`**: se agrega `integrity-attestation` al `docker-compose.dev.yml`. El servicio arranca con la dev key y escribe a `./attestations/` local.
- **Migración**: el campo del CTR `Episode.closed_at` ya existe — no hay schema change.
- **`reglas.md`**: agregar `RN-128` (o número siguiente disponible) "Cada episodio cerrado emite un attestation externo firmado con clave Ed25519 institucional. La attestation es eventualmente consistente con SLO de 24h. Su ausencia NO bloquea el cierre del episodio".

## Decisiones tomadas (2026-04-27)

Las 5 preguntas que originalmente quedaron pendientes fueron resueltas el 2026-04-27. El ADR pasa de **Propuesto** a **Aceptado**:

1. ✅ **VPS institucional separado**: UNSL provee VPS dedicado. Se descarta el fallback de MinIO con bucket aislado — la garantía de "registro externo independiente" para la tesis es más fuerte con VPS separado.

2. ✅ **Custodia de la clave privada: Director de informática UNSL** — sin participación del doctorando. Cumple el driver D3 (independencia institucional). El procedimiento operativo está en `docs/pilot/attestation-deploy-checklist.md`.

3. ✅ **Presupuesto adicional aprobado** para el VPS dedicado.

4. ✅ **SLO de attestation: 24 horas** con alerta a Grafana. 1h sería overkill operacional (ruido); 7d laxo si la auditoría es mensual. 24h da margen para caída de fin de semana sin perder evidencia. Cuando se implemente la métrica `attestation_pending_count` (agenda futura), la alerta se dispara si supera 24h sin atestar.

5. ✅ **Pubkey en ambos lugares**: URL pública institucional (`GET /api/v1/attestations/pubkey` del servicio en VPS UNSL) como **fuente canónica rotable**, + commit en `docs/pilot/attestation-pubkey.pem` como **snapshot reproducible** del período del piloto. Auditores deben verificar que ambas coinciden — discrepancia indica rotación o manipulación.

### Próximos pasos operativos

1. Director de informática UNSL ejecuta `docs/pilot/attestation-deploy-checklist.md` (genera clave Ed25519 en el VPS, distribuye solo la pubkey al doctorando, despliega el servicio).
2. Doctorando recibe la pubkey, la committea como `docs/pilot/attestation-pubkey.pem`, y verifica con `scripts/verify-attestations.py` apuntando al primer JSONL del día.
3. El `ctr-service` del piloto se configura para emitir XADD al stream Redis del VPS UNSL (env var `ATTESTATION_REDIS_URL` apuntando al VPS).

## API BC-breaks

Ninguno respecto a contratos existentes. El `EpisodioCerrado` event no cambia. Los frontends y el tutor no se enteran de la attestation. El api-gateway no expone endpoints nuevos al cliente externo.

## Tasks de implementación (orden sugerido — PR 2 a 4)

**PR 2 — Servicio nuevo `integrity-attestation-service`**:
1. `apps/integrity-attestation-service/` con estructura estándar (`src/integrity_attestation_service/`, `tests/`, `pyproject.toml`).
2. Routes: `POST /attestations`, `GET /attestations/pubkey`, `GET /attestations/{date}`, `GET /healthz`.
3. Service: `signing.py` (carga clave PEM, firma buffer canónico), `journal.py` (append a JSONL del día con file lock).
4. Worker: consumer del stream Redis `attestation.requests`. Single-consumer (un solo worker — no hay paralelismo necesario).
5. Tests unit: buffer canónico bit-exact, firma reproducible con dev key, parsing del JSONL.
6. Settings: `ATTESTATION_PRIVATE_KEY_PEM` env var, `ATTESTATION_LOG_DIR` (default `./attestations/`).
7. `infrastructure/docker-compose.dev.yml`: agregar el servicio en puerto 8012 con dev key.
8. `Makefile`: agregar el servicio a la tabla de puertos del CLAUDE.md.

**PR 3 — Hook en ctr-service para emitir attestation**:
1. En el worker que procesa `EpisodioCerrado`, después de commit transaccional a Postgres, emitir XADD a stream `attestation.requests`.
2. Idempotencia: usar `event_uuid` como `MAXLEN` key en el stream.
3. Tests integration: episodio se cierra → mensaje aparece en stream.
4. Métrica Prometheus: `ctr_attestation_emitted_total{tenant}` para visibilizar.

**PR 4 — Tool CLI `verify-attestations` + smoke test E2E + docs**:
1. `scripts/verify-attestations.py`: toma `--jsonl-dir`, `--pubkey-pem`. Itera líneas, verifica firmas, devuelve exit 0 si todo OK / 1 si alguna falla. Reporte por línea.
2. Smoke test end-to-end: arrancar dev stack, abrir+cerrar episodio, esperar 5s, leer JSONL del día, verificar con la tool.
3. `CLAUDE.md`: bumpear ADR count (17 → 18), bumpear "numerar 022+", agregar invariante "Cada episodio cerrado emite attestation Ed25519 a registro externo (eventual, SLO 24h). Buffer canónico documentado en ADR-021. Su ausencia NO bloquea el cierre".
4. `docs/pilot/protocolo-piloto-unsl.docx`: sección nueva "Auditabilidad externa" con instrucciones para el auditor (cómo descargar el JSONL, dónde está la pubkey, cómo correr la herramienta).
5. `reglas.md`: agregar `RN-128` (atestación externa).
6. `docs/SESSION-LOG.md`: entrada con la fecha de implementación.

## Referencias

- Tesis Sección 7.3 — declara el requisito.
- ADR-005 (Redis Streams) — reusamos el patrón del bus para `attestation.requests`.
- ADR-010 (append-only) — coherencia: el JSONL externo también es append-only.
- ADR-013 (OpenTelemetry) — el integrity-attestation-service emite trazas como cualquier otro servicio.
- `apps/ctr-service/src/ctr_service/workers/integrity_checker.py` — el integrity checker INTERNO no se reemplaza; sigue verificando la cadena de la DB del sistema. Es complementario, no sustituible.
- `packages/contracts/src/platform_contracts/ctr/events.py:57-65` — `EpisodioCerradoPayload` (sin cambios).
- RFC 8032 — Ed25519 specification.
- `audi1.md` G5 — auditoría que motivó este ADR (verificación empírica confirmada 2026-04-27).
