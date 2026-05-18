import { Badge, HeroStatsPanel, HelpButton, PageContainer, ReadonlyField } from "@platform/ui"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Calendar, ChevronDown, ChevronRight, Layers, Plus, Trash2, Users } from "lucide-react"
import { type ReactNode, useState } from "react"
import { Breadcrumb, type BreadcrumbItem } from "../components/Breadcrumb"
import {
  type Carrera,
  type Comision,
  type ComisionCreate,
  type InscripcionCreate,
  type InscripcionOut,
  HttpError,
  type Materia,
  type Periodo,
  type Plan,
  type Universidad,
  type UsuarioComisionCreate,
  type UsuarioComisionOut,
  carrerasApi,
  comisionDocentesApi,
  comisionInscripcionesApi,
  comisionesApi,
  materiasApi,
  periodosApi,
  planesApi,
  universidadesApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

// Label expresivo del periodo: `${codigo} · ${nombre}`. Usamos ambos porque
// `codigo` (ej. "2026-S1") es conciso y `nombre` (ej. "Primer semestre 2026")
// da contexto humano. No hay endpoint GET /periodos/{id} — se resuelve desde
// la lista ya cacheada en `periodosQuery`.
function periodoLabel(p: Periodo): string {
  return `${p.codigo} · ${p.nombre}`
}

const PAGE_LIMIT = 50

interface MateriaContext {
  universidad: string
  carrera: string
  plan: string
  materia: string
  periodo: string
}

export function ComisionesPage(): ReactNode {
  // Cascading selectors: Universidad → Carrera → Plan → Materia.
  // Resetear descendientes en cada cambio para evitar combinaciones inválidas.
  const [universidadId, setUniversidadId] = useState<string>("")
  const [carreraId, setCarreraId] = useState<string>("")
  const [planId, setPlanId] = useState<string>("")
  const [materiaId, setMateriaId] = useState<string>("")
  const [periodoId, setPeriodoId] = useState<string>("")
  const [cursor, setCursor] = useState<string | undefined>(undefined)
  const [showForm, setShowForm] = useState(false)
  const [expandedComisionId, setExpandedComisionId] = useState<string | null>(null)

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
    queryKey: ["materias", { plan_id: planId, limit: 200 }],
    queryFn: () => materiasApi.list({ plan_id: planId, limit: 200 }),
    enabled: !!planId,
  })

  const periodosQuery = useQuery({
    queryKey: ["periodos", { limit: 200 }],
    queryFn: () => periodosApi.list({ limit: 200 }),
  })

  const comisionesQuery = useQuery({
    queryKey: [
      "comisiones",
      { materia_id: materiaId, periodo_id: periodoId, cursor, limit: PAGE_LIMIT },
    ],
    queryFn: () =>
      comisionesApi.list({
        materia_id: materiaId,
        periodo_id: periodoId,
        ...(cursor ? { cursor } : {}),
        limit: PAGE_LIMIT,
      }),
    // Sólo cargamos comisiones cuando materia + periodo están ambos seteados.
    enabled: !!materiaId && !!periodoId,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => comisionesApi.delete(id),
    onMutate: async (id: string) => {
      const key = [
        "comisiones",
        { materia_id: materiaId, periodo_id: periodoId, cursor, limit: PAGE_LIMIT },
      ] as const
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<{
        data: Comision[]
        meta: { cursor_next: string | null; total: number | null }
      }>(key)
      if (previous) {
        queryClient.setQueryData(key, {
          ...previous,
          data: previous.data.filter((c) => c.id !== id),
        })
      }
      return { previous, key }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(ctx.key, ctx.previous)
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["comisiones"] })
    },
  })

  const universidades: Universidad[] = universidadesQuery.data?.data ?? []
  const carreras: Carrera[] = carrerasQuery.data?.data ?? []
  const planes: Plan[] = planesQuery.data?.data ?? []
  const materias: Materia[] = materiasQuery.data?.data ?? []
  const periodos: Periodo[] = periodosQuery.data?.data ?? []
  const items: Comision[] = comisionesQuery.data?.data ?? []
  const cursorNext = comisionesQuery.data?.meta.cursor_next ?? null

  const materiaMap = new Map(materias.map((m) => [m.id, m]))
  const periodoMap = new Map(periodos.map((p) => [p.id, p]))

  const selectedUniversidad = universidades.find((u) => u.id === universidadId)
  const selectedCarrera = carreras.find((c) => c.id === carreraId)
  const selectedPlan = planes.find((p) => p.id === planId)
  const selectedMateria = materiaMap.get(materiaId)
  const selectedPeriodo = periodoMap.get(periodoId)

  // Context del form: ya no hace falta chain fetch — los nombres los tenemos
  // en memoria de los 4 selectores cascadeados + el map de periodos.
  const formContext: MateriaContext | null =
    selectedUniversidad && selectedCarrera && selectedPlan && selectedMateria && selectedPeriodo
      ? {
          universidad: selectedUniversidad.nombre,
          carrera: selectedCarrera.nombre,
          plan: `${selectedPlan.version} (${selectedPlan.año_inicio})`,
          materia: `${selectedMateria.codigo} · ${selectedMateria.nombre}`,
          periodo: periodoLabel(selectedPeriodo),
        }
      : null

  const queryError =
    universidadesQuery.error ||
    carrerasQuery.error ||
    planesQuery.error ||
    materiasQuery.error ||
    periodosQuery.error ||
    comisionesQuery.error
  const errorMsg = queryError
    ? queryError instanceof HttpError
      ? `${queryError.status}: ${queryError.detail || queryError.title}`
      : String(queryError)
    : null

  const loading =
    universidadesQuery.isLoading ||
    periodosQuery.isLoading ||
    (carrerasQuery.isFetching && !!universidadId) ||
    (planesQuery.isFetching && !!carreraId) ||
    (materiasQuery.isFetching && !!planId) ||
    (comisionesQuery.isFetching && !!materiaId && !!periodoId)

  const breadcrumbItems: BreadcrumbItem[] = []
  if (selectedUniversidad) {
    breadcrumbItems.push({ context: "Universidad", label: selectedUniversidad.nombre })
  }
  if (selectedCarrera) {
    breadcrumbItems.push({ context: "Carrera", label: selectedCarrera.nombre })
  }
  if (selectedPlan) {
    breadcrumbItems.push({
      context: "Plan",
      label: `${selectedPlan.version} (${selectedPlan.año_inicio})`,
    })
  }
  if (selectedMateria) {
    breadcrumbItems.push({
      context: "Materia",
      label: `${selectedMateria.codigo} · ${selectedMateria.nombre}`,
    })
  }
  if (selectedPeriodo) {
    breadcrumbItems.push({ context: "Período", label: selectedPeriodo.codigo })
  }

  // Stats agregados (suma de cupo / promedio de budget)
  const totalCupo = items.reduce((s, c) => s + (c.cupo_maximo ?? 0), 0)
  const avgBudget =
    items.length > 0
      ? items.reduce((s, c) => s + Number.parseFloat(c.ai_budget_monthly_usd ?? "0"), 0) /
        items.length
      : 0

  return (
    <PageContainer
      title="Comisiones"
      description="Comisiones de cursada por materia y periodo del tenant actual."
      eyebrow="Inicio · Comisiones"
      helpContent={helpContent.comisiones}
    >
      <div className="space-y-6">
        {/* ═══ Toolbar (CTA) ═══ */}
        <div className="flex items-center justify-between gap-3 flex-wrap animate-fade-in-up">
          <p className="text-xs text-muted leading-relaxed max-w-2xl">
            Seleccioná universidad, carrera, plan, materia y período para listar las comisiones del
            tenant. Las acciones de gestión (docentes, alumnos) se exponen al expandir cada fila.
          </p>
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            disabled={!materiaId || !periodoId}
            className="press-shrink inline-flex items-center gap-1.5 rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50 transition-colors shadow-[0_1px_2px_0_rgba(24,95,165,0.25)]"
          >
            <Plus className="h-3.5 w-3.5" />
            {showForm ? "Cancelar" : "Nueva comisión"}
          </button>
        </div>

        {/* ═══ HeroStatsPanel (cuando hay materia + período seleccionados con datos) ═══ */}
        {materiaId && periodoId && items.length > 0 && (
          <HeroStatsPanel
            eyebrow="Resumen del filtro activo"
            stats={[
              { label: "Comisiones", value: items.length, unit: "listadas" },
              { label: "Cupo total", value: totalCupo, unit: "alumnos" },
              {
                label: "Budget AI",
                value: `$${avgBudget.toFixed(0)}`,
                unit: "USD/mes prom.",
              },
            ]}
          />
        )}

        {breadcrumbItems.length > 0 && <Breadcrumb items={breadcrumbItems} />}

        <div className="rounded-lg border border-border bg-surface p-4 grid grid-cols-1 md:grid-cols-2 gap-4 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
          <Field label="Universidad" required>
            <select
              value={universidadId}
              onChange={(e) => {
                setUniversidadId(e.target.value)
                setCarreraId("")
                setPlanId("")
                setMateriaId("")
                setCursor(undefined)
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
          </Field>
          <Field label="Carrera" required>
            <select
              value={carreraId}
              onChange={(e) => {
                setCarreraId(e.target.value)
                setPlanId("")
                setMateriaId("")
                setCursor(undefined)
              }}
              disabled={!universidadId}
              className={inputClass}
            >
              <option value="">
                {universidadId ? "— Seleccioná una carrera —" : "— Elegí universidad primero —"}
              </option>
              {carreras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.codigo} · {c.nombre}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Plan de estudio" required>
            <select
              value={planId}
              onChange={(e) => {
                setPlanId(e.target.value)
                setMateriaId("")
                setCursor(undefined)
              }}
              disabled={!carreraId}
              className={inputClass}
            >
              <option value="">
                {carreraId ? "— Seleccioná un plan —" : "— Elegí carrera primero —"}
              </option>
              {planes.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.version} ({p.año_inicio})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Materia" required>
            <select
              value={materiaId}
              onChange={(e) => {
                setMateriaId(e.target.value)
                setCursor(undefined)
              }}
              disabled={!planId}
              className={inputClass}
            >
              <option value="">
                {planId ? "— Seleccioná una materia —" : "— Elegí plan primero —"}
              </option>
              {materias.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.codigo} · {m.nombre}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Periodo" required>
            <select
              value={periodoId}
              onChange={(e) => {
                setPeriodoId(e.target.value)
                setCursor(undefined)
              }}
              className={inputClass}
            >
              <option value="">
                {periodos.length === 0
                  ? "— No hay periodos creados —"
                  : "— Seleccioná un periodo —"}
              </option>
              {periodos.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.codigo} · {p.nombre}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {periodos.length === 0 && !periodosQuery.isLoading && (
          <div className="rounded-md border border-warning/40 bg-warning-soft p-4 text-sm text-warning">
            No hay periodos creados. Creá uno desde la página de Periodos para poder gestionar
            comisiones.
          </div>
        )}

        {showForm && materiaId && periodoId && formContext && (
          <ComisionForm
            materiaId={materiaId}
            periodoId={periodoId}
            context={formContext}
            onCreated={async () => {
              setShowForm(false)
              await queryClient.invalidateQueries({ queryKey: ["comisiones"] })
            }}
          />
        )}

        {errorMsg && (
          <div className="rounded-xl border border-danger/30 bg-danger-soft p-4 animate-fade-in-up">
            <div className="text-sm font-semibold text-danger">No pudimos cargar el listado</div>
            <div className="mt-1.5 font-mono text-xs text-danger/85 break-all">{errorMsg}</div>
          </div>
        )}

        {/* ═══ Listado de comisiones ═══ */}
        {!materiaId || !periodoId ? (
          <div className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up">
            <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
              <Layers className="h-7 w-7 text-muted" />
            </div>
            <h2 className="text-base font-semibold text-ink mb-2">Sin filtro activo</h2>
            <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
              Seleccioná universidad, carrera, plan, materia y período para ver sus comisiones.
            </p>
          </div>
        ) : loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 animate-fade-in">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-44 rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up">
            <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
              <Calendar className="h-7 w-7 text-muted" />
            </div>
            <h2 className="text-base font-semibold text-ink mb-2">
              No hay comisiones en este período
            </h2>
            <p className="text-sm text-muted leading-relaxed max-w-md mx-auto mb-5">
              Creá la primera con el botón "Nueva comisión" arriba a la derecha. También podés usar
              bulk-import si tenés un CSV de comisiones.
            </p>
          </div>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {items.map((c, idx) => {
              const expanded = expandedComisionId === c.id
              const materiaNombre = materiaMap.get(c.materia_id)?.nombre ?? c.materia_id
              const periodoCodigo = periodoMap.get(c.periodo_id)?.codigo ?? c.periodo_id
              return (
                <li
                  key={c.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${Math.min(idx, 6) * 50}ms` }}
                >
                  <article
                    className={`group relative overflow-hidden rounded-xl border bg-surface flex flex-col h-full shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] transition-all ${
                      expanded
                        ? "border-accent-brand/40 ring-1 ring-accent-brand/20"
                        : "border-border hover-lift"
                    }`}
                  >
                    <div
                      aria-hidden="true"
                      className={`absolute left-0 top-0 bottom-0 w-1 transition-colors ${expanded ? "bg-accent-brand" : "bg-accent-brand/0 group-hover:bg-accent-brand/60"}`}
                    />

                    <button
                      type="button"
                      onClick={() =>
                        setExpandedComisionId((prev) => (prev === c.id ? null : c.id))
                      }
                      className="press-shrink p-4 text-left flex flex-col gap-3"
                      aria-expanded={expanded}
                    >
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-mono text-[11px] uppercase tracking-wider text-muted px-2 py-0.5 rounded bg-surface-alt border border-border-soft">
                            {c.codigo}
                          </span>
                          <Badge variant="info">{periodoCodigo}</Badge>
                        </div>
                        <span className="text-muted-soft" aria-hidden="true">
                          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </span>
                      </div>
                      <h3
                        className="text-[15px] font-semibold text-ink leading-tight tracking-tight line-clamp-2"
                        title={materiaNombre}
                      >
                        {materiaNombre}
                      </h3>
                      <dl className="grid grid-cols-2 gap-3 mt-auto">
                        <div className="flex flex-col gap-0.5 min-w-0">
                          <span className="text-[10px] uppercase tracking-wider text-muted-soft">
                            Cupo
                          </span>
                          <span className="font-mono tabular-nums text-base font-semibold text-ink leading-none">
                            {c.cupo_maximo}
                          </span>
                        </div>
                        <div className="flex flex-col gap-0.5 min-w-0">
                          <span className="text-[10px] uppercase tracking-wider text-muted-soft">
                            Budget AI
                          </span>
                          <span className="font-mono tabular-nums text-base font-semibold text-ink leading-none">
                            ${c.ai_budget_monthly_usd}
                          </span>
                        </div>
                      </dl>
                    </button>

                    <footer className="flex items-stretch border-t border-border-soft">
                      <span
                        className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium ${
                          expanded
                            ? "text-accent-brand-deep"
                            : "text-muted"
                        }`}
                      >
                        <Users className="h-3.5 w-3.5" />
                        {expanded ? "Cerrar gestión" : "Gestionar"}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          if (
                            window.confirm(
                              `¿Eliminar la comisión ${c.codigo}? Esta acción es lógica (soft-delete).`,
                            )
                          ) {
                            deleteMutation.mutate(c.id)
                          }
                        }}
                        disabled={deleteMutation.isPending}
                        className="press-shrink inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium border-l border-border-soft text-danger hover:bg-danger-soft transition-colors disabled:opacity-50"
                        title="Eliminar comisión"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </footer>

                    {expanded && (
                      <div className="border-t border-border-soft bg-surface-alt animate-fade-in">
                        <ComisionDetail comisionId={c.id} />
                      </div>
                    )}
                  </article>
                </li>
              )
            })}
          </ul>
        )}

        {materiaId && periodoId && (cursor || cursorNext) && (
          <div className="flex items-center justify-end gap-2 px-1 text-xs">
            <button
              type="button"
              onClick={() => setCursor(undefined)}
              disabled={!cursor}
              className="press-shrink rounded-md border border-border bg-surface px-3 py-1.5 hover:bg-surface-alt disabled:opacity-50 transition-colors"
            >
              Inicio
            </button>
            <button
              type="button"
              onClick={() => {
                if (cursorNext) setCursor(cursorNext)
              }}
              disabled={!cursorNext}
              className="press-shrink rounded-md border border-border bg-surface px-3 py-1.5 hover:bg-surface-alt disabled:opacity-50 transition-colors"
            >
              Siguiente
            </button>
          </div>
        )}
      </div>
    </PageContainer>
  )
}

