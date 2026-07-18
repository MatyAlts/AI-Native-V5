import { motion, useReducedMotion } from "framer-motion"
import { GraduationCap, School, Users } from "lucide-react"
import { CTA, Kicker, Wrap } from "../components/primitives"
import { EXPO_OUT } from "../lib/motion"

// El titulo se revela palabra por palabra, sobrio.
const TITLE = ["Enseñá", "a", "programar", "con", "un", "tutor", "de", "IA."]

const container = {
  hidden: {},
  visible: { transition: { delayChildren: 0.12, staggerChildren: 0.05 } },
}

// Las tres audiencias, resumidas en una linea cada una.
const AUDIENCES = [
  { icon: GraduationCap, who: "Alumnos", line: "aprenden con guía personalizada" },
  { icon: Users, who: "Docentes", line: "ven cómo progresa toda la clase" },
  { icon: School, who: "Instituciones", line: "tienen todo ordenado y seguro" },
]

export function Hero() {
  const reduced = useReducedMotion()

  const word = {
    hidden: reduced ? { opacity: 0 } : { opacity: 0, y: 18, filter: "blur(6px)" },
    visible: {
      opacity: 1,
      y: 0,
      filter: "blur(0px)",
      transition: { duration: 0.9, ease: EXPO_OUT },
    },
  }
  const line = {
    hidden: reduced ? { opacity: 0 } : { opacity: 0, y: 14 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.9, ease: EXPO_OUT } },
  }

  return (
    <section
      id="top"
      className="relative overflow-hidden pb-[clamp(56px,8vw,104px)] pt-[clamp(48px,7vw,96px)]"
    >
      <Wrap className="relative">
        <motion.div initial="hidden" animate="visible" variants={container}>
          <motion.div variants={line}>
            <Kicker>La plataforma para enseñar a programar con IA</Kicker>
          </motion.div>

          <h1 className="mt-8 max-w-[16ch] font-display text-[clamp(42px,8.5vw,104px)] font-extrabold leading-[0.98] tracking-[-0.04em] text-ink">
            {TITLE.map((w, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: TITLE es estatico y nunca reordena
              <motion.span key={`${w}-${i}`} variants={word} className="mr-[0.26em] inline-block">
                {w === "IA." ? <span className="text-celeste">{w}</span> : w}
              </motion.span>
            ))}
          </h1>

          <motion.p
            variants={line}
            className="mt-8 max-w-[56ch] text-[clamp(17px,1.9vw,22px)] leading-relaxed text-ink-soft"
          >
            Un tutor de IA acompaña a cada alumno mientras aprende, sin reemplazar al docente. El
            alumno resuelve con guía, el docente ve cómo progresa su clase y la institución mantiene
            todo ordenado y seguro.
          </motion.p>

          <motion.div variants={line} className="mt-10 flex flex-wrap items-center gap-3">
            <CTA href="#demo">Pedí una demo</CTA>
            <CTA href="#producto" variant="ghost">
              Conocé más
            </CTA>
          </motion.div>
        </motion.div>
      </Wrap>

      <Wrap className="mt-[clamp(44px,6vw,80px)]">
        <motion.ul
          className="grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3"
          initial={reduced ? { opacity: 0 } : { opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, ease: EXPO_OUT }}
        >
          {AUDIENCES.map((a) => (
            <li key={a.who} className="flex items-start gap-4 bg-paper px-6 py-6">
              <span
                className="mt-0.5 flex h-10 w-10 flex-none items-center justify-center rounded-full bg-celeste-wash text-celeste-deep"
                aria-hidden="true"
              >
                <a.icon size={20} strokeWidth={1.8} />
              </span>
              <div>
                <p className="font-display text-[17px] font-semibold text-ink">{a.who}</p>
                <p className="mt-1 text-[15px] leading-snug text-ink-soft">{a.line}</p>
              </div>
            </li>
          ))}
        </motion.ul>
      </Wrap>
    </section>
  )
}
