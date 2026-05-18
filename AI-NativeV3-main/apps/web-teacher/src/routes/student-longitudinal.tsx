import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { StudentLongitudinalView } from "../views/StudentLongitudinalView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
  studentId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/student-longitudinal")({
  validateSearch: searchSchema,
  component: function StudentLongitudinalRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId, studentId } = Route.useSearch()
    return (
      <div className="p-6">
        <StudentLongitudinalView
          getToken={getToken}
          {...(comisionId ? { initialComisionId: comisionId } : {})}
          {...(studentId ? { initialStudentId: studentId } : {})}
        />
      </div>
    )
  },
})
