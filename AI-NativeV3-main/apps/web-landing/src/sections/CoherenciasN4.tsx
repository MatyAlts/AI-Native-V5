/**
 * Sección "Las 5 coherencias N4" — explica las cinco dimensiones que el
 * clasificador N4 evalúa por separado. Invariante doctoral (ADR-018): las
 * cinco coherencias nunca se colapsan en un score único. Cada card incluye
 * una mini-visualización SVG abstracta única (no gráficos literales).
 *
 * Coherencias:
 *   - CT                 : patrón temporal sostenido (regularidad)
 *   - CCD_mean           : alineación código ↔ discurso (0=desalineado, 1=alineado)
 *   - CCD_orphan_ratio   : acciones huérfanas sin verbalización (0=bueno, 1=malo)
 *   - CII_stability      : consistencia entre intentos sucesivos
 *   - CII_evolution      : mejora de estrategia entre intentos
 */
import { motion } from "framer-motion"
import type { ReactNode } from "react"

const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

type Coherencia = {
  nombreHumano: string
  nombreTecnico: string
  body: string
  Viz: () => ReactNode
}

// ────────────────────────────────────────────────────────────────────────────
// Mini-visualizaciones SVG (viewBox 200×100, abstractas, stroke fino)
// ────────────────────────────────────────────────────────────────────────────

/**
 * CT — 7 puntos espaciados representando una semana. Algunos llenos
 * (acción), otros vacíos (silencio). Aparecen uno por uno con stagger.
 */
function VizTemporal() {
  const dots = [true, true, false, true, true, false, true]
  return (
    <svg
      viewBox="0 0 200 100"
      className="h-24 w-full"
      role="img"
      aria-label="Visualización de coherencia temporal"
    >
      <line
        x1="20"
        y1="50"
        x2="180"
        y2="50"
        stroke="var(--color-border)"
        strokeWidth="1"
      />
      {dots.map((filled, i) => {
        const cx = 20 + i * ((180 - 20) / 6)
        return (
          <motion.circle
            key={i}
            cx={cx}
            cy={50}
            r={5}
            fill={filled ? "var(--color-accent)" : "var(--color-bg-elevated)"}
            stroke="var(--color-accent)"
            strokeWidth={filled ? 0 : 1.2}
            initial={{ scale: 0, opacity: 0 }}
            whileInView={{ scale: 1, opacity: 1 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{
              duration: 0.4,
              ease: EASE_OUT_EXPO,
              delay: 0.6 + i * 0.08,
            }}
          />
        )
      })}
    </svg>
  )
}

/**
 * CCD_mean — dos curvas paralelas onduladas en fase. Su alineación visual
 * representa la coherencia entre acciones (codear) y discurso (verbalizar).
 */
function VizCodigoDiscurso() {
  const pathA = "M 10 40 Q 50 20, 100 40 T 190 40"
  const pathB = "M 10 65 Q 50 45, 100 65 T 190 65"
  return (
    <svg
      viewBox="0 0 200 100"
      className="h-24 w-full"
      role="img"
      aria-label="Visualización de alineación código y discurso"
    >
      <motion.path
        d={pathA}
        fill="none"
        stroke="var(--color-ink)"
        strokeWidth="1.5"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true, margin: "-50px" }}
        transition={{ duration: 1.1, ease: EASE_OUT_EXPO, delay: 0.5 }}
      />
      <motion.path
        d={pathB}
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="1.5"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true, margin: "-50px" }}
        transition={{ duration: 1.1, ease: EASE_OUT_EXPO, delay: 0.7 }}
      />
    </svg>
  )
}

/**
 * CCD_orphan_ratio — grid 5×3 de cuadrados. Llenos = acción verbalizada,
 * vacíos = acción huérfana. La proporción visual lee el ratio de un vistazo.
 */
