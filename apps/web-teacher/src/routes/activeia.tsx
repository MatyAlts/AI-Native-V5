import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { ActiveIAView } from "../views/ActiveIAView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/activeia")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function ActiveIARoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <ActiveIAView comisionId={comisionId} getToken={getToken} />
  },
})
