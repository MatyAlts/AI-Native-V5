/**
 * Sección "Arquitectura" — diagrama interactivo del stack AI-Native N4.
 *
 * Estructura:
 *  - 3 frontends arriba (web-admin / web-teacher / web-student) en :5173/74/75
 *  - api-gateway al centro como único punto de entrada (:8000, JWT RS256)
 *  - 3 grupos de servicios (académico-operacional / pedagógico-evaluativo / transversal)
 *  - 2 bases compartidas abajo (Postgres con 4 bases lógicas + Redis Streams)
 *
 * Animación de entrada (whileInView, once):
 *  1. Frontends → fade-up + stagger
 *  2. api-gateway → fade-up
 *  3. Líneas frontends → gateway (path drawing con pathLength 0→1)
 *  4. Grupos de servicios (stagger)
 *  5. Líneas gateway → grupos
 *  6. Bases abajo
 *  7. Líneas servicios → bases
 *
 * Interactividad:
 *  - Hover sobre nodo → highlight (fill accent-soft, stroke accent, scale 1.03)
 *  - Tooltip flotante (HTML absolute layer) con descripción del servicio
 */
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { motion } from "framer-motion"

const EASE_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

// ---------- Geometría del diagrama (viewBox 1200 x 800) ----------

const VIEW_WIDTH = 1200
const VIEW_HEIGHT = 800

// Tamaños de nodo.
const NODE_W = 180
const NODE_H = 56
const GATEWAY_W = 260
const GATEWAY_H = 72
const FRONTEND_W = 170
const FRONTEND_H = 64
const DB_W = 200
const DB_H = 72

// Filas (centros Y).
const Y_FRONTENDS = 70
const Y_GATEWAY = 230
const Y_PLANO_LABEL = 330
const Y_SERVICES_START = 380 // top del primer servicio
const SERVICE_VERTICAL_GAP = 14
const Y_DBS = 720

// Columnas X (centros).
const X_COL_LEFT = 170
const X_COL_CENTER = 600
const X_COL_RIGHT = 1030

// Centros X para los 3 frontends.
const X_FRONT_ADMIN = X_COL_LEFT + 20
const X_FRONT_TEACHER = X_COL_CENTER
const X_FRONT_STUDENT = X_COL_RIGHT - 20

// Centros X para las 2 DBs.
const X_DB_PG = 470
const X_DB_REDIS = 730

// ---------- Tipos ----------

type NodeKind = "frontend" | "gateway" | "service" | "db"

type DiagramNode = {
  id: string
  kind: NodeKind
  label: string
  sublabel: string
  tooltip: string
  cx: number
  cy: number
  w: number
  h: number
  group?: "academic" | "pedagogic" | "transversal"
}

type DiagramLine = {
  id: string
  from: string
  to: string
  // Orden lógico de aparición (stage 1: front→gateway, 2: gateway→services, 3: services→dbs)
  stage: 1 | 2 | 3
}

// ---------- Definición de nodos ----------

function makeServicesColumn(
  group: "academic" | "pedagogic" | "transversal",
  centerX: number,
  defs: ReadonlyArray<{ id: string; label: string; sublabel: string; tooltip: string }>,
): DiagramNode[] {
  return defs.map((d, idx) => ({
    id: d.id,
    kind: "service" as const,
    label: d.label,
    sublabel: d.sublabel,
    tooltip: d.tooltip,
    cx: centerX,
    cy: Y_SERVICES_START + idx * (NODE_H + SERVICE_VERTICAL_GAP) + NODE_H / 2,
    w: NODE_W,
    h: NODE_H,
    group,
  }))
}

