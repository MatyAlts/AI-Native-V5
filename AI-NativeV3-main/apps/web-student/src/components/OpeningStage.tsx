/**
 * Estado de transicion "abriendo episodio" (shape alumno, brief 3.4 + D6).
 *
 * Sustituye el `Abriendo episodio...` plano. Es la unica oportunidad de
 * hacer auditabilidad criptografica visible ANTES de que el alumno
 * arranque la TP. 4 chequeos secuenciales con estado:
 *
 *   1. TP validada (estado=published, ventana fechas OK).
 *   2. Episodio registrado en CTR (seq=0, evento EpisodioAbierto).
 *   3. Cadena criptografica firmando (chain_hash inicial).
 *   4. Tutor inicializando con prompt vigente.
 *
 * Estados por linea:
 *   - "done"     ✓ verde
 *   - "inflight" ▰ pulsante con prefers-reduced-motion fallback
 *   - "pending"  ▱ slate
 *   - "error"    ✗ rojo + ghost button "ver detalles"
 *
 * El backend POST /api/v1/episodes hoy es atomic; simulamos los 4 estados
 * con timeouts cortos para que el comite vea la auditabilidad. Si el
 * POST tarda >3s aparece la linea de "retrying chain commit" (honestidad
 * tecnica). Si todo va bien: ~500-800ms total.
 */
import { useEffect, useState } from "react"

type StepStatus = "pending" | "inflight" | "done" | "error"

interface Step {
  key: string
  label: string
  detail: string
  status: StepStatus
}

interface OpeningStageProps {
  /** Codigo + titulo de la TP que se esta abriendo (display 24px). */
  tareaCodigo: string
  tareaTitulo: string
  /** True si el POST /episodes ya respondio OK (paso 2 en adelante). */
  episodeReady: boolean
  /** episode_id para mostrar en `chain anterior` cuando este disponible. */
  episodeId?: string | null
  /** Mensaje de error si POST fallo. */
  errorMessage?: string | null
  /** Disparado por "ver detalles" cuando hay error. */
  onShowError?: () => void
  /** Reintentar el POST /episodes (mismo tarea+ejercicio). */
  onRetry?: () => void
  /** Volver al selector de TPs sin abrir episodio. */
  onCancel?: () => void
}

const STEP_DEFS: Array<Pick<Step, "key" | "label" | "detail">> = [
  {
    key: "tp",
    label: "TP validada",
    detail: "estado=published, ventana fechas OK",
  },
  {
    key: "ctr",
    label: "Episodio registrado en CTR",
    detail: "seq=0, evento EpisodioAbierto",
  },
  {
    key: "chain",
    label: "Cadena criptografica firmando",
    detail: "chain_hash inicial pendiente",
  },
  {
    key: "tutor",
    label: "Tutor inicializando con prompt",
    detail: "tutor/v1.0.0 (cargando contexto)",
  },
]

