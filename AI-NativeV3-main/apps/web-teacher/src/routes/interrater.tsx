import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { InterraterCodingView } from "../views/InterraterCodingView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/interrater")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function InterraterRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <InterraterCodingView comisionId={comisionId} getToken={getToken} />
  },
})
