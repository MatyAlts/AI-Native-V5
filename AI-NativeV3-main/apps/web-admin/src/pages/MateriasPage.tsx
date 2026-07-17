import { HelpButton, PageContainer, ReadonlyField, useConfirm } from "@platform/ui"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Sparkles } from "lucide-react"
import { type ReactNode, useState } from "react"
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
import type { Route } from "../router/Router"
import { helpContent } from "../utils/helpContent"

interface PlanContext {
  universidad: string
  carrera: string
  plan: string
}

export function MateriasPage({ onNavigate }: { onNavigate?: (to: Route) => void }): ReactNode {
  // Cascading selectors: Universidad → Carrera → Plan → lista de Materias.
  // Resetear descendientes en cada cambio para evitar combinaciones inválidas.
  const [universidadId, setUniversidadId] = useState<string>("")
  const [carreraId, setCarreraId] = useState<string>("")
  const [planId, setPlanId] = useState<string>("")
  const [showForm, setShowForm] = useState(false)
  const confirm = useConfirm()

  const queryClient = useQueryClient()

  const universidadesQuery = useQuery({
    queryKey: ["universidades", { limit: 200 }],
    queryFn: () => universidadesApi.list({ limit: 200 }),
  })

  // Server-side filter: carrerasApi.list soporta universidad_id.
  const carrerasQuery = useQuery({
    queryKey: ["carreras", { universidad_id: universidadId, limit: 200 }],
    queryFn: () => carrerasApi.list({ universidad_id: universidadId, limit: 200 }),
    enabled: !!universidadId,
  })

  // Server-side filter: planesApi.list soporta carrera_id.
  const planesQuery = useQuery({
    queryKey: ["planes", { carrera_id: carreraId, limit: 200 }],
    queryFn: () => planesApi.list({ carrera_id: carreraId, limit: 200 }),
    enabled: !!carreraId,
  })

  // Server-side filter: materiasApi.list soporta plan_id.
  const materiasQuery = useQuery({
    queryKey: ["materias", { plan_id: planId }],
    queryFn: () => materiasApi.list({ plan_id: planId }),
    enabled: !!planId,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => materiasApi.delete(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["materias"] }),
  })

  const universidades: Universidad[] = universidadesQuery.data?.data ?? []
  const carreras: Carrera[] = carrerasQuery.data?.data ?? []
  const planes: Plan[] = planesQuery.data?.data ?? []
  const items: Materia[] = materiasQuery.data?.data ?? []

  const loadingUniversidades = universidadesQuery.isLoading
  const loadingCarreras = carrerasQuery.isFetching && !!universidadId
  const loadingPlanes = planesQuery.isFetching && !!carreraId
  const loading = materiasQuery.isFetching && !!planId

  const queryError =
    universidadesQuery.error ||
    carrerasQuery.error ||
    planesQuery.error ||
    materiasQuery.error ||
    deleteMutation.error
  const error = queryError
    ? queryError instanceof HttpError
      ? `${queryError.status}: ${queryError.detail || queryError.title}`
      : String(queryError)
    : null

  const handleDelete = async (m: Materia) => {
    if (
      !(await confirm({
        message: `¿Eliminar la materia "${m.nombre}" (${m.codigo})? La quita del plan. Si ya tiene comisiones/contenido asociado, puede fallar.`,
        tone: "danger",
      }))
    ) {
      return
    }
    deleteMutation.mutate(m.id)
  }

  const planMap = new Map(planes.map((p) => [p.id, p]))
  const selectedPlan = planMap.get(planId)

  // Context del breadcrumb/form: derivado en memoria de los selectores
  // cascadeados — ya no hace falta chain fetch (mismo patrón que ComisionesPage).
  const selectedUniversidad = universidades.find((u) => u.id === universidadId)
  const selectedCarrera = carreras.find((c) => c.id === carreraId)
  const context: Partial<PlanContext> = {
    ...(selectedUniversidad ? { universidad: selectedUniversidad.nombre } : {}),
    ...(selectedCarrera ? { carrera: selectedCarrera.nombre } : {}),
    ...(selectedPlan ? { plan: `${selectedPlan.version} (${selectedPlan.año_inicio})` } : {}),
  }

  const breadcrumbItems: BreadcrumbItem[] = selectedPlan
    ? [
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
            onCreated={() => {
              setShowForm(false)
              void queryClient.invalidateQueries({ queryKey: ["materias"] })
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
                  <th className="px-4 py-2 font-medium text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {[...items]
                  .sort(
                    (a, b) =>
                      a.cuatrimestre_sugerido - b.cuatrimestre_sugerido ||
                      a.codigo.localeCompare(b.codigo),
                  )
                  .map((m) => (
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
                      <td className="px-4 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => handleDelete(m)}
                          className="press-shrink rounded-md px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger-soft"
                        >
                          Eliminar
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </div>

        {/* BK-4: pista de dónde configurar la clave de IA (BYOK puede scopearse
            por materia, facultad o tenant). */}
        <div className="flex items-start gap-2.5 rounded-lg border border-border-soft bg-surface-alt/50 p-3 text-xs text-muted">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent-brand-deep" />
          <span className="leading-relaxed">
            ¿La IA de una materia necesita su propia clave de proveedor? Las claves (por materia,
            facultad o tenant) se configuran en{" "}
            <button
              type="button"
              onClick={() => onNavigate?.("byok")}
              className="font-medium text-accent-brand-deep underline underline-offset-2 hover:text-accent-brand"
            >
              IA · Claves de proveedor
            </button>
            .
          </span>
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
  const [error, setError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: (data: MateriaCreate) => materiasApi.create(data),
    onSuccess: () => onCreated(),
    onError: (err) =>
      setError(
        err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err),
      ),
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    createMutation.mutate({ ...form, plan_id: planId })
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-border-soft bg-surface p-6 space-y-4"
    >
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
          disabled={createMutation.isPending}
          className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
        >
          {createMutation.isPending ? "Creando..." : "Crear"}
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
