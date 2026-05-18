/**
 * Sección "Flujo del alumno" — recorrido en 5 pasos desde que el estudiante
 * entra a su materia hasta que recibe el diagnóstico N4 al cerrar el episodio.
 * Cada paso emite evidencia al CTR (cadena criptográfica append-only).
 *
 * Layout zigzag vertical con línea conectora central animada por scroll.
 */
import { motion } from "framer-motion"
import {
  Activity,
  BookOpen,
  Code2,
  Layers,
  MessageCircle,
} from "lucide-react"
import type { ComponentType, ReactNode, SVGProps } from "react"

const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

type Step = {
  numero: string
  titulo: string
  subtitulo: string
  body: string
  Icon: ComponentType<SVGProps<SVGSVGElement>>
  Mock: () => ReactNode
}

// ────────────────────────────────────────────────────────────────────────────
// Mocks visuales por step (cada uno con su lenguaje propio)
// ────────────────────────────────────────────────────────────────────────────

function MockMateria() {
  return (
    <div className="rounded-lg border border-border bg-bg-elevated p-6 shadow-sm">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-soft">
        Programación I
      </p>
      <p className="mt-3 font-serif text-xl tracking-tight text-ink">
        Algoritmos y Estructuras
      </p>
      <div className="mt-5 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-accent" />
        <p className="font-mono text-xs text-muted">Comisión A · Mañana</p>
      </div>
      <p className="mt-1 font-mono text-[11px] text-muted-soft">
        2026 · 1er cuatrimestre
      </p>
    </div>
  )
}

