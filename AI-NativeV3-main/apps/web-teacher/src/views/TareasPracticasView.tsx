/**
 * Vista de gestión de Trabajos Prácticos (TPs).
 *
 * Permite al docente:
 *  - Listar TPs de una comisión filtrados por estado
 *  - Crear TPs nuevos en estado `draft`
 *  - Editar TPs (sólo en `draft` — backend rechaza 409 en otros estados)
 *  - Publicar (draft → published) y archivar (published → archived)
 *  - Eliminar (soft delete)
 *  - Crear nueva versión (forkea el TP a un nuevo `draft` con parent_tarea_id)
 *  - Ver el historial de versiones
 *
 * Los estados son transiciones puntuales del docente — no hay pipeline async
 * como en Materiales, por lo que NO hay polling acá.
 *
 * Máquina de estados de modales: enum `ModalState` — mutex estricto.
 * Los 5 bools originales (showCreate, editing, viewing, versioningFrom, versionsOf)
 * fueron consolidados en un enum para evitar el race condition de "dos modales
 * abiertos al mismo tiempo" si un handler apagaba uno pero olvidaba el otro.
 */
import { Badge, HelpButton, MarkdownRenderer, Modal, PageContainer } from "@platform/ui"
import {
  Archive,
  ArrowDown,
  ArrowUp,
  Eye,
  FileText,
  GitBranch,
  History,
  Pencil,
  Plus,
  Send,
  Trash2,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useComisionLabel } from "../components/ComisionSelector"
import {
  type Ejercicio,
  type TareaEstado,
  type TareaPractica,
  type TareaPracticaTemplate,
  type TareaPracticaUpdate,
  type TareaPracticaVersionRef,
  type TpEjercicio,
  listEjercicios,
  listMyComisiones,
  tareasPracticasApi,
  tareasPracticasTemplatesApi,
  tpEjerciciosApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
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

type EstadoFilter = "all" | TareaEstado

// Enum para máquina de estados de modales — reemplaza los 5 bools independientes.
type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; tarea: TareaPractica }
  | { kind: "view"; tarea: TareaPractica }
  | { kind: "versioning"; tarea: TareaPractica }
  | { kind: "versions-list"; tarea: TareaPractica }
  | { kind: "composicion"; tarea: TareaPractica }

// ADR-016 — badge "derivado de plantilla": muestra que la instancia fue
// creada por fan-out desde un `TareaPracticaTemplate`. Clickeable para
// mostrar el id del template (puente a la vista "Plantillas").
function TemplateBadge({ templateId }: { templateId: string }) {
  const title = `Derivado de plantilla de cátedra: ${templateId}`
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-[10px] font-medium bg-surface-alt text-body border border-border-soft"
      title={title}
    >
      Plantilla
    </span>
  )
}

// ADR-016 — badge "drift": la instancia divergio de la plantilla de cátedra.
// Desde ese momento, nuevas versiones del template no se propagan
// automáticamente a esta fila (se preserva el link `template_id` pero
// la auto-sincronizacion queda deshabilitada).
function DriftBadge() {
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-[10px] font-medium bg-warning-soft text-warning border border-warning/30"
      title="Este TP divergio de la plantilla de cátedra. No recibira nuevas versiones automáticas del template."
    >
      Drift
    </span>
  )
}

function formatShortDate(iso: string | null): string {
  if (!iso) return "sin fecha"
  const d = new Date(iso)
  return d.toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  })
}

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

