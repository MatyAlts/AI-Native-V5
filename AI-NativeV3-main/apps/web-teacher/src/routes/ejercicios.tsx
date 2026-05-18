import { createFileRoute } from "@tanstack/react-router"
import { EjerciciosView } from "../views/EjerciciosView"

export const Route = createFileRoute("/ejercicios")({
  component: function EjerciciosRoute() {
    const { getToken } = Route.useRouteContext()
    return <EjerciciosView getToken={getToken} />
  },
})
