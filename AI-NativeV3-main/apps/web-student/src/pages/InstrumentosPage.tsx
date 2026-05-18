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
 * ADR de respaldo: ADR-053.
 */

import { useEffect, useState } from "react"
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

export function InstrumentosPage({
  comisionId,
  studentPseudonym,
  groupAssignment = "experimental",
  getToken,
}: Props) {
  return (
    <div className="space-y-8 p-6 max-w-4xl mx-auto">
      <header>
        <h1 className="text-2xl font-semibold text-ink">Instrumentos de investigacion</h1>
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
          validacion coautoral. Los items son placeholders para validar el flujo de la aplicacion;
          el contenido final llega cuando el comite etico UNSL apruebe el protocolo.
        </div>
      </header>

      <CuestionarioIACard
        comisionId={comisionId}
        studentPseudonym={studentPseudonym}
        getToken={getToken}
      />
      <PretestAutoeficaciaCard
        comisionId={comisionId}
        studentPseudonym={studentPseudonym}
        getToken={getToken}
      />
      <TransferenciaCard
        comisionId={comisionId}
        studentPseudonym={studentPseudonym}
        groupAssignment={groupAssignment}
        getToken={getToken}
      />
    </div>
  )
}

// ─── Cuestionario IA ─────────────────────────────────────────────────────

function CuestionarioIACard({
  comisionId,
  studentPseudonym,
  getToken,
}: {
  comisionId: string
  studentPseudonym: string
  getToken: (() => Promise<string | null>) | undefined
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

  if (!catalogo) return <CardLoading title="Cuestionario sobre IA previa" />

  return (
    <CardShell title="Cuestionario sobre experiencia previa con IA" notice={catalogo.draft_notice}>
      {alreadyAnswered ? (
        <p className="text-success text-sm" data-testid="cuestionario-ia-already-answered">
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
          className="space-y-4"
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
            className="px-4 py-2 bg-ink text-canvas rounded-md disabled:opacity-50"
            data-testid="cuestionario-ia-submit"
          >
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
}: {
  comisionId: string
  studentPseudonym: string
  getToken: (() => Promise<string | null>) | undefined
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

  if (!catalogo) return <CardLoading title="Pretest de autoeficacia" />

  return (
    <CardShell title="Pretest de autoeficacia en programacion" notice={catalogo.draft_notice}>
      {alreadyAnswered ? (
        <p className="text-success text-sm" data-testid="pretest-already-answered">
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
          className="space-y-4"
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
            className="px-4 py-2 bg-ink text-canvas rounded-md disabled:opacity-50"
            data-testid="pretest-submit"
          >
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
}: {
  comisionId: string
  studentPseudonym: string
  groupAssignment: "experimental" | "comparison"
  getToken: (() => Promise<string | null>) | undefined
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

  if (!catalogo) return <CardLoading title="Test de transferencia" />

  return (
    <CardShell title="Test de transferencia" notice={catalogo.draft_notice}>
      {error && <p className="text-danger text-sm">{error}</p>}
      <p className="text-xs text-muted mb-4">
        Grupo asignado: <code>{groupAssignment}</code>
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

  if (alreadyAnswered) {
    return (
      <li className="border border-border rounded-md p-3 bg-canvas">
        <p className="text-sm font-medium">{problem.title}</p>
        <p className="text-xs text-success mt-1">Ya respondiste este problema.</p>
      </li>
    )
  }
  return (
    <li
      className="border border-border rounded-md p-3"
      data-testid={`transfer-problem-${problem.test_id}`}
    >
      <p className="text-sm font-medium">{problem.title}</p>
      <p className="text-xs text-muted mt-1">{problem.description}</p>
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
        className="mt-2 px-3 py-1.5 bg-ink text-canvas rounded-md text-sm disabled:opacity-50"
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
        {submitting ? "Enviando..." : "Enviar"}
      </button>
    </li>
  )
}

// ─── Componentes UI compartidos ───────────────────────────────────────────

function CardShell({
  title,
  notice,
  children,
}: {
  title: string
  notice?: string
  children: React.ReactNode
}) {
  return (
    <section className="border border-border rounded-xl bg-surface overflow-hidden">
      <header className="border-b border-border bg-canvas px-4 py-3">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {notice && <p className="text-xs text-muted mt-1 italic leading-snug">{notice}</p>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  )
}

function CardLoading({ title }: { title: string }) {
  return (
    <section className="border border-border rounded-xl bg-surface p-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <p className="text-xs text-muted mt-2">Cargando catalogo...</p>
    </section>
  )
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
  if (item.type === "likert" && item.scale_min !== undefined && item.scale_max !== undefined) {
    const scaleMin = item.scale_min
    const scaleMax = item.scale_max
    return (
      <fieldset className="space-y-1" data-item-id={item.id}>
        <legend className="text-sm text-ink block">{item.text}</legend>
        <div className="flex items-center gap-2">
          {Array.from({ length: scaleMax - scaleMin + 1 }, (_, i) => scaleMin + i).map((n) => (
            <label key={n} className="flex flex-col items-center text-xs">
              <input
                type="radio"
                name={item.id}
                value={n}
                checked={value === n}
                onChange={() => onChange(n)}
                className="mb-0.5"
              />
              {n}
            </label>
          ))}
        </div>
        {item.scale_labels && (
          <p className="text-[10px] text-muted">
            {Object.entries(item.scale_labels)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ")}
          </p>
        )}
      </fieldset>
    )
  }
  if (item.type === "single_choice" && item.options) {
    return (
      <label className="space-y-1 block" data-item-id={item.id}>
        <span className="text-sm text-ink block">{item.text}</span>
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
      <fieldset className="space-y-1" data-item-id={item.id}>
        <legend className="text-sm text-ink block">{item.text}</legend>
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