const NODES: ReadonlyArray<DiagramNode> = [
  // Frontends.
  {
    id: "web-admin",
    kind: "frontend",
    label: "web-admin",
    sublabel: ":5173",
    tooltip: "Configuración institucional · universidades, BYOK, auditoría",
    cx: X_FRONT_ADMIN,
    cy: Y_FRONTENDS,
    w: FRONTEND_W,
    h: FRONTEND_H,
  },
  {
    id: "web-teacher",
    kind: "frontend",
    label: "web-teacher",
    sublabel: ":5174",
    tooltip: "Gestión académica · TPs, ejercicios, dashboard cohorte",
    cx: X_FRONT_TEACHER,
    cy: Y_FRONTENDS,
    w: FRONTEND_W,
    h: FRONTEND_H,
  },
  {
    id: "web-student",
    kind: "frontend",
    label: "web-student",
    sublabel: ":5175",
    tooltip: "Vista del alumno · resuelve con Pyodide + tutor socrático",
    cx: X_FRONT_STUDENT,
    cy: Y_FRONTENDS,
    w: FRONTEND_W,
    h: FRONTEND_H,
  },
  // Gateway.
  {
    id: "api-gateway",
    kind: "gateway",
    label: "api-gateway",
    sublabel: ":8000 · JWT RS256",
    tooltip: "Único punto de entrada · JWT RS256 · ROUTE_MAP",
    cx: X_COL_CENTER,
    cy: Y_GATEWAY,
    w: GATEWAY_W,
    h: GATEWAY_H,
  },
  // Servicios — plano académico-operacional.
  ...makeServicesColumn("academic", X_COL_LEFT, [
    {
      id: "academic-service",
      label: "academic-service",
      sublabel: ":8002",
      tooltip: "CRUDs institucionales · ADR-001 RLS multi-tenant",
    },
    {
      id: "evaluation-service",
      label: "evaluation-service",
      sublabel: ":8004",
      tooltip: "Entregas y calificaciones · TP correcciones",
    },
    {
      id: "analytics-service",
      label: "analytics-service",
      sublabel: ":8005",
      tooltip: "Dashboards cohorte · k-anonymity N>=5",
    },
  ]),
  // Servicios — plano pedagógico-evaluativo.
  ...makeServicesColumn("pedagogic", X_COL_CENTER, [
    {
      id: "tutor-service",
      label: "tutor-service",
      sublabel: ":8006",
      tooltip: "SSE socrático · guardrails · 6 validaciones de TP",
    },
    {
      id: "ctr-service",
      label: "ctr-service",
      sublabel: ":8007",
      tooltip: "Append-only SHA-256 · 8 workers · 8 streams Redis",
    },
    {
      id: "classifier-service",
      label: "classifier-service",
      sublabel: ":8008",
      tooltip: "5 coherencias N4 · hash determinista · LABELER 1.2.0",
    },
  ]),
  // Servicios — plano transversal.
  ...makeServicesColumn("transversal", X_COL_RIGHT, [
    {
      id: "ai-gateway",
      label: "ai-gateway",
      sublabel: ":8011",
      tooltip: "LLM proxy con cache · BYOK por tenant · 4 providers",
    },
    {
      id: "governance-service",
      label: "governance-service",
      sublabel: ":8010",
      tooltip: "Prompts versionados · v1.0.0 / v1.1.0 / etc",
    },
    {
      id: "content-service",
      label: "content-service",
      sublabel: ":8009",
      tooltip: "RAG con pgvector · material de cátedra",
    },
  ]),
  // Bases.
  {
    id: "postgres",
    kind: "db",
    label: "Postgres",
    sublabel: "4 bases · RLS",
    tooltip: "4 bases lógicas aisladas · RLS forced · 17 migraciones",
    cx: X_DB_PG,
    cy: Y_DBS,
    w: DB_W,
    h: DB_H,
  },
  {
    id: "redis",
    kind: "db",
    label: "Redis",
    sublabel: "Streams · 8 part.",
    tooltip: "8 streams CTR particionados · sessions · cache",
    cx: X_DB_REDIS,
    cy: Y_DBS,
    w: DB_W,
    h: DB_H,
  },
]

// ---------- Definición de líneas ----------

