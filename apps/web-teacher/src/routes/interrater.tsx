import { createFileRoute } from "@tanstack/react-router"
import { InterraterView } from "../views/InterraterCodingView"

export const Route = createFileRoute("/interrater")({
  component: function InterraterRoute() {
    const { getToken } = Route.useRouteContext()
    return <InterraterView getToken={getToken} />
  },
})
