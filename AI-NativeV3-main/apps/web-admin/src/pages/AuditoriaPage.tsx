/**
 * Auditoría de integridad CTR para docente_admin / superadmin (ADR-031, D.4).
 *
 * Permite verificar on-demand la cadena criptográfica SHA-256 de un episodio
 * cerrado del piloto. Útil para:
 *   - Mostrar al comité doctoral la integridad del CTR en vivo durante la defensa.
 *   - Diagnóstico ante cualquier sospecha de tampering reportada por
 *     `integrity_compromised=true` del integrity-checker en background (ADR-021).
 *   - Reproducción bit-a-bit en auditorías externas (combinado con el JSONL de
 *     attestations Ed25519 de `integrity-attestation-service`, RN-128).
 *
 * Pega a `/api/v1/audit/episodes/{id}/verify` (alias publico via api-gateway
 * ROUTE_MAP — el handler real vive en ctr-service y verifica recomputando
 * `self_hash` y `chain_hash` de cada evento contra los persistidos).
 */
import { Button, PageContainer } from "@platform/ui"
import { type ReactNode, useState } from "react"
import { type ChainVerificationResult, HttpError, auditApi } from "../lib/api"
import { helpContent } from "../utils/helpContent"

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

type RequestState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; result: ChainVerificationResult }
  | { status: "error"; message: string; statusCode?: number }

// F13 — export a estandares Caliper/xAPI (ADR-046, paper §5.1).
// Endpoints pull-based on-demand del analytics-service, alcanzables via gateway
// ROUTE_MAP prefix `/api/v1/export` (verificado en proxy.py):
//   GET /api/v1/export/caliper/{episode_id} → envelope Caliper 1.2 (dict)
//   GET /api/v1/export/xapi/{episode_id}    → lista de statements xAPI 1.0.3
// FOLLOW-UP: cuando se toque lib/api.ts, mover este fetch inline a un
// `exportApi.caliper/xapi` tipado (hoy inline por scope de la tarea).
type ExportFormat = "caliper" | "xapi"

const EXPORT_FORMATS: { format: ExportFormat; label: string; standard: string }[] = [
  { format: "caliper", label: "Exportar Caliper", standard: "Caliper Analytics 1.2" },
  { format: "xapi", label: "Exportar xAPI", standard: "xAPI 1.0.3" },
]

type ExportState =
  | { status: "idle" }
  | { status: "loading"; format: ExportFormat }
  | { status: "ok"; format: ExportFormat; filename: string }
  | { status: "error"; format: ExportFormat; message: string; statusCode?: number }

async function fetchExport(format: ExportFormat, episodeId: string): Promise<unknown> {
  const response = await fetch(`/api/v1/export/${format}/${encodeURIComponent(episodeId)}`)
  if (!response.ok) {
    const raw = await response.text()
    let detail = raw
    try {
      const body = JSON.parse(raw)
      detail = body.detail ?? body.title ?? raw
    } catch {
      /* not JSON, use raw text */
    }
    throw new HttpError(response.status, response.statusText, detail)
  }
  return response.json()
}

