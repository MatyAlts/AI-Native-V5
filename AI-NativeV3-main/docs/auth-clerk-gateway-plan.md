# Auth real con Clerk en el api-gateway — plan de activación

**Estado:** núcleo backend implementado y verificado en `desarrollo`. NO activado en
producción (el gateway sigue en modo demo). Este doc deja todo listo para retomar.

## Visión (decidida con Juani)

- **Login único** con Clerk para todos (misma entrada).
- **Default: alumno.** Todos arrancan viendo el panel alumno.
- **El admin promueve un correo a docente** (asignándolo a una comisión por email →
  `usuarios_comision`). Ese usuario pasa a ver el panel docente y se le asigna su comisión.
- **Rol dinámico por DB:** docente = su identidad está en `usuarios_comision`; alumno = si no.
- **Ruteo post-login:** login en `/` (alumno) → si es docente, redirige a `/teacher/`;
  `/teacher/` protegido (rebota a `/` si no es docente).

## Datos de Clerk (ya obtenidos)

- Issuer: `https://keen-adder-74.clerk.accounts.dev`
- JWKS:   `https://keen-adder-74.clerk.accounts.dev/.well-known/jwks.json` (RS256, responde 200)
- Publishable key (prod): `pk_test_a2Vlbi1hZGRlci03NC5jbGVyay5hY2NvdW50cy5kZXYk`
- **Email en el token:** configurado en Clerk → Customize session token con
  `{ "email": "{{user.primary_email_address}}" }` (necesario para el matching docente).

## Hecho (en `desarrollo`)

- `ClerkJWTValidator` en `apps/api-gateway/src/api_gateway/services/jwt_validator.py`:
  valida firma JWKS de Clerk, NO exige `aud`, deriva `user_id = uuid5(sub, NAMESPACE)`,
  toma `email` del claim, `tenant_id` fijo, `roles` base.
- **VERIFICADO:** el `user_id` derivado en backend (Python `uuid5`) coincide bit-a-bit con
  el del frontend (JS `uuidv5`), mismo namespace `8f9d2c4a-7b1e-5d3f-9a8c-1e2b3c4d5e6f`.
  (Sin esto el docente no veria sus datos — es la pieza critica y esta OK).

## Falta para activar (en orden)

1. **Config (`config.py` del gateway):** vars para issuer/jwks de Clerk + tenant fijo + roles base.
2. **Wiring (`main.py`):** construir `ClerkJWTValidator` cuando esas vars estén; sino, comportamiento actual (demo).
3. **Fallback seguro (decidir):** que un token Clerk inválido NO tire 401 sino caiga al demo
   durante la transición — o aceptar que apagar el demo es el switch (más riesgoso).
4. **Frontend:** asegurar que web-teacher manda `Authorization: Bearer <token>` (el student ya lo hace);
   ruteo post-login (login en `/` → `/teacher/` si docente; proteger `/teacher/`).
5. **TEST con token real de Clerk** (capturar un session token real de una sesión logueada y
   validarlo localmente contra el `ClerkJWTValidator`) — NO activar en prod sin esto.
6. **Activación en prod:** setear las env vars en EasyPanel (gateway), tag de rollback, verificar
   inmediatamente que se puede entrar. Riesgo: si el JWT falla, NADIE entra → revertir env var.

## Riesgo clave

Activar la validación apagando el demo, sin test con token real, puede dejar a TODOS sin
acceso a producción. Por eso el test (paso 5) es bloqueante antes de la activación (paso 6).
