import { useEffect, useState } from "react"
import { SELECTED_TENANT_STORAGE_KEY } from "../main"

interface Universidad {
  id: string
  tenant_id: string
  nombre: string
  codigo: string
}

/**
 * Dropdown del header alumno para cambiar de universidad activa.
 *
 * Mismo patrón que el TenantSelector del admin y del docente. Por
 * limitación del piloto actual, el alumno solo está realmente inscripto
 * en una comisión por universidad — al cambiar de tenant, las "Mis
 * materias" se recalcula filtrando por inscripciones del tenant nuevo.
 */
export function TenantSelector() {
  const [universidades, setUniversidades] = useState<Universidad[]>([])
  const [selected, setSelected] = useState<string>(
    () => localStorage.getItem(SELECTED_TENANT_STORAGE_KEY) ?? "",
  )
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetch("/api/v1/universidades/mine?limit=100")
      .then((r) => r.json())
      .then((body: { data: Universidad[] }) => {
        if (cancelled) return
        setUniversidades(body.data ?? [])
        if (!selected && body.data?.[0]) {
          const first = body.data[0].tenant_id
          setSelected(first)
          localStorage.setItem(SELECTED_TENANT_STORAGE_KEY, first)
        }
      })
      .catch(() => {
        /* best-effort */
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const tenantId = e.target.value
    setSelected(tenantId)
    localStorage.setItem(SELECTED_TENANT_STORAGE_KEY, tenantId)
    // Volver al home y limpiar query params: los ids del tenant viejo
    // (materiaId, comisionId) son inválidos para el tenant nuevo.
    window.location.replace(window.location.origin + "/")
  }

  if (loading || universidades.length <= 1) {
    return null
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
        Universidad
      </span>
      <select
        value={selected}
        onChange={handleChange}
        className="text-xs bg-white text-ink border border-border rounded px-2 py-1 cursor-pointer focus:outline-none"
      >
        {universidades.map((u) => (
          <option key={u.tenant_id} value={u.tenant_id}>
            {u.codigo}
          </option>
        ))}
      </select>
    </div>
  )
}
