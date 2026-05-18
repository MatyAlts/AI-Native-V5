/**
 * Sección "Números del piloto" — bloque oscuro de alto contraste con 6
 * métricas verificables del sistema. Cada número rueda desde 0 al valor real
 * cuando entra al viewport (animación expo-out de 1.5s). Counters
 * implementados con useMotionValue + animate + useInView de framer-motion 11.
 */
import { useEffect, useRef, useState } from "react"
import { motion, useInView, useMotionValue, animate } from "framer-motion"

type Metric = {
  value: number
  label: string
}

const METRICS: ReadonlyArray<Metric> = [
  { value: 11, label: "Servicios Python activos" },
  { value: 4, label: "Bases lógicas aisladas" },
  { value: 25, label: "Ejercicios canónicos PID-UTN" },
  { value: 43, label: "ADRs registradas" },
  { value: 17, label: "Migraciones Alembic" },
  { value: 30, label: "Tests E2E" },
]

const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

type CounterProps = {
  to: number
  active: boolean
  delaySeconds: number
}

function Counter({ to, active, delaySeconds }: CounterProps) {
  const motionValue = useMotionValue(0)
  const [display, setDisplay] = useState<number>(0)

  useEffect(() => {
    if (!active) return
    const controls = animate(motionValue, to, {
      duration: 1.5,
      delay: delaySeconds,
      ease: EASE_OUT_EXPO,
      onUpdate: (latest) => {
        setDisplay(Math.round(latest))
      },
    })
    return () => {
      controls.stop()
    }
  }, [active, to, delaySeconds, motionValue])

  return <>{display}</>
}

export function Metricas() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: "-120px" })

  return (
    <section className="bg-ink py-40 text-bg">
      <div ref={ref} className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
          className="mb-24 max-w-3xl"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">
            El piloto en números
          </p>
          <h2 className="mt-4 font-serif text-[56px] leading-[1.05] tracking-tight text-bg">
            Sistema completo, verificable end-to-end.
          </h2>
          <p className="mt-6 text-lg text-muted-soft">
            Cada número es trazable contra el repositorio. Nada inflado, nada
            decorativo.
          </p>
        </motion.div>

        <div className="grid grid-cols-2 gap-y-16 md:grid-cols-3 md:gap-y-20 lg:grid-cols-6 lg:gap-y-0">
          {METRICS.map((metric, index) => (
            <motion.div
              key={metric.label}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{
                duration: 0.6,
                ease: EASE_OUT_EXPO,
                delay: index * 0.1,
              }}
              className="relative flex flex-col items-start px-4 lg:px-2"
            >
              <span className="font-serif text-[48px] font-semibold leading-none tracking-tight text-bg md:text-[64px] lg:text-[80px]">
                <Counter
                  to={metric.value}
                  active={inView}
                  delaySeconds={index * 0.1}
                />
              </span>
              <span className="mt-4 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-soft">
                {metric.label}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
