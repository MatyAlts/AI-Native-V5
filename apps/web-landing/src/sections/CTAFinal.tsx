import { Reveal } from "../components/Reveal"
import { CTA, Wrap } from "../components/primitives"

/** Cierre: invitacion a ver la plataforma en vivo. Doble CTA. */
export function CTAFinal() {
  return (
    <section
      id="demo"
      className="relative overflow-hidden border-t border-line bg-paper-deep py-[clamp(72px,11vw,150px)]"
    >
      <Wrap className="relative text-center">
        <Reveal>
          <h2 className="mx-auto max-w-[18ch] font-display text-[clamp(34px,6vw,78px)] font-extrabold leading-[1.0] tracking-[-0.04em] text-ink">
            ¿La querés ver funcionando?
          </h2>
        </Reveal>
        <Reveal delay={0.12}>
          <p className="mx-auto mt-7 max-w-[48ch] text-[clamp(16px,1.8vw,20px)] leading-relaxed text-ink-soft">
            Te mostramos la plataforma con un caso real de tu materia y respondemos todas tus
            preguntas.
          </p>
        </Reveal>
        <Reveal delay={0.2}>
          <div className="mt-11 flex flex-wrap justify-center gap-3">
            <CTA href="#demo">Pedí una demo</CTA>
            <CTA href="#producto" variant="ghost">
              Conocé más
            </CTA>
          </div>
        </Reveal>
      </Wrap>
    </section>
  )
}
