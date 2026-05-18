import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { CohortQuartilesView } from "../views/CohortQuartilesView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/cohort-quartiles")({
  validateSearch: searchSchema,
  component: function CohortQuartilesRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    return (
      <div className="p-6">
        <CohortQuartilesView
          getToken={getToken}
          {...(comisionId ? { initialComisionId: comisionId } : {})}
        />
      </div>
    )
  },
})
