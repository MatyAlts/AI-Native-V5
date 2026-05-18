import { useRef, useState } from "react"
import {
  motion,
  useScroll,
  useTransform,
  useMotionValue,
  useSpring,
  type Variants,
} from "framer-motion"

/**
 * Hero — entrada visual de la landing.
 *
 * Animaciones:
 *  - Stagger entrance: eyebrow → titulo (blur reveal palabra por palabra)
 *    → subtitulo → CTAs → scroll indicator.
 *  - Parallax: el bloque entero se traslada -30% al scrollear.
 *  - Magnetic hover sobre el CTA primario (radio 120px).
 *  - Scroll indicator: dot que baja en loop.
 */

// Easing global expo-out — sensacion Apple landing.
const EXPO_OUT = [0.16, 1, 0.3, 1] as const

// Palabras que reciben color accent dentro del titulo.
const ACCENT_WORDS = new Set([
  "socratica",
  "trazabilidad",
  "cognitiva",
  "criptografica",
])

// Frase del titulo, separada por palabras para animarlas individualmente.
const TITLE_WORDS = [
  "Tutoria",
  "socratica",
  "con",
  "trazabilidad",
  "cognitiva",
  "criptografica.",
]

const containerVariants: Variants = {
  hidden: { opacity: 1 },
  visible: {
    opacity: 1,
    transition: {
      delayChildren: 0.1,
      staggerChildren: 0.08,
    },
  },
}

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.9, ease: EXPO_OUT },
  },
}

const titleContainer: Variants = {
  hidden: { opacity: 1 },
  visible: {
    opacity: 1,
    transition: { delayChildren: 0.2, staggerChildren: 0.06 },
  },
}

const wordReveal: Variants = {
  hidden: { opacity: 0, y: 18, filter: "blur(10px)" },
  visible: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 1.1, ease: EXPO_OUT },
  },
}

function stripAccentSlug(word: string): string {
  // Normaliza para comparar contra ACCENT_WORDS (sin tildes, lowercase, sin punctuation).
  return word
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[.,;:]/g, "")
}