function ComisionForm({
  materiaId,
  periodoId,
  context,
  onCreated,
}: {
  materiaId: string
  periodoId: string
  context: MateriaContext
  onCreated: () => void
}): ReactNode {
  const [form, setForm] = useState<ComisionCreate>({
    materia_id: materiaId,
    periodo_id: periodoId,
    codigo: "",
    nombre: "",
    cupo_maximo: 50,
    horario: {},
    ai_budget_monthly_usd: "100.00",
  })
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: (data: ComisionCreate) => comisionesApi.create(data),
    onMutate: async (data) => {
      const optimistic: Comision = {
        id: `temp-${Date.now()}`,
        tenant_id: "",
        materia_id: data.materia_id,
        periodo_id: data.periodo_id,
        codigo: data.codigo,
        cupo_maximo: data.cupo_maximo ?? 50,
        horario: data.horario ?? {},
        ai_budget_monthly_usd: String(data.ai_budget_monthly_usd ?? "100.00"),
        curso_config_hash: null,
        created_at: new Date().toISOString(),
        deleted_at: null,
      }
      const queries = queryClient.getQueriesData<{
        data: Comision[]
        meta: { cursor_next: string | null; total: number | null }
      }>({ queryKey: ["comisiones"] })
      const snapshots = queries.map(([key, value]) => ({ key, value }))
      for (const { key, value } of snapshots) {
        if (value) {
          queryClient.setQueryData(key, {
            ...value,
            data: [optimistic, ...value.data],
          })
        }
      }
      return { snapshots }
    },
    onError: (err, _data, ctx) => {
      if (ctx?.snapshots) {
        for (const { key, value } of ctx.snapshots) {
          queryClient.setQueryData(key, value)
        }
      }
      setError(err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err))
    },
    onSuccess: () => {
      onCreated()
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["comisiones"] })
    },
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    createMutation.mutate(form)
  }

  return (
    <form onSubmit={submit} className="rounded-lg border border-border-soft bg-white p-6 space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <HelpButton
          size="sm"
          title="Formulario de Comision"
          content={
            <div className="space-y-3 text-muted-soft">
              <p>
                <strong>Completa los siguientes campos</strong> para crear una nueva comision:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Codigo:</strong> Identificador de la comision (ej. C1, ComA). Unico por
                  materia y periodo. Obligatorio.
                </li>
                <li>
                  <strong>Cupo maximo:</strong> Cantidad maxima de estudiantes inscriptos. Default
                  50.
                </li>
                <li>
                  <strong>Budget AI mensual (USD):</strong> Limite de gasto mensual en servicios AI
                  por comision. Default 100.00.
                </li>
              </ul>
            </div>
          }
        />
        <span className="text-sm text-muted">Nueva comision</span>
      </div>

      <div className="grid grid-cols-3 gap-4 rounded-md bg-surface-alt border border-border-soft p-3">
        <ReadonlyField label="Universidad" value={context.universidad} />
        <ReadonlyField label="Carrera" value={context.carrera} />
        <ReadonlyField label="Plan" value={context.plan} />
        <ReadonlyField label="Materia" value={context.materia} />
        <ReadonlyField label="Periodo" value={context.periodo} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Código" required>
          <input
            type="text"
            value={form.codigo}
            onChange={(e) => setForm({ ...form, codigo: e.target.value })}
            required
            minLength={1}
            maxLength={50}
            className={inputClass}
            placeholder="C1"
          />
        </Field>

        <Field label="Nombre" required>
          <input
            type="text"
            value={form.nombre}
            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
            required
            minLength={1}
            maxLength={100}
            className={inputClass}
            placeholder="Comision Manana"
          />
        </Field>

        <Field label="Cupo máximo" required>
          <input
            type="number"
            value={form.cupo_maximo}
            onChange={(e) => setForm({ ...form, cupo_maximo: Number(e.target.value) })}
            min={1}
            max={500}
            required
            className={inputClass}
          />
        </Field>

        <Field label="Budget AI mensual (USD)" required>
          <input
            type="number"
            step="0.01"
            value={form.ai_budget_monthly_usd as string | number}
            onChange={(e) => setForm({ ...form, ai_budget_monthly_usd: e.target.value })}
            min={0}
            max={10000}
            required
            className={inputClass}
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
  "w-full rounded-md border border-border px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600"

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

// ── ComisionDetail: panel expandible con tabs Docentes / Alumnos ──────

type ComisionTab = "docentes" | "alumnos"

function ComisionDetail({ comisionId }: { comisionId: string }): ReactNode {
  const [tab, setTab] = useState<ComisionTab>("docentes")
  const queryClient = useQueryClient()

  const docentesQuery = useQuery({
    queryKey: ["comision-docentes", comisionId],
    queryFn: () => comisionDocentesApi.list(comisionId),
  })

  const inscripcionesQuery = useQuery({
    queryKey: ["comision-inscripciones", comisionId],
    queryFn: () => comisionInscripcionesApi.list(comisionId),
  })

  const removeDocenteMutation = useMutation({
    mutationFn: (ucId: string) => comisionDocentesApi.delete(comisionId, ucId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["comision-docentes", comisionId] }),
  })

  const removeInscripcionMutation = useMutation({
    mutationFn: (inscId: string) => comisionInscripcionesApi.delete(comisionId, inscId),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["comision-inscripciones", comisionId] }),
  })

  const docentes: UsuarioComisionOut[] = docentesQuery.data?.data ?? []
  const inscripciones: InscripcionOut[] = inscripcionesQuery.data?.data ?? []

  return (
    <div className="p-4 space-y-3">
      <div className="flex gap-2 border-b border-border-soft pb-2">
        {(["docentes", "alumnos"] as ComisionTab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t-md border-b-2 transition-colors ${
              tab === t
                ? "border-accent-brand text-accent-brand-deep bg-accent-brand-soft"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t === "docentes" ? "Docentes" : "Alumnos"}
          </button>
        ))}
      </div>

      {tab === "docentes" && (
        <DocentesTab
          comisionId={comisionId}
          docentes={docentes}
          isLoading={docentesQuery.isLoading}
          onRemove={(ucId) => removeDocenteMutation.mutate(ucId)}
          isRemoving={removeDocenteMutation.isPending}
          onAdded={() =>
            void queryClient.invalidateQueries({ queryKey: ["comision-docentes", comisionId] })
          }
        />
      )}

      {tab === "alumnos" && (
        <AlumnosTab
          comisionId={comisionId}
          inscripciones={inscripciones}
          isLoading={inscripcionesQuery.isLoading}
          onRemove={(inscId) => removeInscripcionMutation.mutate(inscId)}
          isRemoving={removeInscripcionMutation.isPending}
          onAdded={() =>
            void queryClient.invalidateQueries({
              queryKey: ["comision-inscripciones", comisionId],
            })
          }
        />
      )}
    </div>
  )
}

