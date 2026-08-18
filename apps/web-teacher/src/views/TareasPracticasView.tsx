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
  CalendarClock,
  Eye,
  FileText,
  GitBranch,
  History,
  Pencil,
  Plus,
  Search,
  Send,
  Trash2,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useComisionLabel } from "../components/ComisionSelector"
import {
  DEFAULT_LANGUAGE,
  type Ejercicio,
  LANGUAGE_LABELS,
  type Language,
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
import { useTutorialDeVista } from "../tour/useTutorialDeVista"
import { tareasPracticasTour } from "../tour/vistas"
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
  | { kind: "edit-fecha"; tarea: TareaPractica }
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

  // Tutorial de la vista (capa 2). Espera a que la lista haya cargado: dos de sus
  // pasos iluminan una card del grid, que antes del fetch no existe.
  useTutorialDeVista(tareasPracticasTour, !loading)

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
            data-tour="tp:filtros"
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
              data-tour="tp:nuevo"
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
              Creá el TP y después componelo con ejercicios del banco desde el botón
              &quot;Composición&quot; de la card. Los ejercicios viven en <code>/ejercicios</code> y
              se reutilizan entre TPs.
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
          <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-tour="tp:lista">
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
                  onEditFecha={() => setModal({ kind: "edit-fecha", tarea: t })}
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
            const created = await tareasPracticasApi.create(
              {
                ...values,
                comision_id: comisionId,
              },
              getToken,
            )
            await refreshList()
            // FR-7: reducir la friccion "crear != componer". En vez de solo
            // cerrar, llevamos al docente directo a la Composicion del TP recien
            // creado (arranca en draft, sin ejercicios) para que asocie ejercicios
            // del banco sin tener que descubrir el boton "Composicion" de la card.
            setModal({ kind: "composicion", tarea: created })
          }}
        />

        {/* Modal: composicion de ejercicios (ADR-047) */}
        {modal.kind === "composicion" && (
          <ComposicionModal tarea={modal.tarea} getToken={getToken} onClose={closeModal} />
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
                permite_pausa: values.permite_pausa,
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
                permite_pausa: values.permite_pausa,
              }
              await tareasPracticasApi.newVersion(modal.tarea.id, patch, getToken)
              closeModal()
              await refreshList()
            }}
          />
        )}

        {/* Modal: editar fecha límite de TP publicado (fix 2026-06-10 #5).
            El backend permite PATCH de solo fecha_fin sin importar el estado
            (_MUTABLE_REGARDLESS_OF_ESTADO) — el contenido pedagógico sigue
            inmutable y exige nueva versión. */}
        {modal.kind === "edit-fecha" && (
          <FechaFinModal
            tarea={modal.tarea}
            onClose={closeModal}
            onSubmit={async (fechaFinIso) => {
              await tareasPracticasApi.update(modal.tarea.id, { fecha_fin: fechaFinIso }, getToken)
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
  onEditFecha,
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
  onEditFecha: () => void
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

      {/* Footer con acciones. flex-wrap: en cards angostos (grid de 3 col) los
          botones no entran en una fila y se cortaban (Archivar quedaba fuera de
          vista, 2026-06-17). Con basis-1/3 entran ~3 por fila y wrapean el resto. */}
      <footer className="flex flex-wrap items-stretch border-t border-border-soft">
        <button
          type="button"
          onClick={onComposicion}
          // Ancla del tutorial de la vista. Esta en todas las cards; el tour ilumina
          // la primera, que es lo que se quiere mostrar.
          data-tour="tp:composicion"
          className={`press-shrink grow basis-1/3 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-colors ${
            estado === "draft"
              ? "text-accent-brand-deep hover:bg-accent-brand-soft"
              : "text-muted hover:bg-surface-alt hover:text-ink"
          }`}
          title="Gestionar ejercicios del TP"
        >
          <FileText className="h-3.5 w-3.5" />
          Composicion
        </button>
        <button
          type="button"
          onClick={onShowVersions}
          className="press-shrink grow basis-1/3 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium text-muted hover:bg-surface-alt hover:text-ink transition-colors"
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
              label="Eliminar"
              tone="danger"
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
              onClick={onEditFecha}
              icon={<CalendarClock className="h-3.5 w-3.5" />}
              label="Fecha"
              tone="brand"
              title="Editar fecha límite de entrega"
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
              label="Archivar"
              tone="warning"
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
      className={`press-shrink grow basis-1/3 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium border-l border-border-soft transition-colors ${toneCls[tone]}`}
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
  permite_pausa: boolean
  template_id?: string | null
  language?: Language
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
  // permite_pausa: en create arranca habilitado (default del backend); en
  // edit/version respeta el valor de la TP existente.
  const [permitePausa, setPermitePausa] = useState(initial?.permite_pausa ?? true)
  // Solo se elige al CREAR: el backend valida que todos los ejercicios del banco
  // coincidan con el lenguaje de la TP (al agregar y al publicar), asi que
  // cambiarlo con ejercicios ya asociados dejaria la TP impublicable. Para
  // cambiar de lenguaje se crea otra.
  const [language, setLanguage] = useState<Language>(initial?.language ?? DEFAULT_LANGUAGE)

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
    if (!codigo.trim() || !titulo.trim()) {
      setFormError("Codigo y titulo son obligatorios")
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
    // ADR-047: post-banco-de-ejercicios el enunciado de la TP es fallback.
    // Si el docente deja vacio, pasamos un placeholder claro para el alumno
    // (y para el backend, que actualmente lo exige no-vacio). Cuando el
    // backend haga el campo nullable, este placeholder se quita.
    const enunciadoFinal = enunciado.trim()
      ? enunciado.trim()
      : "(Esta TP se compone con ejercicios del banco. El detalle de cada ejercicio se muestra al abrir el episodio.)"
    setSubmitting(true)
    try {
      await onSubmit({
        codigo: codigo.trim(),
        titulo: titulo.trim(),
        enunciado: enunciadoFinal,
        fecha_inicio: localInputToIso(fechaInicio),
        fecha_fin: localInputToIso(fechaFin),
        peso,
        rubrica,
        permite_pausa: permitePausa,
        ...(mode === "create" && templateId ? { template_id: templateId } : {}),
        ...(mode === "create" ? { language } : {}),
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
            <label htmlFor="tp-template-select" className="block text-xs text-muted mb-1">
              Inspirar en una plantilla (opcional)
            </label>
            <select
              id="tp-template-select"
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
            <label htmlFor="tp-codigo" className="block text-xs text-muted mb-1">
              Codigo
            </label>
            <input
              id="tp-codigo"
              name="codigo"
              data-testid="tp-form-codigo"
              type="text"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              maxLength={20}
              className="w-full border border-border rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label htmlFor="tp-peso" className="block text-xs text-muted mb-1">
              Peso (0-1)
            </label>
            <input
              id="tp-peso"
              name="peso"
              data-testid="tp-form-peso"
              type="text"
              inputMode="decimal"
              value={peso}
              onChange={(e) => setPeso(e.target.value)}
              className="w-full border border-border rounded px-2 py-1 text-sm font-mono"
            />
          </div>
        </div>

        {!isEditing && (
          <div>
            <label htmlFor="tp-language" className="block text-xs text-muted mb-1">
              Lenguaje
            </label>
            <select
              id="tp-language"
              name="language"
              data-testid="tp-form-language"
              value={language}
              onChange={(e) => setLanguage(e.target.value as Language)}
              className="w-full border border-border rounded px-2 py-1 text-sm"
            >
              {(Object.keys(LANGUAGE_LABELS) as Language[]).map((l) => (
                <option key={l} value={l}>
                  {LANGUAGE_LABELS[l]}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-muted">
              Todos los ejercicios que le asocies tienen que ser de este lenguaje — el backend
              rechaza la mezcla al agregarlos y al publicar. No se puede cambiar despues.
            </p>
          </div>
        )}

        <div>
          <label htmlFor="tp-titulo" className="block text-xs text-muted mb-1">
            Titulo
          </label>
          <input
            id="tp-titulo"
            name="titulo"
            data-testid="tp-form-titulo"
            type="text"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            maxLength={200}
            className="w-full border border-border rounded px-2 py-1 text-sm"
          />
        </div>

        <div className="rounded-lg border border-accent-brand/30 bg-accent-brand-soft p-3 text-xs">
          <strong className="text-ink">Flujo recomendado:</strong>{" "}
          <span className="text-muted">
            componer la TP con ejercicios del banco. Después de guardar, abrí el modal
            &quot;Composición&quot; desde la card para asociar ejercicios. Los ejercicios viven en{" "}
            <code>/ejercicios</code> y son reusables entre TPs (ADR-047).
          </span>
        </div>

        <div>
          <label htmlFor="tp-enunciado" className="block text-xs text-muted mb-1">
            Enunciado introductorio (opcional)
          </label>
          <textarea
            id="tp-enunciado"
            name="enunciado"
            data-testid="tp-form-enunciado"
            value={enunciado}
            onChange={(e) => setEnunciado(e.target.value)}
            rows={6}
            placeholder="Dejalo vacío si vas a componer la TP con ejercicios del banco."
            className="w-full border border-border rounded px-2 py-1 text-sm font-mono"
          />
          <p className="mt-1 text-xs text-muted leading-snug">
            Sólo si esta TP <em>no</em> va a usar ejercicios del banco. Si la componés con
            ejercicios, el alumno verá el enunciado de cada ejercicio y este campo queda ignorado en
            runtime (fallback histórico pre-ADR-047).
          </p>
        </div>

        <div className="rounded-lg border border-border bg-surface-alt/40 p-3">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              data-testid="tp-form-permite-pausa"
              checked={permitePausa}
              onChange={(e) => setPermitePausa(e.target.checked)}
              className="mt-0.5"
            />
            <span className="text-sm text-ink">
              <span className="font-medium">Permitir pausar y retomar</span>
              <span className="block text-xs text-muted leading-snug mt-0.5">
                El alumno puede salir de un episodio y continuarlo despues donde lo dejo.
                Desactivalo si la TP debe resolverse en una sola sesion (ej. evaluacion).
              </span>
            </span>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="tp-fecha-inicio" className="block text-xs text-muted mb-1">
              Fecha inicio
            </label>
            <input
              id="tp-fecha-inicio"
              name="fecha_inicio"
              data-testid="tp-form-fecha-inicio"
              type="datetime-local"
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              className="w-full border border-border rounded px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label htmlFor="tp-fecha-fin" className="block text-xs text-muted mb-1">
              Fecha fin
            </label>
            <input
              id="tp-fecha-fin"
              name="fecha_fin"
              data-testid="tp-form-fecha-fin"
              type="datetime-local"
              value={fechaFin}
              onChange={(e) => setFechaFin(e.target.value)}
              className="w-full border border-border rounded px-2 py-1 text-sm"
            />
          </div>
        </div>

        <div>
          <label htmlFor="tp-rubrica" className="block text-xs text-muted mb-1">
            Rubrica (JSON, opcional)
          </label>
          <textarea
            id="tp-rubrica"
            name="rubrica"
            data-testid="tp-form-rubrica"
            value={rubricaRaw}
            onChange={(e) => setRubricaRaw(e.target.value)}
            rows={4}
            className="w-full border border-border rounded px-2 py-1 text-xs font-mono"
            placeholder='{"criterios": [{"nombre": "...", "puntaje_max": 1.0}]}'
          />
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

// ── Fecha límite modal (fix 2026-06-10 #5) ─────────────────────────────
// Edición acotada a `fecha_fin` para TPs publicados: extender (o acortar)
// la fecha de entrega sin pasar por el fork de versión. El resto del TP
// sigue inmutable. Editar la fecha de una instancia derivada de template
// marca drift igual que cualquier campo canónico (ADR-016) — se avisa.

function FechaFinModal({
  tarea,
  onClose,
  onSubmit,
}: {
  tarea: TareaPractica
  onClose: () => void
  onSubmit: (fechaFinIso: string) => Promise<void>
}) {
  const [fechaFin, setFechaFin] = useState(isoToLocalInput(tarea.fecha_fin))
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const willDrift = Boolean(tarea.template_id && !tarea.has_drift)
  const [driftAck, setDriftAck] = useState(false)

  const handleSubmit = async () => {
    setFormError(null)
    const iso = localInputToIso(fechaFin)
    if (!iso) {
      setFormError("Indicá la nueva fecha límite (el backend no permite quitarla en este modal)")
      return
    }
    if (tarea.fecha_inicio && new Date(iso) <= new Date(tarea.fecha_inicio)) {
      setFormError("La fecha límite debe ser posterior a la fecha de inicio")
      return
    }
    if (willDrift && !driftAck) {
      setFormError("Confirmá que entendés que este cambio marca drift respecto del template")
      return
    }
    setSubmitting(true)
    try {
      await onSubmit(iso)
    } catch (e) {
      setFormError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={`Fecha límite · ${tarea.codigo}: ${tarea.titulo}`}
      size="md"
    >
      <div className="space-y-4">
        <p className="text-sm text-muted leading-relaxed">
          Solo se modifica la fecha de entrega. El enunciado, peso y rúbrica del TP publicado siguen
          inmutables: para cambiarlos, creá una nueva versión.
        </p>

        {willDrift && (
          <div className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm">
            <p className="font-semibold text-warning">Este TP viene de una plantilla de catedra.</p>
            <p className="mt-1 text-warning/90">
              Cambiar la fecha lo marca como drift y deja de recibir actualizaciones automaticas del
              template.
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

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-muted">Inicio</div>
            <div className="font-medium">
              {tarea.fecha_inicio ? formatDateTime(tarea.fecha_inicio) : "sin fecha"}
            </div>
          </div>
          <div>
            <div className="text-muted">Fin actual</div>
            <div className="font-medium">
              {tarea.fecha_fin ? formatDateTime(tarea.fecha_fin) : "sin fecha"}
            </div>
          </div>
        </div>

        <div>
          <label htmlFor="tp-fecha-fin-edit" className="block text-xs text-muted mb-1">
            Nueva fecha límite
          </label>
          <input
            id="tp-fecha-fin-edit"
            name="fecha_fin"
            data-testid="tp-fecha-fin-edit"
            type="datetime-local"
            value={fechaFin}
            onChange={(e) => setFechaFin(e.target.value)}
            className="w-full border border-border rounded px-2 py-1 text-sm"
          />
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
            {submitting ? "Guardando..." : "Guardar fecha"}
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
  const [reordering, setReordering] = useState(false)
  // FR-1: multiselect + busqueda + filtro por materia sobre el banco cargado.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState("")
  const [soloMateria, setSoloMateria] = useState(true)
  const [materiaId, setMateriaId] = useState<string | null>(null)
  const [nuevoPeso, setNuevoPeso] = useState("1.0")

  const editable = tarea.estado === "draft"

  // Una TP admite un solo lenguaje, y el que manda es el de la TP: el backend
  // compara `ejercicio.language != tp.language` al agregar y devuelve 422. El
  // bloqueo de acá evita que el docente arme la seleccion entera y se entere
  // recien al confirmar. No es redundancia: el backend protege la integridad,
  // el cliente protege el tiempo del docente.
  const tpLanguage = tarea.language ?? DEFAULT_LANGUAGE
  const tpLanguageLabel = LANGUAGE_LABELS[tpLanguage]

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

  // FR-1: la materia del TP no viaja en el modelo TareaPractica; la resolvemos
  // desde la comision para poder filtrar el banco por materia (client-side).
  useEffect(() => {
    let cancelled = false
    listMyComisiones(getToken)
      .then((res) => res.items.find((c) => c.id === tarea.comision_id)?.materia_id ?? null)
      .then((m) => {
        if (!cancelled) setMateriaId(m)
      })
      .catch(() => {
        if (!cancelled) setMateriaId(null)
      })
    return () => {
      cancelled = true
    }
  }, [tarea.comision_id, getToken])

  const usedIds = new Set(pairs.map((p) => p.ejercicio_id))
  const disponibles = biblioteca.filter((ej) => !usedIds.has(ej.id))

  // Filtro + orden client-side sobre lo ya cargado (listEjercicios limit=200, sin
  // paginacion server-side). Materia: incluye globales (materia_id === null) para
  // no ocultar el banco compartido. Orden por titulo (legible), no por UUID.
  const query = search.trim().toLowerCase()
  const visibles = disponibles
    .filter((ej) =>
      soloMateria && materiaId ? ej.materia_id === materiaId || ej.materia_id === null : true,
    )
    .filter((ej) =>
      query
        ? ej.titulo.toLowerCase().includes(query) ||
          ej.unidad_tematica.toLowerCase().includes(query)
        : true,
    )
    .sort((a, b) => a.titulo.localeCompare(b.titulo, "es"))

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleAdd() {
    if (selectedIds.size === 0) return
    setAdding(true)
    setError(null)
    try {
      // Insertamos en el orden visible (por titulo) de los seleccionados. Los
      // POST son secuenciales para asignar `orden` incremental sin colisiones.
      const toAdd = visibles.filter((ej) => selectedIds.has(ej.id))
      let nextOrden = pairs.length > 0 ? Math.max(...pairs.map((p) => p.orden)) + 1 : 1
      for (const ej of toAdd) {
        await tpEjerciciosApi.add(
          tarea.id,
          { ejercicio_id: ej.id, orden: nextOrden, peso_en_tp: nuevoPeso },
          getToken,
        )
        nextOrden += 1
      }
      setSelectedIds(new Set())
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
    // Serializamos el reorden: la operacion son 3 PATCH secuenciales (workaround
    // del UNIQUE via orden temporal). Sin este guard, clicks rapidos/dobles lanzan
    // handleReorder concurrentes cuyos PATCH se pisan y dejan `orden` inconsistente.
    if (reordering) return
    const sorted = [...pairs].sort((a, b) => a.orden - b.orden)
    const idx = sorted.findIndex((p) => p.id === pair.id)
    const swapIdx = direction === "up" ? idx - 1 : idx + 1
    if (swapIdx < 0 || swapIdx >= sorted.length) return
    const other = sorted[swapIdx]
    if (!other) return
    setReordering(true)
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
      // L-3: el swap son 3 PATCH secuenciales con orden temporal (max+100). Si
      // falla el 2do/3er PATCH, un ejercicio queda en `orden=temp` y la DB queda
      // inconsistente; sin este refetch la UI mostraria el orden viejo (stale)
      // contra ese estado real. Re-sincronizamos con la DB antes de reportar.
      // `fetchPairs` hace `setError(null)` al arrancar, por eso el mensaje va
      // DESPUES del await (si no, lo pisaria). Si el propio refetch falla, gana
      // su error, que tambien es informacion util.
      await fetchPairs()
      setError(
        `No se pudo completar el reordenamiento (${String(e)}). Se re-sincronizo la lista con el estado actual de la tarea.`,
      )
    } finally {
      setReordering(false)
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
                <p className="text-sm text-muted">Esta TP todavia no tiene ejercicios asociados.</p>
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
                                  disabled={idx === 0 || reordering}
                                  className="p-1 hover:bg-surface-alt rounded disabled:opacity-30 disabled:cursor-not-allowed"
                                  title="Subir"
                                >
                                  <ArrowUp className="h-3 w-3" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleReorder(p, "down")}
                                  disabled={idx === arr.length - 1 || reordering}
                                  className="p-1 hover:bg-surface-alt rounded disabled:opacity-30 disabled:cursor-not-allowed"
                                  title="Bajar"
                                >
                                  <ArrowDown className="h-3 w-3" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleRemove(p.ejercicio_id)}
                                  disabled={reordering}
                                  className="p-1 hover:bg-danger-soft hover:text-danger rounded disabled:opacity-30 disabled:cursor-not-allowed"
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
              <div className="border-t border-border pt-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-muted">Agregar desde la biblioteca</p>
                  {materiaId && (
                    <label className="inline-flex items-center gap-1.5 text-[11px] text-muted cursor-pointer">
                      <input
                        type="checkbox"
                        checked={soloMateria}
                        onChange={(e) => setSoloMateria(e.target.checked)}
                      />
                      Solo de esta materia
                    </label>
                  )}
                </div>

                {/* Buscador por texto (titulo / unidad) */}
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-soft" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar por titulo o unidad..."
                    className="w-full border border-border rounded pl-7 pr-2 py-1 text-sm"
                  />
                </div>

                {/* El motivo se dice antes de que el docente choque contra un
                    checkbox deshabilitado, no despues. */}
                {visibles.some((ej) => (ej.language ?? DEFAULT_LANGUAGE) !== tpLanguage) && (
                  <p
                    id="tp-comp-lenguaje-aviso"
                    className="text-xs text-muted"
                    data-testid="tp-comp-lenguaje-aviso"
                  >
                    Esta TP es de <strong className="font-medium">{tpLanguageLabel}</strong>. Los
                    ejercicios de otro lenguaje aparecen deshabilitados: una tarea practica admite
                    un solo lenguaje, porque el editor del alumno carga un unico entorno por
                    episodio.
                  </p>
                )}

                {/* Lista con multiseleccion */}
                {visibles.length > 0 ? (
                  <div className="max-h-48 overflow-y-auto rounded border border-border-soft divide-y divide-border-soft">
                    {visibles.map((ej) => {
                      const checked = selectedIds.has(ej.id)
                      const ejLanguage = ej.language ?? DEFAULT_LANGUAGE
                      const bloqueado = ejLanguage !== tpLanguage
                      const motivo = bloqueado
                        ? `Esta TP es de ${tpLanguageLabel} y el ejercicio es de ${LANGUAGE_LABELS[ejLanguage]}. Una tarea practica admite un solo lenguaje.`
                        : undefined
                      return (
                        <label
                          key={ej.id}
                          title={motivo}
                          className={`flex items-center gap-2 px-2 py-1.5 text-sm transition-colors ${
                            bloqueado
                              ? "opacity-50 cursor-not-allowed"
                              : checked
                                ? "bg-accent-brand-soft cursor-pointer"
                                : "hover:bg-surface-alt cursor-pointer"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={bloqueado}
                            aria-describedby={bloqueado ? "tp-comp-lenguaje-aviso" : undefined}
                            onChange={() => toggleSelected(ej.id)}
                          />
                          <span className="min-w-0 flex-1 truncate text-ink" title={ej.titulo}>
                            {ej.titulo}
                          </span>
                          {bloqueado && (
                            <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted">
                              {LANGUAGE_LABELS[ejLanguage]}
                            </span>
                          )}
                          <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-soft">
                            {ej.unidad_tematica}
                          </span>
                        </label>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-muted py-2">
                    {disponibles.length === 0
                      ? biblioteca.length === 0
                        ? "No hay ejercicios en la biblioteca. Crea uno desde /ejercicios."
                        : "Todos los ejercicios de la biblioteca ya estan en esta TP."
                      : "Ningun ejercicio coincide con el filtro."}
                  </p>
                )}

                {/* Peso + accion */}
                <div className="flex items-end justify-between gap-2">
                  <div className="w-24">
                    <label htmlFor="tp-comp-peso" className="block text-xs text-muted mb-1">
                      Peso
                    </label>
                    <input
                      id="tp-comp-peso"
                      type="text"
                      value={nuevoPeso}
                      onChange={(e) => setNuevoPeso(e.target.value)}
                      className="w-full border border-border rounded px-2 py-1 text-sm font-mono"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleAdd}
                    disabled={selectedIds.size === 0 || adding}
                    className="px-3 py-1.5 bg-accent-brand text-white rounded text-sm hover:bg-accent-brand-deep disabled:opacity-50"
                  >
                    {adding
                      ? "Agregando..."
                      : selectedIds.size > 0
                        ? `Agregar ${selectedIds.size}`
                        : "Agregar"}
                  </button>
                </div>
                <p className="text-[11px] text-muted-soft leading-snug">
                  Se listan hasta 200 ejercicios del banco (filtro y orden client-side, sin
                  paginacion server-side). El peso se aplica a todos los seleccionados.
                </p>
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
