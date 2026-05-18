import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { MaterialesView } from "../views/MaterialesView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/materiales")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function MaterialesRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <MaterialesView comisionId={comisionId} getToken={getToken} />
  },
})
