import { createFileRoute } from "@tanstack/react-router"
import { UsoIAView } from "../views/UsoIAView"

// Uso/costo de BYOK read-only para el docente (F11). No requiere comisionId:
// las keys son de scope tenant/facultad/materia, el docente ve las visibles.
export const Route = createFileRoute("/uso-ia")({
  component: function UsoIARoute() {
    const { getToken } = Route.useRouteContext()
    return <UsoIAView getToken={getToken} />
  },
})
