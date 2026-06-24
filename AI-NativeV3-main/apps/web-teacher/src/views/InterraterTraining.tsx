import { useState } from "react"
import { EpisodeProcessTrace, PROFILES } from "./interraterShared"

interface Props {
  materiaId: string
  getToken: () => Promise<string | null>
  onPass: () => void
}

const TOTAL = 7
const PASS_THRESHOLD = 6

// ── Anclas de calibración (consenso del equipo, sobre episodios reales de prod) ──
// Cada ancla: el episodio real + su eje correcto + por qué (feedback). El docente
// las clasifica a ciegas y recibe corrección inmediata. Editable: cambiar el
// `episode_id` o el `label` acá ajusta el entrenamiento.
interface Anchor {
  episode_id: string
  context: string
  label: string // canónico (delegacion_pasiva | apropiacion_superficial | apropiacion_reflexiva)
  why: string
  whyNot: string
}

const ANCHORS: Anchor[] = [
  {
    episode_id: "02205295-67ab-45d5-a07e-22be5585cf2a",
    context: "Lo hizo solo y le salió",
    label: "apropiacion_reflexiva",
    why: "No le habló al tutor ni una vez y resolvió el ejercicio. Autonomía total con resultado.",
    whyNot:
      "NO pasiva: el que no usa el tutor es el más autónomo, no el que más delega (ese es el error clásico a evitar).",
  },
  {
    episode_id: "a8150302-988b-4313-921d-49c672301b59",
    context: "Colabora bien con el tutor",
    label: "apropiacion_reflexiva",
    why: "Explica qué hace su código ('open abre el archivo', 'el print muestra un mensaje'), lo ejecuta dos veces para verificar, y justifica usar el modo 'a' ('agrega sin borrar lo que había antes').",
    whyNot: "NO superficial: hay verbalización, verificación propia y justificación, no solo usar la respuesta.",
  },
  {
    episode_id: "2b083646-c873-4323-8bd9-cd674273fee8",
    context: "Usa el tutor de forma operativa",
    label: "apropiacion_superficial",
    why: "Una sola pregunta práctica ('qué herramienta para redondear'). Usó la respuesta sin profundizar.",
    whyNot:
      "NO reflexiva: no contrastó ni explicó el porqué. NO pasiva: sí hizo algo propio con la respuesta.",
  },
  {
    episode_id: "06ddbc14-d1f1-42cf-a128-201dce7d9c2c",
    context: "Lo intentó solo pero se trabó",
    label: "apropiacion_superficial",
    why: "Sin tutor, peleó el ejercicio solo pero no llegó a resolverlo (ejecutó varias veces sin éxito).",
    whyNot:
      "NO reflexiva: no completó ni verificó con éxito. NO pasiva: no delegó, lo intentó por su cuenta.",
  },
  {
    episode_id: "079dede6-32f9-4d73-aa85-91d1cb83f01c",
    context: "Escribió pero no probó",
    label: "apropiacion_superficial",
    why: "Escribió bastante código pero casi no lo ejecutó. Produjo algo propio sin validarlo.",
    whyNot: "NO reflexiva: falta la verificación crítica.",
  },
  {
    episode_id: "2df3242f-512a-4a17-a562-2bda4fc66fdb",
    context: "Se desenganchó",
    label: "apropiacion_superficial",
    why: "Casi no laburó y no habló con el tutor. Baja implicación: se codifica acá por defecto.",
    whyNot: "NO pasiva: no usó el tutor para extraer nada; simplemente no se enganchó.",
  },
  {
    episode_id: "0a3d4388-c4e1-4333-b495-7e7e889d48dd",
    context: "Sobreusa el tutor (la trampa)",
    label: "delegacion_pasiva",
    why: "Escribió su código y lo probó, PERO no paró de pedirle al tutor que se lo revise ('¿en qué me equivoqué?', 'mirá por vos mismo'): sobreuso. Delega el JUICIO.",
    whyNot:
      "Parece reflexiva (verbaliza, verifica en VS Code) pero terceriza cada decisión. El sobreuso manda → pasiva.",
  },
]

const displayOf = (label: string) => PROFILES.find((p) => p.label === label)?.display ?? label

type Phase = "teaching" | "calibration" | "result"

