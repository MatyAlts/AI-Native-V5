# Dev keys del integrity-attestation-service

**ADR-021** — registro externo auditable del CTR.

## ⚠️ DEV ONLY — NO USAR EN PRODUCCION

Estas claves Ed25519 son **publicas, commiteadas al repo, NO secretas**. Existen para que `make dev` y la suite de tests funcionen sin coordinación institucional ni red.

- `dev-private.pem` — clave privada Ed25519 (PKCS8). **Cualquiera con el repo la tiene.** No firma nada de valor.
- `dev-public.pem` — clave pública correspondiente.

El `signer_pubkey_id` derivado (SHA-256 truncado de la pubkey) es **estable y conocido** — los tests de `signing.py` lo asumen.

## Regeneración determinista

Las claves se derivan de un seed fijo (`AI-NativeV3-DEV-ATTESTATION-KEY1`, 32 bytes). Cualquiera que borre estos archivos y corra:

```bash
cd apps/integrity-attestation-service
uv run python dev-keys/regenerate.py
```

obtiene **exactamente las mismas claves**. Eso garantiza:

1. Tests con golden firmas son reproducibles.
2. El `signer_pubkey_id` es estable entre máquinas.
3. Si alguien las modifica accidentalmente, regenerar restaura el estado.

## Producción (piloto UNSL)

En producción, el deploy debe:

1. Setear env var `ATTESTATION_PRIVATE_KEY_PATH` apuntando al PEM de la clave institucional (NO esta).
2. Setear env var `ATTESTATION_PUBLIC_KEY_PATH` correspondientemente.
3. Setear env var `ENVIRONMENT=production`.

El servicio en startup verifica que la pubkey activa **NO sea la dev key** cuando `environment=production`. Si lo es, falla fast — protección contra deploy accidental con clave de juguete.

La clave institucional la genera el director de informática UNSL, sin participación del doctorando (D3 del ADR-021 — independencia institucional).

## Por qué Ed25519

Tabla comparativa en ADR-021. Resumen: claves chicas (32 bytes), firmas chicas (64 bytes), 70k firmas/seg, sin footguns conocidos, soporte nativo en `cryptography` de Python.
