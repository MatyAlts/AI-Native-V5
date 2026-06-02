import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { EjerciciosView } from "../views/EjerciciosView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/ejercicios")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    // El banco se filtra por la materia de la comisión activa. Sin comisión
    // no hay materia → redirigimos al home a elegir una.
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function EjerciciosRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <EjerciciosView comisionId={comisionId} getToken={getToken} />
  },
})
