import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { CampusView } from "../views/CampusView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/campus")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function CampusRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <CampusView comisionId={comisionId} getToken={getToken} />
  },
})