/** Convierte ISO 8601 → valor para `<input type="datetime-local">` (YYYY-MM-DDTHH:mm). */
function isoToLocalInput(iso: string | null): string {
  if (!iso) return ""
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Convierte valor de `<input type="datetime-local">` → ISO 8601 (o null si vacío). */
function localInputToIso(local: string): string | null {
  if (!local) return null
  return new Date(local).toISOString()
}

export function TareasPracticasView({ comisionId, getToken }: Props) {
  const comisionLabelText = useComisionLabel(comisionId)
  const [tareas, setTareas] = useState<TareaPractica[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [estadoFilter, setEstadoFilter] = useState<EstadoFilter>("all")

  // Máquina de estados — un único estado activo a la vez (mutex).
  const [modal, setModal] = useState<ModalState>({ kind: "closed" })

  const closeModal = () => setModal({ kind: "closed" })

  const refreshList = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await tareasPracticasApi.list(
        {
          comision_id: comisionId,
          ...(estadoFilter === "all" ? {} : { estado: estadoFilter }),
        },
        getToken,
      )
      setTareas(r.data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [comisionId, estadoFilter, getToken])

  useEffect(() => {
    refreshList()
  }, [refreshList])

  const handlePublish = async (t: TareaPractica) => {
    try {
      await tareasPracticasApi.publish(t.id, getToken)
      await refreshList()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleArchive = async (t: TareaPractica) => {
    const ok = window.confirm(
      `¿Archivar el TP "${t.codigo}: ${t.titulo}"? Los estudiantes no podrán seguir enviando episodios.`,
    )
    if (!ok) return
    try {
      await tareasPracticasApi.archive(t.id, getToken)
      await refreshList()
    } catch (e) {
      setError(String(e))
    }
  }

  const handleDelete = async (t: TareaPractica) => {
    const ok = window.confirm(
      `¿Eliminar el TP "${t.codigo}: ${t.titulo}"? Esta acción es un soft delete.`,
    )
    if (!ok) return
    try {
      await tareasPracticasApi.delete(t.id, getToken)
      await refreshList()
    } catch (e) {
      setError(String(e))
    }
  }

  const totalDraft = tareas.filter((t) => t.estado === "draft").length
  const totalPublished = tareas.filter((t) => t.estado === "published").length

  return (
    <PageContainer
      title="Trabajos prácticos"
      description={`Diseña los TPs de la comisión. Solo los TPs publicados aceptan episodios. Comisión: ${comisionLabelText}`}
      eyebrow={`Inicio · Tareas prácticas · ${comisionLabelText}`}
      helpContent={helpContent.tareasPracticas}
    >
      <div className="space-y-6">
        {/* ═══ Toolbar: filtros + acciones ════════════════════════════════ */}
        <div className="flex items-center justify-between gap-4 flex-wrap animate-fade-in-up">
          <div
            role="tablist"
            aria-label="Filtro por estado"
            className="flex items-center gap-1 bg-surface border border-border rounded-lg p-1 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]"
          >
            {(["all", "draft", "published", "archived"] as const).map((f) => {
              const labels: Record<typeof f, string> = {
                all: "Todos",
                draft: "Borrador",
                published: "Publicado",
                archived: "Archivado",
              }
              const counts: Record<typeof f, number | null> = {
                all: tareas.length,
                draft: totalDraft,
                published: totalPublished,
                archived: tareas.filter((t) => t.estado === "archived").length,
              }
              const active = estadoFilter === f
              return (
                <button
                  key={f}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setEstadoFilter(f)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors press-shrink ${
                    active ? "bg-ink text-white" : "text-muted hover:text-ink hover:bg-surface-alt"
                  }`}
                >
                  {labels[f]}
                  <span
                    className={`ml-1.5 font-mono tabular-nums text-[10px] ${active ? "text-white/70" : "text-muted-soft"}`}
                  >
                    {counts[f]}
                  </span>
                </button>
              )
            })}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={refreshList}
              disabled={loading}
              className="press-shrink px-3 py-1.5 text-xs border border-border bg-surface rounded-md hover:bg-surface-alt transition-colors disabled:opacity-40 text-muted"
            >
              {loading ? "Cargando..." : "Refrescar"}
            </button>
            <button
              type="button"
              onClick={() => setModal({ kind: "create" })}
              className="press-shrink inline-flex items-center gap-1.5 px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep text-white rounded-md font-medium transition-colors shadow-[0_1px_2px_0_rgba(24,95,165,0.25)]"
            >
              <Plus className="h-3.5 w-3.5" />
              Nuevo TP
            </button>
          </div>
        </div>

        {/* ═══ Error ══════════════════════════════════════════════════════ */}
        {error && (
          <div className="animate-fade-in-up rounded-xl border border-danger/30 bg-danger-soft p-4">
            <div className="text-sm font-semibold text-danger">
              No pudimos completar la operación
            </div>
            <div className="mt-1.5 font-mono text-xs text-danger/85 break-all">{error}</div>
          </div>
        )}

        {/* ═══ Loading skeleton ═══════════════════════════════════════════ */}
        {loading && tareas.length === 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 animate-fade-in">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-44 rounded-xl" />
            ))}
          </div>
        )}

        {/* ═══ Empty state ════════════════════════════════════════════════ */}
        {!loading && tareas.length === 0 && (
          <div className="animate-fade-in-up rounded-2xl border border-dashed border-border bg-surface p-10 max-w-2xl mx-auto text-center">
            <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
              <FileText className="h-7 w-7 text-muted" />
            </div>
            <h2 className="text-lg font-semibold text-ink mb-2">
              Todavía no hay TPs en esta comisión
            </h2>
            <p className="text-sm text-muted leading-relaxed max-w-sm mx-auto mb-5">
              Empezá creando un TP a mano o pedile a la IA un punto de partida que después podés
              editar a fondo.
            </p>
            <div className="flex items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => setModal({ kind: "create" })}
                className="press-shrink inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs bg-accent-brand hover:bg-accent-brand-deep text-white rounded-md font-medium transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                Nuevo TP
              </button>
            </div>
          </div>
        )}

        {/* ═══ Grid de TPs ════════════════════════════════════════════════ */}
        {tareas.length > 0 && (
          <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {tareas.map((t, idx) => (
              <li
                key={t.id}
                className="animate-fade-in-up"
                style={{ animationDelay: `${Math.min(idx, 6) * 50}ms` }}
              >
                <TareaCard
                  tarea={t}
                  onView={() => setModal({ kind: "view", tarea: t })}
                  onEdit={() => setModal({ kind: "edit", tarea: t })}
                  onPublish={() => handlePublish(t)}
                  onArchive={() => handleArchive(t)}
                  onNewVersion={() => setModal({ kind: "versioning", tarea: t })}
                  onDelete={() => handleDelete(t)}
                  onShowVersions={() => setModal({ kind: "versions-list", tarea: t })}
                  onComposicion={() => setModal({ kind: "composicion", tarea: t })}
                />
              </li>
            ))}
          </ul>
        )}

        {/* Modal: crear nuevo TP */}
        <TareaFormModal
          isOpen={modal.kind === "create"}
          title="Nuevo trabajo practico"
          initial={null}
          comisionId={comisionId}
          getToken={getToken}
          onClose={closeModal}
          onSubmit={async (values) => {
            await tareasPracticasApi.create(
              {
                ...values,
                comision_id: comisionId,
              },
              getToken,
            )
            closeModal()
            await refreshList()
          }}
        />

        {/* Modal: composicion de ejercicios (ADR-047) */}
        {modal.kind === "composicion" && (
          <ComposicionModal
            tarea={modal.tarea}
            getToken={getToken}
            onClose={closeModal}
          />
        )}

        {/* Modal: editar TP (draft solamente) */}
        {modal.kind === "edit" && (
          <TareaFormModal
            isOpen={true}
            title={`Editar TP: ${modal.tarea.codigo}`}
            initial={modal.tarea}
            mode="edit"
            onClose={closeModal}
            onSubmit={async (values) => {
              const patch: TareaPracticaUpdate = {
                codigo: values.codigo,
                titulo: values.titulo,
                enunciado: values.enunciado,
                fecha_inicio: values.fecha_inicio,
                fecha_fin: values.fecha_fin,
                peso: values.peso,
                rubrica: values.rubrica,
              }
              await tareasPracticasApi.update(modal.tarea.id, patch, getToken)
              closeModal()
              await refreshList()
            }}
          />
        )}

        {/* Modal: nueva versión desde TP existente */}
        {modal.kind === "versioning" && (
          <TareaFormModal
            isOpen={true}
            title={`Nueva version desde ${modal.tarea.codigo} v${modal.tarea.version}`}
            initial={modal.tarea}
            mode="version"
            onClose={closeModal}
            onSubmit={async (values) => {
              const patch: TareaPracticaUpdate = {
                codigo: values.codigo,
                titulo: values.titulo,
                enunciado: values.enunciado,
                fecha_inicio: values.fecha_inicio,
                fecha_fin: values.fecha_fin,
                peso: values.peso,
                rubrica: values.rubrica,
              }
              await tareasPracticasApi.newVersion(modal.tarea.id, patch, getToken)
              closeModal()
              await refreshList()
            }}
          />
        )}

        {/* Modal: ver detalle TP (solo lectura) */}
        {modal.kind === "view" && (
          <TareaViewModal
            tarea={modal.tarea}
            onClose={closeModal}
            onShowVersions={() => {
              setModal({ kind: "versions-list", tarea: modal.tarea })
            }}
          />
        )}

        {/* Modal: historial de versiones */}
        {modal.kind === "versions-list" && (
          <VersionsModal tarea={modal.tarea} getToken={getToken} onClose={closeModal} />
        )}
      </div>
    </PageContainer>
  )
}

// ── Card ──────────────────────────────────────────────────────────────

function TareaCard({
  tarea,
  onView,
  onEdit,
  onPublish,
  onArchive,
  onNewVersion,
  onDelete,
  onShowVersions,
  onComposicion,
}: {
  tarea: TareaPractica
  onView: () => void
  onEdit: () => void
  onPublish: () => void
  onArchive: () => void
  onNewVersion: () => void
  onDelete: () => void
  onShowVersions: () => void
  onComposicion: () => void
}) {
  const estado = tarea.estado
  const accentByEstado: Record<TareaEstado, string> = {
    draft: "bg-muted-soft",
    published: "bg-success",
    archived: "bg-warning",
  }

  return (
    <article className="hover-lift group relative overflow-hidden rounded-xl border border-border bg-surface flex flex-col h-full shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
      {/* Banda izquierda según estado */}
      <div
        aria-hidden="true"
        className={`absolute left-0 top-0 bottom-0 w-1 ${accentByEstado[estado]} opacity-60 group-hover:opacity-100 transition-opacity`}
      />

      <div className="p-4 flex-1 flex flex-col gap-3">
        {/* Kicker: código + badges */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap min-w-0">
            <span className="font-mono text-[11px] uppercase tracking-wider text-muted px-2 py-0.5 rounded bg-surface-alt border border-border-soft">
              {tarea.codigo}
            </span>
            <span className="font-mono text-[11px] tabular-nums text-muted-soft">
              v{tarea.version}
            </span>
            {tarea.template_id && <TemplateBadge templateId={tarea.template_id} />}
            {tarea.has_drift && <DriftBadge />}
          </div>
          <Badge variant={ESTADO_VARIANT[estado]}>{ESTADO_LABEL[estado]}</Badge>
        </div>

        {/* Headline */}
        <div className="min-w-0">
          <h3
            className="text-[15px] font-semibold text-ink leading-tight tracking-tight line-clamp-2"
            title={tarea.titulo}
          >
            {tarea.titulo}
          </h3>
          {tarea.parent_tarea_id && (
            <div className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted">
              <GitBranch className="h-3 w-3" />
              Versión derivada
            </div>
          )}
        </div>

        {/* Mini-grid de metadatos */}
        <dl className="grid grid-cols-3 gap-2 mt-auto">
          <MetaCell label="Inicio" value={formatShortDate(tarea.fecha_inicio)} />
          <MetaCell label="Fin" value={formatShortDate(tarea.fecha_fin)} />
          <MetaCell label="Peso" value={tarea.peso} mono />
        </dl>
      </div>

      {/* Footer con acciones */}
      <footer className="flex items-stretch border-t border-border-soft">
        <button
          type="button"
          onClick={onComposicion}
          className="press-shrink flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium text-muted hover:bg-surface-alt hover:text-ink transition-colors"
          title="Gestionar ejercicios del TP"
        >
          <FileText className="h-3.5 w-3.5" />
          Composicion
        </button>
        <button
          type="button"
          onClick={onShowVersions}
          className="press-shrink flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium text-muted hover:bg-surface-alt hover:text-ink transition-colors"
          title="Ver historial de versiones"
        >
          <History className="h-3.5 w-3.5" />
          Historial
        </button>
        {estado === "draft" && (
          <>
            <ActionButton
              onClick={onEdit}
              icon={<Pencil className="h-3.5 w-3.5" />}
              label="Editar"
              tone="brand"
            />
            <ActionButton
              onClick={onPublish}
              icon={<Send className="h-3.5 w-3.5" />}
              label="Publicar"
              tone="success"
            />
            <ActionButton
              onClick={onDelete}
              icon={<Trash2 className="h-3.5 w-3.5" />}
              label=""
              tone="danger"
              title="Eliminar"
            />
          </>
        )}
        {estado === "published" && (
          <>
            <ActionButton
              onClick={onView}
              icon={<Eye className="h-3.5 w-3.5" />}
              label="Ver"
              tone="muted"
            />
            <ActionButton
              onClick={onNewVersion}
              icon={<GitBranch className="h-3.5 w-3.5" />}
              label="Versión"
              tone="brand"
              title="Crear nueva versión"
            />
            <ActionButton
              onClick={onArchive}
              icon={<Archive className="h-3.5 w-3.5" />}
              label=""
              tone="warning"
              title="Archivar"
            />
          </>
        )}
        {estado === "archived" && (
          <>
            <ActionButton
              onClick={onView}
              icon={<Eye className="h-3.5 w-3.5" />}
              label="Ver"
              tone="muted"
            />
            <ActionButton
              onClick={onNewVersion}
              icon={<GitBranch className="h-3.5 w-3.5" />}
              label="Versión"
              tone="brand"
              title="Crear nueva versión"
            />
          </>
        )}
      </footer>
    </article>
  )
}

function MetaCell({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[10px] uppercase tracking-wider text-muted-soft">{label}</span>
      <span
        className={`text-xs text-body truncate ${mono ? "font-mono tabular-nums" : ""}`}
        title={value}
      >
        {value}
      </span>
    </div>
  )
}

function ActionButton({
  onClick,
  icon,
  label,
  tone,
  title,
}: {
  onClick: () => void
  icon: React.ReactNode
  label: string
  tone: "brand" | "success" | "warning" | "danger" | "muted"
  title?: string
}) {
  const toneCls: Record<typeof tone, string> = {
    brand: "text-accent-brand-deep hover:bg-accent-brand-soft",
    success: "text-success hover:bg-success-soft",
    warning: "text-warning hover:bg-warning-soft",
    danger: "text-danger hover:bg-danger-soft",
    muted: "text-muted hover:bg-surface-alt hover:text-ink",
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`press-shrink inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium border-l border-border-soft transition-colors ${toneCls[tone]}`}
    >
      {icon}
      {label}
    </button>
  )
}

// ── Form modal (create / edit / new-version) ──────────────────────────
interface FormValues {
  codigo: string
  titulo: string
  enunciado: string
  fecha_inicio: string | null
  fecha_fin: string | null
  peso: string
  rubrica: Record<string, unknown> | null
  template_id?: string | null
}

function TareaFormModal({
  isOpen,
  title,
  initial,
  mode = "create",
  comisionId,
  getToken,
  onClose,
  onSubmit,
}: {
  isOpen: boolean
  title: string
  initial: TareaPractica | null
  mode?: "create" | "edit" | "version"
  comisionId?: string
  getToken?: () => Promise<string | null>
  onClose: () => void
  onSubmit: (values: FormValues) => Promise<void>
}) {
  const isEditing = mode === "edit" || mode === "version"

  const [codigo, setCodigo] = useState(initial?.codigo ?? "")
  const [titulo, setTitulo] = useState(initial?.titulo ?? "")
  const [enunciado, setEnunciado] = useState(initial?.enunciado ?? "")
  const [fechaInicio, setFechaInicio] = useState(isoToLocalInput(initial?.fecha_inicio ?? null))
  const [fechaFin, setFechaFin] = useState(isoToLocalInput(initial?.fecha_fin ?? null))
  const [peso, setPeso] = useState(initial?.peso ?? "1.0")
  const [rubricaRaw, setRubricaRaw] = useState(() =>
    initial?.rubrica ? JSON.stringify(initial.rubrica, null, 2) : "",
  )

  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const showDriftBanner = Boolean(mode === "edit" && initial?.template_id && !initial.has_drift)
  const [driftAck, setDriftAck] = useState(false)

  // Plantillas (briefs pedagogicos) disponibles — solo en modo create.
  const [templates, setTemplates] = useState<TareaPracticaTemplate[]>([])
  const [templateId, setTemplateId] = useState<string | null>(initial?.template_id ?? null)

  useEffect(() => {
    if (!isOpen || mode !== "create" || !comisionId || !getToken) return
    let cancelled = false
    listMyComisiones(getToken)
      .then((res) => res.items.find((c) => c.id === comisionId))
      .then(async (com) => {
        if (cancelled || !com) return
        const list = await tareasPracticasTemplatesApi.list(
          { materia_id: com.materia_id, periodo_id: com.periodo_id },
          getToken,
        )
        if (!cancelled) setTemplates(list.filter((t) => t.estado !== "archived"))
      })
      .catch(() => {
        if (!cancelled) setTemplates([])
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, mode, comisionId, getToken])

  const handleSelectTemplate = (id: string | null) => {
    setTemplateId(id)
    if (id) {
      const t = templates.find((x) => x.id === id)
      if (t) {
        if (!codigo.trim()) setCodigo(t.codigo)
        if (!titulo.trim()) setTitulo(t.titulo)
      }
    }
  }

  const handleSubmit = async () => {
    setFormError(null)
    if (!codigo.trim() || !titulo.trim() || !enunciado.trim()) {
      setFormError("Codigo, titulo y enunciado son obligatorios")
      return
    }
    if (showDriftBanner && !driftAck) {
      setFormError("Confirma que entendes que esta edicion va a marcar drift del template")
      return
    }
    let rubrica: Record<string, unknown> | null = null
    if (rubricaRaw.trim()) {
      try {
        rubrica = JSON.parse(rubricaRaw)
      } catch (e) {
        setFormError(`Rubrica no es JSON valido: ${String(e)}`)
        return
      }
    }
    setSubmitting(true)
    try {
      await onSubmit({
        codigo: codigo.trim(),
        titulo: titulo.trim(),
        enunciado: enunciado.trim(),
        fecha_inicio: localInputToIso(fechaInicio),
        fecha_fin: localInputToIso(fechaFin),
        peso,
        rubrica,
        ...(mode === "create" && templateId ? { template_id: templateId } : {}),
      })
    } catch (e) {
      setFormError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="lg">
      <div className="space-y-4">
        {showDriftBanner && (
          <div className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
            <p className="font-semibold text-warning">Este TP viene de una plantilla de catedra.</p>
            <p className="mt-1 text-warning/90">
              Si lo edita, va a marcarse como drift y no recibira mas actualizaciones automaticas
              del template.
            </p>
            <label className="mt-2 inline-flex items-center gap-2 text-xs text-warning">
              <input
                type="checkbox"
                checked={driftAck}
                onChange={(e) => setDriftAck(e.target.checked)}
              />
              Entiendo y quiero continuar
            </label>
          </div>
        )}

        {formError && (
          <div className="rounded border border-danger/30 bg-danger-soft p-2 text-xs text-danger">
            {formError}
          </div>
        )}

        {mode === "create" && templates.length > 0 && (
          <div>
            <label className="block text-xs text-muted mb-1">
              Inspirar en una plantilla (opcional)
            </label>
            <select
              value={templateId ?? ""}
              onChange={(e) => handleSelectTemplate(e.target.value || null)}
              className="w-full border border-border rounded px-2 py-1 text-sm bg-white"
            >
              <option value="">Sin plantilla</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.codigo}: {t.titulo} (v{t.version}, {t.estado})
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-muted mb-1">Codigo</label>
            <input
              type="text"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              maxLength={20}
              className="w-full border border-border rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Peso (0-1)</label>
            <input
              type="text"
              value={peso}
              onChange={(e) => setPeso(e.target.value)}
              className="w-full border border-border rounded px-2 py-1 text-sm font-mono"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-muted mb-1">Titulo</label>
          <input
            type="text"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            maxLength={200}
            className="w-full border border-border rounded px-2 py-1 text-sm"
          />
        </div>

        <div>
          <label className="block text-xs text-muted mb-1">Enunciado (markdown)</label>
          <textarea
            value={enunciado}
            onChange={(e) => setEnunciado(e.target.value)}
            rows={6}
            className="w-full border border-border rounded px-2 py-1 text-sm font-mono"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-muted mb-1">Fecha inicio</label>
            <input
              type="datetime-local"
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              className="w-full border border-border rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Fecha fin</label>
            <input
              type="datetime-local"
              value={fechaFin}
              onChange={(e) => setFechaFin(e.target.value)}
              className="w-full border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-muted mb-1">Rubrica (JSON, opcional)</label>
          <textarea
            value={rubricaRaw}
            onChange={(e) => setRubricaRaw(e.target.value)}
            rows={4}
            className="w-full border border-border rounded px-2 py-1 text-xs font-mono"
            placeholder='{"criterios": [{"nombre": "...", "puntaje_max": 1.0}]}'
          />
        </div>

        <div className="rounded-lg border border-border-soft bg-surface-alt p-3 text-xs text-muted">
          <strong className="text-ink">Composicion de ejercicios:</strong> al guardar la TP, abri
          el modal &quot;Composicion&quot; desde la card para asociar ejercicios del banco. Los
          ejercicios viven en /ejercicios y son reusables entre TPs (ADR-047).
        </div>

        <div className="flex justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 border border-border rounded text-sm hover:bg-surface-alt"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="px-3 py-1.5 bg-accent-brand text-white rounded text-sm hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {submitting ? "Guardando..." : isEditing ? "Guardar cambios" : "Crear TP"}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Composicion modal (ADR-047) ────────────────────────────────────────

function ComposicionModal({
  tarea,
  getToken,
  onClose,
}: {
  tarea: TareaPractica
  getToken: () => Promise<string | null>
  onClose: () => void
}) {
  const [pairs, setPairs] = useState<TpEjercicio[]>([])
  const [biblioteca, setBiblioteca] = useState<Ejercicio[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [selectedEjercicioId, setSelectedEjercicioId] = useState<string>("")
  const [nuevoPeso, setNuevoPeso] = useState("1.0")

  const editable = tarea.estado === "draft"

  const fetchPairs = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [p, b] = await Promise.all([
        tpEjerciciosApi.list(tarea.id, getToken),
        listEjercicios({ limit: 200 }, getToken).then((r) => r.data),
      ])
      setPairs(p)
      setBiblioteca(b)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [tarea.id, getToken])

  useEffect(() => {
    fetchPairs()
  }, [fetchPairs])

  const usedIds = new Set(pairs.map((p) => p.ejercicio_id))
  const disponibles = biblioteca.filter((ej) => !usedIds.has(ej.id))

  async function handleAdd() {
    if (!selectedEjercicioId) return
    setAdding(true)
    setError(null)
    try {
      const nextOrden = pairs.length > 0 ? Math.max(...pairs.map((p) => p.orden)) + 1 : 1
      await tpEjerciciosApi.add(
        tarea.id,
        { ejercicio_id: selectedEjercicioId, orden: nextOrden, peso_en_tp: nuevoPeso },
        getToken,
      )
      setSelectedEjercicioId("")
      setNuevoPeso("1.0")
      await fetchPairs()
    } catch (e) {
      setError(String(e))
    } finally {
      setAdding(false)
    }
  }

  async function handleRemove(ejercicioId: string) {
    setError(null)
    try {
      await tpEjerciciosApi.remove(tarea.id, ejercicioId, getToken)
      await fetchPairs()
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleReorder(pair: TpEjercicio, direction: "up" | "down") {
    const sorted = [...pairs].sort((a, b) => a.orden - b.orden)
    const idx = sorted.findIndex((p) => p.id === pair.id)
    const swapIdx = direction === "up" ? idx - 1 : idx + 1
    if (swapIdx < 0 || swapIdx >= sorted.length) return
    const other = sorted[swapIdx]!
    setError(null)
    try {
      // Swap atomico no es posible por UNIQUE — usamos un orden temporal alto.
      const temp = Math.max(...pairs.map((p) => p.orden)) + 100
      await tpEjerciciosApi.updatePair(tarea.id, pair.ejercicio_id, { orden: temp }, getToken)
      await tpEjerciciosApi.updatePair(
        tarea.id,
        other.ejercicio_id,
        { orden: pair.orden },
        getToken,
      )
      await tpEjerciciosApi.updatePair(
        tarea.id,
        pair.ejercicio_id,
        { orden: other.orden },
        getToken,
      )
      await fetchPairs()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={`Composicion · ${tarea.codigo}: ${tarea.titulo}`}
      size="lg"
    >
      <div className="space-y-4">
        {!editable && (
          <div className="rounded border border-warning/30 bg-warning-soft p-2 text-xs text-warning">
            La TP esta en estado &quot;{tarea.estado}&quot;. La composicion es solo lectura. Para
            modificarla, crea una nueva version.
          </div>
        )}

        {error && (
          <div className="rounded border border-danger/30 bg-danger-soft p-2 text-xs text-danger">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-sm text-muted">Cargando...</div>
        ) : (
          <>
            {pairs.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-surface p-6 text-center">
                <p className="text-sm text-muted">
                  Esta TP todavia no tiene ejercicios asociados.
                </p>
              </div>
            ) : (
              <div className="border border-border rounded overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-surface-alt border-b border-border">
                    <tr>
                      <th className="text-left px-2 py-1 w-12">Orden</th>
                      <th className="text-left px-2 py-1">Ejercicio</th>
                      <th className="text-left px-2 py-1 w-20">Peso</th>
                      <th className="text-right px-2 py-1 w-32">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...pairs]
                      .sort((a, b) => a.orden - b.orden)
                      .map((p, idx, arr) => (
                        <tr key={p.id} className="border-b border-border last:border-0">
                          <td className="px-2 py-1 font-mono text-xs">{p.orden}</td>
                          <td className="px-2 py-1">{p.ejercicio.titulo}</td>
                          <td className="px-2 py-1 font-mono text-xs">{p.peso_en_tp}</td>
                          <td className="px-2 py-1 text-right">
                            {editable && (
                              <div className="inline-flex items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => handleReorder(p, "up")}
                                  disabled={idx === 0}
                                  className="p-1 hover:bg-surface-alt rounded disabled:opacity-30"
                                  title="Subir"
                                >
                                  <ArrowUp className="h-3 w-3" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleReorder(p, "down")}
                                  disabled={idx === arr.length - 1}
                                  className="p-1 hover:bg-surface-alt rounded disabled:opacity-30"
                                  title="Bajar"
                                >
                                  <ArrowDown className="h-3 w-3" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleRemove(p.ejercicio_id)}
                                  className="p-1 hover:bg-danger-soft hover:text-danger rounded"
                                  title="Quitar"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}

            {editable && (
              <div className="border-t border-border pt-3">
                <p className="text-xs text-muted mb-2">Agregar desde la biblioteca</p>
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <label className="block text-xs text-muted mb-1">Ejercicio</label>
                    <select
                      value={selectedEjercicioId}
                      onChange={(e) => setSelectedEjercicioId(e.target.value)}
                      className="w-full border border-border rounded px-2 py-1 text-sm bg-white"
                    >
                      <option value="">Seleccionar...</option>
                      {disponibles.map((ej) => (
                        <option key={ej.id} value={ej.id}>
                          {ej.titulo} ({ej.unidad_tematica})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="w-24">
                    <label className="block text-xs text-muted mb-1">Peso</label>
                    <input
                      type="text"
                      value={nuevoPeso}
                      onChange={(e) => setNuevoPeso(e.target.value)}
                      className="w-full border border-border rounded px-2 py-1 text-sm font-mono"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleAdd}
                    disabled={!selectedEjercicioId || adding}
                    className="px-3 py-1.5 bg-accent-brand text-white rounded text-sm hover:bg-accent-brand-deep disabled:opacity-50"
                  >
                    {adding ? "Agregando..." : "Agregar"}
                  </button>
                </div>
                {disponibles.length === 0 && biblioteca.length > 0 && (
                  <p className="text-xs text-muted mt-2">
                    Todos los ejercicios de la biblioteca ya estan en esta TP.
                  </p>
                )}
                {biblioteca.length === 0 && (
                  <p className="text-xs text-muted mt-2">
                    No hay ejercicios en la biblioteca. Crea uno desde /ejercicios.
                  </p>
                )}
              </div>
            )}
          </>
        )}

        <div className="flex justify-end pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 border border-border rounded text-sm hover:bg-surface-alt"
          >
            Cerrar
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── View modal ────────────────────────────────────────────────────────

function TareaViewModal({
  tarea,
  onClose,
  onShowVersions,
}: {
  tarea: TareaPractica
  onClose: () => void
  onShowVersions: () => void
}) {
  return (
    <Modal isOpen={true} onClose={onClose} title={`${tarea.codigo}: ${tarea.titulo}`} size="lg">
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HelpButton
            size="sm"
            title="Detalle del TP"
            content={
              <div className="space-y-3 text-body">
                <p>Esta vista muestra el detalle completo del TP en modo solo lectura:</p>
                <ul className="list-disc pl-5 space-y-2">
                  <li>
                    <strong>Estado:</strong> Indica si el TP esta publicado o archivado.
                  </li>
                  <li>
                    <strong>Version:</strong> Numero de version. TPs derivados muestran "derivado".
                  </li>
                  <li>
                    <strong>Enunciado:</strong> Texto completo renderizado en markdown.
                  </li>
                  <li>
                    <strong>Rubrica:</strong> Criterios de evaluacion en JSON (si fueron cargados).
                  </li>
                  <li>
                    <strong>Ver historial:</strong> Navega a la lista de versiones del TP.
                  </li>
                </ul>
              </div>
            }
          />
          <span className="text-sm text-muted">Ayuda sobre esta vista</span>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant={ESTADO_VARIANT[tarea.estado]}>{ESTADO_LABEL[tarea.estado]}</Badge>
          <span className="text-xs text-muted">
            v{tarea.version}
            {tarea.parent_tarea_id && " · derivado"}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <div className="text-muted">Inicio</div>
            <div className="font-medium">
              {tarea.fecha_inicio ? formatDateTime(tarea.fecha_inicio) : "sin fecha"}
            </div>
          </div>
          <div>
            <div className="text-muted">Fin</div>
            <div className="font-medium">
              {tarea.fecha_fin ? formatDateTime(tarea.fecha_fin) : "sin fecha"}
            </div>
          </div>
          <div>
            <div className="text-muted">Peso</div>
            <div className="font-medium tabular-nums">{tarea.peso}</div>
          </div>
        </div>

        <div>
          <div className="text-xs font-medium text-muted mb-1">Enunciado</div>
          <div className="p-3 rounded bg-surface-alt max-h-96 overflow-y-auto">
            <MarkdownRenderer content={tarea.enunciado} />
          </div>
        </div>

        {tarea.rubrica && (
          <div>
            <div className="text-xs font-medium text-muted mb-1">Rúbrica</div>
            {/* Rúbrica se muestra como JSON crudo a propósito — el shape no está
                versionado todavía, así que markdown sería engañoso. */}
            <pre className="p-3 rounded bg-surface-alt text-xs font-mono whitespace-pre-wrap max-h-48 overflow-y-auto">
              {JSON.stringify(tarea.rubrica, null, 2)}
            </pre>
          </div>
        )}

        <div className="flex justify-between pt-2 border-t border-border">
          <button
            type="button"
            onClick={onShowVersions}
            className="px-4 py-1.5 text-sm border border-border rounded-md hover:bg-canvas transition-colors text-muted"
          >
            Ver historial de versiones
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep text-white rounded-md transition-colors"
          >
            Cerrar
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Versions modal (timeline) ─────────────────────────────────────────

function VersionsModal({
  tarea,
  getToken,
  onClose,
}: {
  tarea: TareaPractica
  getToken: () => Promise<string | null>
  onClose: () => void
}) {
  const [versions, setVersions] = useState<TareaPracticaVersionRef[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    tareasPracticasApi
      .versions(tarea.id, getToken)
      .then((v) => {
        if (!cancelled) setVersions(v)
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [tarea.id, getToken])

  // Timeline vertical: ordena por version ascendente para lectura natural.
  const sorted = versions ? [...versions].sort((a, b) => a.version - b.version) : null

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={`Historial de versiones (${tarea.codigo})`}
      size="md"
    >
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HelpButton
            size="sm"
            title="Historial de versiones"
            content={
              <div className="space-y-3 text-body">
                <p>Muestra la linea de tiempo de todas las versiones del TP:</p>
                <ul className="list-disc pl-5 space-y-2">
                  <li>
                    <strong>Version actual:</strong> Marcada en azul, es la version activa del TP.
                  </li>
                  <li>
                    <strong>Versiones anteriores:</strong> Marcadas en gris, son inmutables y solo
                    de referencia.
                  </li>
                  <li>
                    <strong>Estado:</strong> Cada version muestra su estado al momento de la
                    creacion.
                  </li>
                  <li>
                    <strong>Nueva version:</strong> Para modificar el contenido de un TP publicado,
                    usa el boton "Nueva version" en la lista de TPs: esto crea un nuevo borrador
                    linkeado por parent_tarea_id.
                  </li>
                </ul>
              </div>
            }
          />
          <span className="text-sm text-muted">Ayuda sobre el historial</span>
        </div>

        {err && <div className="p-3 rounded bg-danger-soft text-danger text-sm">{err}</div>}

        {!sorted ? (
          <div className="p-6 text-center text-muted text-sm">Cargando versiones...</div>
        ) : sorted.length === 0 ? (
          <div className="p-6 text-center text-muted text-sm">Sin versiones registradas.</div>
        ) : (
          <ol className="relative border-l border-border-soft ml-3 space-y-4">
            {sorted.map((v) => (
              <li key={v.id} className="ml-4">
                <span
                  className={`absolute -left-[9px] w-4 h-4 rounded-full border-2 border-surface ${
                    v.is_current ? "bg-accent-brand" : "bg-border-strong"
                  }`}
                  aria-hidden="true"
                />
                <div
                  className={`rounded border p-3 ${
                    v.is_current
                      ? "border-accent-brand/40 bg-accent-brand-soft"
                      : "border-border-soft bg-surface"
                  }`}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold">v{v.version}</span>
                    <Badge variant={ESTADO_VARIANT[v.estado]}>{ESTADO_LABEL[v.estado]}</Badge>
                    {v.is_current && (
                      <span className="text-xs text-accent-brand-deep font-medium">(actual)</span>
                    )}
                  </div>
                  <div className="text-sm mt-1">{v.titulo}</div>
                  <div className="text-xs text-muted mt-1">{formatDateTime(v.created_at)}</div>
                </div>
              </li>
            ))}
          </ol>
        )}

        <div className="flex justify-end pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep text-white rounded-md transition-colors"
          >
            Cerrar
          </button>
        </div>
      </div>
    </Modal>
  )
}
