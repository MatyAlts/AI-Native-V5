import { motion, type Variants } from "framer-motion"
import { ArrowUpRight } from "lucide-react"

/**
 * Footer — cierre oscuro con 3 columnas + bottom bar.
 *
 * Animaciones:
 *  - Cada bloque fade-up al entrar a viewport (`whileInView`, once).
 *  - Hover en links: flecha translate-x-1 + fade-in.
 *  - Dot del badge "Estado": pulse loop infinito.
 */

const EXPO_OUT = [0.16, 1, 0.3, 1] as const

const blockFadeUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.9, ease: EXPO_OUT },
  },
}

type ResourceLink = {
  label: string
  href: string
}

const RESOURCES: ResourceLink[] = [
  { label: "Repositorio", href: "#repositorio" },
  { label: "Documentación (README.md)", href: "#documentacion" },
  { label: "ADRs (43 decisiones)", href: "#adrs" },
  { label: "CLAUDE.md (invariantes)", href: "#claude-md" },
]

export function Footer() {
  return (
    <footer
      id="footer"
      className="relative w-full bg-ink text-bg"
      style={{ minHeight: "280px" }}
    >
      <div className="mx-auto w-full max-w-7xl px-6 py-20 md:px-12 md:py-24">
        {/* Grid principal — 3 columnas 60/20/20 en desktop. */}
        <div className="grid grid-cols-1 gap-12 md:grid-cols-12 md:gap-10">
          {/* Columna 1 — identidad (60%). */}
          <motion.div
            variants={blockFadeUp}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            className="md:col-span-7"
          >
            <h2
              className="font-serif font-medium leading-none tracking-[-0.02em]"
              style={{ fontSize: "32px" }}
            >
              AI-Native N4
            </h2>
            <p className="mt-5 max-w-xl text-sm leading-relaxed text-muted">
              Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación
              en Programación Universitaria.
            </p>
            <ul className="mt-8 space-y-2 font-mono text-[12px] uppercase tracking-[0.12em] text-muted-soft">
              <li>
                <span className="text-muted">Autor</span>
                <span className="mx-2 text-border">·</span>
                <span className="text-bg">Alberto Alejandro Cortez</span>
              </li>
              <li>
                <span className="text-muted">Co-directora</span>
                <span className="mx-2 text-border">·</span>
                <span className="text-bg">Daniela Carbonari</span>
              </li>
              <li>
                <span className="text-muted">Universidad</span>
                <span className="mx-2 text-border">·</span>
                <span className="text-bg">
                  UNSL — Doctorado en Ingeniería Informática
                </span>
              </li>
            </ul>
          </motion.div>

          {/* Columna 2 — Recursos (20%). */}
          <motion.div
            variants={blockFadeUp}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            transition={{ delay: 0.08 }}
            className="md:col-span-3"
          >
            <h3 className="mb-5 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
              Recursos
            </h3>
            <ul className="space-y-3">
              {RESOURCES.map((link) => (
                <li key={link.href}>
                  <FooterLink label={link.label} href={link.href} />
                </li>
              ))}
            </ul>
          </motion.div>

          {/* Columna 3 — Estado (20%). */}
          <motion.div
            variants={blockFadeUp}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            transition={{ delay: 0.16 }}
            className="md:col-span-2"
          >
            <h3 className="mb-5 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
              Estado
            </h3>
            <div className="inline-flex items-center gap-2 border border-border/20 bg-ink-soft px-3 py-2 text-[11px] font-medium tracking-[0.04em] text-bg">
              <StatusDot />
              <span>Piloto · F0–F9 cerrado · 2026-S1</span>
            </div>
          </motion.div>
        </div>

        {/* Separador horizontal. */}
        <div className="mt-16 h-px w-full bg-border/15" />

        {/* Bottom bar. */}
        <motion.div
          variants={blockFadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          transition={{ delay: 0.24 }}
          className="mt-8 flex flex-col gap-3 font-mono text-[11px] uppercase tracking-[0.14em] text-muted sm:flex-row sm:items-center sm:justify-between"
        >
          <span>© 2026 · Hecho con rigor académico</span>
          <span className="text-muted-soft">v0.1.0 · piloto</span>
        </motion.div>
      </div>
    </footer>
  )
}

function FooterLink({ label, href }: { label: string; href: string }) {
  return (
    <a
      href={href}
      className="group flex items-center gap-1.5 text-sm text-bg transition-colors duration-200 hover:text-accent"
    >
      <span>{label}</span>
      <span className="inline-flex translate-x-0 opacity-0 transition-all duration-200 ease-out group-hover:translate-x-1 group-hover:opacity-100">
        <ArrowUpRight size={14} strokeWidth={1.75} aria-hidden="true" />
      </span>
    </a>
  )
}

function StatusDot() {
  return (
    <span className="relative inline-flex h-1.5 w-1.5">
      <motion.span
        className="absolute inline-flex h-full w-full rounded-full bg-emerald-400"
        animate={{ scale: [1, 1.6, 1], opacity: [0.85, 0.35, 0.85] }}
        transition={{
          duration: 1.8,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
    </span>
  )
}
