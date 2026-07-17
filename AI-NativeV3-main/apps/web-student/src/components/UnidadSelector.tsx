import { useEffect, useState } from "react"
import { type AvailableTarea, type Unidad, listUnidades, tareasPracticasApi } from "../lib/api"

export interface UnidadSelectorProps {
  comisionId: string
  onSelect: (unidadId: string | null) => void
  /**
   * UI-5: si al cargar hay una sola opcion (una unidad, o solo el bucket "sin
   * unidad"), elegir una unidad es un click de mas — el caller salta directo al
   * selector de TPs. Se invoca con el unidadId de esa unica opcion (null =
   * bucket sin unidad). Con 0 opciones o >=2, NO se invoca (empty state / eleccion
   * real). Si no se provee, el componente renderiza normal (backwards-compat).
   */
  onAutoSkip?: (unidadId: string | null) => void
}

interface UnidadConCount {
  unidad: Unidad | null
  cantidad: number
}

/**
 * NB-19: la API de TPs pagina por cursor (`meta.cursor_next`). Los conteos
 * por unidad deben cubrir TODAS las paginas, no solo la primera; de lo
 * contrario una unidad cuyas TPs caen en paginas posteriores aparece con
 * 0 TPs (o el bucket "sin unidad" queda incompleto). Sigue el cursor hasta
 * agotarlo, acumulando. El tope defensivo evita un loop infinito si el
 * backend devolviera un cursor que no avanza.
 */
async function fetchAllAvailableTareas(comisionId: string): Promise<AvailableTarea[]> {
  const all: AvailableTarea[] = []
  const seenCursors = new Set<string>()
  let cursor: string | undefined
  for (let page = 0; page < 100; page++) {
    const res = await tareasPracticasApi.listAvailable(comisionId, cursor)
    all.push(...res.data)
    const next = res.meta.cursor_next
    if (!next || seenCursors.has(next)) break
    seenCursors.add(next)
    cursor = next
  }
  return all
}

export function UnidadSelector({ comisionId, onSelect, onAutoSkip }: UnidadSelectorProps) {
  const [items, setItems] = useState<UnidadConCount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: refetch solo por comision; onAutoSkip es un callback estable por intencion (agregarlo re-dispararia el fetch en cada render).
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([listUnidades(comisionId), fetchAllAvailableTareas(comisionId)])
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
        // UI-5: una sola opcion → no hay eleccion real, saltar directo al selector.
        if (result.length === 1 && onAutoSkip) {
          onAutoSkip(result[0]?.unidad?.id ?? null)
          return
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
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-20 rounded-xl" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="animate-fade-in-up rounded-xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
        <div className="font-semibold">No se pudieron cargar las unidades</div>
        <div className="mt-1 font-mono text-xs opacity-80">{error}</div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="animate-fade-in-up rounded-xl border border-border-soft bg-surface-alt p-6 text-center text-sm text-muted">
        Tu docente todavía no creó unidades ni publicó trabajos prácticos.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <h2 className="animate-fade-in-up text-lg font-semibold text-ink">Unidades</h2>
      <p className="animate-fade-in-up animate-delay-50 text-sm text-muted">
        Elegí una unidad para ver los trabajos prácticos que la componen.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map(({ unidad, cantidad }, index) => {
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
              style={{ animationDelay: `${Math.min(index * 40, 320)}ms` }}
              className="press-shrink animate-fade-in-up group text-left rounded-xl border border-border bg-surface p-4 transition-all hover:border-accent-brand hover:shadow-[0_2px_8px_-2px_rgba(0,0,0,0.08)] focus:outline-none focus:ring-2 focus:ring-accent-brand/30"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-ink transition-colors group-hover:text-accent-brand-deep">
                    {nombre}
                  </div>
                  {descripcion && (
                    <div className="mt-1 text-sm text-muted line-clamp-2">{descripcion}</div>
                  )}
                </div>
                {!isOrphan && (
                  <span className="shrink-0 rounded-full border border-border-soft bg-surface-alt px-2 py-0.5 text-xs font-medium text-muted">
                    #{unidad.orden}
                  </span>
                )}
              </div>
              <div className="mt-3 text-xs text-muted-soft">
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
