/**
 * Diagrama de flujo de un algoritmo PSeInt (HU-031).
 *
 * Solo pinta: las posiciones las calcula `construirDiagramas` de
 * `@platform/pseint` (el layout se prueba allá, sin DOM). SVG inline, sin
 * librerías de gráficos (DESIGN.md), con los tokens de color del tema para
 * que se lea igual en claro y en oscuro.
 *
 * Contrato del DOM (lo usan las pruebas y los lectores de pantalla):
 * - un `<svg role="img">` por diagrama (principal, funciones y subprocesos),
 *   con `aria-label` que nombra el algoritmo;
 * - cada forma es un `<g data-tipo="<TipoNodo>">` con su texto visible;
 * - una lista ordenada (`<ol>`) con los pasos en texto, para quien no ve el
 *   dibujo (oculta visualmente con `sr-only`, no con `display:none`);
 * - con un error de sintaxis no hay `<svg>`: se muestra un aviso con la línea.
 */
import {
  type AristaDiagrama,
  type Diagrama,
  type NodoDiagrama,
  type PuntoDiagrama,
  type TipoNodo,
  construirDiagramas,
} from "@platform/pseint"
import { useId, useMemo } from "react"

export interface DiagramaFlujoProps {
  /** Pseudocódigo PSeInt a dibujar. */
  fuente: string
  className?: string
}

const NOMBRE_TIPO: Record<TipoNodo, string> = {
  inicio: "Inicio",
  fin: "Fin",
  entrada: "Entrada",
  salida: "Salida",
  proceso: "Proceso",
  decision: "Decisión",
  para: "Para",
  llamada: "Llamada",
}

// Colores: solo tokens del tema (packages/ui/src/tokens/theme.css).
const TRAZO = "var(--color-border-strong)"
const RELLENO = "var(--color-surface)"
const TEXTO = "var(--color-ink)"
const ACENTO = "var(--color-accent-brand)"
const ACENTO_SUAVE = "var(--color-accent-brand-soft)"
const FLECHA = "var(--color-muted)"

export function DiagramaFlujo({ fuente, className }: DiagramaFlujoProps) {
  const resultado = useMemo(() => construirDiagramas(fuente), [fuente])
  if (!resultado.ok) {
    return (
      <div
        role="alert"
        className={`rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger ${className ?? ""}`}
      >
        <span className="font-semibold">Línea {resultado.error.linea}:</span>{" "}
        {resultado.error.mensaje}
      </div>
    )
  }
  const varios = resultado.diagramas.length > 1
  return (
    <div className={`space-y-4 ${className ?? ""}`}>
      {resultado.diagramas.map((d) => (
        <DibujoDiagrama key={d.nombre} diagrama={d} conTitulo={varios} />
      ))}
    </div>
  )
}

function DibujoDiagrama({ diagrama, conTitulo }: { diagrama: Diagrama; conTitulo: boolean }) {
  // `useId` trae caracteres que no van en un `url(#…)`.
  const idFlecha = `flecha-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`
  const anclas = useMemo(() => anclasDeEtiquetas(diagrama.aristas), [diagrama.aristas])
  return (
    <figure className="m-0">
      {conTitulo && (
        <figcaption className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
          {diagrama.nombre}
        </figcaption>
      )}
      <div className="overflow-x-auto rounded-md border border-border-soft bg-surface p-2">
        <svg
          role="img"
          aria-label={`Diagrama de flujo de ${diagrama.nombre}`}
          width={diagrama.ancho}
          height={diagrama.alto}
          viewBox={`0 0 ${diagrama.ancho} ${diagrama.alto}`}
          className="block font-mono"
          style={{ maxWidth: "none" }}
        >
          <defs>
            <marker
              id={idFlecha}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={FLECHA} />
            </marker>
          </defs>
          {diagrama.aristas.map((a, k) => (
            <path
              // biome-ignore lint/suspicious/noArrayIndexKey: el orden de las aristas es fijo para un mismo diagrama.
              key={k}
              d={camino(a.puntos)}
              fill="none"
              stroke={FLECHA}
              strokeWidth={1.4}
              markerEnd={`url(#${idFlecha})`}
            />
          ))}
          {diagrama.nodos.map((n) => (
            <Forma key={n.id} nodo={n} />
          ))}
          {diagrama.aristas.map((a, k) =>
            a.etiqueta ? (
              <text
                // biome-ignore lint/suspicious/noArrayIndexKey: idem aristas.
                key={k}
                x={anclas[k]!.x}
                y={anclas[k]!.y}
                fontSize={11}
                fontWeight={600}
                fill={ACENTO}
                textAnchor="start"
              >
                {a.etiqueta}
              </text>
            ) : null,
          )}
        </svg>
      </div>
      <ol className="sr-only">
        {pasos(diagrama).map((p, k) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: un paso por nodo, en orden.
          <li key={k}>{p}</li>
        ))}
      </ol>
    </figure>
  )
}

