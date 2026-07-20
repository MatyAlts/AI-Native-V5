/**
 * Ruta /instrumentos-cohorte del web-teacher.
 *
 * Lectura agregada por cohorte de los 3 instrumentos del diseno cuasi-
 * experimental (P2-1/2/3 del PlanMejora.md). Aplica k-anonymity gate
 * (MIN_STUDENTS_FOR_COHORT_SUMMARY=5) — degrada gracilmente a
 * "Datos insuficientes" cuando hay <5 respondientes.
 *
 * Mismo patron que /progression: requiere ?comisionId=... como search param.
 * Sin comision -> redirect a /.
 *
 * ADR de respaldo: ADR-053.
 */
import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { InstrumentosCohorteView } from "../views/InstrumentosCohorteView"

const searchSchema = z.object({
  comisionId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/instrumentos-cohorte")({
  validateSearch: searchSchema,
  beforeLoad: ({ search }) => {
    if (!search.comisionId) {
      throw redirect({ to: "/" })
    }
  },
  component: function InstrumentosCohorteRoute() {
    const { getToken } = Route.useRouteContext()
    const { comisionId } = Route.useSearch()
    if (!comisionId) return null
    return <InstrumentosCohorteView comisionId={comisionId} getToken={getToken} />
  },
})
