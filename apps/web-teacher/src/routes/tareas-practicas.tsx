import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { TareasPracticasView } from "../views/TareasPracticasView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/tareas-practicas")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function TareasPracticasRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <TareasPracticasView comisionId={comisionId} getToken={getToken} />
  },
})
