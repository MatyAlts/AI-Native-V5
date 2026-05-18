import { HelpButton, Modal, PageContainer } from "@platform/ui"
import { Pencil } from "lucide-react"
import { type ReactNode, useEffect, useState } from "react"
import {
  HttpError,
  type Periodo,
  type PeriodoCreate,
  type PeriodoUpdate,
  periodosApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

function formatError(e: unknown): string {
  return e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e)
}

export function PeriodosPage(): ReactNode {
  const [items, setItems] = useState<Periodo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  const [busyId, setBusyId] = useState<string | null>(null)
  const [editing, setEditing] = useState<Periodo | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await periodosApi.list({ limit: 200 })
      setItems(resp.data)
    } catch (e) {
      setError(formatError(e))
    } finally {
      setLoading(false)
    }
  }

  const closePeriodo = async (p: Periodo) => {
    if (
      !window.confirm(
        `¿Cerrar el periodo "${p.codigo}"?\n\nEsta acción es IRREVERSIBLE — una vez cerrado, el periodo queda frozen y no se puede reabrir ni editar.`,
      )
    ) {
      return
    }
    setBusyId(p.id)
    setError(null)
    try {
      await periodosApi.update(p.id, { estado: "cerrado" })
      await load()
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusyId(null)
    }
  }

  const deletePeriodo = async (p: Periodo) => {
    if (
      !window.confirm(
        `¿Eliminar el periodo "${p.codigo}"?\n\nSi tiene comisiones asociadas, la operación va a fallar.`,
      )
    ) {
      return
    }
    setBusyId(p.id)
    setError(null)
    try {
      await periodosApi.delete(p.id)
      await load()
    } catch (e) {
      setError(formatError(e))
    } finally {
      setBusyId(null)
    }
  }

  // biome-ignore lint/correctness/useExhaustiveDependencies: load — fetch mount-only; el handler usa setState con identidad estable.
  useEffect(() => {
    void load()
  }, [])

  return (
    <PageContainer
      title="Periodos"
      eyebrow="Inicio · Periodos"
      description="Periodos lectivos (ej. 2026-S1, 2026-S2). Cada comision se crea dentro de un periodo."
      helpContent={helpContent.periodos}
    >
      <div className="space-y-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep"
          >
            {showForm ? "Cancelar" : "Nuevo periodo"}
          </button>
        </div>

        {showForm && (
          <PeriodoForm
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
            <div className="p-8 text-center text-muted text-sm">Cargando…</div>
          ) : items.length === 0 ? (
            <div className="p-8 text-center space-y-3">
              <p className="text-muted text-sm">No hay periodos registrados todavia.</p>
              <button
                type="button"
                onClick={() => setShowForm(true)}
                className="rounded-md bg-accent-brand text-white px-4 py-1.5 text-sm hover:bg-accent-brand-deep"
              >
                Crear primer periodo
              </button>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-surface-alt border-b border-border-soft text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">Código</th>
                  <th className="px-4 py-2 font-medium">Nombre</th>
                  <th className="px-4 py-2 font-medium">Inicio</th>
                  <th className="px-4 py-2 font-medium">Fin</th>
                  <th className="px-4 py-2 font-medium">Estado</th>
                  <th className="px-4 py-2 font-medium">Creado</th>
                  <th className="px-4 py-2 font-medium text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => {
                  const isBusy = busyId === p.id
                  const isAbierto = p.estado === "abierto"
                  return (
                    <tr key={p.id} className="border-b border-border-soft">
                      <td className="px-4 py-2 font-mono text-xs">{p.codigo}</td>
                      <td className="px-4 py-2">{p.nombre}</td>
                      <td className="px-4 py-2 text-body text-xs">{p.fecha_inicio}</td>
                      <td className="px-4 py-2 text-body text-xs">{p.fecha_fin}</td>
                      <td className="px-4 py-2">
                        <span
                          className={
                            isAbierto
                              ? "inline-flex rounded-full bg-success-soft text-success px-2 py-0.5 text-xs font-medium"
                              : "inline-flex rounded-full bg-surface-alt text-body px-2 py-0.5 text-xs font-medium"
                          }
                        >
                          {p.estado}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-muted text-xs">
                        {new Date(p.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <div className="inline-flex gap-2">
                          {isAbierto && (
                            <button
                              type="button"
                              onClick={() => setEditing(p)}
                              disabled={isBusy}
                              className="inline-flex items-center gap-1 rounded-md border border-border bg-surface-alt px-2.5 py-1 text-xs font-medium text-body hover:bg-surface-alt disabled:opacity-50"
                              title="Editar nombre y fechas del periodo"
                            >
                              <Pencil className="h-3 w-3" aria-hidden="true" />
                              Editar
                            </button>
                          )}
                          {isAbierto && (
                            <button
                              type="button"
                              onClick={() => void closePeriodo(p)}
                              disabled={isBusy}
                              className="rounded-md border border-warning/40 bg-warning-soft px-2.5 py-1 text-xs font-medium text-warning hover:bg-warning-soft disabled:opacity-50"
                              title="Cerrar periodo (one-way — no se puede reabrir)"
                            >
                              {isBusy ? "..." : "Cerrar"}
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => void deletePeriodo(p)}
                            disabled={isBusy}
                            className="rounded-md border border-danger/40 bg-danger-soft px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger-soft disabled:opacity-50"
                            title="Eliminar periodo (falla si tiene comisiones asociadas)"
                          >
                            {isBusy ? "..." : "Eliminar"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {editing && (
          <EditPeriodoModal
            periodo={editing}
            onClose={() => setEditing(null)}
            onSaved={async () => {
              setEditing(null)
              await load()
            }}
          />
        )}
      </div>
    </PageContainer>
  )
}

function PeriodoForm({ onCreated }: { onCreated: () => void }): ReactNode {
  const [form, setForm] = useState<PeriodoCreate>({
    codigo: "",
    nombre: "",
    fecha_inicio: "",
    fecha_fin: "",
    estado: "abierto",
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.fecha_fin < form.fecha_inicio) {
      setError("La fecha de fin no puede ser anterior a la fecha de inicio.")
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await periodosApi.create(form)
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
          title="Formulario de Periodo"
          content={
            <div className="space-y-3 text-muted-soft">
              <p>
                <strong>Completa los siguientes campos</strong> para crear un nuevo periodo:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Codigo:</strong> Identificador corto y unico (ej. 2026-S1). Solo letras,
                  numeros, guiones. Obligatorio. Inmutable una vez creado.
                </li>
                <li>
                  <strong>Nombre:</strong> Descripcion humana (ej. Primer cuatrimestre 2026).
                  Obligatorio.
                </li>
                <li>
                  <strong>Fecha inicio:</strong> Fecha de inicio del periodo. Obligatorio.
                </li>
                <li>
                  <strong>Fecha fin:</strong> Fecha de cierre del periodo. Debe ser posterior a la
                  fecha de inicio. Obligatorio.
                </li>
                <li>
                  <strong>Estado:</strong> abierto (default) o cerrado. Cerrar es irreversible.
                </li>
              </ul>
            </div>
          }
        />
        <span className="text-sm text-muted">Ayuda sobre el formulario</span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Código" required>
          <input
            type="text"
            value={form.codigo}
            onChange={(e) => setForm({ ...form, codigo: e.target.value })}
            required
            minLength={2}
            maxLength={20}
            pattern="[A-Za-z0-9_-]+"
            className={inputClass}
            placeholder="2026-S1"
          />
        </Field>

        <Field label="Nombre" required>
          <input
            type="text"
            value={form.nombre}
            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
            required
            minLength={2}
            maxLength={100}
            className={inputClass}
            placeholder="Primer cuatrimestre 2026"
          />
        </Field>

        <Field label="Fecha inicio" required>
          <input
            type="date"
            value={form.fecha_inicio}
            onChange={(e) => setForm({ ...form, fecha_inicio: e.target.value })}
            required
            className={inputClass}
          />
        </Field>

        <Field label="Fecha fin" required>
          <input
            type="date"
            value={form.fecha_fin}
            onChange={(e) => setForm({ ...form, fecha_fin: e.target.value })}
            required
            className={inputClass}
          />
        </Field>

        <Field label="Estado">
          <select
            value={form.estado ?? "abierto"}
            onChange={(e) => {
              const next = e.target.value === "cerrado" ? "cerrado" : "abierto"
              setForm({ ...form, estado: next })
            }}
            className={inputClass}
          >
            <option value="abierto">abierto</option>
            <option value="cerrado">cerrado</option>
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

function EditPeriodoModal({
  periodo,
  onClose,
  onSaved,
}: {
  periodo: Periodo
  onClose: () => void
  onSaved: () => void
}): ReactNode {
  const [nombre, setNombre] = useState(periodo.nombre)
  const [fechaInicio, setFechaInicio] = useState(periodo.fecha_inicio)
  const [fechaFin, setFechaFin] = useState(periodo.fecha_fin)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (fechaFin < fechaInicio) {
      setError("La fecha de fin no puede ser anterior a la fecha de inicio.")
      return
    }
    const patch: PeriodoUpdate = {}
    if (nombre !== periodo.nombre) patch.nombre = nombre
    if (fechaInicio !== periodo.fecha_inicio) patch.fecha_inicio = fechaInicio
    if (fechaFin !== periodo.fecha_fin) patch.fecha_fin = fechaFin

    if (Object.keys(patch).length === 0) {
      onClose()
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await periodosApi.update(periodo.id, patch)
      onSaved()
    } catch (err) {
      if (err instanceof HttpError && err.status === 409) {
        setError("Este periodo está cerrado, no se puede editar.")
      } else if (err instanceof HttpError && err.status === 400) {
        setError(err.detail || err.title || "Datos inválidos.")
      } else {
        setError(formatError(err))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal isOpen={true} onClose={onClose} title={`Editar periodo: ${periodo.codigo}`} size="lg">
      <form onSubmit={submit} className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HelpButton
            size="sm"
            title="Campos del formulario"
            content={
              <div className="space-y-3 text-muted-soft">
                <p>
                  <strong>Modifica los siguientes campos</strong> del periodo:
                </p>
                <ul className="list-disc pl-5 space-y-2">
                  <li>
                    <strong>Codigo:</strong> Inmutable. No se puede editar una vez creado.
                  </li>
                  <li>
                    <strong>Nombre:</strong> Descripcion humana del periodo (ej. Primer cuatrimestre
                    2026).
                  </li>
                  <li>
                    <strong>Fecha inicio:</strong> Fecha de inicio del periodo.
                  </li>
                  <li>
                    <strong>Fecha fin:</strong> Fecha de cierre. Debe ser posterior a la fecha de
                    inicio.
                  </li>
                </ul>
              </div>
            }
          />
          <span className="text-sm text-muted">Ayuda sobre los campos</span>
        </div>

        <Field label="Código">
          <input
            type="text"
            value={periodo.codigo}
            disabled
            className={`${inputClass} cursor-not-allowed bg-surface-alt text-muted`}
          />
          <span className="text-xs text-muted">El código es inmutable.</span>
        </Field>

        <Field label="Nombre" required>
          <input
            type="text"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            required
            minLength={2}
            maxLength={100}
            className={inputClass}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Fecha inicio" required>
            <input
              type="date"
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              required
              className={inputClass}
            />
          </Field>

          <Field label="Fecha fin" required>
            <input
              type="date"
              value={fechaFin}
              onChange={(e) => setFechaFin(e.target.value)}
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

        <div className="flex justify-end gap-2 border-t border-sidebar-bg-edge pt-4">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-body hover:bg-surface-alt disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-accent-brand px-4 py-2 text-sm font-medium text-white hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {submitting ? "Guardando..." : "Guardar"}
          </button>
        </div>
      </form>
    </Modal>
  )
}
