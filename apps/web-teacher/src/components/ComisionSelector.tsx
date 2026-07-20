/**
 * Selector de comisión para el docente.
 *
 * Lista las comisiones donde el user tiene rol activo (vía
 * `usuarios_comision`) y persiste la elección en localStorage. La
 * primera vez en una sesión, si hay valor previo en localStorage lo
 * propagamos vía onChange para que el padre arranque con la última
 * elección.
 *
 * F9: cuando exista federación Keycloak con claim `comisiones_activas`,
 * podremos prefiltrar el listado o saltar el selector si el user tiene
 * una sola comisión.
 */
import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { type Comision, comisionesApi } from "../lib/api"

const LS_KEY = "selectedComisionId"

/**
 * Query key estable y compartible para la lista de comisiones del docente.
 * El selector de comisión es estado global (vive en el sidebar y varias
 * vistas lo consumen), así que todos los consumidores comparten esta key
 * para que TanStack Query cachee el resultado una sola vez (staleTime 60s en
 * `main.tsx`) en vez de refetchear por componente. Al ser la misma key, el
 * `useComisionLabel` y el `<ComisionSelector>` reusan la misma entrada.
 */
const COMISIONES_QUERY_KEY = ["comisiones-mias"] as const

interface Props {
  value: string | null
  onChange: (comisionId: string) => void
}

/**
 * Devuelve el label visible para una comisión: prioriza `nombre` y cae a
 * `codigo` si por algún motivo viniera vacío (defensivo — el backend lo
 * declara NOT NULL, ver `ComisionBase` en academic-service). Sin UUID
 * truncado.
 */
export function comisionLabel(c: Comision): string {
  const comision = c.nombre.length > 0 ? c.nombre : c.codigo
  // Prefijar la materia (Prog 1 / Prog 2) para distinguir comisiones de
  // distintas materias. Si el backend no la mandó, cae al nombre solo.
  const materia = c.materia_nombre || c.materia_codigo
  return materia ? `${materia} · ${comision}` : comision
}

/**
 * Hook para resolver `comisionId` → label visible (`nombre || codigo`) sin
 * exponer UUIDs raw en subtítulos. Lee la lista de comisiones del usuario
 * desde la cache compartida de TanStack Query (misma key que el selector, así
 * no dispara un fetch propio si el selector ya la trajo). Mientras la lista
 * no llegó o falló, devuelve el slice del UUID como fallback — evita layout
 * shift, nunca rompe la página y degrada graciosamente ante error.
 */
export function useComisionLabel(comisionId: string): string {
  const { data } = useQuery({
    queryKey: COMISIONES_QUERY_KEY,
    queryFn: () => comisionesApi.listMine(),
  })
  const c = data?.items.find((x) => x.id === comisionId)
  return c ? comisionLabel(c) : `${comisionId.slice(0, 8)}...`
}

export function ComisionSelector({ value, onChange }: Props) {
  const {
    data,
    isPending: loading,
    error,
  } = useQuery({
    queryKey: COMISIONES_QUERY_KEY,
    queryFn: () => comisionesApi.listMine(),
  })
  const comisiones: Comision[] | null = data?.items ?? null

  // Auto-pick: cuando llega la lista y el padre todavía no eligió, sembramos
  // la selección — primero el último valor recordado en localStorage, y si no
  // hay (o quedó stale) caemos a la primera comisión, para que la pantalla
  // arranque con datos en vez de un void. Corre en efecto (no en la queryFn)
  // para no meter side-effects en el fetch; el guard `value` lo vuelve idempotente
  // una vez que el padre confirma la elección.
  useEffect(() => {
    if (value || !comisiones || comisiones.length === 0) return
    const stored = localStorage.getItem(LS_KEY)
    if (stored && comisiones.some((c) => c.id === stored)) {
      onChange(stored)
    } else {
      const first = comisiones[0]
      if (first) onChange(first.id)
    }
  }, [comisiones, value, onChange])

  // Persistir cualquier cambio de selección externa o interna.
  useEffect(() => {
    if (value) localStorage.setItem(LS_KEY, value)
  }, [value])

  function handleSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value
    if (!id) return
    localStorage.setItem(LS_KEY, id)
    onChange(id)
  }

  if (loading) {
    return <div className="text-xs text-muted px-3 py-2">Cargando comisiones...</div>
  }

  if (error) {
    return (
      <div className="text-xs text-danger px-3 py-2">
        Error cargando comisiones: <span className="font-mono">{String(error)}</span>
      </div>
    )
  }

  if (!comisiones || comisiones.length === 0) {
    return (
      <div className="text-xs text-muted px-3 py-2">
        No tenés comisiones asignadas. Pedile al admin que te agregue a una comisión.
      </div>
    )
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted dark:text-muted-soft">Comisión:</span>
      <select
        value={value ?? ""}
        onChange={handleSelect}
        className="rounded border border-border bg-surface text-ink px-2 py-1 text-sm focus:outline-none focus:border-accent-brand focus:ring-1 focus:ring-accent-brand/30"
      >
        <option value="" disabled>
          Seleccioná una comisión
        </option>
        {comisiones.map((c) => (
          <option key={c.id} value={c.id}>
            {comisionLabel(c)}
          </option>
        ))}
      </select>
    </label>
  )
}
