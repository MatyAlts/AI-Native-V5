/**
 * Identidad del estudiante en modo dev (sin Keycloak).
 *
 * En produccion el `student_pseudonym` lo provee el JWT como sub claim.
 * En dev, el `vite.config.ts` inyecta este mismo UUID como header
 * `X-User-Id` para el api-gateway, y los componentes del frontend leen
 * esta constante para resolver "quien soy" sin tener acceso al header
 * (porque vive del lado del proxy server).
 *
 * IMPORTANTE: si cambias este UUID, **tambien hay que cambiar
 * `apps/web-student/vite.config.ts` -> `setDefault("x-user-id", ...)`**
 * para mantener consistencia. Test cases que cambian el seed pueden
 * requerir actualizar ambos.
 */
export const STUDENT_PSEUDONYM_DEV = "e19354fb-c05a-4535-a0bf-a7d3ea09692d"
