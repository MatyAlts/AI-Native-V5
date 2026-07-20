import { createFileRoute } from "@tanstack/react-router"
import { HomeView } from "../views/HomeView"

// Home del docente: lista densa de comisiones con KPIs en strip inline.
// Reemplaza el redirect viejo a /tareas-practicas (shape docente, brief D1).
export const Route = createFileRoute("/")({
  component: function HomeRoute() {
    const { getToken } = Route.useRouteContext()
    return (
      <div className="p-6">
        <HomeView getToken={getToken} />
      </div>
    )
  },
})
