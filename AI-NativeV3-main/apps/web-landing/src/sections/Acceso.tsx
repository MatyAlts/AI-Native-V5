import { useRef } from "react"
import {
  motion,
  useMotionValue,
  useSpring,
  type MotionValue,
  type Variants,
} from "framer-motion"
import { Shield, GraduationCap, Code, ArrowRight } from "lucide-react"
import type { ComponentType, SVGProps } from "react"

/**
 * Sección "Acceso a la plataforma" — 3 cards-CTA a los frontends del piloto
 * (web-admin :5173, web-teacher :5174, web-student :5175).
 *
 * Cada card resume el rol, el usuario dev del seed, y enlaza al puerto correcto.
 * El CTA tiene magnetic hover (radio 80px, atracción hasta 6px).
 * Entrada con stagger 0.15s al entrar al viewport.
 */

const EXPO_OUT = [0.16, 1, 0.3, 1] as const

type FrontendCard = {
  Icon: ComponentType<SVGProps<SVGSVGElement>>
  port: string
  heading: string
  body: string
  bullets: ReadonlyArray<string>
  ctaLabel: string
  href: string
  accentTint: boolean
}

const CARDS: ReadonlyArray<FrontendCard> = [
  {
    Icon: Shield,
    port: ":5173",
    heading: "Admin",
    body: "Gestión institucional. Crear universidades, facultades, comisiones. Cargar BYOK keys. Importar inscripciones via CSV. Auditar cadena CTR.",
    bullets: [
      "Roles: docente_admin, superadmin",
      "Usuario dev: admin@demo-uni.edu",
      "TenantSelector dinámico en header",
    ],
    ctaLabel: "Abrir admin",
    href: "http://localhost:5173",
    accentTint: true,
  },
  {
    Icon: GraduationCap,
    port: ":5174",
    heading: "Docente",
    body: "Gestión académica. Armar TPs vinculando ejercicios del banco, generar ejercicios con IA, ver dashboard de cohorte con k-anonymity, audit del CTR de sus alumnos.",
    bullets: [
      "Rol: docente",
      "Usuario dev: docente01 (UTN)",
      "Wizard IA con BYOK del tenant",
    ],
    ctaLabel: "Abrir docente",
    href: "http://localhost:5174",
    accentTint: false,
  },
  {
    Icon: Code,
    port: ":5175",
    heading: "Alumno",
    body: "Vista de Mis Materias → Unidades → TPs → Ejercicios. Editor Monaco con Pyodide (Python en browser). Tutor socrático con LLM real. Diagnóstico N4 al cierre.",
    bullets: [
      "Rol: estudiante",
      "Usuario dev: alumno01",
      "Editor + tutor + clasificador",
    ],
    ctaLabel: "Abrir alumno",
    href: "http://localhost:5175",
    accentTint: false,
  },
]

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 30 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.8,
      ease: EXPO_OUT,
      delay: index * 0.15,
    },
  }),
}

export function Acceso() {
  return (
    <section id="acceso" className="bg-bg py-32">
      <div className="mx-auto max-w-7xl px-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: EXPO_OUT }}
          className="mb-20 max-w-3xl"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            Probar la plataforma
          </p>
          <h2 className="mt-4 font-serif text-[56px] leading-[1.05] tracking-tight text-ink">
            Tres perspectivas, un mismo modelo.
          </h2>
          <p className="mt-6 text-lg text-muted">
            Cada rol entra por su frontend. Mismo backend, mismo CTR, mismas
            invariantes.
          </p>
        </motion.div>

        {/* Grid de 3 cards */}
        <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
          {CARDS.map((card, index) => (
            <FrontendAccessCard key={card.heading} card={card} index={index} />
          ))}
        </div>
      </div>
    </section>
  )
}