const LINES: ReadonlyArray<DiagramLine> = [
  // Stage 1: frontends → api-gateway
  { id: "l-admin-gw", from: "web-admin", to: "api-gateway", stage: 1 },
  { id: "l-teacher-gw", from: "web-teacher", to: "api-gateway", stage: 1 },
  { id: "l-student-gw", from: "web-student", to: "api-gateway", stage: 1 },
  // Stage 2: api-gateway → servicios (uno por grupo, llega al "top" de la columna)
  { id: "l-gw-academic", from: "api-gateway", to: "academic-service", stage: 2 },
  { id: "l-gw-pedagogic", from: "api-gateway", to: "tutor-service", stage: 2 },
  { id: "l-gw-transversal", from: "api-gateway", to: "ai-gateway", stage: 2 },
  // Stage 3: servicios → bases (último servicio de cada columna baja a la base más cercana)
  { id: "l-analytics-pg", from: "analytics-service", to: "postgres", stage: 3 },
  { id: "l-classifier-pg", from: "classifier-service", to: "postgres", stage: 3 },
  { id: "l-classifier-redis", from: "classifier-service", to: "redis", stage: 3 },
  { id: "l-content-pg", from: "content-service", to: "postgres", stage: 3 },
  { id: "l-content-redis", from: "content-service", to: "redis", stage: 3 },
]

// ---------- Helpers de coordenadas ----------

function nodeById(id: string): DiagramNode {
  const n = NODES.find((x) => x.id === id)
  if (!n) throw new Error(`Nodo no encontrado: ${id}`)
  return n
}

/**
 * Devuelve los puntos de anclaje de una línea entre dos nodos.
 * Si el destino está debajo del origen, salimos por el borde inferior del origen
 * y entramos por el borde superior del destino (orto-vertical). Si están en la
 * misma fila o ligeramente desplazados, usamos una curva Bezier suave.
 */
function lineEndpoints(from: DiagramNode, to: DiagramNode): {
  x1: number
  y1: number
  x2: number
  y2: number
} {
  const goingDown = to.cy > from.cy
  return {
    x1: from.cx,
    y1: goingDown ? from.cy + from.h / 2 : from.cy - from.h / 2,
    x2: to.cx,
    y2: goingDown ? to.cy - to.h / 2 : to.cy + to.h / 2,
  }
}

/**
 * Path con curva suave: sale vertical del origen, entra vertical al destino.
 * Cubic Bezier con tangentes verticales — se ve limpio en diagramas top-down.
 */
function pathBetween(from: DiagramNode, to: DiagramNode): string {
  const { x1, y1, x2, y2 } = lineEndpoints(from, to)
  const dy = y2 - y1
  const c1x = x1
  const c1y = y1 + dy * 0.45
  const c2x = x2
  const c2y = y2 - dy * 0.45
  return `M ${x1} ${y1} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${x2} ${y2}`
}

// ---------- Componente principal ----------

