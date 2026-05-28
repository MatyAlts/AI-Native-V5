/**
 * Hook que trae el mapping student_pseudonym -> {full_name, email} de una
 * comision. Lo usan ProgressionView, CohortAdversarialView y
 * StudentLongitudinalView para mostrar nombres reales en lugar de
 * `Est. xxxxxx`.
 *
 * Los nombres se auto-llenan cuando el alumno se loguea con Clerk en el
 * web-student (POST /api/v1/users/me/profile). Si un alumno no se logueo
 * todavia, su pseudonym no aparece en el mapping y la UI cae al fallback.
 */

import { useEffect, useState } from "react"

import { listStudentProfiles } from "../lib/api"

type TokenGetter = () => Promise<string | null>

export function useStudentProfiles(
  comisionId: string | null | undefined,
  getToken?: TokenGetter,
): Map<string, string> {
  const [map, setMap] = useState<Map<string, string>>(new Map())

  useEffect(() => {
    if (!comisionId) {
      setMap(new Map())
      return
    }
    let cancelled = false
    listStudentProfiles(comisionId, getToken)
      .then((profiles) => {
        if (cancelled) return
        const m = new Map<string, string>()
        for (const p of profiles) {
          if (p.full_name) m.set(p.student_pseudonym, p.full_name)
        }
        setMap(m)
      })
      .catch(() => {
        /* silencioso: la UI cae al `Est. xxxxxx` fallback */
      })
    return () => {
      cancelled = true
    }
  }, [comisionId, getToken])

  return map
}
