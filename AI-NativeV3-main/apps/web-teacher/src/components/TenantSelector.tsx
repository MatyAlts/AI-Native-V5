import { useEffect, useState } from "react"
import { SELECTED_TENANT_STORAGE_KEY } from "../main"

interface Universidad {
  id: string
  tenant_id: string
  nombre: string
  codigo: string
}

/**
 * Dropdown del header docente para cambiar de universidad activa.
 *
 * Guarda el `tenant_id` seleccionado en localStorage. El monkey-patch de
 * `window.fetch` en `main.tsx` inyecta `x-selected-tenant` en cada fetch
 * a `/api/*`. El proxy de Vite lo propaga al api-gateway como `X-Tenant-Id`.
 *
 * Endpoint backend: la policy `authenticated_can_list` (migration
 * `20260515_0001`) permite a cualquier user autenticado listar nombres
 * + códigos de universidades. El aislamiento real se mantiene en las
 * demás tablas (comisiones, ejercicios) por RLS estricta.
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
        /* best-effort: el proxy cae al default */
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
    // Limpiar query params específicos del tenant viejo (comisionId,
    // studentId, etc). Sin esto, un comisionId huérfano queda en la URL
    // y los componentes que filtran por él muestran "comisión no encontrada".
    const url = new URL(window.location.href)
    url.search = ""
    window.location.replace(url.toString())
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
