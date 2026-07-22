import { useState } from "react"
import { EpisodeProcessTrace, PROFILES } from "./interraterShared"

interface Props {
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
    whyNot:
      "NO superficial: hay verbalización, verificación propia y justificación, no solo usar la respuesta.",
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

  if (phase === "teaching") return <Teaching onStart={start} getToken={getToken} />
  if (phase === "result") return <Result correct={correct} onPass={onPass} onRetry={start} />

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
const TONE: Record<string, { dot: string; border: string; bg: string; text: string }> = {
  green: {
    dot: "bg-green-600",
    border: "border-green-300",
    bg: "bg-green-50",
    text: "text-green-900",
  },
  amber: {
    dot: "bg-amber-500",
    border: "border-amber-300",
    bg: "bg-amber-50",
    text: "text-amber-900",
  },
  red: { dot: "bg-red-600", border: "border-red-300", bg: "bg-red-50", text: "text-red-900" },
}

function Teaching({
  onStart,
  getToken,
}: {
  onStart: () => void
  getToken: () => Promise<string | null>
}) {
  return (
    <div className="space-y-6 text-sm leading-relaxed">
      {/* Portada */}
      <section className="rounded-xl border border-border bg-white p-6 space-y-3">
        <h3 className="text-xl font-bold">Cómo reconocer los 3 tipos de alumno</h3>
        <p className="text-muted">
          Leé esto tranquilo antes de empezar. Te enseña a mirar <strong>cómo pensó</strong> cada
          alumno mientras hacía el ejercicio con la IA. Después hacés una práctica corta con 7
          ejemplos reales.
        </p>
        <div className="rounded-lg bg-canvas border border-border p-4">
          <p className="font-semibold mb-1">🎯 La regla de oro</p>
          <p>
            No mires <strong>si le fue bien</strong> en el ejercicio. No mires{" "}
            <strong>si se portó bien</strong>. Mirá una sola cosa: <strong>cómo pensó.</strong>
          </p>
          <p className="text-muted mt-2">
            Es como corregir un examen de matemática: no le bajás la nota de mate porque se copió en
            geografía. Son cosas distintas. Acá te importa solo cómo razonó con la herramienta.
          </p>
        </div>
      </section>

      {/* Los 3 tipos */}
      <section className="space-y-3">
        <h3 className="text-lg font-bold">Los 3 tipos, en una frase</h3>
        <TipoCard
          tone="green"
          emoji="🟢"
          titulo="Reflexivo"
          frase="Piensa, prueba y entiende lo que hace."
          detalle="El que razona: se pregunta por qué, prueba su código, y si le preguntás después sabe explicar qué hizo. Puede lograrlo solo o ayudándose con la IA — lo importante es que la cabeza la pone él."
        />
        <TipoCard
          tone="amber"
          emoji="🟡"
          titulo="Superficial"
          frase="Hace las cosas, pero sin pensarlas mucho."
          detalle="Avanza, usa la IA o trabaja solo, pero no se detiene a verificar ni a entender el porqué. 'Anduvo y listo'. Es el más común de los tres."
        />
        <TipoCard
          tone="red"
          emoji="🔴"
          titulo="Pasivo"
          frase="Quiere que se lo resuelvan; no pone la cabeza."
          detalle="Usa a la IA como una máquina de respuestas: le tira el error y espera la solución, o le hace revisar TODO sin decidir nada él. Aunque tipee el código, el que piensa es el tutor."
        />
      </section>

      {/* Las 5 cosas */}
      <section className="rounded-xl border border-border bg-white p-6 space-y-4">
        <div>
          <h3 className="text-lg font-bold">Las 5 cosas que mirás en cada alumno</h3>
          <p className="text-muted">
            Fijate en estas 5 cosas y vas a saber qué tipo es. (Verde = reflexivo, amarillo =
            superficial, rojo = pasivo.)
          </p>
        </div>
        <Mira
          n="1"
          q="¿Cómo le pregunta a la IA?"
          reflex="Pregunta para entender: '¿por qué da error?', 'qué pasa si…'."
          sup="Pide cosas operativas: 'dame una pista', 'corregime', 'qué herramienta uso'."
          pas="Le tira el error pelado y espera la respuesta servida; o pregunta de a una palabra ('¿en qué línea?', 'int?')."
        />
        <Mira
          n="2"
          q="¿Hace algo con lo que le responden?"
          reflex="Usa la respuesta para mejorar, cambia su enfoque."
          sup="La usa tal cual, sin darle muchas vueltas."
          pas="La ignora, o repite el mismo error sin conectar nada."
        />
        <Mira
          n="3"
          q="¿Prueba su código?"
          reflex="Lo corre, mira qué pasó, lo arregla, vuelve a probar."
          sup="Lo corre pero no profundiza; o directamente no lo prueba."
          pas="No prueba, o tira el código a ver si pega (fuerza bruta), sin entender."
        />
        <Mira
          n="4"
          q="¿Explica por qué hace las cosas?"
          reflex="Dice el porqué de cada decisión."
          sup="Cuenta qué hizo, pero no por qué."
          pas="No explica; respuestas de una palabra."
        />
        <Mira
          n="5"
          q="Si le preguntás después, ¿sabe qué hizo?"
          reflex="Reconstruye su razonamiento, con sentido."
          sup="Cuenta los pasos, pero no los fundamentos."
          pas="No puede, o repite lo que le dijo la IA."
        />
        <p className="text-xs text-muted border-t border-border pt-3">
          <strong>El atajo:</strong> reflexivo = <strong>prueba (3) Y explica (4-5)</strong>, las
          dos cosas. Si falta una, es superficial. Si le terceriza todo a la IA, es pasivo.
        </p>
      </section>

      {/* Ejemplos reales */}
      <section className="space-y-3">
        <h3 className="text-lg font-bold">Cómo se ve cada tipo, con alumnos de verdad</h3>
        <p className="text-muted text-xs">
          Episodios reales. Tocá "Ver el proceso" para mirar lo que hizo el alumno paso a paso.
        </p>
        <Ejemplo
          tone="green"
          tipo="Reflexivo · lo hizo solo"
          episodeId="02205295-67ab-45d5-a07e-22be5585cf2a"
          getToken={getToken}
          resumen="No le habló al tutor ni una vez y resolvió el ejercicio. El que la rema solo y le sale, es reflexivo — no necesitó ayuda."
        />
        <Ejemplo
          tone="green"
          tipo="Reflexivo · colabora bien con el tutor"
          episodeId="a8150302-988b-4313-921d-49c672301b59"
          getToken={getToken}
          resumen="Usó el tutor pero pensando: explica qué hace su código, lo ejecuta dos veces para verificar, y justifica sus decisiones."
          frases={[
            "esta escrito en ingles open, basicamente abrir el archivo",
            "lo acabo de ejecutar dos veces y termina exactamente igual",
            "usaria 'a' porque agrega sin borrar lo que habia antes, no?",
          ]}
        />
        <Ejemplo
          tone="amber"
          tipo="Superficial · usa el tutor sin profundizar"
          episodeId="2b083646-c873-4323-8bd9-cd674273fee8"
          getToken={getToken}
          resumen="Una pregunta práctica, usó la respuesta y siguió. No verificó ni explicó nada."
          frases={["que herramienta me das para poder redondear"]}
        />
        <Ejemplo
          tone="amber"
          tipo="Superficial · lo intentó solo pero se trabó"
          episodeId="06ddbc14-d1f1-42cf-a128-201dce7d9c2c"
          getToken={getToken}
          resumen="Sin tutor, peleó el ejercicio por su cuenta pero quedó a medias (lo corrió varias veces sin lograrlo)."
        />
        <Ejemplo
          tone="red"
          tipo="Pasivo · sobreusa el tutor (¡la trampa!)"
          episodeId="0a3d4388-c4e1-4333-b495-7e7e889d48dd"
          getToken={getToken}
          resumen="Escribió su código, sí, PERO le pregunta TODO al tutor y le hace revisar cada paso. El que decide si está bien es el tutor, no él."
          frases={[
            "tu puedes ver el codigo?",
            "en que me equivoque?",
            "pero mira el codigo por vos mismo",
          ]}
        />
      </section>

      {/* Fronteras */}
      <section className="rounded-xl border border-amber-300 bg-amber-50 p-6 space-y-3">
        <h3 className="text-lg font-bold text-amber-900">
          Cuándo dudás entre dos (lo más difícil)
        </h3>
        <Duda
          titulo="“Hizo cosas pero no sé si pensó” — ¿superficial o reflexivo?"
          regla="Preguntate: ¿probó su código Y explicó el porqué? Las DOS = reflexivo. Si falta una de las dos = superficial. Esta es la frontera donde más se confunde la gente."
        />
        <Duda
          titulo="“Le preguntó un montón a la IA” — ¿colabora o delega?"
          regla="Si le terceriza el JUICIO (le hace revisar todo, le pregunta si está bien a cada paso, sobreuso) = pasivo, aunque escriba su propio código. Si pregunta para ENTENDER y después decide él = reflexivo."
        />
        <Duda
          titulo="“No usó la IA para nada”"
          regla="¡Ojo, este engaña! Si NO usó el tutor pero resolvió → es REFLEXIVO (no pasivo). No usar la IA no es delegar, es no necesitarla. Si lo intentó solo pero no llegó → superficial."
        />
        <Duda
          titulo="“Casi no hay nada para mirar”"
          regla="Si el episodio es muy cortito o no hay evidencia, marcá 'no clasificable'. No lo metas a la fuerza en una caja."
        />
        <Duda
          titulo="“Parece que no hizo nada, pero después explica perfecto”"
          regla="Algunos piensan en la cabeza y dejan poco rastro. Si después explica con sentido qué hizo, esa explicación puede subirlo de categoría. No lo castigues por dejar poco rastro."
        />
      </section>

      {/* La trampa */}
      <section className="rounded-xl border border-red-300 bg-red-50 p-6 text-red-900">
        <h3 className="font-bold mb-1">⚠️ La trampa más común</h3>
        <p>
          Un alumno que escribe su código y lo prueba <em>parece</em> reflexivo. Pero si le pregunta
          TODO al tutor ('¿está bien?', '¿en qué me equivoqué?', 'mirá por vos mismo') en vez de
          decidir él, está <strong>delegando el juicio = pasivo</strong>, aunque tipee cada línea.{" "}
          <strong>Si ves que sobreusa al tutor, es pasivo</strong> — no te dejes engañar por el
          "parece que piensa".
        </p>
      </section>

      {/* Decidir rápido */}
      <section className="rounded-xl border border-border bg-white p-6 space-y-2">
        <h3 className="text-lg font-bold">Para decidir rápido: 3 preguntas en orden</h3>
        <ol className="list-decimal pl-5 space-y-1">
          <li>
            ¿Resolvió por su cuenta? → si lo logró, <strong>reflexivo</strong>; si se trabó,{" "}
            <strong>superficial</strong>.
          </li>
          <li>
            ¿Probó (verificó) Y explicó el porqué? → las dos, <strong>reflexivo</strong>; solo usó
            la respuesta, <strong>superficial</strong>.
          </li>
          <li>
            ¿Le terceriza todo a la IA (sobreuso)? → <strong>pasivo</strong>.
          </li>
        </ol>
      </section>

      {/* CTA */}
      <div className="flex items-center justify-between rounded-xl border border-border bg-white px-6 py-4">
        <p className="text-sm text-muted">
          Cuando lo tengas claro, hacé la práctica: {TOTAL} ejemplos reales. Necesitás{" "}
          <strong>
            {PASS_THRESHOLD} de {TOTAL}
          </strong>{" "}
          para empezar a codificar.
        </p>
        <button
          type="button"
          onClick={onStart}
          className="shrink-0 px-6 py-2.5 rounded-lg bg-[#111111] text-white font-medium hover:opacity-90"
        >
          Empezar la práctica
        </button>
      </div>
    </div>
  )
}

function TipoCard({
  tone,
  emoji,
  titulo,
  frase,
  detalle,
}: {
  tone: string
  emoji: string
  titulo: string
  frase: string
  detalle: string
}) {
  const t = TONE[tone] ?? TONE.green
  return (
    <div className={`rounded-xl border ${t?.border} ${t?.bg} p-4`}>
      <p className={`font-bold ${t?.text}`}>
        {emoji} {titulo} — <span className="font-semibold">{frase}</span>
      </p>
      <p className={`mt-1 ${t?.text} opacity-90`}>{detalle}</p>
    </div>
  )
}

function Mira({
  n,
  q,
  reflex,
  sup,
  pas,
}: {
  n: string
  q: string
  reflex: string
  sup: string
  pas: string
}) {
  return (
    <div className="border-t border-border pt-3">
      <p className="font-semibold mb-1.5">
        {n}. {q}
      </p>
      <div className="grid gap-1.5 sm:grid-cols-3 text-xs">
        <p className="rounded bg-green-50 border border-green-200 px-2 py-1.5 text-green-900">
          <strong>🟢 </strong>
          {reflex}
        </p>
        <p className="rounded bg-amber-50 border border-amber-200 px-2 py-1.5 text-amber-900">
          <strong>🟡 </strong>
          {sup}
        </p>
        <p className="rounded bg-red-50 border border-red-200 px-2 py-1.5 text-red-900">
          <strong>🔴 </strong>
          {pas}
        </p>
      </div>
    </div>
  )
}

function Ejemplo({
  tone,
  tipo,
  episodeId,
  getToken,
  resumen,
  frases,
}: {
  tone: string
  tipo: string
  episodeId: string
  getToken: () => Promise<string | null>
  resumen: string
  frases?: string[]
}) {
  const [open, setOpen] = useState(false)
  const t = TONE[tone] ?? TONE.green
  return (
    <div className={`rounded-xl border ${t?.border} bg-white p-4`}>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${t?.dot}`} />
        <p className="font-semibold">{tipo}</p>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="ml-auto px-3 py-1 text-xs border border-border rounded hover:bg-canvas"
        >
          {open ? "Ocultar proceso" : "Ver el proceso"}
        </button>
      </div>
      <p className="mt-2 text-muted">{resumen}</p>
      {frases && frases.length > 0 && (
        <ul className="mt-2 space-y-1">
          {frases.map((f) => (
            <li
              key={f}
              className="text-xs italic text-body bg-canvas border border-border rounded px-2 py-1"
            >
              “{f}”
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="mt-3">
          <EpisodeProcessTrace episodeId={episodeId} getToken={getToken} />
        </div>
      )}
    </div>
  )
}

function Duda({ titulo, regla }: { titulo: string; regla: string }) {
  return (
    <div className="rounded-lg bg-white border border-amber-200 p-3">
      <p className="font-semibold text-amber-900">{titulo}</p>
      <p className="text-amber-900 opacity-90 mt-0.5">{regla}</p>
    </div>
  )
}
