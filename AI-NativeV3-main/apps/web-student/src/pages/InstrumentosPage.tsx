/**
 * Pagina de instrumentos del diseño cuasi-experimental.
 *
 * Cierran P2-1 (pretest), P2-2 (cuestionario IA), P2-3 (transferencia)
 * del PlanMejora.md como ESQUELETO TECNICO. El contenido academico esta
 * pendiente de validacion coautoral con Ana Garis + comite etico UNSL.
 *
 * Estructura:
 * - Card 1: Cuestionario sobre experiencia previa con IA (1 vez por ciclo)
 * - Card 2: Pretest de autoeficacia en programacion (1 vez por ciclo)
 * - Card 3: Test de transferencia (N problemas)
 *
 * Idempotencia: cada instrumento, si ya fue respondido por el estudiante en
 * la version vigente, muestra "Ya respondiste" y deshabilita re-envio.
 *
 * UX (2026-05-19):
 * - Boton "Volver al menu" al header.
 * - Progreso global N de 3 con check visual por card completada.
 * - Cards colapsables: arrancan colapsadas si ya estan respondidas; la
 *   primera pendiente arranca expandida para reducir clicks.
 * - Placeholders [PLACEHOLDER ...] del catalogo no se muestran al alumno
 *   (eran ruido visual de la fase DRAFT v0.1.0); se preservan en data-* para
 *   inspeccion admin/teacher cuando haga falta.
 * - Likert con etiquetas visuales en los extremos.
 *
 * ADR de respaldo: ADR-053.
 */

import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, CheckCircle2, ChevronDown, ChevronUp, Loader2 } from "lucide-react"
import {
  type InstrumentoCatalogo,
  type InstrumentoCatalogoItem,
  type TestTransferenciaCatalogo,
  type TestTransferenciaProblem,
  instrumentosApi,
} from "../lib/api"

interface Props {
  comisionId: string
  studentPseudonym: string
  // Asignacion del estudiante a grupo (experimental | comparison) — viene del
  // backend en el futuro; por ahora hardcoded en "experimental" porque el
  // grupo de comparacion no tiene acceso al sistema instrumentado.
  groupAssignment?: "experimental" | "comparison"
  getToken: (() => Promise<string | null>) | undefined
}

type InstrumentKey = "cuestionarioIA" | "pretest" | "transferencia"

export function InstrumentosPage({
  comisionId,
  studentPseudonym,
  groupAssignment = "experimental",
  getToken,
}: Props) {
  const navigate = useNavigate()
  const [completed, setCompleted] = useState<Record<InstrumentKey, boolean>>({
    cuestionarioIA: false,
    pretest: false,
    transferencia: false,
  })

  const handleCompletion = (key: InstrumentKey, isComplete: boolean) => {
    setCompleted((prev) => (prev[key] === isComplete ? prev : { ...prev, [key]: isComplete }))
  }

  const completedCount = Object.values(completed).filter(Boolean).length
  const totalCount = 3
  const allDone = completedCount === totalCount

  // La primera card pendiente arranca expandida; las completadas arrancan
  // colapsadas. Si todavia no sabemos el estado, abrimos la primera.
  const firstPendingKey: InstrumentKey | null = !completed.cuestionarioIA
    ? "cuestionarioIA"
    : !completed.pretest
      ? "pretest"
      : !completed.transferencia
        ? "transferencia"
        : null

  return (
    <div className="page-enter flex-1 overflow-y-auto px-6 py-10">
      <div className="space-y-6 max-w-4xl mx-auto">
        {/* ── Header con boton volver + progreso global ───────────────── */}
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => navigate({ to: "/" })}
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink transition-colors"
            data-testid="instrumentos-back-to-menu"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver al menu
          </button>

          <header>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <h1 className="text-2xl font-semibold text-ink">Instrumentos de investigacion</h1>
              <ProgressBadge completed={completedCount} total={totalCount} />
            </div>
            <p className="text-sm text-muted mt-2 leading-relaxed">
              Tu participacion en estos tres instrumentos es voluntaria y nos ayuda a entender mejor
              como aprenden programacion los estudiantes con asistentes de IA. Tus respuestas son
              anonimas y solo se usan para investigacion academica.
            </p>
            <div
              className="mt-3 text-xs text-warning bg-warning-soft border border-warning rounded-md p-3"
              data-testid="instrumentos-draft-notice"
            >
              <strong>Aviso:</strong> los instrumentos estan en version DRAFT v0.1.0 pendiente de
              validacion coautoral. Los items son placeholders para validar el flujo de la
              aplicacion; el contenido final llega cuando el comite etico UNSL apruebe el protocolo.
            </div>
            {allDone && (
              <div
                className="mt-3 flex items-center gap-2 text-sm text-success bg-success-soft border border-success rounded-md p-3"
                data-testid="instrumentos-all-done"
              >
                <CheckCircle2 className="h-5 w-5 flex-shrink-0" />
                <span>
                  Completaste los tres instrumentos. Gracias por participar — tus respuestas ayudan
                  a la investigacion.
                </span>
              </div>
            )}
          </header>
        </div>

        <CuestionarioIACard
          comisionId={comisionId}
          studentPseudonym={studentPseudonym}
          getToken={getToken}
          isExpanded={firstPendingKey === "cuestionarioIA"}
          onCompletedChange={(v) => handleCompletion("cuestionarioIA", v)}
        />
        <PretestAutoeficaciaCard
          comisionId={comisionId}
          studentPseudonym={studentPseudonym}
          getToken={getToken}
          isExpanded={firstPendingKey === "pretest"}
          onCompletedChange={(v) => handleCompletion("pretest", v)}
        />
        <TransferenciaCard
          comisionId={comisionId}
          studentPseudonym={studentPseudonym}
          groupAssignment={groupAssignment}
          getToken={getToken}
          isExpanded={firstPendingKey === "transferencia"}
          onCompletedChange={(v) => handleCompletion("transferencia", v)}
        />
      </div>
    </div>
  )
}