function DocentesTab({
  comisionId,
  docentes,
  isLoading,
  onRemove,
  isRemoving,
  onAdded,
}: {
  comisionId: string
  docentes: UsuarioComisionOut[]
  isLoading: boolean
  onRemove: (id: string) => void
  isRemoving: boolean
  onAdded: () => void
}): ReactNode {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    user_id: "",
    rol: "titular" as UsuarioComisionCreate["rol"],
    fecha_desde: new Date().toISOString().slice(0, 10),
  })
  const [formError, setFormError] = useState<string | null>(null)

  const addMutation = useMutation({
    mutationFn: (data: UsuarioComisionCreate) => comisionDocentesApi.create(comisionId, data),
    onSuccess: () => {
      setShowForm(false)
      setForm({ user_id: "", rol: "titular", fecha_desde: new Date().toISOString().slice(0, 10) })
      onAdded()
    },
    onError: (err) =>
      setFormError(
        err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err),
      ),
  })

  return (
    <div className="space-y-3">
      {isLoading ? (
        <p className="text-xs text-muted">Cargando...</p>
      ) : docentes.length === 0 ? (
        <p className="text-xs text-muted">No hay docentes asignados.</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-left text-muted">
            <tr>
              <th className="py-1 pr-3">User ID</th>
              <th className="py-1 pr-3">Rol</th>
              <th className="py-1 pr-3">Desde</th>
              <th className="py-1 pr-3">Hasta</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {docentes.map((d) => (
              <tr key={d.id} className="border-t border-border-soft">
                <td className="py-1 pr-3 font-mono">{d.user_id.slice(0, 8)}…</td>
                <td className="py-1 pr-3">{d.rol}</td>
                <td className="py-1 pr-3">{d.fecha_desde}</td>
                <td className="py-1 pr-3">{d.fecha_hasta ?? "—"}</td>
                <td className="py-1 text-right">
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(`¿Quitar docente ${d.user_id.slice(0, 8)}…?`)) {
                        onRemove(d.id)
                      }
                    }}
                    disabled={isRemoving}
                    className="text-danger hover:text-danger disabled:opacity-50"
                  >
                    Quitar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showForm ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setFormError(null)
            addMutation.mutate(form)
          }}
          className="grid grid-cols-4 gap-2 items-end"
        >
          <div className="col-span-2">
            <Field label="User ID (UUID)" required>
              <input
                type="text"
                value={form.user_id}
                onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                required
                placeholder="UUID del docente"
                className={inputClass}
              />
            </Field>
          </div>
          <Field label="Rol" required>
            <select
              value={form.rol}
              onChange={(e) => setForm({ ...form, rol: e.target.value as UsuarioComisionCreate["rol"] })}
              className={inputClass}
            >
              <option value="titular">Titular</option>
              <option value="adjunto">Adjunto</option>
              <option value="jtp">JTP</option>
              <option value="ayudante">Ayudante</option>
              <option value="corrector">Corrector</option>
            </select>
          </Field>
          <Field label="Desde" required>
            <input
              type="date"
              value={form.fecha_desde}
              onChange={(e) => setForm({ ...form, fecha_desde: e.target.value })}
              required
              className={inputClass}
            />
          </Field>
          {formError && (
            <div className="col-span-4 text-xs text-danger bg-danger-soft border border-danger/30 rounded p-2">
              {formError}
            </div>
          )}
          <div className="col-span-4 flex gap-2">
            <button
              type="submit"
              disabled={addMutation.isPending}
              className="rounded-md bg-accent-brand text-white px-3 py-1 text-xs font-medium hover:bg-accent-brand-deep disabled:opacity-50"
            >
              {addMutation.isPending ? "Agregando..." : "Agregar"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-md border border-border px-3 py-1 text-xs hover:bg-surface-alt"
            >
              Cancelar
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="text-xs text-accent-brand-deep hover:text-accent-brand-deep font-medium"
        >
          + Agregar docente
        </button>
      )}
    </div>
  )
}

