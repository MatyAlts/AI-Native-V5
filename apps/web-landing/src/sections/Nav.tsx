import { motion, useReducedMotion } from "framer-motion"
import { Wrap } from "../components/primitives"

const LINKS = [
  { href: "#producto", label: "Qué es" },
  { href: "#alumno", label: "Para alumnos" },
  { href: "#docente", label: "Para docentes" },
  { href: "#institucion", label: "Para instituciones" },
]

/** Barra superior slim, sticky. Marca a la izquierda, nav + CTA a la derecha. */
export function Nav() {
  const reduced = useReducedMotion()
  return (
    <motion.header
      className="sticky top-0 z-50 border-b border-line/70 bg-paper/80 backdrop-blur-md"
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
    >
      <Wrap className="flex h-16 items-center justify-between">
        <a
          href="#top"
          className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink"
        >
          <span className="h-2.5 w-2.5 rounded-full bg-celeste" aria-hidden="true" />
          AI-Native
        </a>
        <nav aria-label="Secciones" className="hidden items-center gap-8 lg:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-[14px] font-medium text-ink-soft transition-colors hover:text-ink"
            >
              {l.label}
            </a>
          ))}
        </nav>
        <a
          href="#demo"
          className="rounded-full bg-celeste px-4 py-2 text-[14px] font-semibold text-white transition-colors hover:bg-celeste-deep"
        >
          Pedí una demo
        </a>
      </Wrap>
    </motion.header>
  )
}
