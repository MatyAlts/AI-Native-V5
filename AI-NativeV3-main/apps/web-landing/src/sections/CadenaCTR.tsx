/**
 * Sección "Cadena CTR" — la parte más visual de la landing.
 *
 * Anima la cadena criptográfica del Cognitive Traceability Record:
 * 7 eventos del alumno aparecen secuencialmente, cada uno se "encadena"
 * al anterior con `self_hash` (typewriter) y `chain_hash` que referencia
 * al previo. El primero usa `GENESIS_HASH = "0" * 64`.
 *
 * Incluye un toggle "Simular tampering" que modifica el self_hash del
 * seq=3 con efecto glitch y rompe las flechas posteriores en rojo,
 * ilustrando la propiedad append-only del CTR (ver CLAUDE.md "Propiedades
 * críticas — CTR append-only", ADR-010).
 *
 * Datos exhibidos (hashes ilustrativos formato hex de 8 chars, no reales).
 */
import { motion, AnimatePresence } from "framer-motion"
import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, RotateCcw } from "lucide-react"

type Block = {
  seq: number
  eventType: string
  selfHash: string
  chainHashLeft: string
  chainHashRight: string
}

const BLOCKS: ReadonlyArray<Block> = [
  {
    seq: 0,
    eventType: "episodio_abierto",
    selfHash: "bf6ebb05",
    chainHashLeft: "GENESIS",
    chainHashRight: "0000…",
  },
  {
    seq: 1,
    eventType: "lectura_enunciado",
    selfHash: "a3b127cc",
    chainHashLeft: "de4f8a91",
    chainHashRight: "a3b1+bf6e",
  },
  {
    seq: 2,
    eventType: "edicion_codigo",
    selfHash: "7f2c9e80",
    chainHashLeft: "2c8e1f04",
    chainHashRight: "7f2c+a3b1",
  },
  {
    seq: 3,
    eventType: "codigo_ejecutado",
    selfHash: "d9e0145a",
    chainHashLeft: "8b5d7c1e",
    chainHashRight: "d9e0+7f2c",
  },
  {
    seq: 4,
    eventType: "prompt_enviado",
    selfHash: "4e2a90b3",
    chainHashLeft: "f1a3e6d7",
    chainHashRight: "4e2a+d9e0",
  },
  {
    seq: 5,
    eventType: "tutor_respondio",
    selfHash: "c1f88e22",
    chainHashLeft: "9e4c2b85",
    chainHashRight: "c1f8+4e2a",
  },
  {
    seq: 6,
    eventType: "episodio_cerrado",
    selfHash: "5d3b91f7",
    chainHashLeft: "61aef284",
    chainHashRight: "5d3b+c1f8",
  },
]

const TAMPERED_HASH = "deadbeef"
const TAMPERED_SEQ = 3

const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

/**
 * Typewriter — revela `text` char por char con cadencia de `delayMs` ms.
 * Sólo arranca cuando `start` pasa a true. No usa libs externas.
 */
function Typewriter({
  text,
  start,
  delayMs = 30,
  className,
}: {
  text: string
  start: boolean
  delayMs?: number
  className?: string
}) {
  const [revealed, setRevealed] = useState("")

  useEffect(() => {
    if (!start) {
      setRevealed("")
      return
    }
    let i = 0
    setRevealed("")
    const id = window.setInterval(() => {
      i += 1
      setRevealed(text.slice(0, i))
      if (i >= text.length) {
        window.clearInterval(id)
      }
    }, delayMs)
    return () => window.clearInterval(id)
  }, [text, start, delayMs])

  return (
    <span className={className}>
      {revealed}
      {start && revealed.length < text.length ? (
        <span className="ml-px inline-block w-[1px] animate-pulse bg-current align-middle">
          &nbsp;
        </span>
      ) : null}
    </span>
  )
}

function HashLine({
  label,
  hash,
  start,
  tampered = false,
}: {
  label: string
  hash: string
  start: boolean
  tampered?: boolean
}) {
  // Particion visual: primeros 4 chars accent, resto muted (juego visual).
  const head = hash.slice(0, 4)
  const tail = hash.slice(4)
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-soft">
        {label}
      </span>
      <span
        className={`font-mono text-[12px] leading-none ${
          tampered ? "text-[#C0392B]" : ""
        }`}
      >
        <Typewriter
          text={head}
          start={start}
          delayMs={30}
          className={tampered ? "text-[#C0392B]" : "text-accent"}
        />
        <Typewriter
          text={tail}
          start={start}
          delayMs={30}
          className={tampered ? "text-[#C0392B]" : "text-muted"}
        />
      </span>
    </div>
  )
}