function downloadJson(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function AuditoriaPage(): ReactNode {
  const [episodeId, setEpisodeId] = useState("")
  const [state, setState] = useState<RequestState>({ status: "idle" })
  const [exportState, setExportState] = useState<ExportState>({ status: "idle" })

  const idValid = UUID_PATTERN.test(episodeId.trim())

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!idValid) return
    setState({ status: "loading" })
    try {
      const result = await auditApi.verifyEpisode(episodeId.trim())
      setState({ status: "ok", result })
    } catch (err) {
      if (err instanceof HttpError) {
        setState({
          status: "error",
          message: err.detail || err.title || `HTTP ${err.status}`,
          statusCode: err.status,
        })
      } else {
        setState({ status: "error", message: (err as Error).message })
      }
    }
  }

  const onExport = async (format: ExportFormat) => {
    if (!idValid) return
    const id = episodeId.trim()
    setExportState({ status: "loading", format })
    try {
      const data = await fetchExport(format, id)
      const filename = `${format}-${id}.json`
      downloadJson(data, filename)
      setExportState({ status: "ok", format, filename })
    } catch (err) {
      if (err instanceof HttpError) {
        setExportState({
          status: "error",
          format,
          message: err.detail || err.title || `HTTP ${err.status}`,
          statusCode: err.status,
        })
      } else {
        setExportState({ status: "error", format, message: (err as Error).message })
      }
    }
  }

  const reset = () => {
    setEpisodeId("")
    setState({ status: "idle" })
    setExportState({ status: "idle" })
  }

  return (
    <PageContainer
      title="Auditoria de integridad CTR"
      eyebrow="Inicio · Auditoria de integridad CTR"
      description="Verifica la cadena criptografica SHA-256 de un episodio cerrado del piloto"
      helpContent={helpContent.auditoria}
    >
      <div className="space-y-6">
        <form onSubmit={onSubmit} className="rounded-lg border border-border-soft bg-surface p-4">
          <label
            htmlFor="auditoria-episode-id"
            className="block text-sm font-medium text-body mb-2"
          >
            Episode ID (UUID)
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <input
              id="auditoria-episode-id"
              type="text"
              value={episodeId}
              onChange={(e) => setEpisodeId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="flex-1 min-w-[280px] font-mono text-sm rounded border border-border px-3 py-2"
              disabled={state.status === "loading"}
              aria-invalid={episodeId.length > 0 && !idValid}
            />
            <button
              type="submit"
              disabled={!idValid || state.status === "loading"}
              className="rounded bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border disabled:cursor-not-allowed text-white text-sm px-4 py-2"
            >
              {state.status === "loading" ? "Verificando..." : "Verificar integridad"}
            </button>
            {state.status !== "idle" && (
              <button
                type="button"
                onClick={reset}
                className="text-sm text-muted hover:text-body px-3 py-2"
              >
                Limpiar
              </button>
            )}
          </div>
          {episodeId.length > 0 && !idValid && (
            <p className="text-xs text-[var(--color-danger)] mt-2">
              Formato UUID invalido. Ejemplo: 12345678-1234-1234-1234-123456789abc
            </p>
          )}
        </form>

        <section className="rounded-lg border border-border-soft bg-surface p-4">
          <h2 className="text-sm font-medium text-body">Exportar a estandares abiertos</h2>
          <p className="text-xs text-muted mt-1">
            Descarga los eventos del episodio en formato Caliper Analytics 1.2 o xAPI 1.0.3
            (pull-based, read-only). El CTR sigue siendo la fuente de verdad bit-exacta; estos
            exports son para auditores externos que pidan un formato estandar.
          </p>
          <div className="flex flex-wrap items-center gap-2 mt-3">
            {EXPORT_FORMATS.map(({ format, label, standard }) => (
              <Button
                key={format}
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => onExport(format)}
                disabled={!idValid || exportState.status === "loading"}
                title={idValid ? standard : "Ingresa un Episode ID valido arriba"}
              >
                {exportState.status === "loading" && exportState.format === format
                  ? "Exportando..."
                  : label}
              </Button>
            ))}
          </div>
          {!idValid && (
            <p className="text-xs text-muted mt-2">
              Ingresa un Episode ID valido en el campo de arriba para habilitar el export.
            </p>
          )}
          {exportState.status === "ok" && (
            <div className="rounded-md bg-success-soft border border-success/30 text-success p-3 mt-3">
              <p className="text-sm font-medium">
                Export {exportState.format === "caliper" ? "Caliper" : "xAPI"} descargado
              </p>
              <p className="text-xs mt-1 font-mono break-all">{exportState.filename}</p>
            </div>
          )}
          {exportState.status === "error" && (
            <div className="rounded-md bg-danger-soft border border-danger/30 text-danger p-3 mt-3">
              <p className="text-sm font-medium">
                Error al exportar {exportState.format === "caliper" ? "Caliper" : "xAPI"}
              </p>
              <p className="text-xs mt-1">{exportState.message}</p>
              {exportState.statusCode === 404 && (
                <p className="text-xs mt-2">
                  El episodio no existe, no tiene eventos, o pertenece a otro tenant.
                </p>
              )}
              {exportState.statusCode === 403 && (
                <p className="text-xs mt-2">
                  No perteneces a la comision de este episodio (gate de membresia).
                </p>
              )}
            </div>
          )}
        </section>

        {state.status === "error" && (
          <div className="rounded-lg bg-danger-soft border border-danger/30 text-danger p-4">
            <p className="font-medium">Error al verificar</p>
            <p className="text-sm mt-1">{state.message}</p>
            {state.statusCode === 404 && (
              <p className="text-xs mt-2 text-danger">
                El episodio no existe (todavia no se cerro o pertenece a otro tenant).
              </p>
            )}
          </div>
        )}

        {state.status === "ok" && <VerificationResultCard result={state.result} />}
      </div>
    </PageContainer>
  )
}

function VerificationResultCard({ result }: { result: ChainVerificationResult }): ReactNode {
  const ok = result.valid && !result.integrity_compromised
  const compromisedNotFailingNow = !result.valid ? false : result.integrity_compromised

  return (
    <div
      data-testid="audit-result"
      data-valid={result.valid ? "true" : "false"}
      data-events-count={String(result.events_count)}
      className={`rounded-lg border p-5 ${
        ok
          ? "bg-success-soft border-success/30 text-success"
          : "bg-danger-soft border-danger/30 text-danger"
      }`}
    >
      <div className="flex items-baseline gap-3">
        <span className="text-2xl">{ok ? "OK" : "FAIL"}</span>
        <span className="font-medium">
          {ok
            ? "Cadena integra"
            : result.valid
              ? "Verificacion paso pero integrity_compromised=true (flag persistente)"
              : "Cadena rota"}
        </span>
      </div>
      <p className="text-sm mt-2">{result.message}</p>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <div>
          <dt className="text-xs uppercase opacity-60">Episode ID</dt>
          <dd className="font-mono break-all">{result.episode_id}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase opacity-60">Eventos</dt>
          <dd className="font-mono">{result.events_count}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase opacity-60">Cadena valida</dt>
          <dd className="font-mono">{result.valid ? "true" : "false"}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase opacity-60">Failing seq</dt>
          <dd className="font-mono">{result.failing_seq === null ? "—" : result.failing_seq}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-xs uppercase opacity-60">integrity_compromised (flag persistente)</dt>
          <dd className="font-mono">{result.integrity_compromised ? "true" : "false"}</dd>
        </div>
      </dl>

      {compromisedNotFailingNow && (
        <p className="text-xs mt-4 italic opacity-80">
          La verificacion on-demand paso, pero el integrity-checker en background marco este
          episodio como comprometido en algun momento (ADR-021). Investigar el log historico antes
          de descartar.
        </p>
      )}
    </div>
  )
}
