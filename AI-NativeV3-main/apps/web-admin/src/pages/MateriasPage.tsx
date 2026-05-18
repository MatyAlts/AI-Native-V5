import { HelpButton, PageContainer, ReadonlyField } from "@platform/ui"
import { type ReactNode, useEffect, useRef, useState } from "react"
import { Breadcrumb, type BreadcrumbItem } from "../components/Breadcrumb"
import {
  type Carrera,
  HttpError,
  type Materia,
  type MateriaCreate,
  type Plan,
  type Universidad,
  carrerasApi,
  materiasApi,
  planesApi,
  universidadesApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface PlanContext {
  universidad: string
  carrera: string
  plan: string
}

export function MateriasPage(): ReactNode {
  // Cascading selectors: Universidad → Carrera → Plan → lista de Materias.
  // Resetear descendientes en cada cambio para evitar combinaciones inválidas.
  const [universidades, setUniversidades] = useState<Universidad[]>([])
  const [universidadId, setUniversidadId] = useState<string>("")
  const [carreras, setCarreras] = useState<Carrera[]>([])
  const [carreraId, setCarreraId] = useState<string>("")
  const [planes, setPlanes] = useState<Plan[]>([])
  const [planId, setPlanId] = useState<string>("")
  const [items, setItems] = useState<Materia[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingUniversidades, setLoadingUniversidades] = useState(false)
  const [loadingCarreras, setLoadingCarreras] = useState(false)
  const [loadingPlanes, setLoadingPlanes] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [context, setContext] = useState<Partial<PlanContext>>({})
  const [contextLoading, setContextLoading] = useState(false)
  // Cache plan_id → contexto resuelto. Persistido en ref para sobrevivir
  // re-renders sin disparar efectos.
  const contextCache = useRef<Map<string, PlanContext>>(new Map())

  const loadUniversidades = async () => {
    setLoadingUniversidades(true)
    setError(null)
    try {
      const res = await universidadesApi.list({ limit: 200 })
      setUniversidades(res.data)
    } catch (e) {
      setError(e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e))
    } finally {
      setLoadingUniversidades(false)
    }
  }

  const loadCarreras = async (uid: string) => {
    if (!uid) {
      setCarreras([])
      return
    }
    setLoadingCarreras(true)
    setError(null)
    try {
      const res = await carrerasApi.list({ universidad_id: uid, limit: 200 })
      setCarreras(res.data)
    } catch (e) {
      setError(e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e))
    } finally {
      setLoadingCarreras(false)
    }
  }

  const loadPlanes = async (cid: string) => {
    if (!cid) {
      setPlanes([])
      return
    }
    setLoadingPlanes(true)
    setError(null)
    try {
      const res = await planesApi.list({ carrera_id: cid, limit: 200 })
      setPlanes(res.data)
    } catch (e) {
      setError(e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e))
    } finally {
      setLoadingPlanes(false)
    }
  }

  const loadMaterias = async (pid: string) => {
    if (!pid) {
      setItems([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await materiasApi.list({ plan_id: pid })
      setItems(res.data)
    } catch (e) {
      setError(e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e))
    } finally {
      setLoading(false)
    }
  }

  // biome-ignore lint/correctness/useExhaustiveDependencies: loadUniversidades — fetch mount-only; el handler usa setState con identidad estable.
  useEffect(() => {
    void loadUniversidades()
  }, [])

  // biome-ignore lint/correctness/useExhaustiveDependencies: loadCarreras — depende solo de universidadId; el handler captura el arg en cada call.
  useEffect(() => {
    void loadCarreras(universidadId)
  }, [universidadId])

  // biome-ignore lint/correctness/useExhaustiveDependencies: loadPlanes — depende solo de carreraId; el handler captura el arg en cada call.
  useEffect(() => {
    void loadPlanes(carreraId)
  }, [carreraId])

  // biome-ignore lint/correctness/useExhaustiveDependencies: loadMaterias — depende solo de planId; el handler captura el arg en cada call.
  useEffect(() => {
    void loadMaterias(planId)
  }, [planId])

  // Chain fetch: plan → carrera → universidad. No bloquea la lista de materias.
  // Cacheado por plan_id en `contextCache` para evitar refetch al re-seleccionar.
  useEffect(() => {
    if (!planId) {
      setContext({})
      setContextLoading(false)
      return
    }
    const cached = contextCache.current.get(planId)
    if (cached) {
      setContext(cached)
      setContextLoading(false)
      return
    }
    let cancelled = false
    setContextLoading(true)
    setContext({})
    ;(async () => {
      try {
        const plan = await planesApi.get(planId)
        if (cancelled) return
        const carrera = await carrerasApi.get(plan.carrera_id)
        if (cancelled) return
        const universidad = await universidadesApi.get(carrera.universidad_id)
        if (cancelled) return
        const resolved: PlanContext = {
          universidad: universidad.nombre,
          carrera: carrera.nombre,
          plan: `${plan.version} (${plan.año_inicio})`,
        }
        contextCache.current.set(planId, resolved)
        setContext(resolved)
      } catch {
        // Silencioso: no rompemos la página por un breadcrumb. Queda en "?".
        if (!cancelled) setContext({})
      } finally {
        if (!cancelled) setContextLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [planId])

  const planMap = new Map(planes.map((p) => [p.id, p]))
  const selectedPlan = planMap.get(planId)

  const breadcrumbItems: BreadcrumbItem[] = selectedPlan
    ? contextLoading && !context.plan
      ? [{ label: "… cargando contexto" }]
      : [
          { context: "Universidad", label: context.universidad ?? "?" },
          { context: "Carrera", label: context.carrera ?? "?" },
          {
            context: "Plan",
            label: context.plan ?? `${selectedPlan.version} (${selectedPlan.año_inicio})`,
          },
        ]
    : []

  return (
    <PageContainer
      title="Materias"
      eyebrow="Inicio · Materias"
      description="Asignaturas de un plan de estudios."
      helpContent={helpContent.materias}
    >
      <div className="space-y-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            disabled={!universidadId || !carreraId || !planId}
            className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {showForm ? "Cancelar" : "Nueva materia"}
          </button>
        </div>

        {breadcrumbItems.length > 0 && <Breadcrumb items={breadcrumbItems} />}

        <div className="rounded-lg border border-border-soft bg-surface p-4 grid grid-cols-3 gap-4">
          <Field label="Universidad" required>
            {loadingUniversidades ? (
              <span className="text-sm text-muted">Cargando universidades…</span>
            ) : universidades.length === 0 ? (
              <span className="text-sm text-muted">
                No hay universidades creadas. Primero creá una universidad.
              </span>
            ) : (
              <select
                value={universidadId}
                onChange={(e) => {
                  setUniversidadId(e.target.value)
                  setCarreraId("")
                  setPlanId("")
                }}
                className={inputClass}
              >
                <option value="">— Seleccioná una universidad —</option>
                {universidades.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.codigo} · {u.nombre}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Carrera" required>
            {loadingCarreras ? (
              <span className="text-sm text-muted">Cargando carreras…</span>
            ) : !universidadId ? (
              <select value="" disabled className={inputClass}>
                <option value="">— Primero seleccioná una universidad —</option>
              </select>
            ) : carreras.length === 0 ? (
              <span className="text-sm text-muted">No hay carreras en esta universidad.</span>
            ) : (
              <select
                value={carreraId}
                onChange={(e) => {
                  setCarreraId(e.target.value)
                  setPlanId("")
                }}
                className={inputClass}
              >
                <option value="">— Seleccioná una carrera —</option>
                {carreras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.codigo} · {c.nombre}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Plan de estudios" required>
            {loadingPlanes ? (
              <span className="text-sm text-muted">Cargando planes…</span>
            ) : !carreraId ? (
              <select value="" disabled className={inputClass}>
                <option value="">— Primero seleccioná una carrera —</option>
              </select>
            ) : planes.length === 0 ? (
              <span className="text-sm text-muted">No hay planes en esta carrera.</span>
            ) : (
              <select
                value={planId}
                onChange={(e) => setPlanId(e.target.value)}
                className={inputClass}
              >
                <option value="">— Seleccioná un plan —</option>
                {planes.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.version} ({p.año_inicio}){p.vigente ? " · vigente" : ""}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>

        {showForm && planId && (
          <MateriaForm
            planId={planId}
            context={context}
            onCreated={async () => {
              setShowForm(false)
              await loadMaterias(planId)
            }}
          />
        )}

        {error && (
          <div className="rounded-md border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
            {error}
          </div>
        )}

        <div className="rounded-lg border border-border-soft bg-surface overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-muted text-sm">Cargando…</div>
          ) : !universidadId ? (
            <div className="p-8 text-center text-muted text-sm">
              Seleccioná universidad, carrera y plan para ver sus materias.
            </div>
          ) : !carreraId ? (
            <div className="p-8 text-center text-muted text-sm">
              Seleccioná una carrera y un plan para ver sus materias.
            </div>
          ) : !planId ? (
            <div className="p-8 text-center text-muted text-sm">
              Seleccioná un plan para ver sus materias.
            </div>
          ) : items.length === 0 ? (
            <div className="p-8 text-center space-y-3">
              <p className="text-muted text-sm">No hay materias en este plan todavia.</p>
              {planId && (
                <button
                  type="button"
                  onClick={() => setShowForm(true)}
                  className="rounded-md bg-accent-brand text-white px-4 py-1.5 text-sm hover:bg-accent-brand-deep"
                >
                  Crear primera materia
                </button>
              )}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-surface-alt border-b border-border-soft text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">Código</th>
                  <th className="px-4 py-2 font-medium">Nombre</th>
                  <th className="px-4 py-2 font-medium">Plan</th>
                  <th className="px-4 py-2 font-medium">Horas</th>
                  <th className="px-4 py-2 font-medium">Cuatri.</th>
                </tr>
              </thead>
              <tbody>
                {items.map((m) => (
                  <tr key={m.id} className="border-b border-border-soft">
                    <td className="px-4 py-2 font-mono text-xs">{m.codigo}</td>
                    <td className="px-4 py-2">{m.nombre}</td>
                    <td className="px-4 py-2 text-muted text-xs">
                      {planMap.get(m.plan_id)?.version ?? m.plan_id}
                    </td>
                    <td className="px-4 py-2">{m.horas_totales} h</td>
                    <td className="px-4 py-2">
                      <span className="inline-flex items-center rounded-full bg-surface-alt px-2 py-0.5 text-xs">
                        {m.cuatrimestre_sugerido}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </PageContainer>
  )
}

function MateriaForm({
  planId,
  context,
  onCreated,
}: {
  planId: string
  context: Partial<PlanContext>
  onCreated: () => void
}): ReactNode {
  const [form, setForm] = useState<MateriaCreate>({
    plan_id: planId,
    nombre: "",
    codigo: "",
    horas_totales: 96,
    cuatrimestre_sugerido: 1,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await materiasApi.create({ ...form, plan_id: planId })
      onCreated()
    } catch (e) {
      setError(e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="rounded-lg border border-border-soft bg-surface p-6 space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <HelpButton
          size="sm"
          title="Formulario de Materia"
          content={
            <div className="space-y-3 text-muted-soft">
              <p>
                <strong>Completa los siguientes campos</strong> para crear una nueva materia:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Codigo:</strong> Identificador unico dentro del plan (ej. PROG1, ALG-LIN).
                  Solo letras, numeros, guiones, puntos. Obligatorio.
                </li>
                <li>
                  <strong>Nombre:</strong> Nombre completo de la asignatura (ej. Programacion I).
                  Obligatorio.
                </li>
                <li>
                  <strong>Horas totales:</strong> Carga horaria total. Minimo 16, maximo 500.
                  Obligatorio.
                </li>
                <li>
                  <strong>Cuatrimestre sugerido:</strong> Numero de cuatrimestre recomendado en el
                  plan (1, 2, 3...). Obligatorio.
                </li>
                <li>
                  <strong>Objetivos:</strong> Opcional. Descripcion de los objetivos pedagogicos de
                  la materia.
                </li>
              </ul>
            </div>
          }
        />
        <span className="text-sm text-muted">Nueva materia</span>
      </div>

      <div className="grid grid-cols-3 gap-4 rounded-md bg-surface-alt border border-border-soft p-3">
        <ReadonlyField label="Universidad" value={context.universidad ?? "—"} />
        <ReadonlyField label="Carrera" value={context.carrera ?? "—"} />
        <ReadonlyField label="Plan" value={context.plan ?? "—"} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Código" required>
          <input
            type="text"
            value={form.codigo}
            onChange={(e) => setForm({ ...form, codigo: e.target.value })}
            required
            pattern="[A-Za-z0-9_.-]+"
            className={inputClass}
            placeholder="PROG1"
          />
        </Field>

        <Field label="Nombre" required>
          <input
            type="text"
            value={form.nombre}
            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
            required
            minLength={2}
            className={inputClass}
            placeholder="Programación I"
          />
        </Field>

        <Field label="Horas totales" required>
          <input
            type="number"
            value={form.horas_totales}
            onChange={(e) => setForm({ ...form, horas_totales: Number(e.target.value) })}
            min={16}
            max={500}
            required
            className={inputClass}
          />
        </Field>

        <Field label="Cuatrimestre sugerido" required>
          <input
            type="number"
            value={form.cuatrimestre_sugerido}
            onChange={(e) =>
              setForm({
                ...form,
                cuatrimestre_sugerido: Number(e.target.value),
              })
            }
            min={1}
            max={20}
            required
            className={inputClass}
          />
        </Field>

        <Field label="Objetivos">
          <textarea
            value={form.objetivos ?? ""}
            onChange={(e) => {
              const v = e.target.value
              setForm((prev) => {
                const { objetivos: _omit, ...rest } = prev
                return v ? { ...rest, objetivos: v } : rest
              })
            }}
            maxLength={5000}
            rows={3}
            className={inputClass}
            placeholder="Opcional"
          />
        </Field>
      </div>

      {error && (
        <div className="rounded-md border border-danger/40 bg-danger-soft p-3 text-xs text-danger">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
        >
          {submitting ? "Creando..." : "Crear"}
        </button>
      </div>
    </form>
  )
}

const inputClass =
  "w-full rounded-md border border-border px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-brand"

function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: ReactNode
}): ReactNode {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: children es el control (input/select/textarea) wrappeado por el padre — patrón de form helper.
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-body">
        {label}
        {required && <span className="text-danger ml-0.5">*</span>}
      </span>
      {children}
    </label>
  )
}
