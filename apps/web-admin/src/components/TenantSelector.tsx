import { useEffect, useState } from "react"
import { SELECTED_TENANT_STORAGE_KEY } from "../constants"

interface Universidad {
  id: string
  tenant_id: string
  nombre: string
  codigo: string
}

/**
 * Dropdown del header admin para seleccionar bajo qué tenant operar.
 *
 * El admin del piloto tiene rol superadmin → puede ver TODAS las
 * universidades (policy `superadmin_view_all`). Al elegir una, guardamos
 * su `tenant_id` en localStorage, que el monkey-patch de `window.fetch`
 * en `main.tsx` inyecta como header `x-selected-tenant` en todo call a
 * `/api/*`. El proxy de Vite lo propaga al api-gateway como X-Tenant-Id.
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
        // Si no había selección, default a la primera (UTN normalmente).
        if (!selected && body.data?.[0]) {
          const first = body.data[0].tenant_id
          setSelected(first)
          localStorage.setItem(SELECTED_TENANT_STORAGE_KEY, first)
        }
      })
      .catch(() => {
        /* best-effort: el header default del proxy nos cubre */
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
    // Volver al home y limpiar query params: ids específicos del tenant
    // viejo (comisionId, etc.) son inválidos para el tenant nuevo.
    window.location.replace(window.location.origin + "/")
  }

  if (loading) {
    return (
      <div className="text-xs text-muted px-3 py-1.5">Cargando universidades…</div>
    )
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border bg-surface">
      <label className="text-[10px] font-semibold uppercase tracking-wider text-muted">
        Universidad activa
      </label>
      <select
        value={selected}
        onChange={handleChange}
        className="text-sm bg-surface text-ink border-none focus:outline-none focus:ring-0 cursor-pointer"
      >
        {universidades.map((u) => (
          <option key={u.tenant_id} value={u.tenant_id}>
            {u.nombre} ({u.codigo})
          </option>
        ))}
      </select>
    </div>
  )
}
