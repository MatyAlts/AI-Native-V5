import { HelpButton, PageContainer, StateMessage, useConfirm } from "@platform/ui"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"
import {
  type Facultad,
  type FacultadCreate,
  HttpError,
  type Universidad,
  facultadesApi,
  universidadesApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

export function FacultadesPage(): ReactNode {
  // `selectedUniversidadId = null` = todavía no hubo selección manual; el id
  // efectivo cae a la primera universidad cargada (auto-select del patrón viejo,
  // ahora derivado en memoria en vez de un useEffect + setState).
  const [selectedUniversidadId, setSelectedUniversidadId] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const confirm = useConfirm()

  const queryClient = useQueryClient()

  const universidadesQuery = useQuery({
    queryKey: ["universidades", { limit: 200 }],
    queryFn: () => universidadesApi.list({ limit: 200 }),
  })

  const universidades: Universidad[] = universidadesQuery.data?.data ?? []
  const universidadId = selectedUniversidadId ?? universidades[0]?.id ?? ""

  // Server-side filter: facultadesApi.list soporta universidad_id.
  const facultadesQuery = useQuery({
    queryKey: ["facultades", { universidad_id: universidadId, limit: 200 }],
    queryFn: () => facultadesApi.list({ universidad_id: universidadId, limit: 200 }),
    enabled: !!universidadId,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => facultadesApi.delete(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["facultades"] }),
  })

  const items: Facultad[] = facultadesQuery.data?.data ?? []

  const loadingUnis = universidadesQuery.isLoading
  const loading = facultadesQuery.isFetching && !!universidadId

  const queryError = universidadesQuery.error || facultadesQuery.error || deleteMutation.error
  const error = queryError
    ? queryError instanceof HttpError
      ? `${queryError.status}: ${queryError.detail || queryError.title}`
      : String(queryError)
    : null

  const uniMap = new Map(universidades.map((u) => [u.id, u]))

  const handleDelete = async (f: Facultad) => {
    if (
      !(await confirm({
        message: `¿Eliminar la facultad ${f.nombre}? Esta acción es lógica (soft-delete).`,
        tone: "danger",
      }))
    ) {
      return
    }
    deleteMutation.mutate(f.id)
  }

  return (
    <PageContainer
      title="Facultades"
      eyebrow="Inicio · Facultades"
      description="Divisiones academicas dentro de una universidad."
      helpContent={helpContent.facultades}
    >
      <div className="space-y-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            disabled={universidades.length === 0 || !universidadId}
            className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {showForm ? "Cancelar" : "Crear facultad"}
          </button>
        </div>

        <div className="rounded-lg border border-border-soft bg-surface p-4">
          {/* biome-ignore lint/a11y/noLabelWithoutControl: el select se renderea dentro del label en la rama final del ternario; biome no detecta el control bajo conditionals. */}
          <label className="flex flex-col gap-1 max-w-md">
            <span className="text-xs font-medium text-body">Universidad</span>
            {loadingUnis ? (
              <span className="text-sm text-muted">Cargando universidades…</span>
            ) : universidades.length === 0 ? (
              <span className="text-sm text-muted">
                No hay universidades creadas. Primero creá una universidad.
              </span>
            ) : (
              <select
                value={universidadId}
                onChange={(e) => setSelectedUniversidadId(e.target.value)}
                className={inputClass}
              >
                {universidades.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.codigo} · {u.nombre}
                  </option>
                ))}
              </select>
            )}
          </label>
        </div>

        {showForm && universidadId && (
          <FacultadForm
            universidadId={universidadId}
            onCreated={() => {
              setShowForm(false)
              void queryClient.invalidateQueries({ queryKey: ["facultades"] })
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
            <StateMessage variant="loading" />
          ) : !universidadId ? (
            <StateMessage
              variant="empty"
              title="Seleccione una universidad"
              description="Eliga una universidad para ver sus facultades."
            />
          ) : items.length === 0 ? (
            <StateMessage
              variant="empty"
              title="Sin facultades"
              description="No hay facultades en esta universidad."
            />
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-accent-brand/10 border-b-2 border-accent-brand/40 text-left">
                <tr>
                  <th className="px-4 py-2.5 font-semibold text-accent-brand-deep text-[11px] uppercase tracking-wider">
                    Código
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-accent-brand-deep text-[11px] uppercase tracking-wider">
                    Nombre
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-accent-brand-deep text-[11px] uppercase tracking-wider">
                    Universidad
                  </th>
                  <th className="px-4 py-2.5 font-medium" />
                </tr>
              </thead>
              <tbody>
                {items.map((f) => (
                  <tr
                    key={f.id}
                    className="border-b border-border-soft hover:bg-accent-brand/8 transition-colors"
                  >
                    <td className="px-4 py-2 font-mono text-xs">{f.codigo}</td>
                    <td className="px-4 py-2">{f.nombre}</td>
                    <td className="px-4 py-2 text-muted text-xs">
                      {uniMap.get(f.universidad_id)?.nombre ?? f.universidad_id}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => handleDelete(f)}
                        disabled={deleteMutation.isPending && deleteMutation.variables === f.id}
                        className="text-xs text-danger px-2 py-1 rounded hover:bg-danger-soft transition-colors disabled:opacity-50"
                      >
                        {deleteMutation.isPending && deleteMutation.variables === f.id
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

function FacultadForm({
  universidadId,
  onCreated,
}: {
  universidadId: string
  onCreated: () => void
}): ReactNode {
  const [form, setForm] = useState<FacultadCreate>({
    universidad_id: universidadId,
    nombre: "",
    codigo: "",
  })
  const [error, setError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: (data: FacultadCreate) => facultadesApi.create(data),
    onSuccess: () => onCreated(),
    onError: (err) =>
      setError(
        err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err),
      ),
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    createMutation.mutate({ ...form, universidad_id: universidadId })
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-border-soft bg-surface p-6 space-y-4"
    >
      <div className="flex items-center gap-2 mb-2">
        <HelpButton
          size="sm"
          title="Formulario de Facultad"
          content={
            <div className="space-y-3 text-muted-soft">
              <p>
                <strong>Completa los siguientes campos</strong> para crear una nueva facultad:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Codigo:</strong> Identificador corto unico dentro de la universidad (ej.
                  FCFMyN). Solo letras, numeros, guiones. Obligatorio.
                </li>
                <li>
                  <strong>Nombre:</strong> Nombre completo de la facultad (ej. Facultad de Ciencias
                  Fisico-Matematicas y Naturales). Obligatorio.
                </li>
              </ul>
            </div>
          }
        />
        <span className="text-sm text-muted">Nueva facultad</span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Código" required>
          <input
            type="text"
            value={form.codigo}
            onChange={(e) => setForm({ ...form, codigo: e.target.value })}
            required
            minLength={2}
            maxLength={50}
            pattern="[A-Za-z0-9_-]+"
            className={inputClass}
            placeholder="FCFMyN"
          />
        </Field>

        <Field label="Nombre" required>
          <input
            type="text"
            value={form.nombre}
            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
            required
            minLength={2}
            maxLength={200}
            className={inputClass}
            placeholder="Facultad de Ciencias Físico-Matemáticas y Naturales"
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
