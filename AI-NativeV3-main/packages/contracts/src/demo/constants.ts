/**
 * Constantes del piloto demo (UNSL).
 *
 * Estos UUIDs se usan tanto desde frontends en dev mode (cuando
 * Keycloak no tiene el realm onboardeado) como desde scripts/seeds.
 * Vivían duplicados en cada `apps/web-*` antes de F10 — moverlos acá
 * evita que un cambio de UUID demo obligue a tocar N archivos.
 *
 * En prod (F9 con Keycloak federation), el `comision_id` lo trae el
 * claim `comisiones_activas` del JWT y NO se usa el constante.
 */

/**
 * Comisión demo del piloto UNSL. Coincide con el UUID que crean
 * `scripts/seed-demo-data.py` y `scripts/seed-3-comisiones.py`
 * (comision A-Mañana). El selector real lo sobreescribe apenas el
 * backend devuelve `usuarios_comision` con datos.
 */
export const DEMO_COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

/**
 * Tenant demo (UNSL) — coincide en string con la comisión por
 * convención de los seeds, pero conceptualmente es distinto.
 * Mantener separado para que un futuro split de UUIDs no rompa nada.
 */
export const DEMO_TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
