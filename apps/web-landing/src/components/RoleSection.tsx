import { motion, useReducedMotion } from "framer-motion"
import type { LucideIcon } from "lucide-react"
import { EXPO_OUT, VIEWPORT } from "../lib/motion"
import { Reveal } from "./Reveal"
import { Kicker, Wrap } from "./primitives"

export type FeatureCluster = {
  icon: LucideIcon
  heading: string
  items: string[]
}

type RoleSectionProps = {
  id: string
  /** Etiqueta corta de la audiencia (ej: "Para el alumno"). */
  who: string
  /** Numero de orden, tenue, como marca editorial. */
  index: string
  title: string
  intro: string
  clusters: FeatureCluster[]
  /** Invierte columnas en desktop para romper la monotonia entre secciones. */
  reversed?: boolean
  /** Fondo alterno para dar ritmo vertical. */
  tinted?: boolean
}

/**
 * Apartado por rol: encabezado editorial a un lado y funcionalidades agrupadas
 * en clusters tematicos al otro. Escaneable, sin grid de cards identicas.
 */
export function RoleSection({
  id,
  who,
  index,
  title,
  intro,
  clusters,
  reversed = false,
  tinted = false,
}: RoleSectionProps) {
  const reduced = useReducedMotion()

  return (
    <section
      id={id}
      className={`py-[clamp(64px,9vw,132px)] ${tinted ? "border-y border-line bg-paper-warm" : ""}`}
    >
      <Wrap>
        <div className="grid gap-x-16 gap-y-12 md:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
          <div
            className={`md:sticky md:top-24 md:self-start ${
              reversed ? "md:order-2" : "md:order-1"
            }`}
          >
            <div className="flex items-baseline gap-4">
              <span
                className="font-display text-[clamp(28px,3.4vw,44px)] font-light leading-none text-celeste-soft"
                aria-hidden="true"
              >
                {index}
              </span>
              <Reveal>
                <Kicker>{who}</Kicker>
              </Reveal>
            </div>
            <Reveal delay={0.08}>
              <h2 className="mt-6 max-w-[15ch] font-display text-[clamp(30px,4.2vw,54px)] font-bold leading-[1.04] tracking-[-0.03em] text-ink">
                {title}
              </h2>
            </Reveal>
            <Reveal delay={0.14}>
              <p className="mt-6 max-w-[40ch] text-[clamp(15px,1.6vw,18px)] leading-relaxed text-ink-soft">
                {intro}
              </p>
            </Reveal>
          </div>

          <div className={reversed ? "md:order-1" : "md:order-2"}>
            <div className="space-y-0">
              {clusters.map((c, i) => (
                <Reveal
                  key={c.heading}
                  delay={i * 0.06}
                  className="border-t border-line py-8 first:border-t-0 first:pt-0"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-celeste-wash text-celeste-deep"
                      aria-hidden="true"
                    >
                      <c.icon size={18} strokeWidth={1.8} />
                    </span>
                    <h3 className="font-display text-[clamp(18px,2.1vw,24px)] font-semibold tracking-[-0.02em] text-ink">
                      {c.heading}
                    </h3>
                  </div>
                  <ul className="mt-5 grid list-none gap-x-8 gap-y-3 sm:grid-cols-2">
                    {c.items.map((item, ii) => (
                      <motion.li
                        key={item}
                        className="flex items-baseline gap-3 text-[clamp(15px,1.5vw,16.5px)] leading-relaxed text-ink-soft"
                        initial={reduced ? { opacity: 0 } : { opacity: 0, x: -8 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={VIEWPORT}
                        transition={{ duration: 0.5, delay: ii * 0.04, ease: EXPO_OUT }}
                      >
                        <span
                          className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-celeste"
                          aria-hidden="true"
                        />
                        <span>{item}</span>
                      </motion.li>
                    ))}
                  </ul>
                </Reveal>
              ))}
            </div>
          </div>
        </div>
      </Wrap>
    </section>
  )
}
