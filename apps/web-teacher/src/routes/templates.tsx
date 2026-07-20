import { createFileRoute } from "@tanstack/react-router"
import { TemplatesView } from "../views/TemplatesView"

export const Route = createFileRoute("/templates")({
  component: function TemplatesRoute() {
    const { getToken } = Route.useRouteContext()
    return <TemplatesView getToken={getToken} />
  },
})
