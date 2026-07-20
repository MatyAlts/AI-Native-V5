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

## Hecho y verificado (actualizado)

- ✅ `ClerkJWTValidator` (validator).
- ✅ **Config** (`config.py`): `auth_provider`, `clerk_base_roles`.
- ✅ **Wiring** (`main.py`): `AUTH_PROVIDER=clerk` construye el `ClerkJWTValidator`.
- ✅ **TEST con token real de Clerk**: validó firma JWKS + extrajo email + derivó user_id.
  Confirmado: `user_id` Python = `user_id` JS (mismo namespace). **El validator anda de verdad.**

## Falta para activar (en orden)

1. **Frontend — mandar el token (PRERREQUISITO):** el web-student ya manda
   `Authorization: Bearer <token>` (en su `lib/api.ts`). **El web-teacher NO** (su fetch override
   no agrega Authorization). Hay que hacer que el teacher (y admin) manden el token de Clerk
   (`window.Clerk.session.getToken()`) en cada request. **Sin esto, al activar, el teacher da 401 en todo.**
2. **Frontend — ruteo post-login:** login en `/` → si es docente (tiene comisiones en
   `/comisiones/mis`), redirigir a `/teacher/`; proteger `/teacher/` (rebotar a `/` si no es docente).
3. **Activación en prod (el switch, con cuidado):** en EasyPanel, servicio `api-gateway`, setear:
   - `AUTH_PROVIDER=clerk`
   - `JWT_ISSUER=https://keen-adder-74.clerk.accounts.dev`
   - `JWT_JWKS_URI=https://keen-adder-74.clerk.accounts.dev/.well-known/jwks.json`
   - **Dejar `DEV_TRUST_HEADERS=true` como fallback** (un request sin token cae al demo, no rompe).
   Tag de rollback antes. Redeploy del gateway. **Verificar inmediatamente que se puede entrar.**

## Riesgo clave

El paso 1 (frontend manda token) es **bloqueante**: si activás el modo Clerk sin que el front mande
el token, los requests sin token caen al demo (ok), pero el flujo docente real no funciona. Y si
apagás `DEV_TRUST_HEADERS`, un token faltante/inválido = 401 = nadie entra. Activar con
`DEV_TRUST_HEADERS=true` mitiga (fallback al demo).

## Riesgo clave

Activar la validación apagando el demo, sin test con token real, puede dejar a TODOS sin
acceso a producción. Por eso el test (paso 5) es bloqueante antes de la activación (paso 6).
