/**
 * Tenant (universidad) que se preselecciona en el TenantSelector del alumno.
 *
 * Por que NO se usa la comision en la que esta inscripto: el cliente no tiene
 * ese dato. `GET /materias/mias` (MateriaInscripta) no trae tenant/universidad
 * y ademas es tenant-scoped (se resuelve con `x-selected-tenant`), asi que no se
 * puede consultar entre tenants antes de elegir uno. Lo que si hay:
 * `/universidades/mine` (solo universidades con inscripcion activa del alumno).
 * El backend las ordena por UUID -> el "primero" es arbitrario (QA 08/10 #16).
 *
 * Regla: ultima eleccion persistida si sigue valida; si no, alfabetico por
 * nombre (determinista).
 */
export function elegirTenantInicial(
  universidades: ReadonlyArray<{ tenant_id: string; nombre: string }>,
  persistido: string | null | undefined,
): string {
  if (persistido && universidades.some((u) => u.tenant_id === persistido)) return persistido
  const ordenadas = [...universidades].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"))
  return ordenadas[0]?.tenant_id ?? ""
}
