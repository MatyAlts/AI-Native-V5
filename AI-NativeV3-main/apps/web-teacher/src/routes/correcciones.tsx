import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { CorreccionesView } from "../views/CorreccionesView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/correcciones")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function CorreccionesRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <CorreccionesView comisionId={comisionId} getToken={getToken} />
  },
})