function BlockCard({
  block,
  index,
  step,
  tampered,
}: {
  block: Block
  index: number
  step: number
  tampered: boolean
}) {
  const isVisible = step >= index
  const isTampered = tampered && block.seq === TAMPERED_SEQ
  const isBroken = tampered && block.seq > TAMPERED_SEQ

  const effectiveSelf = isTampered ? TAMPERED_HASH : block.selfHash

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={
        isVisible
          ? {
              opacity: 1,
              scale: 1,
              x: isTampered ? [0, -3, 3, -2, 2, 0] : 0,
            }
          : { opacity: 0, scale: 0.95 }
      }
      transition={{
        opacity: { duration: 0.2, ease: EASE_OUT_EXPO },
        scale: { duration: 0.2, ease: EASE_OUT_EXPO },
        x: { duration: 0.4, ease: "easeInOut" },
      }}
      className={`relative flex h-[180px] w-[160px] shrink-0 flex-col justify-between border bg-bg-elevated p-3 ${
        isTampered
          ? "border-[#C0392B] shadow-[0_0_0_1px_#C0392B33]"
          : isBroken
            ? "border-[#C0392B]/40"
            : "border-border shadow-[0_1px_2px_rgba(10,10,10,0.04)]"
      }`}
    >
      {/* Top: seq + event_type */}
      <div className="flex flex-col gap-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-soft">
          seq={block.seq}
        </span>
        <span className="font-sans text-[12px] font-semibold leading-tight text-ink">
          {block.eventType}
        </span>
      </div>

      {/* Middle: self_hash typewriter */}
      <HashLine
        label="self_hash"
        hash={effectiveSelf}
        start={isVisible}
        tampered={isTampered}
      />

      {/* Bottom: chain_hash + composicion */}
      <div className="flex flex-col gap-1">
        <HashLine
          label="chain_hash"
          hash={block.chainHashLeft}
          start={isVisible}
        />
        <span className="font-mono text-[9px] tracking-tight text-muted-soft">
          {block.chainHashRight}
        </span>
      </div>

      {/* Glitch overlay para tampering */}
      <AnimatePresence>
        {isTampered ? (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.4, 0, 0.3, 0] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6, times: [0, 0.2, 0.4, 0.6, 1] }}
            className="pointer-events-none absolute inset-0 bg-[#C0392B]/10"
            aria-hidden
          />
        ) : null}
      </AnimatePresence>
    </motion.div>
  )
}

function Arrow({
  visible,
  broken,
}: {
  visible: boolean
  broken: boolean
}) {
  const color = broken ? "#C0392B" : "#A3A3A3"
  return (
    <svg
      viewBox="0 0 40 10"
      width={40}
      height={10}
      className="shrink-0"
      aria-hidden
    >
      <defs>
        <marker
          id={`ctr-arrow-${broken ? "broken" : "ok"}`}
          markerWidth={6}
          markerHeight={6}
          refX={5}
          refY={3}
          orient="auto"
        >
          <path d="M0,0 L6,3 L0,6 z" fill={color} />
        </marker>
      </defs>
      <motion.line
        x1={0}
        y1={5}
        x2={34}
        y2={5}
        stroke={color}
        strokeWidth={1.2}
        strokeDasharray={broken ? "3 3" : "0"}
        markerEnd={`url(#ctr-arrow-${broken ? "broken" : "ok"})`}
        initial={{ pathLength: 0, opacity: 0 }}
        animate={
          visible
            ? { pathLength: 1, opacity: 1 }
            : { pathLength: 0, opacity: 0 }
        }
        transition={{ duration: 0.3, ease: EASE_OUT_EXPO }}
      />
    </svg>
  )
}

