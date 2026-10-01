/**
 * Ruta /mis-notas del web-student.
 *
 * Change `alumno-ve-su-nota-sin-depender-del-listado`: lista las entregas
 * de la comision del alumno directamente — no depende de `TareaSelector`
 * (que solo itera TPs `published`), asi que una TP archivada no le hace
 * perder el acceso a su nota.
 *
 * Sin search params, mismo criterio que /reflexiones: el filtro por
 * estudiante lo hace el backend con X-User-Id; la comision se resuelve
 * dentro de la pagina (materias del alumno, con picker si cursa mas de una).
 */
import { createFileRoute } from "@tanstack/react-router"
import { MisNotasPage } from "../pages/MisNotasPage"

export const Route = createFileRoute("/mis-notas")({
  component: MisNotasPage,
})