function camino(puntos: PuntoDiagrama[]): string {
  return puntos.map((p, k) => `${k === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ")
}

function Forma({ nodo }: { nodo: NodoDiagrama }) {
  const { x, y, ancho: w, alto: h } = nodo
  const destacada = nodo.tipo === "decision" || nodo.tipo === "para"
  const comun = {
    fill: destacada ? ACENTO_SUAVE : RELLENO,
    stroke: destacada ? ACENTO : TRAZO,
    strokeWidth: 1.4,
  }
  let forma: React.ReactNode
  switch (nodo.tipo) {
    case "inicio":
    case "fin":
      forma = <rect x={x} y={y} width={w} height={h} rx={h / 2} {...comun} />
      break
    case "entrada":
    case "salida": {
      const s = 12
      forma = (
        <polygon
          points={puntos([x + s, y], [x + w, y], [x + w - s, y + h], [x, y + h])}
          {...comun}
        />
      )
      break
    }
    case "decision":
      forma = (
        <polygon
          points={puntos([x + w / 2, y], [x + w, y + h / 2], [x + w / 2, y + h], [x, y + h / 2])}
          {...comun}
        />
      )
      break
    case "para": {
      const s = 14
      forma = (
        <polygon
          points={puntos(
            [x + s, y],
            [x + w - s, y],
            [x + w, y + h / 2],
            [x + w - s, y + h],
            [x + s, y + h],
            [x, y + h / 2],
          )}
          {...comun}
        />
      )
      break
    }
    case "llamada":
      forma = (
        <>
          <rect x={x} y={y} width={w} height={h} {...comun} />
          <line x1={x + 8} y1={y} x2={x + 8} y2={y + h} stroke={TRAZO} strokeWidth={1.4} />
          <line x1={x + w - 8} y1={y} x2={x + w - 8} y2={y + h} stroke={TRAZO} strokeWidth={1.4} />
        </>
      )
      break
    default:
      forma = <rect x={x} y={y} width={w} height={h} {...comun} />
  }
  return (
    <g data-tipo={nodo.tipo} data-linea={nodo.linea}>
      {forma}
      <text
        x={x + w / 2}
        y={y + h / 2}
        fontSize={12}
        fill={TEXTO}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {nodo.etiqueta}
      </text>
    </g>
  )
}

function puntos(...ps: [number, number][]): string {
  return ps.map(([a, b]) => `${a},${b}`).join(" ")
}

/**
 * Dónde va la etiqueta (V/F/caso) de cada arista. Si la arista sale sola de
 * su punto (las puntas del rombo de un `Si`), va pegada a la salida. Si
 * varias comparten el tronco (las ramas de un `Segun`), va donde la rama se
 * separa del tronco.
 */
function anclasDeEtiquetas(aristas: AristaDiagrama[]): PuntoDiagrama[] {
  const salidas = new Map<string, number>()
  const clave = (a: AristaDiagrama) => `${a.desde}@${a.puntos[0]!.x},${a.puntos[0]!.y}`
  for (const a of aristas) salidas.set(clave(a), (salidas.get(clave(a)) ?? 0) + 1)
  return aristas.map((a) => {
    const [p0, p1] = [a.puntos[0]!, a.puntos[1]!]
    if ((salidas.get(clave(a)) ?? 0) > 1) {
      const codo = a.puntos.find((p) => p.x !== p0.x)
      if (codo) return { x: codo.x + 4, y: codo.y - 4 }
      return { x: p0.x + 4, y: (p0.y + p1.y) / 2 + 4 }
    }
    if (p0.y === p1.y) {
      // Sale en horizontal: la etiqueta arriba del tramo.
      const hacia = p1.x >= p0.x ? 1 : -1
      return { x: p0.x + hacia * 6 - (hacia < 0 ? 8 : 0), y: p0.y - 5 }
    }
    // Sale en vertical: al costado del tramo.
    return { x: p0.x + 5, y: p0.y + 14 }
  })
}

/** Un paso por forma, en el orden del dibujo, con a dónde sigue. */
function pasos(d: Diagrama): string[] {
  const numero = new Map(d.nodos.map((n, k) => [n.id, k + 1]))
  return d.nodos.map((n, k) => {
    const texto = `${NOMBRE_TIPO[n.tipo]}: ${n.etiqueta}.`
    const sale = d.aristas.filter((a) => a.desde === n.id)
    if (sale.length === 0) return texto
    if (sale.length === 1 && !sale[0]!.etiqueta) {
      const destino = numero.get(sale[0]!.hasta)
      return destino === k + 2 ? texto : `${texto} Sigue en el paso ${destino}.`
    }
    const partes = sale.map((a, j) => {
      const destino = numero.get(a.hasta)
      if (n.tipo === "para") {
        return `${j === 0 ? "en cada vuelta" : "al terminar"}, sigue en el paso ${destino}`
      }
      if (a.etiqueta === "V") return `si es Verdadero, sigue en el paso ${destino}`
      if (a.etiqueta === "F") return `si es Falso, sigue en el paso ${destino}`
      if (a.etiqueta === "De Otro Modo") return `en otro caso, sigue en el paso ${destino}`
      if (a.etiqueta) return `si vale ${a.etiqueta}, sigue en el paso ${destino}`
      return `sigue en el paso ${destino}`
    })
    return `${texto} ${partes.join("; ")}.`
  })
}
