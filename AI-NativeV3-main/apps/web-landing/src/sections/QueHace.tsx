/**
 * Sección "Qué hace la plataforma" — explica las 3 capacidades núcleo de
 * AI-Native N4: tutor socrático con BYOK, cadena CTR criptográfica y
 * clasificador N4 multidimensional. Layout tipo Stripe/Linear: minimalista,
 * grid de 3 columnas con divisores verticales finos y entrada animada.
 */
import { motion } from "framer-motion"
import { MessageCircle, Link2, Layers3 } from "lucide-react"
import type { ComponentType, SVGProps } from "react"

type Pillar = {
  Icon: ComponentType<SVGProps<SVGSVGElement>>
  heading: string
  body: string
  stat: string
}

const PILLARS: ReadonlyArray<Pillar> = [
  {
    Icon: MessageCircle,
    heading: "Tutor socrático",
    body: "LLM real (Mistral, OpenAI, Anthropic, Gemini) que NO da la respuesta. Pregunta, contradice, guía. Cada universidad trae su API key (BYOK).",
    stat: "4 providers · BYOK encriptado AES-256-GCM",
  },
  {
    Icon: Link2,
    heading: "Cadena CTR append-only",
    body: "Cada evento del estudiante (lectura, edición, pregunta, ejecución) firma a su predecesor con SHA-256. Tampering detectable al seq exacto. Verificable on-demand.",
    stat: "SHA-256 · 11 eventos típicos · 0ms cost per chain",
  },
  {
    Icon: Layers3,
    heading: "Clasificador multidimensional",
    body: "5 coherencias separadas (CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution). Nunca colapsadas en score único. Hash determinista garantiza reproducibilidad bit-a-bit.",
    stat: "5 dimensiones · hash determinista · reproducible",
  },
]

const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

export function QueHace() {
  return (
    <section className="bg-bg py-32">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
          className="mb-20 max-w-3xl"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            El núcleo
          </p>
          <h2 className="mt-4 font-serif text-[56px] leading-[1.05] tracking-tight text-ink">
            Tres cosas que hace bien.
          </h2>
          <p className="mt-6 text-lg text-muted">
            Pensadas para piloto académico, defendibles doctoralmente.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 gap-12 md:grid-cols-3 md:gap-0">
          {PILLARS.map((pillar, index) => {
            const { Icon, heading, body, stat } = pillar
            return (
              <motion.div
                key={heading}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{
                  duration: 0.7,
                  ease: EASE_OUT_EXPO,
                  delay: index * 0.15,
                }}
                className="relative md:px-10 md:first:pl-0 md:last:pr-0"
              >
                {index > 0 ? (
                  <motion.span
                    aria-hidden="true"
                    initial={{ scaleY: 0 }}
                    whileInView={{ scaleY: 1 }}
                    viewport={{ once: true, margin: "-100px" }}
                    transition={{
                      duration: 0.9,
                      ease: EASE_OUT_EXPO,
                      delay: index * 0.15 + 0.1,
                    }}
                    style={{ transformOrigin: "top" }}
                    className="absolute left-0 top-0 hidden h-full w-px bg-border md:block"
                  />
                ) : null}

                <motion.div
                  initial={{ rotate: -180, opacity: 0 }}
                  whileInView={{ rotate: 0, opacity: 1 }}
                  viewport={{ once: true, margin: "-100px" }}
                  transition={{
                    duration: 1.2,
                    ease: EASE_OUT_EXPO,
                    delay: index * 0.15 + 0.05,
                  }}
                  className="inline-flex"
                >
                  <Icon
                    width={32}
                    height={32}
                    strokeWidth={1.5}
                    className="text-ink"
                  />
                </motion.div>

                <h3 className="mt-6 font-serif text-[28px] leading-tight tracking-tight text-ink">
                  {heading}
                </h3>

                <p className="mt-4 text-base leading-relaxed text-muted">
                  {body}
                </p>

                <p className="mt-8 font-mono text-[11px] uppercase tracking-[0.15em] text-muted-soft">
                  {stat}
                </p>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
