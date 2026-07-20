/**
 * Observabilidad del RAG (F3) — componentes para que el docente pueda:
 *  - Ver los chunks generados de un material (texto, orden, metadata, embedding).
 *  - Probar una consulta de retrieval REAL y ver los top-k con su score.
 *
 * Los fetch van inline (no via lib/api.ts) contra el api-gateway, que rutea
 * `/api/v1/materiales/*` al content-service. En dev el proxy de Vite inyecta
 * los headers X-*; en prod el Bearer de Clerk viaja via `getToken`.
 */
import { Badge, Modal } from "@platform/ui"
import { FlaskConical, Layers, RotateCw } from "lucide-react"
import { useCallback, useEffect, useState } from "react"

type TokenGetter = () => Promise<string | null>

async function jsonHeaders(getToken: TokenGetter): Promise<Record<string, string>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const token = await getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function throwIfNotOk(r: Response): Promise<void> {
  if (r.ok) return
  const raw = await r.text()
  let detail = raw
  try {
    const body = JSON.parse(raw)
    detail = body.detail ?? body.title ?? raw
  } catch {
    /* not JSON */
  }
  throw new Error(`${r.status}: ${detail}`)
}

// ── Tipos (espejo de los schemas del content-service) ─────────────────

export interface ChunkOut {
  id: string
  material_id: string
  contenido: string
  chunk_type: string
  position: number
  meta: Record<string, unknown>
  embedding_model: string | null
  has_embedding: boolean
}

interface MaterialChunksResponse {
  material_id: string
  estado: string
  chunks_count: number
  embedding_model: string | null
  is_semantic_embedding: boolean | null
  data: ChunkOut[]
  meta: { offset: number; limit: number; returned: number; next_offset: number | null }
}

interface RetrievedChunk {
  id: string
  contenido: string
  material_id: string
  material_nombre: string
  position: number
  chunk_type: string
  meta: Record<string, unknown>
  score_vector: number
  score_rerank: number | null
}

interface RetrievalTestResponse {
  chunks: RetrievedChunk[]
  chunks_used_hash: string
  latency_ms: number
  rerank_applied: boolean
  embedder_model: string
  is_semantic_embedding: boolean
  reranker_model: string
}

// ── Fetch inline ──────────────────────────────────────────────────────

