/**
 * Vista de gestión de materiales del curso (RAG).
 *
 * Permite al docente:
 *  - Subir PDFs / Markdown / ZIP / texto plano para indexar en el RAG
 *  - Ver el listado de materiales con su estado de procesamiento
 *  - Eliminar materiales (soft delete)
 *
 * Estado del pipeline (estado del Material):
 *   uploaded → extracting → chunking → embedding → indexed
 *                                                  ↘ failed
 *
 * Para los estados intermedios, polleamos cada 2s al endpoint GET /materiales/{id}
 * hasta que llegue a un estado terminal (indexed | failed). El polling se cancela
 * en cleanup del useEffect cuando el componente se desmonta.
 */
import { Badge, HelpButton, PageContainer } from "@platform/ui"
import { FileArchive, FileText, FileType, Film, Library, Trash2, Upload } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useComisionLabel } from "../components/ComisionSelector"
import {
  type Material,
  type MaterialEstado,
  type MaterialTipo,
  comisionesApi,
  materialesApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

/**
 * Resuelve el materia_id de una comision. Estados:
 *  - { status: "loading" } mientras hacemos fetch
 *  - { status: "not-found" } si la comision no esta entre las del caller
 *    (caso comun: comisionId viene de URL o localStorage de un tenant
 *    distinto al activo)
 *  - { status: "ready"; materiaId } cuando la encontramos
 *  - { status: "error" } si el fetch falla
 */
type MateriaIdState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "ready"; materiaId: string }
  | { status: "error" }

function useMateriaId(comisionId: string): MateriaIdState {
  const [state, setState] = useState<MateriaIdState>({ status: "loading" })
  useEffect(() => {
    let cancelled = false
    setState({ status: "loading" })
    comisionesApi
      .listMine()
      .then((res) => {
        if (cancelled) return
        const c = res.items.find((x) => x.id === comisionId)
        if (c) setState({ status: "ready", materiaId: c.materia_id })
        else setState({ status: "not-found" })
      })
      .catch(() => {
        if (cancelled) return
        setState({ status: "error" })
      })
    return () => {
      cancelled = true
    }
  }, [comisionId])
  return state
}

const TERMINAL_STATES: MaterialEstado[] = ["indexed", "failed"]

const TIPO_LABEL: Record<MaterialTipo, string> = {
  pdf: "PDF",
  markdown: "Markdown",
  code_archive: "ZIP",
  text: "Texto",
  video: "Video",
}

const TIPO_VARIANT: Record<MaterialTipo, "danger" | "info" | "success" | "default" | "warning"> = {
  pdf: "danger",
  markdown: "info",
  code_archive: "success",
  text: "default",
  video: "warning",
}

const TIPO_ICON: Record<MaterialTipo, React.ComponentType<{ className?: string }>> = {
  pdf: FileText,
  markdown: FileType,
  code_archive: FileArchive,
  text: FileText,
  video: Film,
}

const ESTADO_LABEL: Record<MaterialEstado, string> = {
  uploaded: "Subido",
  extracting: "Extrayendo texto",
  chunking: "Particionando",
  embedding: "Embeddings",
  indexed: "Indexado",
  failed: "Error",
}

const ESTADO_VARIANT: Record<MaterialEstado, "default" | "success" | "danger"> = {
  uploaded: "default",
  extracting: "default",
  chunking: "default",
  embedding: "default",
  indexed: "success",
  failed: "danger",
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffSec = Math.floor((now - then) / 1000)
  if (diffSec < 60) return "hace unos segundos"
  if (diffSec < 3600) return `hace ${Math.floor(diffSec / 60)} min`
  if (diffSec < 86400) return `hace ${Math.floor(diffSec / 3600)} h`
  if (diffSec < 86400 * 2) return "ayer"
  if (diffSec < 86400 * 7) return `hace ${Math.floor(diffSec / 86400)} días`
  return new Date(iso).toLocaleDateString()
}

