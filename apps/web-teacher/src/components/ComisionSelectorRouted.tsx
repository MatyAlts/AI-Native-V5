/**
 * Wrapper de ComisionSelector que persiste el valor en URL search params
 * (?comisionId=X) en vez de localStorage. Hace shareable la URL.
 *
 * Si el path actual no admite `comisionId` (ej. /templates, /kappa), el
 * componente igual muestra el selector pero su valor solo afecta a futuras
 * navegaciones, no al estado actual.
 *
 * Para que el auto-pick del selector siga funcionando aunque la fuente de
 * verdad sea la URL, persistimos también en localStorage al cambiar — el
 * selector "interno" se autodescubre desde ese mismo storage en el primer
 * mount.
 */
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { useCallback } from "react"
import { ComisionSelector } from "./ComisionSelector"

const LS_KEY = "selectedComisionId"

export function ComisionSelectorRouted() {
  const navigate = useNavigate()
  // El tipo de `state.location.search` en TanStack Router depende de la ruta
  // activa. Como este selector vive en `__root` (no atado a una ruta concreta),
  // tratamos el search como genérico Record para extraer `comisionId` opcional.
  const search = useRouterState({
    select: (s) => s.location.search as Record<string, unknown>,
  })
  const currentComisionId = typeof search.comisionId === "string" ? search.comisionId : null

  const handleChange = useCallback(
    (newId: string | null) => {
      if (newId) localStorage.setItem(LS_KEY, newId)
      navigate({
        search: ((prev: Record<string, unknown>) => ({
          ...prev,
          comisionId: newId ?? undefined,
          // biome-ignore lint/suspicious/noExplicitAny: search update dinámico — el tipo es por-ruta
        })) as any,
      })
    },
    [navigate],
  )

  return <ComisionSelector value={currentComisionId} onChange={handleChange} />
}
