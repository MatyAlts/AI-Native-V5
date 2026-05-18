# Auditabilidad externa del CTR — protocolo del piloto UNSL

**Referencias**: ADR-021, RN-128, tesis Sección 7.3.

> **Nota operativa**: este documento es la **fuente Markdown editable** del contenido que va al `protocolo-piloto-unsl.docx` (sección "Auditabilidad externa"). El `.docx` se regenera con `make generate-protocol`. Cuando se regenere por cualquier motivo, el contenido de aquí debe promoverse al `generate_protocol.js`.

---

## ¿Por qué un registro externo?

La tesis declara en la Sección 7.3 que el hash final de cada episodio cerrado del CTR **se almacena en dos ubicaciones**: en la base de datos del sistema (Postgres `episodes.last_chain_hash`) y en un **registro externo auditable** independiente. La duplicación es lo que detecta manipulación del sistema mismo: si alguien con acceso root recalcula los hashes en cadena de la DB del piloto, queda evidencia en el registro externo que no controla.

Sin esto, un atacante con root podría modificar eventos del CTR + recalcular toda la cadena hash en Postgres, y la manipulación sería **indetectable desde dentro del sistema**. La propiedad de "auditabilidad externa" es contribución (i)/(ii) declarada en el abstract de la tesis.

## Diseño

| Componente | Rol |
|---|---|
| `ctr-service` (existente) | Persiste `EpisodioCerrado`. Después del commit, emite XADD a stream Redis `attestation.requests`. **Fail-soft**: si Redis cae, el cierre del episodio NO se revierte. |
| `integrity-attestation-service` (nuevo, puerto 8012) | Consumer del stream. Firma cada request con clave **Ed25519 institucional** y appendea a `attestations-YYYY-MM-DD.jsonl`. |
| `scripts/verify-attestations.py` | Tool CLI standalone para auditores. Verifica firmas bit-exact con la pubkey. |

**Flujo end-to-end** (asíncrono, eventualmente consistente — SLO 24h):

```
estudiante cierra episodio
       │
       ▼
tutor-service emite EpisodioCerrado al CTR
       │
       ▼
ctr-service worker persiste evento en Postgres ─── COMMIT ───┐
       │                                                       │
       ▼ (post-commit, NO bloquea)                              │
XADD a stream attestation.requests                              │
       │                                                       │
       ▼                                                       │
integrity-attestation-service (consumer single-worker)          │
       │                                                       │
       ├─ compute_canonical_buffer()                            │
       ├─ sign_buffer(private_key_ed25519)                      │
       ├─ append_attestation a JSONL del día                    │
       └─ XACK al stream                                        │
                                                                │
                              ┌────────────────────────────────┘
                              ▼
                       (asíncronamente)
                              │
                              ▼
                  Auditor externo:
                  python scripts/verify-attestations.py
                    --jsonl-dir <institutional-storage>
                    --pubkey-pem <pubkey>
                  → reporte OK/FAIL/duplicados
```

## Buffer canónico de firma (bit-exact)

```
canonical = f"{episode_id}|{tenant_id}|{final_chain_hash}|{total_events}|{ts_episode_closed}|{schema_version}".encode("utf-8")
```

Reglas críticas:

- Separador: `|` (U+007C, sin espacios).
- Orden de campos **fijo** (no alfabético — evitar ambigüedad si se renombran campos).
- `episode_id` y `tenant_id`: lowercase UUID con dashes.
- `final_chain_hash`: 64 hex chars lowercase.
- `total_events`: integer decimal sin separadores.
- `ts_episode_closed`: ISO-8601 UTC con sufijo `Z` (no `+00:00`).
- `schema_version`: `"1.0.0"` literal en v1.
- Encoding: UTF-8.
- `ts_attested` **NO entra en la firma** (sería trivialmente atacable).

Algoritmo de firma: **Ed25519** (RFC 8032). Justificación en ADR-021.

## Procedimiento de auditoría

### Paso 1 — Obtener la pubkey institucional

Tres fuentes válidas, en orden de preferencia:

