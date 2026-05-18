/**
 * Vista de Plantillas de TP (refactor 2026-05-12).
 *
 * Permite a la cátedra gestionar BRIEFS pedagógicos por (materia, período).
 * Un brief es una consigna corta de qué debe cubrir el TP — sirve como
 * prompt para que el docente o el wizard de IA generen el TP real en
 * cada comisión. NO hay fan-out automático.
 *
 * Workflow operativo:
 *  1. Seleccionar contexto academico (Univ -> ... -> Materia + Periodo)
 *  2. Lista de plantillas; crear una nueva (código + título + consigna + peso)
 *  3. Publicar / archivar / nueva versión
 *  4. Exportar como prompt para usar en una IA externa o en el wizard interno
 *
 * Patron de estados de modal: `ModalState` discriminated union — mutex
 * estricto para evitar doble modal. Mismo patron que `TareasPracticasView`.
 */
import { Badge, HelpButton, Modal, PageContainer } from "@platform/ui"
import {
  Archive,
  Eye,
  FileStack,
  GitBranch,
  Layers,
  Pencil,
  Plus,
  Send,
  Trash2,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import {
  type AcademicContext,
  AcademicContextSelector,
} from "../components/AcademicContextSelector"
import {
  type TareaEstado,
  type TareaPractica,
  type TareaPracticaTemplate,
  type TareaPracticaTemplateCreate,
  type TareaPracticaTemplateUpdate,
  tareasPracticasTemplatesApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
}

const ESTADO_LABEL: Record<TareaEstado, string> = {
  draft: "Borrador",
  published: "Publicado",
  archived: "Archivado",
}

const ESTADO_VARIANT: Record<TareaEstado, "default" | "success" | "warning"> = {
  draft: "default",
  published: "success",
  archived: "warning",
}

type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; template: TareaPracticaTemplate }
  | { kind: "view"; template: TareaPracticaTemplate }
  | { kind: "instances"; template: TareaPracticaTemplate }
  | { kind: "new-version"; template: TareaPracticaTemplate }

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function TemplatesView({ getToken }: Props) {
  const [ctx, setCtx] = useState<AcademicContext | null>(null)
  const [templates, setTemplates] = useState<TareaPracticaTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modal, setModal] = useState<ModalState>({ kind: "closed" })

  const closeModal = () => setModal({ kind: "closed" })

  const refreshList = useCallback(async () => {
    if (!ctx) {
      setTemplates([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const list = await tareasPracticasTemplatesApi.list(
        { materia_id: ctx.materiaId, periodo_id: ctx.periodoId },
        getToken,
      )
      setTemplates(list)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [ctx, getToken])

  useEffect(() => {
    refreshList()
  }, [refreshList])

  const handlePublish = async (t: TareaPracticaTemplate) => {
    try {
      await tareasPracticasTemplatesApi.publish(t.id, getToken)
      await refreshList()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleArchive = async (t: TareaPracticaTemplate) => {
    const ok = window.confirm(
      `Archivar la plantilla "${t.codigo}: ${t.titulo}"? Las instancias en comisiones no se archivan automáticamente.`,
    )
    if (!ok) return
    try {
      await tareasPracticasTemplatesApi.archive(t.id, getToken)
      await refreshList()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDelete = async (t: TareaPracticaTemplate) => {
    const ok = window.confirm(
      `Eliminar la plantilla "${t.codigo}: ${t.titulo}"? Soft delete. Las instancias existentes quedan con link muerto al template.`,
    )
    if (!ok) return
    try {
      await tareasPracticasTemplatesApi.delete(t.id, getToken)
      await refreshList()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <PageContainer
      title="Plantillas de Trabajos Prácticos"
      description="Briefs pedagógicos a nivel cátedra (materia + período). Definen QUÉ debe cubrir el TP sin escribir el enunciado completo. Sirven como prompt para que el docente o el wizard de IA generen el TP en cada comisión."
      eyebrow="Inicio · Plantillas (cátedra)"
      helpContent={helpContent.templates}
    >
      <div className="space-y-6">
        <AcademicContextSelector value={ctx} onChange={setCtx} getToken={getToken} />

        {!ctx ? (
          <div className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up">
            <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
              <Layers className="h-7 w-7 text-muted" />
            </div>
            <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
              Seleccioná universidad, facultad, carrera, plan, materia y período para ver o crear
              plantillas.
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3 flex-wrap animate-fade-in-up">
              <p className="text-xs text-muted leading-relaxed max-w-2xl">
                Templates canónicos para esta materia y período. Crear uno auto-instancia un TP en
                cada comisión existente. Las nuevas versiones se propagan a las instancias sin
                drift.
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={refreshList}
                  disabled={loading}
                  className="press-shrink px-3 py-1.5 text-xs border border-border bg-surface rounded-md hover:bg-surface-alt disabled:opacity-40 text-muted transition-colors"
                >
                  {loading ? "Cargando..." : "Refrescar"}
                </button>
                <button
                  type="button"
                  onClick={() => setModal({ kind: "create" })}
                  className="press-shrink inline-flex items-center gap-1.5 px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep text-white rounded-md font-medium transition-colors shadow-[0_1px_2px_0_rgba(24,95,165,0.25)]"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Nueva plantilla
                </button>
              </div>
            </div>

            {error && (
              <div className="animate-fade-in-up rounded-xl border border-danger/30 bg-danger-soft p-4">
                <div className="text-sm font-semibold text-danger">
                  No pudimos cargar las plantillas
                </div>
                <div className="mt-1.5 font-mono text-xs text-danger/85 break-all">{error}</div>
              </div>
            )}

            {loading && templates.length === 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 animate-fade-in">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="skeleton h-40 rounded-xl" />
                ))}
              </div>
            ) : templates.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up">
                <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
                  <FileStack className="h-7 w-7 text-muted" />
                </div>
                <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
                  No hay plantillas para esta materia y período. Creá la primera con el botón "Nueva
                  plantilla".
                </p>
              </div>
            ) : (
              <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {templates.map((t, idx) => (
                  <li
                    key={t.id}
                    className="animate-fade-in-up"
                    style={{ animationDelay: `${Math.min(idx, 6) * 50}ms` }}
                  >
                    <TemplateCard
                      template={t}
                      onView={() => setModal({ kind: "view", template: t })}
                      onEdit={() => setModal({ kind: "edit", template: t })}
                      onPublish={() => handlePublish(t)}
                      onArchive={() => handleArchive(t)}
                      onDelete={() => handleDelete(t)}
                      onShowInstances={() => setModal({ kind: "instances", template: t })}
                      onNewVersion={() => setModal({ kind: "new-version", template: t })}
                    />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {/* Modal: crear plantilla */}
        {modal.kind === "create" && ctx && (
          <TemplateFormModal
            title="Nueva plantilla de TP"
            initial={null}
            submitLabel="Crear plantilla"
            onClose={closeModal}
            onSubmit={async (values) => {
              const body: TareaPracticaTemplateCreate = {
                materia_id: ctx.materiaId,
                periodo_id: ctx.periodoId,
                codigo: values.codigo,
                titulo: values.titulo,
                consigna: values.consigna,
                peso: values.peso,
              }
              await tareasPracticasTemplatesApi.create(body, getToken)
              closeModal()
              await refreshList()
            }}
          />
        )}

        {/* Modal: editar plantilla (draft solamente) */}
        {modal.kind === "edit" && (
          <TemplateFormModal
            title={`Editar plantilla: ${modal.template.codigo}`}
            initial={modal.template}
            submitLabel="Guardar cambios"
            onClose={closeModal}
            lockCodigo
            onSubmit={async (values) => {
              const patch: TareaPracticaTemplateUpdate = {
                titulo: values.titulo,
                consigna: values.consigna,
                peso: values.peso,
              }
              await tareasPracticasTemplatesApi.update(modal.template.id, patch, getToken)
              closeModal()
              await refreshList()
            }}
          />
        )}

        {/* Modal: nueva version */}
        {modal.kind === "new-version" && (
          <NewVersionModal
            template={modal.template}
            getToken={getToken}
            onClose={closeModal}
            onDone={async () => {
              closeModal()
              await refreshList()
            }}
          />
        )}

        {/* Modal: ver detalle plantilla */}
        {modal.kind === "view" && (
          <TemplateViewModal template={modal.template} getToken={getToken} onClose={closeModal} />
        )}

        {/* Modal: ver instancias */}
        {modal.kind === "instances" && (
          <InstancesModal template={modal.template} getToken={getToken} onClose={closeModal} />
        )}
      </div>
    </PageContainer>
  )
}

// ── Card ──────────────────────────────────────────────────────────────

function TemplateCard({
  template,
  onView,
  onEdit,
  onPublish,
  onArchive,
  onDelete,
  onShowInstances,
  onNewVersion,
}: {
  template: TareaPracticaTemplate
  onView: () => void
  onEdit: () => void
  onPublish: () => void
  onArchive: () => void
  onDelete: () => void
  onShowInstances: () => void
  onNewVersion: () => void
}) {
  const estado = template.estado
  const accentByEstado: Record<TareaEstado, string> = {
    draft: "bg-muted-soft",
    published: "bg-success",
    archived: "bg-warning",
  }
  return (
    <article className="hover-lift group relative overflow-hidden rounded-xl border border-border bg-surface flex flex-col h-full shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
      <div
        aria-hidden="true"
        className={`absolute left-0 top-0 bottom-0 w-1 ${accentByEstado[estado]} opacity-60 group-hover:opacity-100 transition-opacity`}
      />

      <div className="p-4 flex-1 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="font-mono text-[11px] uppercase tracking-wider text-muted px-2 py-0.5 rounded bg-surface-alt border border-border-soft">
              {template.codigo}
            </span>
            <span className="font-mono text-[11px] tabular-nums text-muted-soft">
              v{template.version}
            </span>
          </div>
          <Badge variant={ESTADO_VARIANT[estado]}>{ESTADO_LABEL[estado]}</Badge>
        </div>

        <div className="min-w-0">
          <h3
            className="text-[15px] font-semibold text-ink leading-tight tracking-tight line-clamp-2"
            title={template.titulo}
          >
            {template.titulo}
          </h3>
          {template.parent_template_id && (
            <div className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted">
              <GitBranch className="h-3 w-3" />
              Versión derivada
            </div>
          )}
        </div>

        <div className="flex items-center justify-between text-xs text-muted mt-auto pt-2 border-t border-border-soft">
          <span className="text-[10px] uppercase tracking-wider text-muted-soft">Peso</span>
          <span className="font-mono tabular-nums text-body">{template.peso}</span>
        </div>
      </div>

      <footer className="flex items-stretch border-t border-border-soft text-[11px] font-medium">
        <button
          type="button"
          onClick={onShowInstances}
          className="press-shrink flex-1 inline-flex items-center justify-center gap-1.5 px-2 py-2.5 text-muted hover:bg-surface-alt hover:text-ink transition-colors"
          title="Ver instancias en comisiones"
        >
          <Layers className="h-3.5 w-3.5" />
          Instancias
        </button>
        <button
          type="button"
          onClick={onView}
          className="press-shrink inline-flex items-center justify-center gap-1.5 px-2 py-2.5 border-l border-border-soft text-muted hover:bg-surface-alt hover:text-ink transition-colors"
          title="Ver detalle"
        >
          <Eye className="h-3.5 w-3.5" />
        </button>
        {estado === "draft" && (
          <>
            <button
              type="button"
              onClick={onEdit}
              className="press-shrink inline-flex items-center justify-center gap-1.5 px-2 py-2.5 border-l border-border-soft text-accent-brand-deep hover:bg-accent-brand-soft transition-colors"
              title="Editar"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onPublish}
              className="press-shrink inline-flex items-center justify-center gap-1.5 px-2 py-2.5 border-l border-border-soft text-success hover:bg-success-soft transition-colors"
              title="Publicar"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onDelete}
              className="press-shrink inline-flex items-center justify-center gap-1.5 px-2 py-2.5 border-l border-border-soft text-danger hover:bg-danger-soft transition-colors"
              title="Eliminar"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        {estado === "published" && (
          <>
            <button
              type="button"
              onClick={onNewVersion}
              className="press-shrink inline-flex items-center justify-center gap-1.5 px-2 py-2.5 border-l border-border-soft text-accent-brand-deep hover:bg-accent-brand-soft transition-colors"
              title="Nueva versión"
            >
              <GitBranch className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onArchive}
              className="press-shrink inline-flex items-center justify-center gap-1.5 px-2 py-2.5 border-l border-border-soft text-warning hover:bg-warning-soft transition-colors"
              title="Archivar"
            >
              <Archive className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        {estado === "archived" && (
          <button
            type="button"
            onClick={onNewVersion}
            className="press-shrink inline-flex items-center justify-center gap-1.5 px-2 py-2.5 border-l border-border-soft text-accent-brand-deep hover:bg-accent-brand-soft transition-colors"
            title="Nueva versión"
          >
            <GitBranch className="h-3.5 w-3.5" />
          </button>
        )}
      </footer>
    </article>
  )
}

// ── Form modal (create / edit) ────────────────────────────────────────

interface FormValues {
  codigo: string
  titulo: string
  consigna: string
  peso: string
}

function TemplateFormModal({
  title,
  initial,
  submitLabel,
  onClose,
  onSubmit,
  lockCodigo = false,
}: {
  title: string
  initial: TareaPracticaTemplate | null
  submitLabel: string
  onClose: () => void
  onSubmit: (values: FormValues) => Promise<void>
  lockCodigo?: boolean
}) {
  const [codigo, setCodigo] = useState(initial?.codigo ?? "")
  const [titulo, setTitulo] = useState(initial?.titulo ?? "")
  const [consigna, setConsigna] = useState(initial?.consigna ?? "")
  const [peso, setPeso] = useState(initial?.peso ?? "1.0")
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setSubmitting(true)
    try {
      await onSubmit({
        codigo: codigo.trim(),
        titulo: titulo.trim(),
        consigna: consigna.trim(),
        peso: peso.trim(),
      })
    } catch (err) {
      setFormError(String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal isOpen={true} onClose={onClose} title={title} size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HelpButton
            size="sm"
            title="Plantilla pedagógica (brief)"
            content={
              <div className="space-y-3 text-sidebar-text-muted">
                <p>
                  La plantilla es un <strong>brief pedagógico</strong>: una consigna corta de qué
                  debe cubrir el TP. NO se copia automáticamente a las comisiones — sirve como
                  prompt para que el docente o la IA generen los TPs en cada comisión.
                </p>
                <ul className="list-disc pl-5 space-y-2">
                  <li>
                    <strong>Código:</strong> Identificador corto (ej. TP1). Inmutable una vez
                    creada.
                  </li>
                  <li>
                    <strong>Título:</strong> Nombre descriptivo del TP.
                  </li>
                  <li>
                    <strong>Consigna:</strong> Directiva pedagógica — qué temas, qué profundidad,
                    qué tipo de ejercicios debería contener el TP. Pensala como un PROMPT.
                  </li>
                  <li>
                    <strong>Peso:</strong> Ponderación entre 0 y 1.
                  </li>
                </ul>
                <p>
                  Cuando la guardés, podés <strong>exportarla como prompt</strong> (botón en la
                  vista) o <strong>usarla como entrada del wizard de IA</strong> para generar los
                  ejercicios en cada comisión.
                </p>
              </div>
            }
          />
          <span className="text-sm text-muted">Ayuda sobre el formulario</span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="block text-xs font-medium text-muted mb-1">Código</span>
            <input
              type="text"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              required
              disabled={lockCodigo}
              placeholder="TP1"
              className="w-full px-2 py-1.5 text-sm border border-border rounded bg-surface disabled:opacity-60"
            />
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-muted mb-1">Peso (0 – 1)</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={peso}
              onChange={(e) => setPeso(e.target.value)}
              required
              className="w-full px-2 py-1.5 text-sm border border-border rounded bg-surface tabular-nums"
            />
          </label>
        </div>

        <label className="block">
          <span className="block text-xs font-medium text-muted mb-1">Título</span>
          <input
            type="text"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            required
            placeholder="Ej: Recursión y divide & conquer"
            className="w-full px-2 py-1.5 text-sm border border-border rounded bg-surface"
          />
        </label>

        <label className="block">
          <span className="block text-xs font-medium text-muted mb-1">
            Consigna pedagógica
          </span>
          <textarea
            value={consigna}
            onChange={(e) => setConsigna(e.target.value)}
            required
            rows={10}
            placeholder="Qué debe cubrir el TP: temas, profundidad, tipo de ejercicios, restricciones. Sirve como prompt para el docente o la IA."
            className="w-full px-2 py-1.5 text-sm border border-border rounded bg-surface"
          />
          <p className="text-xs text-muted mt-1">
            Pensala como un prompt: describí QUÉ tiene que enseñar el TP, no el enunciado completo.
          </p>
        </label>

        {formError && (
          <div className="p-2 rounded bg-danger-soft text-danger text-xs">{formError}</div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-border-soft">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-1.5 text-sm border border-border rounded hover:bg-surface-alt disabled:opacity-40"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border-strong text-white rounded font-medium"
          >
            {submitting ? "Guardando..." : submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  )
}

// ── New-version modal ─────────────────────────────────────────────────

function NewVersionModal({
  template,
  getToken,
  onClose,
  onDone,
}: {
  template: TareaPracticaTemplate
  getToken: () => Promise<string | null>
  onClose: () => void
  onDone: () => Promise<void>
}) {
  const [titulo, setTitulo] = useState(template.titulo)
  const [consigna, setConsigna] = useState(template.consigna)
  const [peso, setPeso] = useState(template.peso)
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr(null)
    setSubmitting(true)
    try {
      await tareasPracticasTemplatesApi.newVersion(
        template.id,
        { patch: { titulo, consigna, peso } },
        getToken,
      )
      await onDone()
    } catch (e2) {
      setErr(String(e2))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={`Nueva versión desde ${template.codigo} v${template.version}`}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HelpButton
            size="sm"
            title="Crear nueva versión de plantilla"
            content={
              <div className="space-y-3 text-sidebar-text-muted">
                <p>
                  Crea una nueva versión (v+1) en estado borrador. La versión anterior queda
                  archivable y los TPs ya creados que referencian la versión vieja preservan su
                  link — la trazabilidad histórica no se rompe.
                </p>
              </div>
            }
          />
          <span className="text-sm text-muted">Ayuda sobre nueva versión</span>
        </div>

        <label className="block">
          <span className="block text-xs font-medium text-muted mb-1">Título</span>
          <input
            type="text"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            required
            className="w-full px-2 py-1.5 text-sm border border-border rounded bg-surface"
          />
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-muted mb-1">Consigna pedagógica</span>
          <textarea
            value={consigna}
            onChange={(e) => setConsigna(e.target.value)}
            required
            rows={10}
            className="w-full px-2 py-1.5 text-sm border border-border rounded bg-surface"
          />
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-muted mb-1">Peso</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={peso}
            onChange={(e) => setPeso(e.target.value)}
            required
            className="w-full px-2 py-1.5 text-sm border border-border rounded bg-surface tabular-nums"
          />
        </label>

        {err && <div className="p-2 rounded bg-danger-soft text-danger text-xs">{err}</div>}

        <div className="flex justify-end gap-2 pt-2 border-t border-border-soft">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-1.5 text-sm border border-border rounded hover:bg-surface-alt disabled:opacity-40"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border-strong text-white rounded font-medium"
          >
            {submitting ? "Creando..." : "Crear nueva versión"}
          </button>
        </div>
      </form>
    </Modal>
  )
}

// ── View modal ────────────────────────────────────────────────────────

function TemplateViewModal({
  template,
  getToken,
  onClose,
}: {
  template: TareaPracticaTemplate
  getToken: () => Promise<string | null>
  onClose: () => void
}) {
  const [promptText, setPromptText] = useState<string | null>(null)
  const [loadingPrompt, setLoadingPrompt] = useState(false)
  const [copied, setCopied] = useState(false)
  const [promptErr, setPromptErr] = useState<string | null>(null)

  const handleExportPrompt = async () => {
    setLoadingPrompt(true)
    setPromptErr(null)
    try {
      const r = await tareasPracticasTemplatesApi.exportPrompt(template.id, getToken)
      setPromptText(r.prompt)
    } catch (e) {
      setPromptErr(String(e))
    } finally {
      setLoadingPrompt(false)
    }
  }

  const handleCopy = async () => {
    if (!promptText) return
    try {
      await navigator.clipboard.writeText(promptText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // navigator.clipboard requires HTTPS in prod — falla silenciosa en dev http.
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={`${template.codigo}: ${template.titulo}`}
      size="lg"
    >
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Badge variant={ESTADO_VARIANT[template.estado]}>{ESTADO_LABEL[template.estado]}</Badge>
          <span className="text-xs text-muted">
            v{template.version}
            {template.parent_template_id && " · derivada"}
          </span>
          <span className="text-xs text-muted">Peso: {template.peso}</span>
        </div>

        <div>
          <div className="text-xs font-medium text-muted mb-1">Consigna pedagógica</div>
          <div className="p-3 rounded bg-surface-alt max-h-96 overflow-y-auto whitespace-pre-wrap text-sm">
            {template.consigna}
          </div>
        </div>

        {/* Exportar como prompt */}
        <div className="border-t border-border-soft pt-3">
          {promptText === null ? (
            <button
              type="button"
              onClick={handleExportPrompt}
              disabled={loadingPrompt}
              className="px-3 py-1.5 text-sm border border-accent-brand text-accent-brand hover:bg-accent-brand hover:text-white rounded disabled:opacity-40"
            >
              {loadingPrompt ? "Generando..." : "Exportar como prompt"}
            </button>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted">Prompt para IA</span>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="px-2 py-1 text-xs border border-border rounded hover:bg-surface-alt"
                >
                  {copied ? "Copiado ✓" : "Copiar al portapapeles"}
                </button>
              </div>
              <pre className="p-3 rounded bg-surface-alt text-xs whitespace-pre-wrap max-h-72 overflow-y-auto border border-border-soft">
                {promptText}
              </pre>
            </div>
          )}
          {promptErr && (
            <div className="mt-2 p-2 rounded bg-danger-soft text-danger text-xs">{promptErr}</div>
          )}
        </div>

        <div className="flex justify-end pt-2 border-t border-border-soft">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm bg-ink hover:bg-accent-brand-deep text-white rounded"
          >
            Cerrar
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Instances modal ───────────────────────────────────────────────────

function InstancesModal({
  template,
  getToken,
  onClose,
}: {
  template: TareaPracticaTemplate
  getToken: () => Promise<string | null>
  onClose: () => void
}) {
  const [instances, setInstances] = useState<TareaPractica[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    tareasPracticasTemplatesApi
      .instances(template.id, getToken)
      .then((r) => {
        if (!cancelled) setInstances(r)
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [template.id, getToken])

  return (
    <Modal isOpen={true} onClose={onClose} title={`Instancias de ${template.codigo}`} size="lg">
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HelpButton
            size="sm"
            title="TPs derivados de esta plantilla"
            content={
              <div className="space-y-3 text-sidebar-text-muted">
                <p>
                  Lista los <strong>TPs creados manualmente</strong> que referencian esta plantilla
                  via <code>template_id</code>. Es la trazabilidad: "qué TPs nacieron inspirados por
                  este brief".
                </p>
                <p>
                  Como ya no hay fan-out automático, esta lista arranca vacía y se llena a medida
                  que los docentes crean TPs eligiendo esta plantilla como prompt.
                </p>
              </div>
            }
          />
          <span className="text-sm text-muted">Ayuda sobre las instancias</span>
        </div>

        {err && <div className="p-3 rounded bg-danger-soft text-danger text-sm">{err}</div>}
        {!instances ? (
          <div className="p-6 text-center text-muted text-sm">Cargando instancias...</div>
        ) : instances.length === 0 ? (
          <div className="p-6 text-center text-muted text-sm">
            Sin TPs derivados. Cuando un docente cree un TP en su comisión usando esta plantilla
            como guía, aparecerá acá.
          </div>
        ) : (
          <div className="rounded border border-border-soft overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-surface-alt border-b border-border-soft">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Comision</th>
                  <th className="text-left px-3 py-2 font-medium">Estado</th>
                  <th className="text-right px-3 py-2 font-medium">Version</th>
                  <th className="text-left px-3 py-2 font-medium">Sincronizacion</th>
                  <th className="text-left px-3 py-2 font-medium">Actualizada</th>
                </tr>
              </thead>
              <tbody>
                {instances.map((i) => (
                  <tr key={i.id} className="border-b border-border-soft last:border-0">
                    <td className="px-3 py-2 font-mono text-xs" title={i.comision_id}>
                      {i.comision_id.slice(0, 8)}...
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={ESTADO_VARIANT[i.estado]}>{ESTADO_LABEL[i.estado]}</Badge>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted">v{i.version}</td>
                    <td className="px-3 py-2">
                      {i.has_drift ? (
                        <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-warning-soft text-warning">
                          Drift
                        </span>
                      ) : (
                        <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-success-soft text-success">
                          Sincronizada
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted">{formatDateTime(i.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex justify-end pt-2 border-t border-border-soft">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm bg-ink hover:bg-accent-brand-deep text-white rounded"
          >
            Cerrar
          </button>
        </div>
      </div>
    </Modal>
  )
}