export function Arquitectura() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  // svgScale: relación px-render / unidad-viewBox para posicionar tooltips en HTML overlay.
  const [svgScale, setSvgScale] = useState<{ x: number; y: number }>({ x: 1, y: 1 })

  const hoveredNode = useMemo(
    () => (hoveredId ? NODES.find((n) => n.id === hoveredId) ?? null : null),
    [hoveredId],
  )

  // El tooltip se posiciona en HTML absolute layer encima del SVG escalado.
  // Calculamos su posición en px multiplicando coords del viewBox por svgScale.
  const tooltipStyle: CSSProperties | undefined = hoveredNode
    ? {
        left: hoveredNode.cx * svgScale.x,
        top: (hoveredNode.cy + hoveredNode.h / 2 + 12) * svgScale.y,
        transform: "translateX(-50%)",
      }
    : undefined

  // Actualizamos la escala cuando cambia el tamaño del SVG renderizado.
  // Patrón useRef + useEffect (no callback ref con setState) para evitar
  // loop infinito: callback ref se ejecuta en cada render y dispara setState,
  // que dispara re-render, que vuelve a invocar el callback ref...
  const svgElementRef = useRef<SVGSVGElement | null>(null)

  useEffect(() => {
    const svg = svgElementRef.current
    if (!svg) return
    const update = () => {
      const rect = svg.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        setSvgScale((prev) => {
          const next = { x: rect.width / VIEW_WIDTH, y: rect.height / VIEW_HEIGHT }
          // Evitar setState con valores idénticos (corta el bucle si React renderiza por otra razón).
          if (Math.abs(prev.x - next.x) < 0.001 && Math.abs(prev.y - next.y) < 0.001) {
            return prev
          }
          return next
        })
      }
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(svg)
    return () => ro.disconnect()
  }, [])

  return (
    <section
      id="arquitectura"
      className="relative w-full bg-bg px-6 py-32 md:px-12"
    >
      <div className="mx-auto max-w-7xl">
        {/* Header. */}
        <div className="mb-16 max-w-3xl">
          <motion.span
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8, ease: EASE_EXPO }}
            className="mb-6 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted"
          >
            <span className="inline-block h-px w-6 bg-border" />
            Arquitectura
          </motion.span>

          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1.0, ease: EASE_EXPO, delay: 0.05 }}
            className="font-serif font-medium leading-[1.02] tracking-[-0.022em] text-ink"
            style={{ fontSize: "clamp(2.25rem, 4.5vw, 3.5rem)" }}
          >
            Once servicios, cuatro bases, tres frontends.
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1.0, ease: EASE_EXPO, delay: 0.15 }}
            className="mt-6 max-w-2xl text-base leading-relaxed text-muted md:text-lg"
          >
            Plano académico-operacional y plano pedagógico-evaluativo,
            desacoplados por bus Redis Streams.
          </motion.p>
        </div>

        {/* Contenedor del diagrama. */}
        <div
          ref={containerRef}
          className="relative overflow-x-auto rounded-lg border border-border bg-bg-elevated p-6 md:p-12"
        >
          <div className="relative mx-auto" style={{ minWidth: 900 }}>
            <svg
              ref={svgElementRef}
              viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
              preserveAspectRatio="xMidYMid meet"
              className="block h-auto w-full"
              role="img"
              aria-label="Diagrama de arquitectura: 3 frontends, api-gateway, 9 servicios en 3 planos, Postgres y Redis"
            >
              {/* Etiquetas de plano (mono uppercase). */}
              <PlanoLabel x={X_COL_LEFT} y={Y_PLANO_LABEL} text="Académico-operacional" />
              <PlanoLabel x={X_COL_CENTER} y={Y_PLANO_LABEL} text="Pedagógico-evaluativo" />
              <PlanoLabel x={X_COL_RIGHT} y={Y_PLANO_LABEL} text="Transversal" />

              {/* Líneas (path drawing). Se dibujan ANTES que los nodos para quedar debajo. */}
              {LINES.map((line) => {
                const from = nodeById(line.from)
                const to = nodeById(line.to)
                const d = pathBetween(from, to)
                // Delay base por stage, para encadenar visualmente con la entrada de nodos.
                const baseDelay = 0.6 + (line.stage - 1) * 0.5
                const isHighlighted =
                  hoveredId !== null &&
                  (hoveredId === line.from || hoveredId === line.to)
                return (
                  <motion.path
                    key={line.id}
                    d={d}
                    fill="none"
                    stroke={isHighlighted ? "var(--color-accent)" : "var(--color-border)"}
                    strokeWidth={isHighlighted ? 1.5 : 1}
                    initial={{ pathLength: 0, opacity: 0 }}
                    whileInView={{ pathLength: 1, opacity: 1 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{
                      pathLength: { duration: 0.7, ease: EASE_EXPO, delay: baseDelay },
                      opacity: { duration: 0.2, delay: baseDelay },
                      stroke: { duration: 0.2 },
                    }}
                  />
                )
              })}

              {/* Nodos. Cada uno entra con fade-up + stagger por kind/group. */}
              {NODES.map((node) => {
                const delay = nodeDelay(node)
                const isHovered = hoveredId === node.id
                return (
                  <Node
                    key={node.id}
                    node={node}
                    delay={delay}
                    hovered={isHovered}
                    onEnter={() => setHoveredId(node.id)}
                    onLeave={() => setHoveredId(null)}
                  />
                )
              })}
            </svg>

            {/* Tooltip flotante (HTML overlay sobre el SVG). */}
            {hoveredNode && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, ease: EASE_EXPO }}
                className="pointer-events-none absolute z-20 max-w-xs whitespace-normal rounded-md border border-border bg-bg-elevated px-3 py-2 font-sans text-xs leading-snug text-ink shadow-sm"
                style={tooltipStyle}
              >
                <span className="block font-mono text-[10px] uppercase tracking-wider text-muted">
                  {hoveredNode.label}
                </span>
                <span className="mt-1 block text-ink-soft">{hoveredNode.tooltip}</span>
              </motion.div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------- Sub-componentes ----------