1. **Endpoint del servicio**: `GET https://attestation.unsl.edu.ar/api/v1/attestations/pubkey`
2. **Commit en el repo**: `docs/pilot/attestation-pubkey.pem` (snapshot del período del piloto)
3. **Director de informática UNSL** (canal institucional fuera de banda)

Las tres deben coincidir. Discrepancias indican rotación o manipulación.

### Paso 2 — Obtener el journal del período auditado

```bash
# Para cada día YYYY-MM-DD del período:
curl -o attestations-YYYY-MM-DD.jsonl \
    https://attestation.unsl.edu.ar/api/v1/attestations/YYYY-MM-DD
```

O coordinar con el director de informática para acceder al storage institucional directamente.

### Paso 3 — Verificar firmas con la tool

```bash
python scripts/verify-attestations.py \
    --jsonl-dir ./attestations/ \
    --pubkey-pem ./pubkey.pem \
    --verbose
```

**Exit codes**:

- `0` — todas las firmas validan + sin duplicados sospechosos.
- `1` — al menos una firma inválida (manipulación detectada).
- `2` — error de I/O (path inválido, PEM corrupto).

**Output**:

```
Verificando con pubkey_id=<12-hex>
Directorio: ./attestations/

--- attestations-2026-04-27.jsonl ---
[OK]   episode_id=... ts_attested=... final_chain_hash=...
[OK]   episode_id=...
...

============================================================
Total attestations procesadas:  150
Firmas válidas:                  150
Firmas inválidas:                0
```

### Paso 4 — Cross-check contra la DB del CTR

Para cada attestation auditada, el auditor puede solicitar al doctorando:

```sql
SELECT id, last_chain_hash, events_count, closed_at
FROM episodes
WHERE id = '<episode_id>';
```

Y comparar:

- `last_chain_hash` (DB) vs `final_chain_hash` (attestation) — deben coincidir.
- `events_count` (DB) vs `total_events` (attestation) — deben coincidir.
- `closed_at` (DB) vs `ts_episode_closed` (attestation) — deben coincidir hasta el segundo.

Cualquier discrepancia indica manipulación de la DB del piloto **después** del cierre del episodio (porque el attestation se firmó al momento del cierre y no se puede modificar sin invalidar la firma).

## Limitaciones declaradas

1. **Pérdida de attestations en caída de Redis**: si el stream Redis estuvo caído, los attestations de episodios cerrados durante esa ventana **no se emiten**. La DB del CTR sigue íntegra, pero no hay registro externo de esos episodios. Mitigación: reconciliation job futuro (declarado como agenda en ADR-021).

2. **Pérdida del journal institucional**: si UNSL pierde el archivo JSONL (incendio del VPS, error humano), se pierde toda la evidencia externa. Es responsabilidad institucional replicar a otro VPS o storage. La tesis declara esto explícitamente.

3. **Confianza centralizada en la institución**: todo el modelo asume que UNSL custodia la clave privada y el journal de buena fe. Si UNSL coordinara con el doctorando para falsear evidencia, la propiedad se rompe. Mitigación: la separación de roles (clave generada por director de informática, journal en VPS institucional, código del doctorando) hace ese coordinamiento operacionalmente difícil pero no imposible. Para garantías criptográficas independientes de la institución, el ADR-021 deja como agenda futura migrar a OpenTimestamps (anclar a Bitcoin) o Certificate Transparency log.

4. **Patrones regex de buffer canónico no validados por terceros**: un auditor que reimplemente la verificación en Go o Rust debe seguir bit-exact las reglas del ADR-021. Una desviación (ej. cambiar `|` por `,` o reordenar campos) invalida la verificación. Mitigación: tests golden con firma reproducible (`6333bee9...ad1606`) en `apps/integrity-attestation-service/tests/unit/test_signing.py`.

## Smoke test del flujo

Para verificar que el servicio está vivo y firma correctamente:

```bash
# Levantar el servicio (en otra terminal)
uv run uvicorn integrity_attestation_service.main:app --port 8012 --reload

# Correr el smoke test
scripts/smoke-test-attestation.sh
```

El script valida los 6 puntos del flow: health, pubkey, POST válido, POST inválido (422), GET JSONL del día, y verificación criptográfica con la tool CLI.
