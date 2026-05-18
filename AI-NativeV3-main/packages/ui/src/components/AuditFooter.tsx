/**
 * Footer de auditabilidad fijo (compartido por web-student y web-teacher).
 *
 * Status bar de IDE: muestra version del prompt, hash del classifier y
 * estado de la cadena CTR. Renderiza igual en TODOS los estados del flujo
 * (welcome, opening, episode activo, post-cierre). Cumple PRODUCT.md
 * Design Principle 2 ("Auditabilidad visible, no oculta") y la
 * "Auditable Hex Rule" del DESIGN.md.
 *
 * Honestidad tecnica:
 *  - prompt_version es el VIGENTE en runtime para el tutor-service. La
 *    fuente declarativa esta en `ai-native-prompts/manifest.yaml`
 *    (expuesta via GET /api/v1/active_configs); por ahora es hardcoded
 *    `tutor/v1.0.0` con TODO de conectarlo cuando ese endpoint este en
 *    el ROUTE_MAP del api-gateway.
 *  - classifier_config_hash truncado primer-4 + ultimos-4. Si hay
 *    classification reciente en sessionStorage, lo usa; sino "pendiente".
 *  - n_eventos cadena: poll cada 30s al verify del episodio activo. Sin
 *    episodio activo cae al ultimo conocido + label "ultima verificacion:
 *    hace X". NO live counter falso.
 *
 * Tambien expone `labeler` (default 1.1.0) para extension futura.
 */
import { useEffect, useState } from "react"

const LS_AUDIT_HASH_KEY = "audit-classifier-hash"
const LS_AUDIT_CHAIN_KEY = "audit-chain-state"

const PROMPT_VERSION = "tutor/v1.0.0"
const LABELER_VERSION = "1.1.0"

interface ChainState {
  events: number
  lastVerifiedAt: number | null
  episodeId: string | null
}

interface VerifyResponse {
  episode_id: string
  events_count: number
  is_intact: boolean
  reason: string | null
}

function truncateHash(hash: string | null): string {
  if (!hash || hash.length < 10) return "pendiente"
  return `${hash.slice(0, 4)}...${hash.slice(-4)}`
}

function relativeAgo(ts: number | null): string {
  if (ts === null) return "nunca"
  const seconds = Math.floor((Date.now() - ts) / 1000)
  if (seconds < 5) return "ahora"
  if (seconds < 60) return `hace ${seconds}s`
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)}m`
  return `hace ${Math.floor(seconds / 3600)}h`
}

interface AuditFooterProps {
  /** Episodio activo si lo hay; usado para poll del verify endpoint. */
  episodeId: string | null
  /** Hash del classifier de la classification mas reciente (si existe). */
  classifierHash?: string | null
  /** Suplemento opcional. Hoy lo usa la vista adversaria (guardrails_corpus). */
  extraLabel?: string
}

export function AuditFooter({ episodeId, classifierHash, extraLabel }: AuditFooterProps) {
  const [chain, setChain] = useState<ChainState>(() => {
    if (typeof window === "undefined") {
      return { events: 0, lastVerifiedAt: null, episodeId: null }
    }
    try {
      const raw = window.sessionStorage.getItem(LS_AUDIT_CHAIN_KEY)
      if (!raw) return { events: 0, lastVerifiedAt: null, episodeId: null }
      const parsed = JSON.parse(raw) as ChainState
      return parsed
    } catch {
      return { events: 0, lastVerifiedAt: null, episodeId: null }
    }
  })

  const [hash, setHash] = useState<string | null>(() => {
    if (classifierHash) return classifierHash
    if (typeof window === "undefined") return null
    return window.sessionStorage.getItem(LS_AUDIT_HASH_KEY)
  })

  // Cuando llega un classifierHash nuevo desde la page, lo persistimos.
  useEffect(() => {
    if (classifierHash && classifierHash.length >= 10) {
      setHash(classifierHash)
      try {
        window.sessionStorage.setItem(LS_AUDIT_HASH_KEY, classifierHash)
      } catch {
        // ignore
      }
    }
  }, [classifierHash])

  // Poll cada 30s al verify del episodio activo. Sin episodio activo,
  // el footer queda con el ultimo valor conocido del session storage.
  useEffect(() => {
    if (!episodeId) return
    let cancelled = false

    async function verifyOnce() {
      try {
        const r = await fetch(`/api/v1/audit/episodes/${episodeId}/verify`, {
          method: "POST",
        })
        if (!r.ok) return
        const data = (await r.json()) as VerifyResponse
        if (cancelled) return
        const next: ChainState = {
          events: data.events_count,
          lastVerifiedAt: Date.now(),
          episodeId,
        }
        setChain(next)
        try {
          window.sessionStorage.setItem(LS_AUDIT_CHAIN_KEY, JSON.stringify(next))
        } catch {
          // ignore
        }
      } catch {
        // Best-effort. El footer mantiene el ultimo valor conocido.
      }
    }

    void verifyOnce()
    const interval = window.setInterval(verifyOnce, 30_000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [episodeId])

  const chainLabel = (() => {
    if (chain.events === 0 && chain.lastVerifiedAt === null) {
      return "cadena: sin verificacion previa"
    }
    if (episodeId && chain.episodeId === episodeId) {
      return `cadena: ${chain.events} eventos verificados`
    }
    return `cadena: ${chain.events} eventos (ultima verificacion: ${relativeAgo(chain.lastVerifiedAt)})`
  })()

  return (
    <footer
      data-testid="audit-footer"
      aria-label="Trazabilidad y auditabilidad del piloto"
      className="border-t border-border bg-surface-alt px-6 py-2 font-mono text-xs text-muted flex flex-wrap items-center gap-x-3 gap-y-1"
    >
      <span>prompt: {PROMPT_VERSION}</span>
      <span aria-hidden="true">{"·"}</span>
      <span>
        classifier: <span data-testid="audit-classifier-hash">{truncateHash(hash)}</span>
      </span>
      <span aria-hidden="true">{"·"}</span>
      <span>labeler: {LABELER_VERSION}</span>
      <span aria-hidden="true">{"·"}</span>
      <span data-testid="audit-chain-label">{chainLabel}</span>
      {extraLabel && (
        <>
          <span aria-hidden="true">{"·"}</span>
          <span data-testid="audit-extra-label">{extraLabel}</span>
        </>
      )}
    </footer>
  )
}
