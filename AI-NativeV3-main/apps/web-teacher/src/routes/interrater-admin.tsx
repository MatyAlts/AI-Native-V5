import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { InterraterAdminView } from "../views/InterraterAdminView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/interrater-admin")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function InterraterAdminRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <InterraterAdminView comisionId={comisionId} getToken={getToken} />
  },
})
