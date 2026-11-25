/**
 * Ruta /mis-notas del web-student.
 *
 * Change `alumno-ve-su-nota-sin-depender-del-listado`: lista las entregas
 * de la comision del alumno directamente — no depende de `TareaSelector`
 * (que solo itera TPs `published`), asi que una TP archivada no le hace
 * perder el acceso a su nota.
 *
 * El filtro por estudiante lo hace el backend con X-User-Id; la comision se
 * resuelve dentro de la pagina (materias del alumno, con picker si cursa mas
 * de una). `comisionId` (HU-035, desde la pagina del curso) es solo la
 * seleccion inicial del picker: si no es una comision del alumno se ignora.
 */
import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { MisNotasPage } from "../pages/MisNotasPage"

const searchSchema = z.object({
  comisionId: z.string().optional().catch(undefined),
})

export const Route = createFileRoute("/mis-notas")({
  validateSearch: searchSchema,
  component: MisNotasRoute,
})

function MisNotasRoute() {
  const { comisionId } = Route.useSearch()
  return <MisNotasPage {...(comisionId ? { comisionIdInicial: comisionId } : {})} />
}