// ─── Cuestionario IA ─────────────────────────────────────────────────────

function CuestionarioIACard({
  comisionId,
  studentPseudonym,
  getToken,
  isExpanded,
  onCompletedChange,
}: {
  comisionId: string
  studentPseudonym: string
  getToken: (() => Promise<string | null>) | undefined
  isExpanded: boolean
  onCompletedChange: (v: boolean) => void
}) {
  const [catalogo, setCatalogo] = useState<InstrumentoCatalogo | null>(null)
  const [responses, setResponses] = useState<Record<string, unknown>>({})
  const [alreadyAnswered, setAlreadyAnswered] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      instrumentosApi.cuestionarioIA.catalogo(getToken),
      instrumentosApi.cuestionarioIA.me(comisionId, undefined, getToken),
    ])
      .then(([cat, existing]) => {
        setCatalogo(cat)
        if (existing) setAlreadyAnswered(true)
      })
      .catch((e) => setError(String(e)))
  }, [comisionId, getToken])

  useEffect(() => {
    onCompletedChange(alreadyAnswered)
  }, [alreadyAnswered, onCompletedChange])

  if (!catalogo)
    return <CardLoading title="Cuestionario sobre experiencia previa con IA" isExpanded={isExpanded} />

  return (
    <CardShell
      title="Cuestionario sobre experiencia previa con IA"
      isComplete={alreadyAnswered}
      defaultExpanded={isExpanded}
    >
      {alreadyAnswered ? (
        <p className="text-sm text-muted" data-testid="cuestionario-ia-already-answered">
          Ya respondiste este cuestionario. Gracias.
        </p>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            setSubmitting(true)
            setError(null)
            try {
              await instrumentosApi.cuestionarioIA.submit(
                {
                  comision_id: comisionId,
                  student_pseudonym: studentPseudonym,
                  instrument_version: catalogo.instrument_version,
                  responses,
                },
                getToken,
              )
              setAlreadyAnswered(true)
            } catch (err) {
              setError(String(err))
            } finally {
              setSubmitting(false)
            }
          }}
          className="space-y-5"
          data-testid="cuestionario-ia-form"
        >
          {catalogo.items.map((item) => (
            <ItemRenderer
              key={item.id}
              item={item}
              value={responses[item.id]}
              onChange={(value) => setResponses((prev) => ({ ...prev, [item.id]: value }))}
            />
          ))}
          {error && <p className="text-danger text-sm">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 bg-ink text-canvas rounded-md disabled:opacity-50 inline-flex items-center gap-2"
            data-testid="cuestionario-ia-submit"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitting ? "Enviando..." : "Enviar respuestas"}
          </button>
        </form>
      )}
    </CardShell>
  )
}

// ─── Pretest Autoeficacia ────────────────────────────────────────────────

