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
import { useEffect, useState } from "react"
import { type Comision, comisionesApi } from "../lib/api"

const LS_KEY = "selectedComisionId"

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
  if (c.nombre.length > 0) return c.nombre
  return c.codigo
}

/**
 * Hook para resolver `comisionId` → label visible (`nombre || codigo`) sin
 * exponer UUIDs raw en subtítulos. Carga la lista de comisiones del usuario
 * y cachea localmente en el state del componente. Mientras la lista no
 * llegó, devuelve el slice del UUID como fallback inicial — evita layout
 * shift y nunca rompe la página.
 */
export function useComisionLabel(comisionId: string): string {
  const [label, setLabel] = useState<string>(`${comisionId.slice(0, 8)}...`)
  useEffect(() => {
    let cancelled = false
    comisionesApi
      .listMine()
      .then((res) => {
        if (cancelled) return
        const c = res.items.find((x) => x.id === comisionId)
        if (c) setLabel(comisionLabel(c))
      })
      .catch(() => {
        /* mantener fallback UUID slice — degradación graciosa */
      })
    return () => {
      cancelled = true
    }
  }, [comisionId])
  return label
}

export function ComisionSelector({ value, onChange }: Props) {
  const [comisiones, setComisiones] = useState<Comision[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // mount-only fetch — value/onChange se leen una sola vez para sembrar la elección
  // recordada en localStorage; añadirlas refetcharía las comisiones cada vez que el
  // padre cambia el valor seleccionado.
  // biome-ignore lint/correctness/useExhaustiveDependencies: value — ver comentario arriba.
  // biome-ignore lint/correctness/useExhaustiveDependencies: onChange — ver comentario arriba.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    comisionesApi
      .listMine()
      .then((res) => {
        if (cancelled) return
        setComisiones(res.items)
        // Auto-pick: si el padre todavía no eligió, intentamos primero el
        // último valor recordado en localStorage; si no hay (o es stale),
        // caemos a la primera comisión del listado para que la pantalla
        // arranque con datos en vez de un void.
        if (!value && res.items.length > 0) {
          const stored = localStorage.getItem(LS_KEY)
          if (stored && res.items.some((c) => c.id === stored)) {
            onChange(stored)
          } else {
            const first = res.items[0]
            if (first) onChange(first.id)
          }
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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
        Error cargando comisiones: <span className="font-mono">{error}</span>
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