export function Hero() {
  const sectionRef = useRef<HTMLElement | null>(null)
  const primaryRef = useRef<HTMLAnchorElement | null>(null)

  // Parallax fuerte en scroll: cuando el hero arranca a salir del viewport,
  // su contenido se traslada hacia arriba un 30%.
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  })
  const parallaxY = useTransform(scrollYProgress, [0, 1], ["0%", "-30%"])
  const parallaxOpacity = useTransform(scrollYProgress, [0, 0.8], [1, 0])

  // Magnetic hover sobre el CTA primario.
  const magneticX = useMotionValue(0)
  const magneticY = useMotionValue(0)
  const springX = useSpring(magneticX, { stiffness: 200, damping: 18 })
  const springY = useSpring(magneticY, { stiffness: 200, damping: 18 })

  const handlePrimaryMove = (event: React.MouseEvent<HTMLAnchorElement>) => {
    const node = primaryRef.current
    if (!node) return
    const rect = node.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const dx = event.clientX - cx
    const dy = event.clientY - cy
    const distance = Math.hypot(dx, dy)
    const RADIUS = 120
    if (distance > RADIUS) {
      magneticX.set(0)
      magneticY.set(0)
      return
    }
    // Mapeo suave: cuanto mas cerca, mas atraccion (max ~8px).
    const strength = 1 - distance / RADIUS
    magneticX.set(dx * 0.18 * strength)
    magneticY.set(dy * 0.18 * strength)
  }

  const handlePrimaryLeave = () => {
    magneticX.set(0)
    magneticY.set(0)
  }

  return (
    <section
      ref={sectionRef}
      id="hero"
      className="relative min-h-screen w-full overflow-hidden bg-bg"
    >
      {/* Grain sutil — SVG inline con turbulence + opacidad baja. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0 opacity-[0.04] mix-blend-multiply"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='200' height='200' filter='url(%23n)' opacity='0.6'/></svg>\")",
        }}
      />

      {/* Tag de tesis en esquina superior derecha. */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: EXPO_OUT, delay: 0.4 }}
        className="absolute right-6 top-6 z-20 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted md:right-10 md:top-10"
      >
        <PulseDot />
        <span>Tesis doctoral · UNSL · 2026</span>
      </motion.div>

      {/* Contenedor parallaxed con todo el contenido del hero. */}
      <motion.div
        style={{ y: parallaxY, opacity: parallaxOpacity }}
        className="relative z-10 flex min-h-screen w-full flex-col items-center justify-center px-6 md:px-12"
      >
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="mx-auto flex w-full max-w-6xl flex-col items-center text-center"
        >
          {/* Eyebrow. */}
          <motion.span
            variants={fadeUp}
            className="mb-8 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted"
          >
            <span className="inline-block h-px w-6 bg-border" />
            Plataforma · AI-Native N4
            <span className="inline-block h-px w-6 bg-border" />
          </motion.span>

          {/* Titulo gigante en serif, palabra por palabra con blur reveal. */}
          <motion.h1
            variants={titleContainer}
            className="font-serif font-medium leading-[0.98] tracking-[-0.025em] text-ink"
            style={{
              fontSize: "clamp(3.5rem, 8.5vw, 6rem)",
            }}
          >
            {TITLE_WORDS.map((word, idx) => {
              const slug = stripAccentSlug(word)
              const isAccent = ACCENT_WORDS.has(slug)
              return (
                <span
                  key={`${word}-${idx}`}
                  className="inline-block overflow-hidden align-baseline"
                >
                  <motion.span
                    variants={wordReveal}
                    className={
                      isAccent
                        ? "mr-[0.22em] inline-block text-accent"
                        : "mr-[0.22em] inline-block"
                    }
                  >
                    {/* Render manual de la palabra real (con tildes). */}
                    {renderRealWord(idx)}
                  </motion.span>
                </span>
              )
            })}
          </motion.h1>

          {/* Subtitulo. */}
          <motion.p
            variants={fadeUp}
            className="mt-10 max-w-2xl text-base leading-relaxed text-muted md:text-lg"
          >
            Modelo de evaluación N4 multidimensional. Cadena criptográfica
            append-only verificable. Tutor con LLM real, no scripted.
          </motion.p>

          {/* CTAs. */}
          <motion.div
            variants={fadeUp}
            className="mt-12 flex flex-col items-center gap-4 sm:flex-row sm:gap-5"
          >
            <motion.a
              ref={primaryRef}
              href="#acceso"
              onMouseMove={handlePrimaryMove}
              onMouseLeave={handlePrimaryLeave}
              style={{ x: springX, y: springY }}
              className="group relative inline-flex items-center justify-center bg-ink px-8 py-4 text-sm font-medium text-bg transition-colors duration-200 hover:bg-ink-soft"
            >
              <span className="relative z-10">Probar la plataforma</span>
              <span
                aria-hidden="true"
                className="ml-2 inline-block transition-transform duration-300 ease-out group-hover:translate-x-1"
              >
                →
              </span>
            </motion.a>

            <a
              href="#arquitectura"
              className="group inline-flex items-center justify-center border border-border bg-transparent px-8 py-4 text-sm font-medium text-ink transition-colors duration-200 hover:border-ink"
            >
              <span>Cómo funciona</span>
              <span
                aria-hidden="true"
                className="ml-2 inline-block transition-transform duration-300 ease-out group-hover:translate-x-1"
              >
                →
              </span>
            </a>
          </motion.div>
        </motion.div>

        {/* Scroll indicator anclado al bottom. */}
        <motion.div
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          transition={{ delay: 1.4, duration: 0.9, ease: EXPO_OUT }}
          className="absolute bottom-10 left-1/2 z-10 flex -translate-x-1/2 flex-col items-center gap-3"
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
            Scroll
          </span>
          <ScrollDotLine />
        </motion.div>
      </motion.div>
    </section>
  )
}

// Mapping idx → palabra real con tildes / caracteres correctos.
// El slug normalizado se usa solo para identificar accent — el render usa la versión correcta.
function renderRealWord(idx: number): string {
  const realWords = [
    "Tutoría",
    "socrática",
    "con",
    "trazabilidad",
    "cognitiva",
    "criptográfica.",
  ]
  return realWords[idx] ?? ""
}

function PulseDot() {
  return (
    <span className="relative inline-flex h-2 w-2">
      <motion.span
        className="absolute inline-flex h-full w-full rounded-full bg-accent"
        animate={{ scale: [1, 2.2], opacity: [0.5, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
      />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
    </span>
  )
}

function ScrollDotLine() {
  return (
    <div className="relative h-12 w-px overflow-hidden bg-border">
      <motion.span
        className="absolute left-1/2 top-0 h-2 w-px -translate-x-1/2 bg-ink"
        animate={{ y: [0, 48] }}
        transition={{
          duration: 2.4,
          repeat: Infinity,
          ease: [0.65, 0, 0.35, 1],
        }}
      />
    </div>
  )
}