function PretestAutoeficaciaCard({
  comisionId,
  studentPseudonym,
  getToken,
  isExpanded,
  onCompletedChange,
}: {
  comisionId: string
  studentPseudonym: string
  getToken: (() => Promise<string | null>) | undefined
  isExpanded: boolean
  onCompletedChange: (v: boolean) => void
}) {
  const [catalogo, setCatalogo] = useState<InstrumentoCatalogo | null>(null)
  const [responses, setResponses] = useState<Record<string, number>>({})
  const [alreadyAnswered, setAlreadyAnswered] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      instrumentosApi.pretest.catalogo(getToken),
      instrumentosApi.pretest.me(comisionId, undefined, getToken),
    ])
      .then(([cat, existing]) => {
        setCatalogo(cat)
        if (existing) setAlreadyAnswered(true)
      })
      .catch((e) => setError(String(e)))
  }, [comisionId, getToken])

  useEffect(() => {
    onCompletedChange(alreadyAnswered)
  }, [alreadyAnswered, onCompletedChange])

  if (!catalogo)
    return <CardLoading title="Pretest de autoeficacia en programacion" isExpanded={isExpanded} />

  return (
    <CardShell
      title="Pretest de autoeficacia en programacion"
      isComplete={alreadyAnswered}
      defaultExpanded={isExpanded}
    >
      {alreadyAnswered ? (
        <p className="text-sm text-muted" data-testid="pretest-already-answered">
          Ya respondiste el pretest. Gracias.
        </p>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            setSubmitting(true)
            setError(null)
            try {
              await instrumentosApi.pretest.submit(
                {
                  comision_id: comisionId,
                  student_pseudonym: studentPseudonym,
                  instrument_version: catalogo.instrument_version,
                  responses,
                },
                getToken,
              )
              setAlreadyAnswered(true)
            } catch (err) {
              setError(String(err))
            } finally {
              setSubmitting(false)
            }
          }}
          className="space-y-5"
          data-testid="pretest-form"
        >
          {catalogo.items.map((item) => (
            <ItemRenderer
              key={item.id}
              item={item}
              value={responses[item.id]}
              onChange={(value) =>
                setResponses((prev) => ({ ...prev, [item.id]: value as number }))
              }
            />
          ))}
          {error && <p className="text-danger text-sm">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 bg-ink text-canvas rounded-md disabled:opacity-50 inline-flex items-center gap-2"
            data-testid="pretest-submit"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitting ? "Enviando..." : "Enviar respuestas"}
          </button>
        </form>
      )}
    </CardShell>
  )
}

// ─── Test Transferencia ──────────────────────────────────────────────────

function TransferenciaCard({
  comisionId,
  studentPseudonym,
  groupAssignment,
  getToken,
  isExpanded,
  onCompletedChange,
}: {
  comisionId: string
  studentPseudonym: string
  groupAssignment: "experimental" | "comparison"
  getToken: (() => Promise<string | null>) | undefined
  isExpanded: boolean
  onCompletedChange: (v: boolean) => void
}) {
  const [catalogo, setCatalogo] = useState<TestTransferenciaCatalogo | null>(null)
  const [answered, setAnswered] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      instrumentosApi.transferencia.catalogo(getToken),
      instrumentosApi.transferencia.me(comisionId, undefined, getToken),
    ])
      .then(([cat, mine]) => {
        setCatalogo(cat)
        setAnswered(new Set(mine.map((r) => r.test_id)))
      })
      .catch((e) => setError(String(e)))
  }, [comisionId, getToken])

  // Considera la card completa cuando todos los problemas estan respondidos.
  const allAnswered = useMemo(() => {
    if (!catalogo) return false
    return catalogo.problems.length > 0 && catalogo.problems.every((p) => answered.has(p.test_id))
  }, [catalogo, answered])

  useEffect(() => {
    onCompletedChange(allAnswered)
  }, [allAnswered, onCompletedChange])

  if (!catalogo) return <CardLoading title="Test de transferencia" isExpanded={isExpanded} />

  const remaining = catalogo.problems.length - answered.size

  return (
    <CardShell
      title="Test de transferencia"
      isComplete={allAnswered}
      defaultExpanded={isExpanded}
      headerExtra={
        catalogo.problems.length > 0 && !allAnswered ? (
          <span className="text-xs text-muted">
            {answered.size} / {catalogo.problems.length} resueltos
          </span>
        ) : null
      }
    >
      {error && <p className="text-danger text-sm mb-3">{error}</p>}
      <p className="text-xs text-muted mb-4">
        Grupo asignado: <code>{groupAssignment}</code>
        {!allAnswered && catalogo.problems.length > 0 && (
          <> · Faltan {remaining} problema{remaining === 1 ? "" : "s"}.</>
        )}
      </p>
      <ul className="space-y-3">
        {catalogo.problems.map((problem) => (
          <TransferProblemItem
            key={problem.test_id}
            problem={problem}
            alreadyAnswered={answered.has(problem.test_id)}
            comisionId={comisionId}
            studentPseudonym={studentPseudonym}
            groupAssignment={groupAssignment}
            instrumentVersion={catalogo.instrument_version}
            onSubmitted={() => setAnswered((prev) => new Set([...prev, problem.test_id]))}
            getToken={getToken}
          />
        ))}
      </ul>
    </CardShell>
  )
}

