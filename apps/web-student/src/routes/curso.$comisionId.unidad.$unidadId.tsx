/**
 * Ruta /curso/$comisionId/unidad/$unidadId del web-student (HU-035): una
 * unidad del campus con sus pestañas Introduccion y Trabajos practicos.
 * Ver `views/UnidadView.tsx`.
 *
 * `pestana` va en la URL (link compartible, y el "atras" del navegador vuelve
 * a la pestaña anterior). Sin `pestana` se abre la Introduccion.
 */
import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { hoyCampus } from "../lib/fechaCampus"
import { UnidadView } from "../views/UnidadView"

const searchSchema = z.object({
  pestana: z.enum(["introduccion", "tps"]).optional().catch(undefined),
})

export const Route = createFileRoute("/curso/$comisionId/unidad/$unidadId")({
  validateSearch: searchSchema,
  component: UnidadPage,
})

function UnidadPage() {
  const { comisionId, unidadId } = Route.useParams()
  const { pestana } = Route.useSearch()
  const { getToken } = Route.useRouteContext()
  return (
    <UnidadView
      comisionId={comisionId}
      unidadId={unidadId}
      pestana={pestana ?? "introduccion"}
      getToken={getToken}
      hoy={hoyCampus()}
    />
  )
}