function PlanoLabel({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <motion.text
      x={x}
      y={y}
      textAnchor="middle"
      className="fill-muted font-mono"
      style={{ fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase" }}
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, ease: EASE_EXPO, delay: 0.7 }}
    >
      {text.toUpperCase()}
    </motion.text>
  )
}

function Node({
  node,
  delay,
  hovered,
  onEnter,
  onLeave,
}: {
  node: DiagramNode
  delay: number
  hovered: boolean
  onEnter: () => void
  onLeave: () => void
}) {
  const x = node.cx - node.w / 2
  const y = node.cy - node.h / 2

  const fill = hovered ? "var(--color-accent-soft)" : "#FFFFFF"
  const stroke = hovered ? "var(--color-accent)" : "var(--color-border)"
  const strokeWidth = hovered ? 1.5 : 1

  return (
    <motion.g
      style={{
        transformOrigin: `${node.cx}px ${node.cy}px`,
        cursor: "pointer",
      }}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, ease: EASE_EXPO, delay }}
      animate={{ scale: hovered ? 1.03 : 1 }}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onFocus={onEnter}
      onBlur={onLeave}
      tabIndex={0}
      aria-label={`${node.label} ${node.sublabel}`}
    >
      <rect
        x={x}
        y={y}
        width={node.w}
        height={node.h}
        rx={8}
        ry={8}
        fill={fill}
        stroke={stroke}
        strokeWidth={strokeWidth}
        style={{ transition: "fill 0.18s ease, stroke 0.18s ease" }}
      />
      <text
        x={node.cx}
        y={node.cy - 4}
        textAnchor="middle"
        dominantBaseline="middle"
        className="fill-ink"
        style={{ fontSize: node.kind === "gateway" ? 16 : 14, fontWeight: 500 }}
      >
        {node.label}
      </text>
      <text
        x={node.cx}
        y={node.cy + 14}
        textAnchor="middle"
        dominantBaseline="middle"
        className="fill-muted font-mono"
        style={{ fontSize: 10 }}
      >
        {node.sublabel}
      </text>
    </motion.g>
  )
}

// ---------- Delays de entrada ----------

/**
 * Calcula el delay de entrada de un nodo según su rol en el flujo.
 *  - frontends: 0.0 - 0.2 (stagger horizontal)
 *  - gateway:   0.45
 *  - servicios: 1.15 + stagger por columna y fila
 *  - bases:     2.0 - 2.1
 */
function nodeDelay(node: DiagramNode): number {
  if (node.kind === "frontend") {
    const order = node.id === "web-admin" ? 0 : node.id === "web-teacher" ? 1 : 2
    return 0 + order * 0.1
  }
  if (node.kind === "gateway") return 0.45
  if (node.kind === "service") {
    const colOrder =
      node.group === "academic" ? 0 : node.group === "pedagogic" ? 1 : 2
    // Posición dentro de la columna: 0, 1, 2 (top→bottom).
    const rowIdx = Math.round(
      (node.cy - NODE_H / 2 - Y_SERVICES_START) / (NODE_H + SERVICE_VERTICAL_GAP),
    )
    return 1.15 + colOrder * 0.08 + rowIdx * 0.06
  }
  // db
  return node.id === "postgres" ? 2.0 : 2.1
}
