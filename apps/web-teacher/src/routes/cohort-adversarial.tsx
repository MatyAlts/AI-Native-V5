import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { CohortAdversarialView } from "../views/CohortAdversarialView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/cohort-adversarial")({
  validateSearch: searchSchema,
  component: function CohortAdversarialRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    return (
      <div className="p-6">
        <CohortAdversarialView
          getToken={getToken}
          {...(comisionId ? { initialComisionId: comisionId } : {})}
        />
      </div>
    )
  },
})
