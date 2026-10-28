import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { PedidosAyudaView } from "../views/PedidosAyudaView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/pedidos-ayuda")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function PedidosAyudaRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <PedidosAyudaView comisionId={comisionId} getToken={getToken} />
  },
})