function MockUnidades() {
  const unidades = ["Secuenciales", "Condicionales", "Iterativas"]
  return (
    <div className="space-y-3">
      {unidades.map((u, i) => (
        <div
          key={u}
          className="rounded-lg border border-border bg-bg-elevated px-5 py-4"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm text-ink">{u}</p>
            <span className="font-mono text-[11px] text-muted-soft">
              {i === 0 ? "5 TPs" : i === 1 ? "4 TPs" : "6 TPs"}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

function MockEditor() {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-[#0A0A0A] shadow-md">
      <div className="flex items-center gap-1.5 border-b border-white/5 bg-[#141414] px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-[#FF5F57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#FEBC2E]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28C840]" />
        <span className="ml-3 font-mono text-[10px] text-white/40">
          tp_03.py
        </span>
      </div>
      <pre className="font-mono text-[11px] leading-relaxed text-white/85 px-5 py-4">
        <span className="text-[#C586C0]">def</span>{" "}
        <span className="text-[#DCDCAA]">factorial</span>(n):{"\n"}
        {"    "}
        <span className="text-[#C586C0]">if</span> n {"<="} 1:{"\n"}
        {"        "}
        <span className="text-[#C586C0]">return</span> 1{"\n"}
        {"    "}
        <span className="text-[#C586C0]">return</span> n * factorial(n - 1)
      </pre>
      <div className="flex items-center justify-between border-t border-white/5 bg-[#141414] px-4 py-2.5">
        <span className="font-mono text-[10px] text-white/40">Pyodide</span>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded bg-accent px-3 py-1 font-mono text-[11px] text-white"
        >
          <span>▶</span>
          <span>Ejecutar</span>
        </button>
      </div>
    </div>
  )
}

function MockTutorChat() {
  return (
    <div className="space-y-3">
      <div className="ml-auto max-w-[80%] rounded-2xl rounded-tr-sm bg-ink px-5 py-3 text-sm text-bg shadow-sm">
        Profe, no entiendo por qué mi factorial devuelve None.
      </div>
      <div className="max-w-[88%] rounded-2xl rounded-tl-sm border border-border bg-bg-elevated px-5 py-3.5 text-sm leading-relaxed text-ink shadow-sm">
        <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-accent">
          Tutor
        </p>
        <p className="mt-2">
          Antes de cambiar nada, ¿qué devuelve tu función cuando el parámetro
          es 1? Recorré línea por línea y contame.
        </p>
      </div>
    </div>
  )
}

function MockDiagnostico() {
  const bars = [
    { label: "CT", value: 0.72 },
    { label: "CCD_mean", value: 0.65 },
    { label: "CCD_orphan", value: 0.18 },
    { label: "CII_stab", value: 0.81 },
    { label: "CII_evol", value: 0.54 },
  ]
  return (
    <div className="rounded-lg border border-border bg-bg-elevated p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-soft">
          Diagnóstico N4
        </p>
        <span className="rounded-full bg-accent-soft px-3 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em] text-accent">
          Autónomo
        </span>
      </div>
      <div className="mt-5 space-y-2.5">
        {bars.map((b, i) => (
          <div key={b.label} className="flex items-center gap-3">
            <span className="w-20 font-mono text-[10px] text-muted">
              {b.label}
            </span>
            <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-border-soft">
              <motion.div
                className="absolute inset-y-0 left-0 bg-accent"
                initial={{ width: 0 }}
                whileInView={{ width: `${b.value * 100}%` }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{
                  duration: 0.9,
                  ease: EASE_OUT_EXPO,
                  delay: 0.4 + i * 0.08,
                }}
              />
            </div>
            <span className="w-10 text-right font-mono text-[10px] text-ink">
              {b.value.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────

const STEPS: ReadonlyArray<Step> = [
  {
    numero: "01",
    titulo: "Entra a su materia",
    subtitulo: "Vista de Mis Materias",
    body: "El alumno ve sus inscripciones activas. La lista refleja /api/v1/materias/mias filtrado por tenant aislado.",
    Icon: BookOpen,
    Mock: MockMateria,
  },
  {
    numero: "02",
    titulo: "Elige una unidad temática",
    subtitulo: "Materia → Unidades → TP",
    body: "Las unidades agrupan TPs por tema (Secuenciales, Condicionales, etc). El alumno elige una y ve los TPs disponibles.",
    Icon: Layers,
    Mock: MockUnidades,
  },
  {
    numero: "03",
    titulo: "Resuelve con Pyodide",
    subtitulo: "Editor Monaco · Pyodide en navegador",
    body: "Python ejecuta en el browser, sin servidor. Cada ejecución emite codigo_ejecutado al CTR firmado SHA-256.",
    Icon: Code2,
    Mock: MockEditor,
  },
  {
    numero: "04",
    titulo: "Charla con el tutor",
    subtitulo: "Tutor socrático con LLM real",
    body: "Mistral, OpenAI o Anthropic (según BYOK del tenant). El tutor NO da la respuesta. Pregunta, contradice, fuerza al alumno a verbalizar su modelo mental.",
    Icon: MessageCircle,
    Mock: MockTutorChat,
  },
  {
    numero: "05",
    titulo: "Cierra y recibe diagnóstico N4",
    subtitulo: "Las 5 coherencias separadas",
    body: "Al cerrar el episodio, el clasificador procesa todos los eventos del CTR y emite las 5 coherencias + diagnóstico cualitativo (autónomo, superficial, delegación pasiva, etc).",
    Icon: Activity,
    Mock: MockDiagnostico,
  },
]

export function FlujoAlumno() {
  return (
    <section className="bg-bg py-32">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
          className="mb-20 max-w-3xl"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            El flujo del alumno
          </p>
          <h2 className="mt-4 font-serif text-[56px] leading-[1.05] tracking-tight text-ink">
            De la duda al diagnóstico.
          </h2>
          <p className="mt-6 text-lg text-muted">
            Cinco pasos. Cada uno graba evidencia al CTR.
          </p>
        </motion.div>

        <div className="relative">
          {/* Línea conectora central, dibujada path-drawing al entrar al viewport */}
          <motion.span
            aria-hidden="true"
            initial={{ scaleY: 0 }}
            whileInView={{ scaleY: 1 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 2, ease: EASE_OUT_EXPO }}
            style={{ transformOrigin: "top" }}
            className="absolute left-1/2 top-0 hidden h-full w-px -translate-x-1/2 bg-border md:block"
          />

          <div className="space-y-24">
            {STEPS.map((step, index) => {
              const isLeft = index % 2 === 0
              const isLast = index === STEPS.length - 1
              const { Icon, Mock } = step

              return (
                <div
                  key={step.numero}
                  className="relative grid grid-cols-1 items-center gap-10 md:grid-cols-[1fr_auto_1fr] md:gap-12"
                >
                  {/* Bloque texto */}
                  <motion.div
                    initial={{
                      opacity: 0,
                      x: isLeft ? -48 : 48,
                    }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, margin: "-100px" }}
                    transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
                    className={`${
                      isLeft
                        ? "md:col-start-1 md:text-right"
                        : "md:col-start-3 md:order-3 md:text-left"
                    }`}
                  >
                    <div
                      className={`inline-flex items-center gap-3 ${
                        isLeft ? "md:flex-row-reverse" : ""
                      }`}
                    >
                      <Icon
                        width={20}
                        height={20}
                        strokeWidth={1.5}
                        className="text-accent"
                      />
                      <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
                        Paso {step.numero}
                      </p>
                    </div>
                    <h3
                      className={`mt-4 font-serif tracking-tight text-ink ${
                        isLast ? "text-[40px] leading-[1.1]" : "text-[32px] leading-tight"
                      }`}
                    >
                      {step.titulo}
                    </h3>
                    <p className="mt-3 font-mono text-[12px] uppercase tracking-[0.12em] text-accent">
                      {step.subtitulo}
                    </p>
                    <p className="mt-5 text-base leading-relaxed text-muted">
                      {step.body}
                    </p>
                  </motion.div>

                  {/* Nodo central sobre la línea */}
                  <div className="relative hidden md:col-start-2 md:flex md:items-center md:justify-center">
                    <motion.div
                      initial={{ scale: 0, opacity: 0 }}
                      whileInView={{ scale: 1, opacity: 1 }}
                      viewport={{ once: true, margin: "-100px" }}
                      transition={{
                        duration: 0.6,
                        ease: EASE_OUT_EXPO,
                        delay: 0.2,
                      }}
                      className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-bg-elevated font-mono text-xs text-ink shadow-sm"
                    >
                      {step.numero}
                    </motion.div>
                  </div>

                  {/* Mock visual */}
                  <motion.div
                    initial={{
                      opacity: 0,
                      x: isLeft ? 48 : -48,
                    }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, margin: "-100px" }}
                    transition={{
                      duration: 0.8,
                      ease: EASE_OUT_EXPO,
                      delay: 0.15,
                    }}
                    whileHover={{ y: -2 }}
                    className={`${
                      isLeft
                        ? "md:col-start-3"
                        : "md:col-start-1 md:order-1"
                    }`}
                  >
                    <Mock />
                  </motion.div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