export function MaterialesView({ comisionId, getToken }: Props) {
  const comisionLabelText = useComisionLabel(comisionId)
  const materiaIdState = useMateriaId(comisionId)
  const materiaId =
    materiaIdState.status === "ready" ? materiaIdState.materiaId : null
  const [materiales, setMateriales] = useState<Material[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  // Map de id → timeout pendiente de polling. Se limpia en cleanup.
  const pollTimers = useRef<Map<string, number>>(new Map())
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refreshList = useCallback(async () => {
    if (!materiaId) return
    setLoading(true)
    setError(null)
    try {
      const r = await materialesApi.list({ materia_id: materiaId }, getToken)
      setMateriales(r.data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [materiaId, getToken])

  useEffect(() => {
    // Si el hook de materia ya termino y NO encontro materia para esta
    // comision, salimos del loading state y mostramos mensaje claro.
    // Sin esto, el componente quedaba con loading=true para siempre.
    if (materiaIdState.status === "not-found") {
      setLoading(false)
      setError(
        "La comisión seleccionada no pertenece a tu universidad activa, " +
          "o no encontramos materia asociada. Cambiá de universidad en el selector " +
          "del header o pedile al admin que la asigne.",
      )
      setMateriales([])
      return
    }
    if (materiaIdState.status === "error") {
      setLoading(false)
      setError("No pudimos resolver la materia de esta comisión.")
      setMateriales([])
      return
    }
    refreshList()
  }, [refreshList, materiaIdState.status])

  // Polling de materiales en estado intermedio.
  useEffect(() => {
    const timers = pollTimers.current

    const pollOne = (id: string) => {
      const tick = async () => {
        try {
          const updated = await materialesApi.get(id, getToken)
          setMateriales((prev) => prev.map((m) => (m.id === id ? updated : m)))
          if (!TERMINAL_STATES.includes(updated.estado)) {
            const handle = window.setTimeout(tick, 2000)
            timers.set(id, handle)
          } else {
            timers.delete(id)
          }
        } catch {
          // Silencio en errores transitorios — el próximo refresh corregirá.
          timers.delete(id)
        }
      }
      const handle = window.setTimeout(tick, 2000)
      timers.set(id, handle)
    }

    for (const m of materiales) {
      if (!TERMINAL_STATES.includes(m.estado) && !timers.has(m.id)) {
        pollOne(m.id)
      }
    }

    return () => {
      // Sólo cleanup en unmount real; los timers en curso siguen vigentes
      // entre re-renders porque el ref es estable.
    }
  }, [materiales, getToken])

  // Cleanup completo al desmontar.
  useEffect(() => {
    const timers = pollTimers.current
    return () => {
      for (const handle of timers.values()) {
        clearTimeout(handle)
      }
      timers.clear()
    }
  }, [])

  const handleUpload = async () => {
    if (!file || !materiaId) return
    setUploading(true)
    setUploadError(null)
    try {
      await materialesApi.upload(materiaId, file, getToken)
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ""
      await refreshList()
    } catch (e) {
      const msg = String(e)
      if (msg.includes("413")) {
        setUploadError("El archivo supera el límite de 50 MB.")
      } else {
        setUploadError(msg)
      }
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (m: Material) => {
    const ok = window.confirm(`¿Eliminar el material "${m.nombre}"? El RAG dejará de usarlo.`)
    if (!ok) return
    try {
      await materialesApi.delete(m.id, getToken)
      await refreshList()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <PageContainer
      title="Materiales del curso"
      description={`Corpus del RAG para el tutor socrático. Comisión: ${comisionLabelText}`}
      eyebrow={`Inicio · Materiales · ${comisionLabelText}`}
      helpContent={helpContent.materiales}
    >
      <div className="space-y-6">
        {/* ═══ Upload form ════════════════════════════════════════════════ */}
        <section className="rounded-xl border border-border bg-surface p-5 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] animate-fade-in-up">
          <div className="flex items-center gap-2 mb-3">
            <HelpButton
              size="sm"
              title="Subir material"
              content={
                <div className="space-y-3 text-body">
                  <p>
                    <strong>Formatos y limites aceptados</strong>:
                  </p>
                  <ul className="list-disc pl-5 space-y-2">
                    <li>
                      <strong>PDF:</strong> Apuntes, libros, guias de ejercicios.
                    </li>
                    <li>
                      <strong>Markdown (.md):</strong> Documentacion, tutoriales estructurados.
                    </li>
                    <li>
                      <strong>Texto (.txt):</strong> Material de referencia en texto plano.
                    </li>
                    <li>
                      <strong>ZIP:</strong> Archivos de codigo fuente (se indexa el contenido
                      interno).
                    </li>
                    <li>
                      <strong>Tamano maximo:</strong> 50 MB por archivo.
                    </li>
                  </ul>
                </div>
              }
            />
            <h2 className="text-sm font-semibold text-ink leading-tight">Subir material nuevo</h2>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.md,.txt,.zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={uploading}
              className="text-sm text-body file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-border file:bg-surface-alt file:text-body file:font-medium hover:file:bg-surface-alt file:cursor-pointer"
            />
            {file && (
              <span className="font-mono text-xs text-muted">
                {file.name} · {formatBytes(file.size)}
              </span>
            )}
            <button
              type="button"
              onClick={handleUpload}
              disabled={!file || !materiaId || uploading}
              className="press-shrink inline-flex items-center gap-1.5 px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border-strong text-white rounded-md font-medium transition-colors shadow-[0_1px_2px_0_rgba(24,95,165,0.25)]"
            >
              <Upload className="h-3.5 w-3.5" />
              {uploading ? "Subiendo..." : "Subir"}
            </button>
          </div>
          <p className="text-xs text-muted leading-relaxed mt-2">
            Formatos aceptados: PDF, Markdown (.md), texto (.txt), ZIP de código. Tamaño máximo: 50
            MB por archivo.
          </p>
          {uploadError && (
            <div className="mt-3 rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
              {uploadError}
            </div>
          )}
        </section>

        {/* ═══ Materials list ═════════════════════════════════════════════ */}
        <section className="space-y-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted">
              Corpus indexado ({materiales.length})
            </h2>
            <button
              type="button"
              onClick={refreshList}
              disabled={loading}
              className="press-shrink px-3 py-1 text-xs border border-border bg-surface rounded-md hover:bg-surface-alt disabled:opacity-40 text-muted transition-colors"
            >
              {loading ? "Cargando..." : "Refrescar"}
            </button>
          </div>

          {error && (
            <div className="rounded-xl border border-danger/30 bg-danger-soft p-4 animate-fade-in-up">
              <div className="text-sm font-semibold text-danger">No pudimos cargar el corpus</div>
              <div className="mt-1.5 font-mono text-xs text-danger/85 break-all">{error}</div>
            </div>
          )}

          {loading && materiales.length === 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 animate-fade-in">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-28 rounded-xl" />
              ))}
            </div>
          ) : materiales.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-surface p-10 text-center animate-fade-in-up">
              <div className="inline-flex items-center justify-center rounded-full bg-surface-alt p-4 mb-4">
                <Library className="h-7 w-7 text-muted" />
              </div>
              <p className="text-sm text-muted leading-relaxed max-w-md mx-auto">
                Esta materia todavía no tiene materiales indexados. El RAG del tutor responde solo
                con el contexto de los archivos cargados.
              </p>
            </div>
          ) : (
            <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {materiales.map((m, idx) => (
                <li
                  key={m.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${Math.min(idx, 6) * 50}ms` }}
                >
                  <MaterialCard material={m} onDelete={() => handleDelete(m)} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </PageContainer>
  )
}

function MaterialCard({
  material,
  onDelete,
}: {
  material: Material
  onDelete: () => void
}) {
  const tipo = material.tipo
  const estado = material.estado
  const isProcessing = !TERMINAL_STATES.includes(estado)
  const Icon = TIPO_ICON[tipo]

  return (
    <article className="hover-lift group relative overflow-hidden rounded-xl border border-border bg-surface flex flex-col h-full shadow-[0_1px_2px_0_rgba(0,0,0,0.04)]">
      <div className="p-4 flex-1 flex flex-col gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-surface-alt border border-border-soft text-muted">
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h3
              className="text-sm font-semibold text-ink leading-tight truncate"
              title={material.nombre}
            >
              {material.nombre}
            </h3>
            <div className="mt-0.5 text-[11px] text-muted font-mono tabular-nums">
              {formatBytes(material.tamano_bytes)} · {formatRelative(material.created_at)}
            </div>
          </div>
        </div>

        {material.error_message && (
          <div
            className="rounded-md border border-danger/20 bg-danger-soft px-2.5 py-1.5 text-[11px] text-danger truncate"
            title={material.error_message}
          >
            {material.error_message}
          </div>
        )}

        <div className="flex items-center justify-between gap-2 mt-auto pt-2 border-t border-border-soft">
          <div className="flex items-center gap-1.5 flex-wrap">
            <Badge variant={TIPO_VARIANT[tipo]}>{TIPO_LABEL[tipo]}</Badge>
            <span className={isProcessing ? "animate-pulse-soft" : ""}>
              <Badge variant={ESTADO_VARIANT[estado]}>{ESTADO_LABEL[estado]}</Badge>
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="font-mono tabular-nums text-xs text-muted" title="Chunks indexados">
              {material.chunks_count ?? "…"}
              <span className="text-muted-soft ml-0.5">chunks</span>
            </span>
            <button
              type="button"
              onClick={onDelete}
              className="press-shrink inline-flex items-center gap-1 px-2 py-1 text-[11px] text-danger hover:bg-danger-soft rounded transition-colors"
              title="Eliminar material"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}
