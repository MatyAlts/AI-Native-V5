import { Eye, Layers, MousePointerClick, Sparkles } from "lucide-react"
import { Reveal } from "../components/Reveal"
import { Kicker, Wrap } from "../components/primitives"

const BENEFITS = [
  {
    icon: Sparkles,
    title: "Guía real, no respuestas regaladas",
    desc: "El alumno piensa y construye la solución. La IA acompaña el proceso en lugar de resolver por él.",
  },
  {
    icon: Eye,
    title: "Ves cómo progresa cada alumno",
    desc: "Sabés exactamente cómo trabajó y avanzó cada persona de la clase, con un registro confiable.",
  },
  {
    icon: Layers,
    title: "Lista para tu institución",
    desc: "Varias materias, comisiones e instituciones con datos separados y control de accesos desde el primer día.",
  },
  {
    icon: MousePointerClick,
    title: "Sin fricción para el alumno",
    desc: "Todo pasa en el navegador. No hay nada que instalar ni configurar para empezar a trabajar.",
  },
]

/** Por que elegir la plataforma: beneficios comerciales, neutros. */
export function Beneficios() {
  return (
    <section id="beneficios" className="py-[clamp(64px,9vw,132px)]">
      <Wrap>
        <div className="max-w-[40ch]">
          <Reveal>
            <Kicker>Por qué elegirla</Kicker>
          </Reveal>
          <Reveal delay={0.08}>
            <h2 className="mt-7 font-display text-[clamp(30px,4.4vw,56px)] font-bold leading-[1.03] tracking-[-0.03em] text-ink">
              Pensada para enseñar mejor, no para reemplazar al docente.
            </h2>
          </Reveal>
        </div>

        <div className="mt-[clamp(36px,5vw,64px)] grid gap-x-14 gap-y-10 sm:grid-cols-2">
          {BENEFITS.map((b, i) => (
            <Reveal key={b.title} delay={i * 0.06} className="flex items-start gap-5">
              <span
                className="flex h-11 w-11 flex-none items-center justify-center rounded-full bg-celeste-wash text-celeste-deep"
                aria-hidden="true"
              >
                <b.icon size={20} strokeWidth={1.8} />
              </span>
              <div>
                <h3 className="font-display text-[clamp(19px,2.2vw,24px)] font-semibold tracking-[-0.02em] text-ink">
                  {b.title}
                </h3>
                <p className="mt-2.5 max-w-[46ch] text-[15px] leading-relaxed text-ink-soft">
                  {b.desc}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </Wrap>
    </section>
  )
}