export function InterraterTraining({ getToken, onPass }: Props) {
  const [phase, setPhase] = useState<Phase>("teaching")
  const [idx, setIdx] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)
  const [correct, setCorrect] = useState(0)

  const start = () => {
    setPhase("calibration")
    setIdx(0)
    setPicked(null)
    setCorrect(0)
  }

  const pick = (label: string) => {
    if (picked) return
    setPicked(label)
    if (label === ANCHORS[idx]?.label) setCorrect((c) => c + 1)
  }

  const next = () => {
    if (idx + 1 >= TOTAL) {
      setPhase("result")
      return
    }
    setIdx((i) => i + 1)
    setPicked(null)
  }

  if (phase === "teaching") return <Teaching onStart={start} />
  if (phase === "result")
    return <Result correct={correct} onPass={onPass} onRetry={start} />

  // calibration
  const a = ANCHORS[idx]
  if (!a) return null
  const isCorrect = picked === a.label
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Entrenamiento · calibración</h3>
        <span className="text-sm text-muted">
          Episodio {idx + 1} de {TOTAL} · aciertos {correct}
        </span>
      </div>

      <div className="rounded-xl border border-border bg-white p-4">
        <p className="text-xs text-muted mb-3">
          Mirá el proceso del alumno y elegí el eje. Después te digo si acertaste.
        </p>
        <EpisodeProcessTrace episodeId={a.episode_id} getToken={getToken} />

        <div className="mt-4 flex flex-wrap gap-2">
          {PROFILES.map((p) => {
            const chosen = picked === p.label
            const reveal = picked !== null
            const isAnswer = p.label === a.label
            const ring = reveal
              ? isAnswer
                ? "ring-2 ring-green-600"
                : chosen
                  ? "ring-2 ring-danger"
                  : "opacity-50"
              : "opacity-80 hover:opacity-100"
            return (
              <button
                key={p.label}
                type="button"
                disabled={picked !== null}
                onClick={() => pick(p.label)}
                className={`flex-1 min-w-[150px] px-3 py-2 rounded text-white text-xs font-medium transition disabled:cursor-default ${p.color} ${ring}`}
              >
                {p.display}
              </button>
            )
          })}
        </div>

        {picked && (
          <div
            className={`mt-4 rounded-lg px-4 py-3 text-sm ${
              isCorrect
                ? "bg-green-50 border border-green-300 text-green-900"
                : "bg-danger-soft border border-danger/40 text-danger"
            }`}
          >
            <p className="font-semibold mb-1">
              {isCorrect ? "✓ Correcto" : "✗ Incorrecto"} — es {displayOf(a.label)} ({a.context})
            </p>
            <p className="mb-1">{a.why}</p>
            <p className="text-xs opacity-90">{a.whyNot}</p>
            <button
              type="button"
              onClick={next}
              className="mt-3 px-4 py-1.5 rounded bg-[#111111] text-white text-xs font-medium hover:opacity-90"
            >
              {idx + 1 >= TOTAL ? "Ver resultado" : "Siguiente"}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function Result({
  correct,
  onPass,
  onRetry,
}: {
  correct: number
  onPass: () => void
  onRetry: () => void
}) {
  const passed = correct >= PASS_THRESHOLD
  return (
    <div
      className={`rounded-xl border px-6 py-8 text-center ${
        passed ? "border-green-300 bg-green-50" : "border-amber-300 bg-amber-50"
      }`}
    >
      <p className="text-3xl font-bold mb-1">
        {correct} / {TOTAL}
      </p>
      {passed ? (
        <>
          <p className="text-green-900 font-semibold mb-1">¡Aprobaste el entrenamiento!</p>
          <p className="text-sm text-green-800 mb-5">
            Alcanzaste el mínimo de {PASS_THRESHOLD}/{TOTAL}. Ya podés codificar el corpus de la
            materia.
          </p>
          <button
            type="button"
            onClick={onPass}
            className="px-6 py-2.5 rounded-lg bg-green-600 text-white font-medium hover:bg-green-700"
          >
            Empezar a codificar
          </button>
        </>
      ) : (
        <>
          <p className="text-amber-900 font-semibold mb-1">Todavía no</p>
          <p className="text-sm text-amber-800 mb-5">
            Necesitás al menos {PASS_THRESHOLD}/{TOTAL} para desbloquear la codificación. Repasá las
            anclas y reintentá.
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="px-6 py-2.5 rounded-lg bg-amber-600 text-white font-medium hover:bg-amber-700"
          >
            Reintentar
          </button>
        </>
      )}
    </div>
  )
}

// ── Enseñanza completa de los 3 ejes ────────────────────────────────────────
function Teaching({ onStart }: { onStart: () => void }) {
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-white p-6 space-y-5 text-sm leading-relaxed">
        <div>
          <h3 className="text-lg font-bold mb-1">Antes de codificar: cómo se reconoce cada eje</h3>
          <p className="text-muted">
            Vas a clasificar cada episodio en <strong>uno de tres ejes</strong>. Lo único que medís
            es <strong>cómo se apropió el alumno de la IA</strong>: no si le fue bien en el
            ejercicio, no si se portó bien. Solo cómo pensó con la herramienta.
          </p>
        </div>

        <Eje
          color="bg-green-600"
          title="Apropiación reflexiva"
          definition="Piensa, verifica y justifica — solo o colaborando con el tutor."
          forms={[
            "Lo resolvió solo, sin usar el tutor, y lo logró.",
            "Usó el tutor pero razonando: pregunta el porqué, prueba, itera, integra lo que el tutor le devuelve.",
          ]}
          tell="Hay razonamiento propio Y verificación. Construye sobre lo que recibe."
        />
        <Eje
          color="bg-warning"
          title="Apropiación superficial"
          definition="Hace algo propio, pero sin verificar críticamente ni fundamentar."
          forms={[
            "Usa el tutor de forma operativa ('dame una pista', 'qué herramienta'), sin profundizar.",
            "Lo intenta solo pero se traba y no llega.",
            "Escribe código pero no lo prueba.",
            "Se desengancha: actividad mínima, casi no labura.",
          ]}
          tell="Hay interacción o trabajo propio, pero falta la verificación crítica o la justificación."
        />
        <Eje
          color="bg-danger"
          title="Delegación pasiva"
          definition="Terceriza el trabajo o el juicio. Inversión cognitiva mínima."
          forms={[
            "Sobreusa el tutor: le pregunta todo y le hace revisar cada paso, aunque tipee su propio código. Delega el JUICIO.",
          ]}
          tell="Se apoya compulsivamente en el tutor. La plataforma marca 'sobreuso' (overuse)."
        />

        <div className="rounded-lg bg-canvas border border-border p-4">
          <p className="font-semibold mb-2">Tres reglas para tener grabadas</p>
          <ol className="list-decimal pl-5 space-y-1">
            <li>
              <strong>No usó el tutor y resolvió → reflexiva</strong> (no pasiva). No usar la IA no
              es delegar: es no necesitarla.
            </li>
            <li>
              <strong>Sobreusa el tutor → pasiva</strong>, aunque tipee su propio código. Delega el
              juicio.
            </li>
            <li>
              <strong>Sin evidencia suficiente → no clasificable.</strong> No fuerces una categoría.
            </li>
          </ol>
        </div>

        <div className="rounded-lg bg-canvas border border-border p-4">
          <p className="font-semibold mb-2">Cómo decidir en 10 segundos</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>¿Resolvió por su cuenta? → reflexiva (si lo logró) · superficial (si se trabó).</li>
            <li>¿Verificó y justificó? → reflexiva. ¿Usó la respuesta sin más? → superficial.</li>
            <li>¿Sobreusó el tutor (le terceriza el juicio)? → pasiva.</li>
          </ul>
        </div>

        <div className="rounded-lg bg-amber-50 border border-amber-300 p-4 text-amber-900">
          <p className="font-semibold mb-1">⚠️ La trampa más común</p>
          <p>
            Un alumno que escribe su código y lo prueba <em>parece</em> reflexivo. Pero si le
            pregunta TODO al tutor ('¿está bien?', '¿en qué me equivoqué?') en vez de decidir él,
            está <strong>delegando el juicio = pasiva</strong>, aunque tipee cada línea. Si hay
            sobreuso, es pasiva.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-border bg-white px-6 py-4">
        <p className="text-sm text-muted">
          Cuando lo tengas claro, hacé el entrenamiento: {TOTAL} episodios reales. Necesitás{" "}
          <strong>{PASS_THRESHOLD}/{TOTAL}</strong> para desbloquear la codificación.
        </p>
        <button
          type="button"
          onClick={onStart}
          className="shrink-0 px-6 py-2.5 rounded-lg bg-[#111111] text-white font-medium hover:opacity-90"
        >
          Empezar el entrenamiento
        </button>
      </div>
    </div>
  )
}

function Eje({
  color,
  title,
  definition,
  forms,
  tell,
}: {
  color: string
  title: string
  definition: string
  forms: string[]
  tell: string
}) {
  return (
    <div className="border-t border-border pt-4">
      <div className="flex items-center gap-2 mb-1">
        <span className={`inline-block w-3 h-3 rounded-full ${color}`} />
        <h4 className="font-semibold">{title}</h4>
      </div>
      <p className="mb-2">{definition}</p>
      <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-1">
        Formas en que aparece
      </p>
      <ul className="list-disc pl-5 space-y-0.5 mb-2">
        {forms.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <p className="text-xs text-muted">
        <strong>Cómo lo reconocés:</strong> {tell}
      </p>
    </div>
  )
}
