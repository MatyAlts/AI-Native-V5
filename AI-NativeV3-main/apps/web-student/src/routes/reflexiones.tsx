/**
 * Ruta /reflexiones del web-student.
 *
 * Vista de solo lectura del historial de reflexiones metacognitivas del
 * estudiante (ADR-035). Cierra el gap auditado: hasta hoy la reflexion solo
 * era visible inmediatamente post-cierre dentro de EpisodePage.tsx.
 *
 * Acceso: desde el menu de la home (boton "Mis reflexiones"). Sin search
 * params — el filtro por estudiante lo hace el backend con X-User-Id.
 */
import { createFileRoute } from "@tanstack/react-router"
import { MisReflexionesPage } from "../pages/MisReflexionesPage"

export const Route = createFileRoute("/reflexiones")({
  component: MisReflexionesPage,
})
