import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { ExportView } from "../views/ExportView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/export")({
  validateSearch: searchSchema,
  component: function ExportRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    return (
      <ExportView getToken={getToken} {...(comisionId ? { comisionIdDefault: comisionId } : {})} />
    )
  },
})
