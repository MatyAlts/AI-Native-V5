/**
 * Selector dropdown de comisiones para el web-admin.
 *
 * Carga la lista via `comisionesApi.list()` y notifica al parent via onChange.
 * Para superadmin/docente_admin lista TODAS las comisiones del tenant; el
 * filtrado por rol vive en el backend (Casbin).
 *
 * Uso:
 *   <ComisionPicker value={comisionId} onChange={setComisionId} />
 *
 * Reemplaza el patrón anterior de hardcodear `DEMO_COMISION_ID`. Los hooks
 * que reciben este `value` y lo pasan a un fetchFn deben memoizar el callback
 * con `useCallback(() => api.foo(comisionId), [comisionId])` para no entrar
 * en loop infinito (gotcha documentada en CLAUDE.md "Frontends React").
 */
import { type ReactNode, useEffect, useMemo, useState } from "react"
import { type Comision, comisionesApi } from "../lib/api"

interface ComisionPickerProps {
  value: string | null
  onChange: (comisionId: string | null) => void
  /** Texto del placeholder cuando no hay valor seleccionado. */
  placeholder?: string
  /** Si `true`, dispara onChange con la primera comisión al cargar — útil en
   * páginas que NO pueden renderizar sin selección. Default: false. */
  autoSelectFirst?: boolean
  className?: string
}

export function ComisionPicker({
  value,
  onChange,
  placeholder = "Seleccionar comisión…",
  autoSelectFirst = false,
  className = "",
}: ComisionPickerProps): ReactNode {
  const [items, setItems] = useState<Comision[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: fetch mount-only; meter value/onChange/autoSelectFirst causaria refetch infinito por identidad cambiante del closure del parent (CLAUDE.md "Frontends React").
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    comisionesApi
      .list({ limit: 100 })
      .then((page) => {
        if (cancelled) return
        setItems(page.data)
        if (autoSelectFirst && value === null) {
          const first = page.data[0]
          if (first !== undefined) onChange(first.id)
        }
        setLoading(false)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setError(`Error: ${e.message}`)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const options = useMemo(
    () =>
      items.map((c) => ({
        id: c.id,
        label: c.codigo,
      })),
    [items],
  )

  if (loading) {
    return (
      <span className={`text-sm text-muted-soft ${className}`} aria-busy="true">
        Cargando comisiones…
      </span>
    )
  }
  if (error) {
    return (
      <span className={`text-sm text-[var(--color-danger)] ${className}`} role="alert">
        {error}
      </span>
    )
  }
  if (items.length === 0) {
    return (
      <span className={`text-sm text-muted-soft ${className}`}>
        Sin comisiones (sembrar con `make seed-3-comisiones`)
      </span>
    )
  }

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
      className={`rounded border border-border px-3 py-1 text-sm bg-white ${className}`}
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  )
}