function VizHuerfanas() {
  const cols = 5
  const rows = 3
  // Patrón: algunas huérfanas distribuidas (ratio bajo = saludable).
  const filled = new Set([0, 1, 3, 4, 5, 7, 8, 9, 10, 13, 14])
  const cellW = 22
  const cellH = 18
  const gap = 6
  const totalW = cols * cellW + (cols - 1) * gap
  const totalH = rows * cellH + (rows - 1) * gap
  const offsetX = (200 - totalW) / 2
  const offsetY = (100 - totalH) / 2
  return (
    <svg
      viewBox="0 0 200 100"
      className="h-24 w-full"
      role="img"
      aria-label="Visualización de acciones huérfanas"
    >
      {Array.from({ length: rows * cols }).map((_, i) => {
        const r = Math.floor(i / cols)
        const c = i % cols
        const x = offsetX + c * (cellW + gap)
        const y = offsetY + r * (cellH + gap)
        const isFilled = filled.has(i)
        return (
          <motion.rect
            key={i}
            x={x}
            y={y}
            width={cellW}
            height={cellH}
            rx={2}
            fill={isFilled ? "var(--color-accent)" : "none"}
            stroke="var(--color-accent)"
            strokeWidth={isFilled ? 0 : 1.2}
            initial={{ opacity: 0, scale: 0.6 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{
              duration: 0.4,
              ease: EASE_OUT_EXPO,
              delay: 0.5 + i * 0.03,
            }}
          />
        )
      })}
    </svg>
  )
}

/**
 * CII_stability — círculos concéntricos. Cuanto más concéntricos, mayor
 * la estabilidad de la estrategia entre intentos.
 */
function VizEstabilidad() {
  const radii = [8, 18, 28]
  return (
    <svg
      viewBox="0 0 200 100"
      className="h-24 w-full"
      role="img"
      aria-label="Visualización de estabilidad inter-iteración"
    >
      {radii.map((r, i) => (
        <motion.circle
          key={i}
          cx={100}
          cy={50}
          r={r}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={i === 0 ? 2 : 1.2}
          initial={{ scale: 0, opacity: 0 }}
          whileInView={{ scale: 1, opacity: i === 0 ? 1 : 0.7 - i * 0.15 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{
            duration: 0.7,
            ease: EASE_OUT_EXPO,
            delay: 0.5 + i * 0.18,
          }}
          style={{ transformOrigin: "100px 50px" }}
        />
      ))}
    </svg>
  )
}

/**
 * CII_evolution — línea ascendente con dots que crecen de izquierda a
 * derecha (su tamaño representa progresión de complejidad/calidad).
 */
function VizEvolucion() {
  const points = [
    { x: 20, y: 75, r: 3 },
    { x: 60, y: 62, r: 4 },
    { x: 100, y: 48, r: 5 },
    { x: 140, y: 34, r: 6 },
    { x: 180, y: 22, r: 7 },
  ]
  const path = points.reduce(
    (acc, p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`),
    ""
  )
  return (
    <svg
      viewBox="0 0 200 100"
      className="h-24 w-full"
      role="img"
      aria-label="Visualización de evolución inter-iteración"
    >
      <motion.path
        d={path}
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="1.5"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true, margin: "-50px" }}
        transition={{ duration: 1.1, ease: EASE_OUT_EXPO, delay: 0.5 }}
      />
      {points.map((p, i) => (
        <motion.circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={p.r}
          fill="var(--color-accent)"
          initial={{ scale: 0, opacity: 0 }}
          whileInView={{ scale: 1, opacity: 1 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{
            duration: 0.45,
            ease: EASE_OUT_EXPO,
            delay: 1.0 + i * 0.1,
          }}
          style={{ transformOrigin: `${p.x}px ${p.y}px` }}
        />
      ))}
    </svg>
  )
}

// ────────────────────────────────────────────────────────────────────────────

const COHERENCIAS: ReadonlyArray<Coherencia> = [
  {
    nombreHumano: "Temporal",
    nombreTecnico: "CT",
    body: "Patrón de trabajo sostenido en el tiempo. Mide regularidad: ¿la actividad se distribuye o se concentra en atracones?",
    Viz: VizTemporal,
  },
  {
    nombreHumano: "Código ↔ Discurso",
    nombreTecnico: "CCD_mean",
    body: "Alineación entre acciones (codear, ejecutar) y verbalización (preguntar, anotar). Score 0 = totalmente desalineado, 1 = perfectamente alineado.",
    Viz: VizCodigoDiscurso,
  },
  {
    nombreHumano: "Acciones huérfanas",
    nombreTecnico: "CCD_orphan_ratio",
    body: "Ratio de acciones sin verbalización reflexiva acompañante. Score 0 = todo verbalizado, 1 = todo huérfano. Cuanto más bajo, mejor.",
    Viz: VizHuerfanas,
  },
  {
    nombreHumano: "Estabilidad",
    nombreTecnico: "CII_stability",
    body: "Consistencia entre intentos sucesivos en el mismo ejercicio. Mide si el alumno mantiene una estrategia coherente turno tras turno.",
    Viz: VizEstabilidad,
  },
  {
    nombreHumano: "Evolución",
    nombreTecnico: "CII_evolution",
    body: "Si la estrategia mejora entre intentos. Medible por delta de complejidad y corrección entre iteraciones del mismo ejercicio.",
    Viz: VizEvolucion,
  },
]

export function CoherenciasN4() {
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
            Modelo N4
          </p>
          <h2 className="mt-4 font-serif text-[56px] leading-[1.05] tracking-tight text-ink">
            Cinco coherencias. Cinco dimensiones independientes.
          </h2>
          <p className="mt-6 text-lg text-muted">
            El clasificador NO colapsa en un score único. La tesis depende de
            análisis multidimensional.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-5 lg:gap-5">
          {COHERENCIAS.map((coh, index) => {
            const isLastOdd =
              index === COHERENCIAS.length - 1 && COHERENCIAS.length % 2 !== 0
            return (
              <motion.article
                key={coh.nombreTecnico}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{
                  duration: 0.7,
                  ease: EASE_OUT_EXPO,
                  delay: index * 0.15,
                }}
                className={`relative flex flex-col border-t-2 border-accent bg-bg-elevated p-8 ${
                  isLastOdd ? "md:col-span-2 lg:col-span-1" : ""
                }`}
              >
                <h3 className="font-serif text-[22px] leading-tight tracking-tight text-ink">
                  {coh.nombreHumano}
                </h3>

                <div className="mt-6">
                  <coh.Viz />
                </div>

                <p className="mt-6 text-sm leading-relaxed text-muted">
                  {coh.body}
                </p>

                <p className="mt-8 font-mono text-[11px] uppercase tracking-[0.15em] text-muted-soft">
                  {coh.nombreTecnico}
                </p>
              </motion.article>
            )
          })}
        </div>
      </div>
    </section>
  )
}
