import { HelpButton, PageContainer, StateMessage } from "@platform/ui"
import { Plus, Trash2 } from "lucide-react"
import { type ReactNode, useEffect, useState } from "react"
import { HttpError, type Universidad, type UniversidadCreate, universidadesApi } from "../lib/api"
import { helpContent } from "../utils/helpContent"

export function UniversidadesPage(): ReactNode {
  const [items, setItems] = useState<Universidad[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await universidadesApi.list()
      setItems(resp.data)
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

  const handleDelete = async (u: Universidad) => {
    if (!window.confirm(`¿Eliminar universidad ${u.nombre}?`)) return
    setDeletingId(u.id)
    setError(null)
    try {
      await universidadesApi.delete(u.id)
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
      title="Universidades"
      description="Listado global. Crear requiere rol superadmin."
      eyebrow="Inicio · Universidades"
      helpContent={helpContent.universidades}
    >
      <div className="space-y-6">
        <div className="flex items-center justify-between gap-3 flex-wrap animate-fade-in-up">
          <p className="text-xs text-muted leading-relaxed max-w-2xl">
            Tope de la jerarquía académica. Cada universidad se vincula a un realm de Keycloak para
            la federación LDAP institucional.
          </p>
          <button
            type="button"
            onClick={() => setShowForm(!showForm)}
            className="press-shrink inline-flex items-center gap-1.5 rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep transition-colors shadow-[0_1px_2px_0_rgba(24,95,165,0.25)]"
          >
            {showForm ? "Cancelar" : (<>
              <Plus className="h-3.5 w-3.5" /> Nueva universidad
            </>)}
          </button>
        </div>

        {showForm && (
          <UniversidadForm
            onCreated={async () => {
              setShowForm(false)
              await load()
            }}
          />
        )}

        {error && (
          <div className="animate-fade-in-up rounded-xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
            {error}
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 animate-fade-in">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-28 rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <StateMessage
            variant="empty"
            title="Sin universidades"
            description="No hay universidades registradas todavia."
          />
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {items.map((u, idx) => (
              <li
                key={u.id}
                className="animate-fade-in-up"
                style={{ animationDelay: `${Math.min(idx, 6) * 50}ms` }}
              >
                <article className="hover-lift group relative overflow-hidden rounded-xl border border-border bg-surface flex flex-col h-full shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
                  <div
                    aria-hidden="true"
                    className="absolute left-0 top-0 bottom-0 w-1 bg-accent-brand/0 group-hover:bg-accent-brand/60 transition-colors"
                  />
                  <div className="p-4 flex-1 flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] uppercase tracking-wider text-muted px-2 py-0.5 rounded bg-surface-alt border border-border-soft">
                        {u.codigo}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider text-muted-soft">
                        {new Date(u.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-ink leading-tight tracking-tight" title={u.nombre}>
                      {u.nombre}
                    </h3>
                    <div className="text-[11px] font-mono text-muted truncate" title={u.keycloak_realm}>
                      realm: {u.keycloak_realm}
                    </div>
                  </div>
                  <footer className="flex items-stretch border-t border-border-soft">
                    <button
                      type="button"
                      onClick={() => void handleDelete(u)}
                      disabled={deletingId === u.id}
                      className="press-shrink flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs text-danger hover:bg-danger-soft transition-colors disabled:opacity-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      {deletingId === u.id ? "Eliminando…" : "Eliminar"}
                    </button>
                  </footer>
                </article>
              </li>
            ))}
          </ul>
        )}
      </div>
    </PageContainer>
  )
}

function UniversidadForm({
  onCreated,
}: {
  onCreated: () => void
}): ReactNode {
  const [form, setForm] = useState<UniversidadCreate>({
    nombre: "",
    codigo: "",
    keycloak_realm: "",
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await universidadesApi.create(form)
      onCreated()
    } catch (e) {
      setError(e instanceof HttpError ? `${e.status}: ${e.detail || e.title}` : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-border bg-surface p-6 space-y-4 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] animate-fade-in-up">
      <div className="flex items-center gap-2 mb-2">
        <HelpButton
          size="sm"
          title="Formulario de Universidad"
          content={
            <div className="space-y-3 text-muted-soft">
              <p>
                <strong>Completa los siguientes campos</strong> para crear una nueva universidad:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Nombre:</strong> Nombre completo de la institucion (ej. Universidad
                  Nacional de San Luis).
                </li>
                <li>
                  <strong>Codigo:</strong> Identificador corto unico (ej. unsl). Solo letras,
                  numeros, guiones. Inmutable una vez creado.
                </li>
                <li>
                  <strong>Dominio email:</strong> Opcional. Dominio institucional (ej. unsl.edu.ar).
                </li>
                <li>
                  <strong>Keycloak realm:</strong> Nombre del realm en Keycloak. Debe existir o
                  crearse via onboarding. Inmutable una vez creado.
                </li>
              </ul>
            </div>
          }
        />
        <span className="text-sm text-muted">Nueva universidad</span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Nombre" required>
          <input
            type="text"
            value={form.nombre}
            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
            required
            minLength={2}
            className={inputClass}
            placeholder="Universidad Nacional de San Luis"
          />
        </Field>

        <Field label="Código" required>
          <input
            type="text"
            value={form.codigo}
            onChange={(e) => setForm({ ...form, codigo: e.target.value })}
            required
            pattern="[A-Za-z0-9_-]+"
            className={inputClass}
            placeholder="unsl"
          />
        </Field>

        <Field label="Dominio email">
          <input
            type="text"
            value={form.dominio_email ?? ""}
            onChange={(e) => setForm({ ...form, dominio_email: e.target.value })}
            className={inputClass}
            placeholder="unsl.edu.ar"
          />
        </Field>

        <Field label="Keycloak realm" required>
          <input
            type="text"
            value={form.keycloak_realm}
            onChange={(e) => setForm({ ...form, keycloak_realm: e.target.value })}
            required
            className={inputClass}
            placeholder="unsl"
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
  "w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-brand transition-colors"

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