function TransferProblemItem({
  problem,
  alreadyAnswered,
  comisionId,
  studentPseudonym,
  groupAssignment,
  instrumentVersion,
  onSubmitted,
  getToken,
}: {
  problem: TestTransferenciaProblem
  alreadyAnswered: boolean
  comisionId: string
  studentPseudonym: string
  groupAssignment: "experimental" | "comparison"
  instrumentVersion: string
  onSubmitted: () => void
  getToken: (() => Promise<string | null>) | undefined
}) {
  const [startedAt] = useState(Date.now())
  const [response, setResponse] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cleanTitle = stripPlaceholderPrefix(problem.title)
  const cleanDescription = stripPlaceholderPrefix(problem.description)

  if (alreadyAnswered) {
    return (
      <li className="border border-success bg-success-soft rounded-md p-3 flex items-start gap-2">
        <CheckCircle2 className="h-5 w-5 text-success flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="text-sm font-medium" data-original-title={problem.title}>
            {cleanTitle}
          </p>
          <p className="text-xs text-success mt-0.5">Ya respondiste este problema.</p>
        </div>
      </li>
    )
  }
  return (
    <li
      className="border border-border rounded-md p-3"
      data-testid={`transfer-problem-${problem.test_id}`}
    >
      <p className="text-sm font-medium" data-original-title={problem.title}>
        {cleanTitle}
      </p>
      <p className="text-xs text-muted mt-1" data-original-description={problem.description}>
        {cleanDescription}
      </p>
      <textarea
        value={response}
        onChange={(e) => setResponse(e.target.value)}
        rows={5}
        className="mt-2 w-full border border-border rounded-md p-2 font-mono text-xs"
        placeholder="Tu respuesta..."
      />
      {error && <p className="text-danger text-xs mt-1">{error}</p>}
      <button
        type="button"
        disabled={submitting || !response.trim()}
        className="mt-2 px-3 py-1.5 bg-ink text-canvas rounded-md text-sm disabled:opacity-50 inline-flex items-center gap-2"
        onClick={async () => {
          setSubmitting(true)
          setError(null)
          try {
            await instrumentosApi.transferencia.submit(
              {
                comision_id: comisionId,
                student_pseudonym: studentPseudonym,
                instrument_version: instrumentVersion,
                group_assignment: groupAssignment,
                test_id: problem.test_id,
                time_taken_seconds: Math.floor((Date.now() - startedAt) / 1000),
                response_detail: { answer: response },
              },
              getToken,
            )
            onSubmitted()
          } catch (err) {
            setError(String(err))
          } finally {
            setSubmitting(false)
          }
        }}
      >
        {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {submitting ? "Enviando..." : "Enviar"}
      </button>
    </li>
  )
}

// ─── Componentes UI compartidos ───────────────────────────────────────────

function ProgressBadge({ completed, total }: { completed: number; total: number }) {
  const allDone = completed === total
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
        allDone
          ? "bg-success-soft border-success text-success"
          : "bg-canvas border-border text-muted"
      }`}
      data-testid="instrumentos-progress-badge"
    >
      {allDone && <CheckCircle2 className="h-3.5 w-3.5" />}
      {completed} de {total} completados
    </span>
  )
}

function CardShell({
  title,
  isComplete,
  defaultExpanded = false,
  headerExtra,
  children,
}: {
  title: string
  isComplete?: boolean
  defaultExpanded?: boolean
  headerExtra?: React.ReactNode
  children: React.ReactNode
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  return (
    <section
      className={`border rounded-xl bg-surface overflow-hidden transition-colors ${
        isComplete ? "border-success" : "border-border"
      }`}
      data-testid="instrument-card"
      data-instrument-complete={isComplete ? "true" : "false"}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full border-b border-border bg-canvas px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-surface transition-colors"
        aria-expanded={expanded}
        data-testid="instrument-card-toggle"
      >
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          {isComplete && (
            <CheckCircle2
              className="h-5 w-5 text-success flex-shrink-0"
              aria-label="Completado"
            />
          )}
          <h2 className="text-base font-semibold text-ink truncate">{title}</h2>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {headerExtra}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted" />
          )}
        </div>
      </button>
      {expanded && <div className="p-4">{children}</div>}
    </section>
  )
}

function CardLoading({ title, isExpanded }: { title: string; isExpanded: boolean }) {
  return (
    <section className="border border-border rounded-xl bg-surface overflow-hidden">
      <div className="border-b border-border bg-canvas px-4 py-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        <Loader2 className="h-4 w-4 animate-spin text-muted" />
      </div>
      {isExpanded && (
        <p className="text-xs text-muted p-4">Cargando catalogo...</p>
      )}
    </section>
  )
}

/**
 * Quita los prefijos [PLACEHOLDER ...] del texto que ve el alumno.
 *
 * El catalogo viene del backend con marcadores DRAFT v0.1.0 tipo
 * "[PLACEHOLDER GARIS] ...", "[PLACEHOLDER CATEDRA UNSL — TP-1] ...",
 * "[PLACEHOLDER GARIS — Lishinski 2016 #5] ...". Esos marcadores son
 * para los autores (Garis, catedra UNSL) y son ruido visual para el alumno.
 *
 * El texto original se preserva en `data-original-*` para que sea inspeccionable
 * desde admin/teacher si hace falta. Cuando el comite etico apruebe el contenido
 * final, los marcadores se quitan del backend y este helper queda no-op.
 */
function stripPlaceholderPrefix(text: string): string {
  return text.replace(/^\[PLACEHOLDER[^\]]*\]\s*/i, "").trim()
}

function ItemRenderer({
  item,
  value,
  onChange,
}: {
  item: InstrumentoCatalogoItem
  value: unknown
  onChange: (v: unknown) => void
}) {
  const cleanText = stripPlaceholderPrefix(item.text)

  if (item.type === "likert" && item.scale_min !== undefined && item.scale_max !== undefined) {
    const scaleMin = item.scale_min
    const scaleMax = item.scale_max
    const labels = item.scale_labels ?? {}
    const minLabel = labels[String(scaleMin)] ?? labels.min
    const maxLabel = labels[String(scaleMax)] ?? labels.max
    const range = Array.from({ length: scaleMax - scaleMin + 1 }, (_, i) => scaleMin + i)

    return (
      <fieldset
        className="space-y-2 border border-border rounded-md p-3 bg-canvas"
        data-item-id={item.id}
        data-original-text={item.text}
      >
        <legend className="text-sm text-ink block px-1 leading-snug">{cleanText}</legend>
        <div className="flex items-center justify-between gap-3 pt-1">
          {minLabel && (
            <span className="text-[11px] text-muted text-right max-w-[28%] leading-tight">
              {minLabel}
            </span>
          )}
          <div className="flex items-center gap-1.5 flex-1 justify-center">
            {range.map((n) => {
              const checked = value === n
              return (
                <label
                  key={n}
                  className={`flex flex-col items-center text-xs cursor-pointer rounded-md px-1.5 py-1 border transition-colors ${
                    checked
                      ? "bg-ink border-ink text-canvas"
                      : "border-border text-muted hover:border-ink"
                  }`}
                >
                  <input
                    type="radio"
                    name={item.id}
                    value={n}
                    checked={checked}
                    onChange={() => onChange(n)}
                    className="sr-only"
                  />
                  <span className="font-semibold">{n}</span>
                </label>
              )
            })}
          </div>
          {maxLabel && (
            <span className="text-[11px] text-muted text-left max-w-[28%] leading-tight">
              {maxLabel}
            </span>
          )}
        </div>
      </fieldset>
    )
  }

  if (item.type === "single_choice" && item.options) {
    return (
      <label className="space-y-1 block" data-item-id={item.id} data-original-text={item.text}>
        <span className="text-sm text-ink block">{cleanText}</span>
        <select
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="border border-border rounded-md p-1.5 text-sm w-full max-w-md"
        >
          <option value="">— seleccionar —</option>
          {item.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </label>
    )
  }

  if (item.type === "multiple_choice" && item.options) {
    const selected = (value as string[]) ?? []
    return (
      <fieldset className="space-y-1" data-item-id={item.id} data-original-text={item.text}>
        <legend className="text-sm text-ink block">{cleanText}</legend>
        <div className="flex flex-wrap gap-2">
          {item.options.map((opt) => (
            <label key={opt} className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={(e) => {
                  if (e.target.checked) onChange([...selected, opt])
                  else onChange(selected.filter((s) => s !== opt))
                }}
              />
              {opt}
            </label>
          ))}
        </div>
      </fieldset>
    )
  }

  return (
    <div className="text-xs text-muted italic" data-item-id={item.id}>
      [Renderer no implementado para tipo: {item.type}]
    </div>
  )
}
