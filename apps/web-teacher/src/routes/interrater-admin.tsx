import { createFileRoute } from "@tanstack/react-router"
import { InterraterAdminView } from "../views/InterraterAdminView"

export const Route = createFileRoute("/interrater-admin")({
  component: function InterraterAdminRoute() {
    const { getToken } = Route.useRouteContext()
    return <InterraterAdminView getToken={getToken} />
  },
})
