import { HelpButton, PageContainer, ReadonlyField, useConfirm } from "@platform/ui"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"
import {
  type Carrera,
  HttpError,
  type Plan,
  type PlanCreate,
  type Universidad,
  carrerasApi,
  facultadesApi,
  planesApi,
  universidadesApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface CarreraContext {
  universidad: string
  facultad: string
}

export function PlanesPage(): ReactNode {
  // Cascading selectors: Universidad → Carrera → lista de Planes.
  // Resetear descendientes en cada cambio para evitar combinaciones inválidas.
  const [universidadId, setUniversidadId] = useState<string>("")
  const [carreraId, setCarreraId] = useState<string>("")
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

  // Context del form (breadcrumb readonly): chain fetch carrera → facultad + universidad.
  // TanStack Query cachea por carreraId, reemplazando el ref-cache manual anterior.
  // Silencioso: si falla, `data` queda undefined y el form muestra "—" (no rompe la página).
  const contextQuery = useQuery({
    queryKey: ["plan-context", carreraId],
    queryFn: async (): Promise<CarreraContext> => {
      const carrera = await carrerasApi.get(carreraId)
      const [facultad, universidad] = await Promise.all([
        facultadesApi.get(carrera.facultad_id),
        universidadesApi.get(carrera.universidad_id),
      ])
      return { universidad: universidad.nombre, facultad: facultad.nombre }
    },
    enabled: !!carreraId,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => planesApi.delete(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["planes"] }),
  })

  const universidades: Universidad[] = universidadesQuery.data?.data ?? []
  const carreras: Carrera[] = carrerasQuery.data?.data ?? []
  const items: Plan[] = planesQuery.data?.data ?? []
  const context: Partial<CarreraContext> = contextQuery.data ?? {}

  // Error banner: agrega errores de queries + delete (el context es silencioso by design).
  const queryError =
    universidadesQuery.error || carrerasQuery.error || planesQuery.error || deleteMutation.error
  const error = queryError
    ? queryError instanceof HttpError
      ? `${queryError.status}: ${queryError.detail || queryError.title}`
      : String(queryError)
    : null

  const loadingUniversidades = universidadesQuery.isLoading
  const loadingCarreras = carrerasQuery.isFetching
  const loading = planesQuery.isFetching

  const carreraMap = new Map(carreras.map((c) => [c.id, c]))

  const handleDelete = async (p: Plan) => {
    if (
      !(await confirm({
        message: `¿Eliminar el plan ${p.version} (${p.año_inicio})? Esta acción es lógica (soft-delete).`,
        tone: "danger",
      }))
    ) {
      return
    }
    deleteMutation.mutate(p.id)
  }

  return (
    <PageContainer
      title="Planes de estudio"
      eyebrow="Inicio · Planes de estudio"
      description="Versiones de plan vigentes y derogadas por carrera."
      helpContent={helpContent.planes}
    >
      <div className="space-y-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            disabled={!universidadId || !carreraId}
            className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {showForm ? "Cancelar" : "Crear plan"}
          </button>
        </div>

        <div className="rounded-lg border border-border-soft bg-surface p-4 grid grid-cols-2 gap-4">
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
                onChange={(e) => setCarreraId(e.target.value)}
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
        </div>

        {showForm && carreraId && (
          <PlanForm
            carreraId={carreraId}
            context={context}
            onCreated={async () => {
              setShowForm(false)
              await queryClient.invalidateQueries({ queryKey: ["planes"] })
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
              Seleccioná una universidad y una carrera para ver sus planes.
            </div>
          ) : !carreraId ? (
            <div className="p-8 text-center text-muted text-sm">
              Seleccioná una carrera para ver sus planes.
            </div>
          ) : items.length === 0 ? (
            <div className="p-8 text-center space-y-3">
              <p className="text-muted text-sm">
                No hay planes de estudio en esta carrera todavia.
              </p>
              {carreraId && (
                <button
                  type="button"
                  onClick={() => setShowForm(true)}
                  className="rounded-md bg-accent-brand text-white px-4 py-1.5 text-sm hover:bg-accent-brand-deep"
                >
                  Crear primer plan
                </button>
              )}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-surface-alt border-b border-border-soft text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">Versión</th>
                  <th className="px-4 py-2 font-medium">Año inicio</th>
                  <th className="px-4 py-2 font-medium">Carrera</th>
                  <th className="px-4 py-2 font-medium">Ordenanza</th>
                  <th className="px-4 py-2 font-medium">Estado</th>
                  <th className="px-4 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id} className="border-b border-border-soft">
                    <td className="px-4 py-2 font-mono text-xs">{p.version}</td>
                    <td className="px-4 py-2">{p.año_inicio}</td>
                    <td className="px-4 py-2 text-muted text-xs">
                      {carreraMap.get(p.carrera_id)?.nombre ?? p.carrera_id}
                    </td>
                    <td className="px-4 py-2 text-muted text-xs">{p.ordenanza ?? "—"}</td>
                    <td className="px-4 py-2">
                      <span
                        className={
                          p.vigente
                            ? "inline-flex items-center rounded-full bg-success-soft text-success px-2 py-0.5 text-xs"
                            : "inline-flex items-center rounded-full bg-surface-alt text-body px-2 py-0.5 text-xs"
                        }
                      >
                        {p.vigente ? "vigente" : "derogado"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => handleDelete(p)}
                        disabled={deleteMutation.isPending && deleteMutation.variables === p.id}
                        className="text-xs text-danger hover:text-danger disabled:opacity-50"
                      >
                        {deleteMutation.isPending && deleteMutation.variables === p.id
                          ? "Eliminando…"
                          : "Eliminar"}
                      </button>
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

function PlanForm({
  carreraId,
  context,
  onCreated,
}: {
  carreraId: string
  context: Partial<CarreraContext>
  onCreated: () => void
}): ReactNode {
  const currentYear = new Date().getFullYear()
  const [form, setForm] = useState<PlanCreate>({
    carrera_id: carreraId,
    version: "",
    año_inicio: currentYear,
    ordenanza: "",
    vigente: true,
  })
  const [error, setError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: (payload: PlanCreate) => planesApi.create(payload),
    onSuccess: () => onCreated(),
    onError: (err) =>
      setError(
        err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err),
      ),
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const { ordenanza: _omit, ...rest } = form
    const trimmedOrdenanza = form.ordenanza?.trim()
    const payload: PlanCreate = {
      ...rest,
      carrera_id: carreraId,
      ...(trimmedOrdenanza ? { ordenanza: trimmedOrdenanza } : {}),
    }
    createMutation.mutate(payload)
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-border-soft bg-surface p-6 space-y-4"
    >
      <div className="flex items-center gap-2 mb-2">
        <HelpButton
          size="sm"
          title="Formulario de Plan de Estudio"
          content={
            <div className="space-y-3 text-muted-soft">
              <p>
                <strong>Completa los siguientes campos</strong> para crear un nuevo plan de estudio:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Version:</strong> Identificador del plan (ej. 2024, Plan-2020). Libre pero
                  unico por carrera. Obligatorio.
                </li>
                <li>
                  <strong>Ano de inicio:</strong> Ano en que entra en vigencia el plan. Obligatorio.
                </li>
                <li>
                  <strong>Ordenanza:</strong> Opcional. Referencia a la resolucion del Consejo
                  Superior (ej. Res. CS No 12/24).
                </li>
                <li>
                  <strong>Vigencia:</strong> Indica si el plan esta activo para nuevas
                  inscripciones.
                </li>
              </ul>
            </div>
          }
        />
        <span className="text-sm text-muted">Nuevo plan de estudio</span>
      </div>

      <div className="grid grid-cols-2 gap-4 rounded-md bg-surface-alt border border-border-soft p-3">
        <ReadonlyField label="Universidad" value={context.universidad ?? "—"} />
        <ReadonlyField label="Facultad" value={context.facultad ?? "—"} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Versión" required>
          <input
            type="text"
            value={form.version}
            onChange={(e) => setForm({ ...form, version: e.target.value })}
            required
            minLength={1}
            maxLength={50}
            className={inputClass}
            placeholder="2024"
          />
        </Field>

        <Field label="Año de inicio" required>
          <input
            type="number"
            value={form.año_inicio}
            onChange={(e) => setForm({ ...form, año_inicio: Number(e.target.value) })}
            min={1900}
            max={2100}
            required
            className={inputClass}
          />
        </Field>

        <Field label="Ordenanza">
          <input
            type="text"
            value={form.ordenanza ?? ""}
            onChange={(e) => setForm({ ...form, ordenanza: e.target.value })}
            maxLength={100}
            className={inputClass}
            placeholder="Opcional — Res. CS Nº 12/24"
          />
        </Field>

        <Field label="Vigencia" required>
          <select
            value={form.vigente ? "true" : "false"}
            onChange={(e) => setForm({ ...form, vigente: e.target.value === "true" })}
            required
            className={inputClass}
          >
            <option value="true">Vigente</option>
            <option value="false">Derogado</option>
          </select>
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
