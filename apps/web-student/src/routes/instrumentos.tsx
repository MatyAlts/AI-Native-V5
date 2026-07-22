/**
 * Ruta /instrumentos del web-student.
 *
 * Acceso a los 3 instrumentos del diseno cuasi-experimental (P2-1 pretest,
 * P2-2 cuestionario IA previa, P2-3 test transferencia) del PlanMejora.md.
 *
 * Requiere `?comisionId=...` como search param para saber a que cohorte
 * pertenecen las respuestas. Sin comisionId, redirige a /.
 *
 * El `studentPseudonym` viene del dev-user en dev mode; en prod viene del
 * JWT sub claim (mismo pattern que el resto del web-student).
 *
 * ADR de respaldo: ADR-053.
 */
import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { STUDENT_PSEUDONYM_DEV } from "../lib/dev-user"
import { InstrumentosPage } from "../pages/InstrumentosPage"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/instrumentos")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      // Sin comision no podemos persistir respuestas con tenant_id correcto.
      // El estudiante debe entrar desde el menu de su materia.
      throw redirect({ to: "/" })
    }
  },
  component: function InstrumentosRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return (
      <InstrumentosPage
        comisionId={comisionId}
        studentPseudonym={STUDENT_PSEUDONYM_DEV}
        getToken={getToken}
      />
    )
  },
})