function FrontendAccessCard({
  card,
  index,
}: {
  card: FrontendCard
  index: number
}) {
  const ctaRef = useRef<HTMLAnchorElement | null>(null)

  // Magnetic hover sobre el CTA — radio 80px, atracción suave hasta ~6px.
  const magneticX = useMotionValue(0)
  const magneticY = useMotionValue(0)
  const springX = useSpring(magneticX, { stiffness: 220, damping: 18 })
  const springY = useSpring(magneticY, { stiffness: 220, damping: 18 })

  const handleCtaMove = (event: React.MouseEvent<HTMLAnchorElement>) => {
    const node = ctaRef.current
    if (!node) return
    const rect = node.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const dx = event.clientX - cx
    const dy = event.clientY - cy
    const distance = Math.hypot(dx, dy)
    const RADIUS = 80
    if (distance > RADIUS) {
      magneticX.set(0)
      magneticY.set(0)
      return
    }
    const strength = 1 - distance / RADIUS
    magneticX.set(dx * 0.22 * strength)
    magneticY.set(dy * 0.22 * strength)
  }

  const handleCtaLeave = () => {
    magneticX.set(0)
    magneticY.set(0)
  }

  const { Icon, port, heading, body, bullets, ctaLabel, href, accentTint } =
    card

  return (
    <motion.article
      custom={index}
      variants={cardVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
      whileHover={{ scale: 1.02 }}
      transition={{ scale: { duration: 0.4, ease: EXPO_OUT } }}
      className={
        accentTint
          ? "group relative flex flex-col rounded-2xl border border-border bg-accent-soft p-10 transition-colors duration-300 hover:border-ink-soft hover:shadow-[0_8px_24px_-12px_rgba(10,10,10,0.12)]"
          : "group relative flex flex-col rounded-2xl border border-border bg-bg-elevated p-10 transition-colors duration-300 hover:border-ink-soft hover:shadow-[0_8px_24px_-12px_rgba(10,10,10,0.12)]"
      }
    >
      {/* Icono */}
      <Icon
        width={40}
        height={40}
        strokeWidth={1.5}
        className="text-accent"
        aria-hidden="true"
      />

      {/* Tag mono del puerto */}
      <span className="mt-8 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
        {port}
      </span>

      {/* Heading */}
      <h3 className="mt-2 font-serif text-[32px] leading-tight tracking-tight text-ink">
        {heading}
      </h3>

      {/* Body */}
      <p className="mt-4 text-base leading-relaxed text-muted">{body}</p>

      {/* Bullets */}
      <ul className="mt-6 space-y-2">
        {bullets.map((bullet) => (
          <li
            key={bullet}
            className="flex items-start gap-2 text-sm leading-relaxed text-ink-soft"
          >
            <span
              aria-hidden="true"
              className="mt-[0.55em] inline-block h-[3px] w-[3px] flex-shrink-0 rounded-full bg-muted"
            />
            <span>{bullet}</span>
          </li>
        ))}
      </ul>

      {/* Spacer para empujar el CTA al fondo */}
      <div className="flex-1" />

      {/* CTA magnetic */}
      <MagneticCta
        ctaRef={ctaRef}
        href={href}
        label={ctaLabel}
        x={springX}
        y={springY}
        onMove={handleCtaMove}
        onLeave={handleCtaLeave}
      />
    </motion.article>
  )
}

function MagneticCta({
  ctaRef,
  href,
  label,
  x,
  y,
  onMove,
  onLeave,
}: {
  ctaRef: React.RefObject<HTMLAnchorElement | null>
  href: string
  label: string
  x: MotionValue<number>
  y: MotionValue<number>
  onMove: (event: React.MouseEvent<HTMLAnchorElement>) => void
  onLeave: () => void
}) {
  return (
    <motion.a
      ref={ctaRef}
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ x, y }}
      className="mt-10 inline-flex w-full items-center justify-center gap-2 bg-ink px-6 py-4 text-sm font-medium text-bg transition-colors duration-200 hover:bg-ink-soft"
    >
      <span>{label}</span>
      <ArrowRight
        size={16}
        strokeWidth={1.75}
        aria-hidden="true"
        className="transition-transform duration-300 ease-out group-hover:translate-x-1"
      />
    </motion.a>
  )
}
