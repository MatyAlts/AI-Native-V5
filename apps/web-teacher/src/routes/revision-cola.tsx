import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { RevisionColaView } from "../views/RevisionColaView"

// `comisionId` es OPCIONAL a proposito (D8/5.3): el endpoint
// `GET /api/v1/classifications/review-queue` acepta filtrar por comision o no
// filtrar — a diferencia de otras vistas (Correcciones, Unidades) esta
// pantalla no redirige al home si falta: sin comision, muestra la cola
// entera del tenant.
const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/revision-cola")({
  validateSearch: searchSchema,
  component: function RevisionColaRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    return <RevisionColaView comisionId={comisionId} getToken={getToken} />
  },
})
