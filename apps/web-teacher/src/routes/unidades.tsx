import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { UnidadesView } from "../views/UnidadesView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/unidades")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function UnidadesRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <UnidadesView comisionId={comisionId} getToken={getToken} />
  },
})