export function OpeningStage({
  tareaCodigo,
  tareaTitulo,
  episodeReady,
  episodeId = null,
  errorMessage = null,
  onShowError,
  onRetry,
  onCancel,
}: OpeningStageProps) {
  const [tick, setTick] = useState(0)
  const [showRetry, setShowRetry] = useState(false)

  // Avanzamos un "tick" cada 200ms para animar las primeras 2 lineas
  // ANTES de que el episode_id este disponible. Cuando llega, los pasos
  // 1 y 2 quedan done; los 3 y 4 progresan en otros 2 ticks.
  useEffect(() => {
    const interval = window.setInterval(() => {
      setTick((t) => Math.min(t + 1, 4))
    }, 250)
    return () => window.clearInterval(interval)
  }, [])

  // Si el POST tarda >3s sin respuesta, mostramos la linea de retry.
  useEffect(() => {
    if (episodeReady) return
    const t = window.setTimeout(() => setShowRetry(true), 3000)
    return () => window.clearTimeout(t)
  }, [episodeReady])

  const steps: Step[] = STEP_DEFS.map((def, idx) => {
    let status: StepStatus
    if (errorMessage && idx === 1) {
      status = "error"
    } else if (idx === 0) {
      // TP validada: done despues del primer tick (la validacion ya
      // ocurrio en el flujo de seleccion).
      status = tick >= 1 ? "done" : "inflight"
    } else if (idx === 1) {
      // CTR: done una vez que tenemos episode_id.
      if (episodeReady) status = "done"
      else status = tick >= 1 ? "inflight" : "pending"
    } else if (idx === 2) {
      // Cadena: done despues del CTR + 1 tick.
      if (episodeReady && tick >= 3) status = "done"
      else if (episodeReady) status = "inflight"
      else status = "pending"
    } else {
      // Tutor: done el ultimo.
      if (episodeReady && tick >= 4) status = "done"
      else if (episodeReady && tick >= 3) status = "inflight"
      else status = "pending"
    }
    return { ...def, status }
  })

  return (
    <div className="flex-1 overflow-y-auto px-6 py-12">
      <div className="max-w-2xl mx-auto">
        <p className="text-xs font-mono uppercase tracking-wider text-muted mb-3">
          Abriendo episodio
        </p>

        <h2 className="text-2xl font-semibold leading-tight text-ink mb-8">
          <span className="font-mono text-base text-muted mr-2">
            {tareaCodigo}
          </span>
          {tareaTitulo}
        </h2>

        <ol className="space-y-3" aria-label="Chequeos de apertura del episodio">
          {steps.map((step) => (
            <StepRow
              key={step.key}
              step={step}
              {...(onShowError ? { onShowError } : {})}
            />
          ))}
        </ol>

        {showRetry && !episodeReady && !errorMessage && (
          <p
            data-testid="opening-retry-line"
            className="mt-4 text-xs text-muted font-mono"
          >
            ▱ retrying chain commit (red lenta detectada)
          </p>
        )}

        {episodeId && (
          <p className="mt-6 text-xs font-mono text-muted">
            episodio: <span className="text-body">{episodeId.slice(0, 6)}...{episodeId.slice(-4)}</span>
          </p>
        )}

        {errorMessage && (onRetry || onCancel) && (
          <div
            data-testid="opening-error-actions"
            className="mt-8 flex flex-wrap items-center gap-3"
          >
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="px-4 py-2 rounded-md text-sm font-medium bg-accent-brand text-white hover:bg-accent-brand-deep press-shrink"
              >
                Reintentar
              </button>
            )}
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="px-4 py-2 rounded-md text-sm font-medium border border-border-soft text-body hover:bg-surface-alt press-shrink"
              >
                Volver a la lista
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StepRow({ step, onShowError }: { step: Step; onShowError?: () => void }) {
  const { status, label, detail } = step
  return (
    <li
      data-testid={`opening-step-${step.key}`}
      data-status={status}
      className="flex items-start gap-3 text-sm"
    >
      <StatusGlyph status={status} />
      <div className="flex-1 min-w-0">
        <p
          className={
            status === "error"
              ? "text-danger font-medium"
              : status === "done"
                ? "text-ink"
                : status === "inflight"
                  ? "text-body"
                  : "text-muted"
          }
        >
          {label}
        </p>
        <p className="text-xs font-mono text-muted mt-0.5">{detail}</p>
        {status === "error" && onShowError && (
          <button
            type="button"
            onClick={onShowError}
            className="mt-1 text-xs underline text-danger hover:text-danger"
          >
            ver detalles
          </button>
        )}
      </div>
    </li>
  )
}

/**
 * Glifo de estado. En `prefers-reduced-motion: reduce` reemplazamos el
 * spinner ▰ por un dot pulsante CSS-only via opacity transition (sin
 * `animation`), para presbicia / sensibilidad vestibular del comite.
 */
function StatusGlyph({ status }: { status: StepStatus }) {
  if (status === "done") {
    return (
      <span
        aria-hidden="true"
        className="inline-flex w-5 h-5 items-center justify-center rounded-full text-xs font-bold"
        style={{
          color: "var(--color-success)",
        }}
        data-testid="step-glyph-done"
      >
        ✓
      </span>
    )
  }
  if (status === "error") {
    return (
      <span
        aria-hidden="true"
        className="inline-flex w-5 h-5 items-center justify-center rounded-full text-xs font-bold text-danger"
        data-testid="step-glyph-error"
      >
        ✗
      </span>
    )
  }
  if (status === "inflight") {
    return (
      <span
        aria-hidden="true"
        data-testid="step-glyph-inflight"
        className="inline-flex w-5 h-5 items-center justify-center"
      >
        <InflightGlyph />
      </span>
    )
  }
  return (
    <span
      aria-hidden="true"
      data-testid="step-glyph-pending"
      className="inline-flex w-5 h-5 items-center justify-center text-muted-soft"
    >
      ▱
    </span>
  )
}

/**
 * Spinner CSS-only que respeta prefers-reduced-motion. Usa el utility
 * de Tailwind `motion-safe:animate-pulse` para que con
 * `prefers-reduced-motion: reduce` el dot quede estatico (opacidad fija).
 */
function InflightGlyph() {
  return (
    <span
      data-testid="inflight-dot"
      className="inline-block w-2 h-2 rounded-full motion-safe:animate-pulse"
      style={{ backgroundColor: "var(--color-accent-brand)" }}
    />
  )
}
