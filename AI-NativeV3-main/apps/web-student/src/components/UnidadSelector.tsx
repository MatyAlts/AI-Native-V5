import { useEffect, useState } from "react"
import {
  type AvailableTarea,
  type Unidad,
  listUnidades,
  tareasPracticasApi,
} from "../lib/api"

export interface UnidadSelectorProps {
  comisionId: string
  onSelect: (unidadId: string | null) => void
}

interface UnidadConCount {
  unidad: Unidad | null
  cantidad: number
}

export function UnidadSelector({ comisionId, onSelect }: UnidadSelectorProps) {
  const [items, setItems] = useState<UnidadConCount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      listUnidades(comisionId),
      tareasPracticasApi.listAvailable(comisionId).then((p) => p.data),
    ])
      .then(([unidades, tareas]) => {
        if (cancelled) return
        const countByUnidad = new Map<string | null, number>()
        for (const t of tareas) {
          const key = t.unidad_id ?? null
          countByUnidad.set(key, (countByUnidad.get(key) ?? 0) + 1)
        }
        const sorted = [...unidades].sort((a, b) => a.orden - b.orden)
        const result: UnidadConCount[] = sorted.map((u) => ({
          unidad: u,
          cantidad: countByUnidad.get(u.id) ?? 0,
        }))
        const sinUnidadCount = countByUnidad.get(null) ?? 0
        if (sinUnidadCount > 0) {
          result.push({ unidad: null, cantidad: sinUnidadCount })
        }
        setItems(result)
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
  }, [comisionId])

  if (loading) {
    return (
      <div className="space-y-3 animate-pulse">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 rounded-lg bg-gray-100" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        <div className="font-semibold">No se pudieron cargar las unidades</div>
        <div className="mt-1 font-mono text-xs">{error}</div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center text-sm text-gray-600">
        Tu docente todavía no creó unidades ni publicó trabajos prácticos.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold text-gray-900">Unidades</h2>
      <p className="text-sm text-gray-600">
        Elegí una unidad para ver los trabajos prácticos que la componen.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map(({ unidad, cantidad }) => {
          const isOrphan = unidad === null
          const key = isOrphan ? "sin-unidad" : unidad.id
          const nombre = isOrphan ? "Sin unidad asignada" : unidad.nombre
          const descripcion = isOrphan
            ? "Trabajos prácticos que el docente todavía no agrupó en una unidad."
            : (unidad.descripcion ?? null)

          return (
            <button
              key={key}
              type="button"
              onClick={() => onSelect(isOrphan ? null : unidad.id)}
              className="group text-left rounded-xl border border-gray-200 bg-white p-4 transition hover:border-blue-400 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-gray-900 group-hover:text-blue-700">
                    {nombre}
                  </div>
                  {descripcion && (
                    <div className="mt-1 text-sm text-gray-600 line-clamp-2">
                      {descripcion}
                    </div>
                  )}
                </div>
                {!isOrphan && (
                  <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                    #{unidad.orden}
                  </span>
                )}
              </div>
              <div className="mt-3 text-xs text-gray-500">
                {cantidad === 0
                  ? "Sin TPs publicados"
                  : `${cantidad} TP${cantidad !== 1 ? "s" : ""} disponible${cantidad !== 1 ? "s" : ""}`}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
