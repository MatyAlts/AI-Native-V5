import { Reveal } from "../components/Reveal"
import { Kicker, Wrap } from "../components/primitives"

const STEPS = [
  {
    n: "01",
    title: "El alumno trabaja en el navegador",
    desc: "Resuelve las tareas prácticas reales de su cursada con un editor de código, sin instalar nada.",
  },
  {
    n: "02",
    title: "El tutor de IA lo guía",
    desc: "Le hace preguntas y le da pistas apoyándose en el material de la materia, en lugar de darle la respuesta hecha.",
  },
  {
    n: "03",
    title: "El docente acompaña a su clase",
    desc: "Ve cómo progresa cada alumno y toda la comisión, y sabe a quién necesita darle una mano.",
  },
]

/** Que es: explicacion clara de la plataforma + como funciona en 3 pasos. */
export function QueEs() {
  return (
    <section
      id="producto"
      className="border-y border-line bg-paper-warm py-[clamp(64px,9vw,128px)]"
    >
      <Wrap>
        <div className="grid gap-x-16 gap-y-10 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <div>
            <Reveal>
              <Kicker>Qué es</Kicker>
            </Reveal>
            <Reveal delay={0.08}>
              <h2 className="mt-7 max-w-[16ch] font-display text-[clamp(32px,4.4vw,58px)] font-bold leading-[1.03] tracking-[-0.03em] text-ink">
                Un tutor de IA que guía, sin reemplazar al docente.
              </h2>
            </Reveal>
          </div>

          <div className="md:pt-3">
            <Reveal>
              <p className="max-w-[52ch] text-[clamp(16px,1.7vw,19px)] leading-relaxed text-ink-soft">
                AI-Native es una plataforma para enseñar a programar. El alumno aprende con guía
                personalizada, el docente ve cómo progresa su clase en tiempo real y la institución
                tiene toda la actividad ordenada y segura en un mismo lugar.
              </p>
            </Reveal>
            <Reveal delay={0.08}>
              <p className="mt-5 max-w-[52ch] text-[clamp(16px,1.7vw,19px)] leading-relaxed text-ink-soft">
                No es un chatbot que resuelve por el alumno. Es un acompañamiento pensado para que
                la persona piense, con el docente siempre al frente de la cursada.
              </p>
            </Reveal>
          </div>
        </div>

        <div className="mt-[clamp(48px,7vw,88px)]">
          <Reveal>
            <p className="text-[13px] font-semibold uppercase tracking-[0.16em] text-celeste-deep">
              Cómo funciona
            </p>
          </Reveal>
          <ol className="mt-8 grid gap-px overflow-hidden rounded-2xl border border-line bg-line md:grid-cols-3">
            {STEPS.map((s, i) => (
              <Reveal
                key={s.n}
                as="li"
                delay={i * 0.08}
                className="flex flex-col bg-paper px-7 py-8"
              >
                <span className="font-display text-[clamp(30px,3.5vw,44px)] font-light leading-none text-celeste-soft">
                  {s.n}
                </span>
                <h3 className="mt-5 font-display text-[19px] font-semibold tracking-[-0.015em] text-ink">
                  {s.title}
                </h3>
                <p className="mt-2.5 text-[15px] leading-relaxed text-ink-soft">{s.desc}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </Wrap>
    </section>
  )
}
