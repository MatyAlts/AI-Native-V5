/**
 * Eventos del plano académico — lado TypeScript.
 */
import { z } from "zod"

const Uuid = z.string().uuid()

const AcademicBase = z.object({
  event_uuid: Uuid,
  tenant_id: Uuid,
  ts: z.string().datetime(),
})

export const UniversidadCreada = AcademicBase.extend({
  event_type: z.literal("UniversidadCreada"),
  payload: z.object({
    universidad_id: Uuid,
    nombre: z.string(),
    codigo: z.string(),
    config_keycloak_realm: z.string(),
  }),
})
export type UniversidadCreada = z.infer<typeof UniversidadCreada>

export const ComisionCreada = AcademicBase.extend({
  event_type: z.literal("ComisionCreada"),
  payload: z.object({
    comision_id: Uuid,
    materia_id: Uuid,
    periodo_id: Uuid,
    codigo: z.string(),
    cupo_maximo: z.number().int().nonnegative(),
  }),
})
export type ComisionCreada = z.infer<typeof ComisionCreada>

export const EstudianteInscripto = AcademicBase.extend({
  event_type: z.literal("EstudianteInscripto"),
  payload: z.object({
    inscripcion_id: Uuid,
    comision_id: Uuid,
    student_pseudonym: Uuid,
    rol: z.enum(["regular", "oyente", "reinscripcion"]),
  }),
})
export type EstudianteInscripto = z.infer<typeof EstudianteInscripto>