async function fetchChunks(
  materialId: string,
  getToken: TokenGetter,
): Promise<MaterialChunksResponse> {
  const r = await fetch(`/api/v1/materiales/${materialId}/chunks?limit=200`, {
    headers: await jsonHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

async function runRetrieval(
  body: { query: string; materia_id: string; top_k: number },
  getToken: TokenGetter,
): Promise<RetrievalTestResponse> {
  const r = await fetch("/api/v1/materiales/probar-retrieval", {
    method: "POST",
    headers: await jsonHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function reingestMaterial(materialId: string, getToken: TokenGetter): Promise<void> {
  const r = await fetch(`/api/v1/materiales/${materialId}/reingest`, {
    method: "POST",
    headers: await jsonHeaders(getToken),
  })
  await throwIfNotOk(r)
}

// ── Aviso de embeddings mock ──────────────────────────────────────────

function MockEmbeddingWarning({ model }: { model: string | null }) {
  return (
    <div className="rounded-lg border border-warning/30 bg-warning-soft px-3 py-2 text-xs text-warning leading-relaxed">
      <strong>Embeddings no semánticos ({model ?? "mock"}).</strong> Este corpus se indexó con
      vectores deterministas por hash: el orden y los scores son reproducibles pero{" "}
      <em>no reflejan relevancia real</em>. Para retrieval real, activá el embedder de producción (
      <code className="font-mono">EMBEDDER=gemini</code> con{" "}
      <code className="font-mono">GEMINI_API_KEY</code>) y reprocesá el material.
    </div>
  )
}

// ── Modal: ver chunks de un material ──────────────────────────────────

export function MaterialChunksModal({
  materialId,
  materialName,
  getToken,
  isOpen,
  onClose,
}: {
  materialId: string | null
  materialName: string
  getToken: TokenGetter
  isOpen: boolean
  onClose: () => void
}) {
  const [state, setState] = useState<
    | { status: "idle" }
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; data: MaterialChunksResponse }
  >({ status: "idle" })

  useEffect(() => {
    if (!isOpen || !materialId) return
    let cancelled = false
    setState({ status: "loading" })
    fetchChunks(materialId, getToken)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data })
      })
      .catch((e) => {
        if (!cancelled) setState({ status: "error", message: String(e) })
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, materialId, getToken])

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Chunks · ${materialName}`} size="xl">
      {state.status === "loading" && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-16 rounded-lg" />
          ))}
        </div>
      )}

      {state.status === "error" && (
        <div className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs text-danger break-all">
          {state.message}
        </div>
      )}

      {state.status === "ready" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Badge variant="info">{state.data.chunks_count} chunks</Badge>
            {state.data.embedding_model && (
              <span className="font-mono text-[11px]">{state.data.embedding_model}</span>
            )}
            {state.data.is_semantic_embedding === true && (
              <Badge variant="success">retrieval real</Badge>
            )}
          </div>

          {state.data.is_semantic_embedding === false && (
            <MockEmbeddingWarning model={state.data.embedding_model} />
          )}

          {state.data.data.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-surface-alt p-6 text-center text-sm text-muted">
              Este material no tiene chunks. Si el estado es <strong>Error</strong>, probá
              reprocesarlo desde la tarjeta.
            </div>
          ) : (
            <ol className="space-y-2 max-h-[55vh] overflow-y-auto pr-1">
              {state.data.data.map((c) => (
                <li
                  key={c.id}
                  className="rounded-lg border border-border bg-surface p-3 shadow-[0_1px_2px_0_rgba(0,0,0,0.03)]"
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5">
                      <Badge variant="default">#{c.position}</Badge>
                      <span className="text-[11px] text-muted font-mono">{c.chunk_type}</span>
                      {!c.has_embedding && <Badge variant="warning">sin vector</Badge>}
                    </div>
                  </div>
                  <p className="text-xs text-body whitespace-pre-wrap leading-relaxed">
                    {c.contenido}
                  </p>
                  {Object.keys(c.meta).length > 0 && (
                    <div className="mt-1.5 font-mono text-[10px] text-muted-soft truncate">
                      {JSON.stringify(c.meta)}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Modal>
  )
}

// ── Probador de retrieval ─────────────────────────────────────────────

function scorePct(score: number): number {
  return Math.max(0, Math.min(100, Math.round(score * 100)))
}

export function RetrievalTester({
  materiaId,
  getToken,
}: {
  materiaId: string
  getToken: TokenGetter
}) {
  const [query, setQuery] = useState("")
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RetrievalTestResponse | null>(null)

  const submit = useCallback(async () => {
    const q = query.trim()
    if (!q) return
    setRunning(true)
    setError(null)
    try {
      const res = await runRetrieval({ query: q, materia_id: materiaId, top_k: 5 }, getToken)
      setResult(res)
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }, [query, materiaId, getToken])

  return (
    <section className="rounded-xl border border-border bg-surface p-5 shadow-[0_1px_2px_0_rgba(0,0,0,0.04)] animate-fade-in-up">
      <div className="flex items-center gap-2 mb-3">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-surface-alt border border-border-soft text-muted">
          <FlaskConical className="h-4 w-4" />
        </span>
        <div>
          <h2 className="text-sm font-semibold text-ink leading-tight">Probar retrieval</h2>
          <p className="text-xs text-muted leading-tight">
            Corré una consulta real sobre el corpus y mirá qué chunks recupera el tutor.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit()
          }}
          placeholder="Ej: ¿qué es la recursión?"
          disabled={running}
          className="flex-1 min-w-[220px] rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-muted-soft focus:outline-none focus:ring-2 focus:ring-accent-brand/30 focus:border-accent-brand"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!query.trim() || running}
          className="press-shrink inline-flex items-center gap-1.5 px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border-strong text-white rounded-md font-medium transition-colors"
        >
          {running ? "Buscando..." : "Probar"}
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger break-all">
          {error}
        </div>
      )}

      {result && !error && (
        <div className="mt-4 space-y-3 animate-fade-in">
          <div className="flex items-center gap-2 flex-wrap text-[11px] text-muted">
            <Badge variant={result.is_semantic_embedding ? "success" : "warning"}>
              {result.is_semantic_embedding ? "retrieval real" : "retrieval mock"}
            </Badge>
            <span className="font-mono">{result.embedder_model}</span>
            <span>·</span>
            <span className="font-mono">
              reranker: {result.reranker_model}
              {result.rerank_applied ? "" : " (off)"}
            </span>
            <span>·</span>
            <span className="tabular-nums">{result.latency_ms.toFixed(0)} ms</span>
          </div>

          {!result.is_semantic_embedding && <MockEmbeddingWarning model={result.embedder_model} />}

          {result.chunks.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-surface-alt p-6 text-center text-sm text-muted">
              Sin resultados por encima del umbral de similitud. Probá con otra consulta o verificá
              que la materia tenga materiales indexados.
            </div>
          ) : (
            <ol className="space-y-2">
              {result.chunks.map((c, idx) => (
                <li
                  key={c.id}
                  className="rounded-lg border border-border bg-surface p-3 shadow-[0_1px_2px_0_rgba(0,0,0,0.03)]"
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Badge variant="default">#{idx + 1}</Badge>
                      <span className="text-[11px] text-muted truncate" title={c.material_nombre}>
                        {c.material_nombre} · chunk {c.position}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <ScorePill label="vec" value={c.score_vector} />
                      {c.score_rerank != null && (
                        <ScorePill label="rerank" value={c.score_rerank} />
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-body whitespace-pre-wrap leading-relaxed line-clamp-4">
                    {c.contenido}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  )
}

function ScorePill({ label, value }: { label: string; value: number }) {
  return (
    <span className="inline-flex items-center gap-1.5" title={`${label}: ${value.toFixed(4)}`}>
      <span className="text-[10px] uppercase tracking-wide text-muted-soft">{label}</span>
      <span className="h-1.5 w-12 rounded-full bg-surface-alt overflow-hidden">
        <span
          className="block h-full rounded-full bg-accent-brand"
          style={{ width: `${scorePct(value)}%` }}
        />
      </span>
      <span className="font-mono text-[11px] tabular-nums text-body">{value.toFixed(2)}</span>
    </span>
  )
}

// Re-export íconos usados por MaterialesView para acciones por material.
export { Layers as ViewChunksIcon, RotateCw as ReingestIcon }
