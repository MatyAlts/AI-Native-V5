# ADR-038 — BYOK: encriptación AES-GCM + master key por env var

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez
- **Tags**: seguridad, crypto, secrets, byok
- **Epic**: ai-native-completion-and-byok / Sec 1-7

## Contexto y problema

El piloto necesita BYOK (Bring-Your-Own-Key): el admin institucional
configura keys de Anthropic/Gemini/Mistral con scope (tenant/facultad/materia)
desde web-admin. La key plaintext **no puede vivir en disco** — hay que
encriptar at-rest. Tres opciones:

1. **DB encriptada (AES-GCM con master key por env var)**.
2. **K8s SealedSecrets**: la key se encripta con la pubkey del controller;
   solo el cluster puede desencriptar.
3. **Vault / KMS**: servicio dedicado que provee desencriptacion on-demand.

## Drivers de la decisión

- **UX del admin**: el req critico para defensa es "el admin academico
  rota keys desde la web". K8s SealedSecrets requiere `kubectl` + RBAC —
  barrera de adopcion. Vault requiere infra dedicada.
- **Recursos del piloto-1**: no hay sysadmin dedicado.
- **Auditabilidad doctoral**: el comite necesita ver que las keys estan
  encriptadas at-rest (defensa: AES-256-GCM con master key separada de
  la DB).
- **Migracion futura**: si compliance UNSL pide Vault en piloto-2, se
  migra (la API publica de `crypto.py` no cambia — el adapter detras
  cambia).

## Decisión

**A — DB encriptada con AES-256-GCM + master key por env var**.

Helper compartido: `packages/platform-ops/src/platform_ops/crypto.py`
con `encrypt(plaintext, master_key) -> bytes` y `decrypt(...) -> bytes`.

Master key:
- 32 bytes random (AES-256).
- Vive en env var `BYOK_MASTER_KEY` (base64 encoded).
- Generar con `openssl rand -base64 32`.
- Solo el ai-gateway (caller principal del resolver) la necesita.

Storage:
- Tabla `byok_keys.encrypted_value BYTEA` (formato `nonce(12) || ct+tag`).
- Tabla `byok_keys_usage` para budget tracking mensual.
- Ambas con RLS por `tenant_id` + UNIQUE parcial
  `(tenant_id, scope_type, scope_id, provider) WHERE revoked_at IS NULL`.

## Consecuencias

### Positivas

- Admin rota keys desde web-admin en piloto-1 (UX → defensa).
- AES-GCM provee confidencialidad + integridad (tampering detectado).
- El helper `crypto.py` esta cubierto por 10 tests unitarios:
  round-trip, tampering del ciphertext, master key incorrecta,
  nonce fresh por encryption, master key de tamano incorrecto rechazado.
- Defensa testeada: el helper NO loguea plaintext ni master key.

### Negativas / trade-offs

- **Master key compromise**: si la env var del pod se filtra, todas las
  BYOK keys quedan expuestas. Mitigacion: pod isolation (Helm secret),
  audit log de accesos al pod (Loki), rotacion anual o tras incidente.
- **Master key rotation requiere downtime ~30s**: procedimiento operacional
  documentado en `docs/pilot/runbook.md` (5 steps: generar nueva master,
  leer todas las keys con la vieja, re-encriptar, commit, rotar env var,
  restart). NO automatica.
- **Sin separacion de duties**: el sysadmin del cluster puede leer la
  master key (env var). Vault/KMS lo evitarian — diferido a piloto-2.

## Rollback

Feature flag `BYOK_ENABLED=false` desactiva el resolver y fuerza fallback
a env var legacy (`ANTHROPIC_API_KEY`, etc.). Migracion Alembic reversible
(`downgrade()` drops las tablas).

## Referencias

- Helper: `packages/platform-ops/src/platform_ops/crypto.py`
- Tests: `packages/platform-ops/tests/test_crypto.py`
- Migracion: `apps/academic-service/alembic/versions/20260504_0002_add_byok_keys.py`
- Resolver: `apps/ai-gateway/src/ai_gateway/services/byok.py`
- Spec: `openspec/changes/ai-native-completion-and-byok/specs/byok-multiprovider/spec.md`
- ADR-039 — Resolver jerarquico (consumidor de este ADR).