export function CadenaCTR() {
  // Stagger: step 0 = nada; step N = bloques 0..N-1 visibles. Total = BLOCKS.length.
  const [step, setStep] = useState(0)
  const [tampered, setTampered] = useState(false)

  // Loop infinito: arranca al entrar al viewport, reinicia cada 8s.
  const [inView, setInView] = useState(false)
  useEffect(() => {
    if (!inView) return
    let current = 0
    setStep(0)
    const tick = window.setInterval(() => {
      current += 1
      if (current > BLOCKS.length) {
        current = 0
        setStep(0)
        return
      }
      setStep(current)
    }, 400)
    return () => window.clearInterval(tick)
  }, [inView])

  // Reset tampering cuando se reinicia el ciclo
  useEffect(() => {
    if (step === 0) {
      setTampered(false)
    }
  }, [step])

  const allVisible = step >= BLOCKS.length

  const gridPattern = useMemo(
    () =>
      "linear-gradient(to right, #E5E5E5 1px, transparent 1px), linear-gradient(to bottom, #E5E5E5 1px, transparent 1px)",
    [],
  )

  return (
    <section className="relative bg-bg-elevated py-40">
      {/* Grid pattern sutil de fondo */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage: gridPattern,
          backgroundSize: "48px 48px",
          maskImage:
            "radial-gradient(ellipse at center, black 30%, transparent 75%)",
          WebkitMaskImage:
            "radial-gradient(ellipse at center, black 30%, transparent 75%)",
        }}
      />

      <div className="relative mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          onViewportEnter={() => setInView(true)}
          transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
          className="mb-20 max-w-3xl"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            Trazabilidad criptografica
          </p>
          <h2 className="mt-4 font-serif text-[64px] leading-[1.02] tracking-tight text-ink">
            Cada accion del alumno firma a la anterior.
          </h2>
          <p className="mt-6 text-lg text-muted">
            Cadena SHA-256 append-only. Tampering detectable al evento exacto.
            Verificable on-demand.
          </p>
        </motion.div>

        {/* Cadena animada */}
        <div className="overflow-x-auto pb-4">
          <div className="flex min-w-max items-center justify-start gap-0 px-2 py-8">
            {BLOCKS.map((block, index) => {
              const isLast = index === BLOCKS.length - 1
              const arrowVisible = step > index
              const arrowBroken = tampered && index >= TAMPERED_SEQ
              return (
                <div key={block.seq} className="flex items-center">
                  <BlockCard
                    block={block}
                    index={index}
                    step={step}
                    tampered={tampered}
                  />
                  {!isLast ? (
                    <div className="px-2">
                      <Arrow visible={arrowVisible} broken={arrowBroken} />
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>

        {/* Controles tampering */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: allVisible ? 1 : 0.4 }}
          transition={{ duration: 0.4, ease: EASE_OUT_EXPO }}
          className="mt-10 flex flex-col items-start gap-4"
        >
          <div className="flex flex-wrap items-center gap-3">
            {!tampered ? (
              <button
                type="button"
                onClick={() => setTampered(true)}
                disabled={!allVisible}
                className="inline-flex items-center gap-2 border border-border bg-bg-elevated px-4 py-2 font-mono text-[11px] uppercase tracking-[0.15em] text-ink-soft transition-colors duration-200 hover:border-ink disabled:cursor-not-allowed disabled:opacity-50"
              >
                <AlertTriangle width={14} height={14} strokeWidth={1.6} />
                Simular tampering en seq=3
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setTampered(false)}
                className="inline-flex items-center gap-2 border border-border bg-bg-elevated px-4 py-2 font-mono text-[11px] uppercase tracking-[0.15em] text-ink-soft transition-colors duration-200 hover:border-ink"
              >
                <RotateCcw width={14} height={14} strokeWidth={1.6} />
                Restaurar cadena
              </button>
            )}

            <AnimatePresence>
              {tampered ? (
                <motion.span
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -8 }}
                  transition={{ duration: 0.3, ease: EASE_OUT_EXPO }}
                  className="inline-flex items-center gap-2 font-mono text-[11px] text-[#C0392B]"
                >
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#C0392B]" />
                  Cadena rota en seq=3 · recomputado no coincide con persistido
                </motion.span>
              ) : null}
            </AnimatePresence>
          </div>

          <p className="max-w-2xl text-sm leading-relaxed text-muted">
            Modificar un evento historico cambia su <span className="font-mono text-[12px] text-ink-soft">self_hash</span>, y todos los{" "}
            <span className="font-mono text-[12px] text-ink-soft">chain_hash</span> posteriores dejan de validar. La cadena no se puede reescribir sin
            que el verificador lo detecte.
          </p>
        </motion.div>
      </div>
    </section>
  )
}
