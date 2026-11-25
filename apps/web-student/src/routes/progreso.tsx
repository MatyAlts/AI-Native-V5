/**
 * Ruta /progreso del web-student (F9).
 *
 * Vista de solo lectura de la progresion pedagogica longitudinal del alumno:
 * trayectoria de apropiacion en tareas analogas (CII), episodios y señales
 * pedagogicas vs cohorte. El pseudonimo lo resuelve la pagina
 * (getCurrentUserUuid con fallback al /student/me/episodes). `comisionId`
 * (HU-035, desde la pagina del curso) es solo la seleccion inicial del
 * selector de comision: si no es una comision del alumno se ignora.
 */
import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { MiProgresoPage } from "../pages/MiProgresoPage"

const searchSchema = z.object({
  comisionId: z.string().optional().catch(undefined),
})

export const Route = createFileRoute("/progreso")({
  validateSearch: searchSchema,
  component: ProgresoRoute,
})

function ProgresoRoute() {
  const { comisionId } = Route.useSearch()
  return <MiProgresoPage {...(comisionId ? { comisionIdInicial: comisionId } : {})} />
}
