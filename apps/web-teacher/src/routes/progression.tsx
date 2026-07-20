import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { ProgressionView } from "../views/ProgressionView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/progression")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      // Sin comision -> volver a la home (lista de cohortes). Resuelve F8 del
      // brief docente: el EmptyHero clonado se elimina; el flujo correcto
      // es entrar desde "Abrir cohorte" en la home.
      throw redirect({ to: "/" })
    }
  },
  component: function ProgressionRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <ProgressionView comisionId={comisionId} getToken={getToken} />
  },
})
