import { HelpButton, PageContainer, StateMessage } from "@platform/ui"
import { type ReactNode, useEffect, useState } from "react"
import {
  type Carrera,
  type CarreraCreate,
  type Facultad,
  HttpError,
  carrerasApi,
  facultadesApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

export function CarrerasPage(): ReactNode {
  const [items, setItems] = useState<Carrera[]>([])
  const [facultades, setFacultades] = useState<Facultad[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [carrs, facs] = await Promise.all([carrerasApi.list(), facultadesApi.list()])
      setItems(carrs.data)
      setFacultades(facs.data)
    } catch (e) {
      setError(e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e))
    } finally {
      setLoading(false)
    }
  }

  // biome-ignore lint/correctness/useExhaustiveDependencies: load — fetch mount-only; el handler usa setState con identidad estable.
  useEffect(() => {
    void load()
  }, [])

  const facMap = new Map(facultades.map((f) => [f.id, f]))
  const noFacultades = facultades.length === 0

  const handleDelete = async (c: Carrera) => {
    if (!window.confirm(`¿Eliminar carrera ${c.nombre}?`)) return
    setDeletingId(c.id)
    setError(null)
    try {
      await carrerasApi.delete(c.id)
      await load()
    } catch (e) {
      const msg = e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e)
      window.alert(`No se pudo eliminar: ${msg}`)
      setError(msg)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <PageContainer
      title="Carreras"
      eyebrow="Inicio · Carreras"
      description="Programas academicos del tenant actual."
      helpContent={helpContent.carreras}
    >
      <div className="space-y-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            disabled={noFacultades}
            title={noFacultades ? "Primero creá una facultad" : undefined}
            className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {showForm ? "Cancelar" : "Nueva carrera"}
          </button>
        </div>

        {showForm && !noFacultades && (
          <CarreraForm
            facultades={facultades}
            onCreated={async () => {
              setShowForm(false)
              await load()
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
          ) : items.length === 0 ? (
            <StateMessage
              variant="empty"
              title="Sin carreras"
              description={
                noFacultades
                  ? "No hay carreras creadas. Primero crea una facultad."
                  : "No hay carreras creadas."
              }
            />
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-surface-alt border-b border-border-soft text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">Código</th>
                  <th className="px-4 py-2 font-medium">Nombre</th>
                  <th className="px-4 py-2 font-medium">Facultad</th>
                  <th className="px-4 py-2 font-medium">Duración</th>
                  <th className="px-4 py-2 font-medium">Modalidad</th>
                  <th className="px-4 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className="border-b border-border-soft">
                    <td className="px-4 py-2 font-mono text-xs">{c.codigo}</td>
                    <td className="px-4 py-2">{c.nombre}</td>
                    <td className="px-4 py-2 text-muted text-xs">
                      {facMap.get(c.facultad_id)?.nombre ?? c.facultad_id}
                    </td>
                    <td className="px-4 py-2">{c.duracion_semestres} sem.</td>
                    <td className="px-4 py-2">
                      <span className="inline-flex items-center rounded-full bg-surface-alt px-2 py-0.5 text-xs">
                        {c.modalidad}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => void handleDelete(c)}
                        disabled={deletingId === c.id}
                        className="text-xs text-danger hover:text-danger disabled:opacity-50"
                      >
                        {deletingId === c.id ? "Eliminando…" : "Eliminar"}
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

function CarreraForm({
  facultades,
  onCreated,
}: {
  facultades: Facultad[]
  onCreated: () => void
}): ReactNode {
  const firstFacultadId = facultades[0]?.id ?? ""
  const [form, setForm] = useState<CarreraCreate>({
    facultad_id: firstFacultadId,
    nombre: "",
    codigo: "",
    duracion_semestres: 8,
    modalidad: "presencial",
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await carrerasApi.create(form)
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
          title="Formulario de Carrera"
          content={
            <div className="space-y-3 text-muted-soft">
              <p>
                <strong>Completa los siguientes campos</strong> para crear una nueva carrera:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Facultad:</strong> Facultad a la que pertenece la carrera. Obligatorio.
                </li>
                <li>
                  <strong>Codigo:</strong> Identificador corto unico (ej. LIS, ING-COMP). Solo
                  letras, numeros, guiones. Obligatorio.
                </li>
                <li>
                  <strong>Nombre:</strong> Nombre completo del programa (ej. Licenciatura en
                  Sistemas). Obligatorio.
                </li>
                <li>
                  <strong>Duracion:</strong> Cantidad de semestres del plan. Tipicamente 8 o 10.
                </li>
                <li>
                  <strong>Modalidad:</strong> Presencial, virtual o hibrida.
                </li>
              </ul>
            </div>
          }
        />
        <span className="text-sm text-muted">Nueva carrera</span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Facultad" required>
          <select
            value={form.facultad_id}
            onChange={(e) => setForm({ ...form, facultad_id: e.target.value })}
            required
            className={inputClass}
          >
            {facultades.map((f) => (
              <option key={f.id} value={f.id}>
                {f.nombre}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Código" required>
          <input
            type="text"
            value={form.codigo}
            onChange={(e) => setForm({ ...form, codigo: e.target.value })}
            required
            pattern="[A-Za-z0-9_-]+"
            className={inputClass}
            placeholder="LIS"
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
            placeholder="Licenciatura en Sistemas"
          />
        </Field>

        <Field label="Duración (semestres)" required>
          <input
            type="number"
            value={form.duracion_semestres}
            onChange={(e) => setForm({ ...form, duracion_semestres: Number(e.target.value) })}
            min={1}
            max={20}
            required
            className={inputClass}
          />
        </Field>

        <Field label="Modalidad" required>
          <select
            value={form.modalidad}
            onChange={(e) =>
              setForm({
                ...form,
                modalidad: e.target.value as NonNullable<CarreraCreate["modalidad"]>,
              })
            }
            required
            className={inputClass}
          >
            <option value="presencial">Presencial</option>
            <option value="virtual">Virtual</option>
            <option value="hibrida">Híbrida</option>
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