function AlumnosTab({
  comisionId,
  inscripciones,
  isLoading,
  onRemove,
  isRemoving,
  onAdded,
}: {
  comisionId: string
  inscripciones: InscripcionOut[]
  isLoading: boolean
  onRemove: (id: string) => void
  isRemoving: boolean
  onAdded: () => void
}): ReactNode {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<InscripcionCreate>({
    student_pseudonym: "",
    fecha_inscripcion: new Date().toISOString().slice(0, 10),
  })
  const [formError, setFormError] = useState<string | null>(null)

  const addMutation = useMutation({
    mutationFn: (data: InscripcionCreate) => comisionInscripcionesApi.create(comisionId, data),
    onSuccess: () => {
      setShowForm(false)
      setForm({ student_pseudonym: "", fecha_inscripcion: new Date().toISOString().slice(0, 10) })
      onAdded()
    },
    onError: (err) =>
      setFormError(
        err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err),
      ),
  })

  return (
    <div className="space-y-3">
      {isLoading ? (
        <p className="text-xs text-muted">Cargando...</p>
      ) : inscripciones.length === 0 ? (
        <p className="text-xs text-muted">No hay alumnos inscriptos.</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-left text-muted">
            <tr>
              <th className="py-1 pr-3">Student pseudonym</th>
              <th className="py-1 pr-3">Rol</th>
              <th className="py-1 pr-3">Estado</th>
              <th className="py-1 pr-3">Fecha inscripción</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {inscripciones.map((i) => (
              <tr key={i.id} className="border-t border-border-soft">
                <td className="py-1 pr-3 font-mono">{i.student_pseudonym.slice(0, 8)}…</td>
                <td className="py-1 pr-3">{i.rol}</td>
                <td className="py-1 pr-3">{i.estado}</td>
                <td className="py-1 pr-3">{i.fecha_inscripcion}</td>
                <td className="py-1 text-right">
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(`¿Quitar alumno ${i.student_pseudonym.slice(0, 8)}…?`)) {
                        onRemove(i.id)
                      }
                    }}
                    disabled={isRemoving}
                    className="text-danger hover:text-danger disabled:opacity-50"
                  >
                    Quitar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showForm ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setFormError(null)
            addMutation.mutate(form)
          }}
          className="grid grid-cols-3 gap-2 items-end"
        >
          <div className="col-span-2">
            <Field label="Student pseudonym (UUID)" required>
              <input
                type="text"
                value={form.student_pseudonym}
                onChange={(e) => setForm({ ...form, student_pseudonym: e.target.value })}
                required
                placeholder="UUID del estudiante"
                className={inputClass}
              />
            </Field>
          </div>
          <Field label="Fecha inscripción" required>
            <input
              type="date"
              value={form.fecha_inscripcion}
              onChange={(e) => setForm({ ...form, fecha_inscripcion: e.target.value })}
              required
              className={inputClass}
            />
          </Field>
          {formError && (
            <div className="col-span-3 text-xs text-danger bg-danger-soft border border-danger/30 rounded p-2">
              {formError}
            </div>
          )}
          <div className="col-span-3 flex gap-2">
            <button
              type="submit"
              disabled={addMutation.isPending}
              className="rounded-md bg-accent-brand text-white px-3 py-1 text-xs font-medium hover:bg-accent-brand-deep disabled:opacity-50"
            >
              {addMutation.isPending ? "Inscribiendo..." : "Inscribir"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-md border border-border px-3 py-1 text-xs hover:bg-surface-alt"
            >
              Cancelar
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="text-xs text-accent-brand-deep hover:text-accent-brand-deep font-medium"
        >
          + Inscribir alumno
        </button>
      )}
    </div>
  )
}
