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
import { PageContainer } from "@platform/ui"
import { type ReactNode, useState } from "react"
import { type ChainVerificationResult, HttpError, auditApi } from "../lib/api"
import { helpContent } from "../utils/helpContent"

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

type RequestState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; result: ChainVerificationResult }
  | { status: "error"; message: string; statusCode?: number }

export function AuditoriaPage(): ReactNode {
  const [episodeId, setEpisodeId] = useState("")
  const [state, setState] = useState<RequestState>({ status: "idle" })

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

  const reset = () => {
    setEpisodeId("")
    setState({ status: "idle" })
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
        ok ? "bg-success-soft border-success/30 text-success" : "bg-danger-soft border-danger/30 text-danger"
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
