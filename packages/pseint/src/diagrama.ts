/**
 * Diagramas de flujo de PSeInt (HU-031).
 *
 * Un diagrama es una estructura ya ubicada (con coordenadas): quien lo dibuja
 * (`DiagramaFlujo` en `@platform/ui`) solo pinta, no calcula posiciones. Así
 * el layout se prueba acá, sin DOM.
 *
 * El layout es propio y estructurado (sin librerías de grafos): cada bloque
 * del algoritmo se ubica como un árbol vertical sobre un eje central, las
 * ramas de un `Si`/`Segun` van lado a lado, y las vueltas de los ciclos
 * suben por un carril al costado del bloque. Las flechas son polilíneas
 * ortogonales. Es determinista: el mismo fuente da siempre el mismo dibujo.
 */
import type { ErrorPseint } from "./index"
import { type Expr, type Funcion, type Instr, parsear } from "./parser"

/**
 * Formas, con la convención de PSeInt:
 * - `inicio` / `fin`: terminal ovalado ("Algoritmo nombre" / "FinAlgoritmo").
 * - `entrada`: `Leer` (paralelogramo).
 * - `salida`: `Escribir` (paralelogramo).
 * - `proceso`: asignación o `Definir`/`Dimension` (rectángulo).
 * - `decision`: `Si`, `Mientras`, `Repetir…Hasta Que` y `Segun` (rombo).
 * - `para`: cabecera del `Para` (hexágono).
 * - `llamada`: llamada a un `SubProceso` como instrucción (rectángulo con
 *   doble borde lateral).
 */
export type TipoNodo =
  | "inicio"
  | "fin"
  | "entrada"
  | "salida"
  | "proceso"
  | "decision"
  | "para"
  | "llamada"

export interface NodoDiagrama {
  id: string
  tipo: TipoNodo
  /** Texto dentro de la forma, tal como lo escribiría PSeInt (p. ej. `Leer n`, `n <- n + 1`, `n > 0`). */
  etiqueta: string
  /** Línea del fuente, desde 1. */
  linea: number
  /** Esquina superior izquierda de la caja que contiene la forma. */
  x: number
  y: number
  ancho: number
  alto: number
}

export interface PuntoDiagrama {
  x: number
  y: number
}

export interface AristaDiagrama {
  desde: string
  hasta: string
  /**
   * "V"/"F" en las salidas de un `Si`, `Mientras` o `Repetir`; el valor del
   * caso (o "De Otro Modo") en las de un `Segun`; vacío en el resto.
   */
  etiqueta: string
  /** Polilínea de la flecha, del borde de `desde` al de `hasta`. Al menos 2 puntos. */
  puntos: PuntoDiagrama[]
}

export interface Diagrama {
  /** Nombre del algoritmo, función o subproceso. */
  nombre: string
  nodos: NodoDiagrama[]
  aristas: AristaDiagrama[]
  /** Tamaño total del dibujo: todos los nodos y puntos entran en [0, ancho] x [0, alto]. */
  ancho: number
  alto: number
}

export type ResultadoDiagrama =
  | { ok: true; diagramas: Diagrama[] }
  | { ok: false; error: ErrorPseint }

// ── Medidas ──────────────────────────────────────────────────────────────
// Pensadas para texto monoespaciado de ~12px (el que usa `DiagramaFlujo`).

/** Ancho aproximado de un carácter. */
const CARACTER = 7.5
/** Separación vertical entre bloques. */
const GAP_V = 36
/** Separación horizontal entre ramas. */
const GAP_H = 32
/** Distancia del carril de una vuelta al bloque que rodea. */
const CARRIL = 22
/** Margen alrededor de todo el dibujo. */
const MARGEN = 16
const ALTO_CAJA = 40
const ALTO_ROMBO = 60
const ANCHO_MIN = 96
/** Ancho que ocupa una rama vacía (un `Si` sin `SiNo`, un caso sin cuerpo). */
const ANCHO_RAMA_VACIA = 24

function anchoDe(tipo: TipoNodo, etiqueta: string): number {
  const texto = etiqueta.length * CARACTER
  switch (tipo) {
    case "decision":
      // El rombo necesita más ancho que el texto para que entre entre las puntas.
      return Math.max(ANCHO_MIN + 24, Math.round(texto * 1.5 + 40))
    case "entrada":
    case "salida":
    case "para":
      return Math.max(ANCHO_MIN, Math.round(texto + 48))
    default:
      return Math.max(ANCHO_MIN, Math.round(texto + 32))
  }
}

// ── Etiquetas: expresiones e instrucciones como texto PSeInt ─────────────

const PRECEDENCIA: Record<string, number> = {
  O: 1,
  Y: 2,
  "=": 4,
  "<>": 4,
  "<": 4,
  ">": 4,
  "<=": 4,
  ">=": 4,
  "+": 5,
  "-": 5,
  "*": 6,
  "/": 6,
  MOD: 6,
  "^": 8,
}

function precedencia(e: Expr): number {
  if (e.k === "bin") return PRECEDENCIA[e.op] ?? 9
  if (e.k === "un") return e.op === "NO" ? 3 : 7
  return 9
}

function numero(v: number): string {
  if (v === Math.PI) return "PI"
  return String(v)
}

function texto(e: Expr): string {
  switch (e.k) {
    case "num":
      return numero(e.v)
    case "str":
      return e.v.includes('"') ? `'${e.v}'` : `"${e.v}"`
    case "bool":
      return e.v ? "Verdadero" : "Falso"
    case "var":
      return e.nombre
    case "idx":
      return `${e.nombre}[${e.indices.map(texto).join(", ")}]`
    case "call":
      return `${e.nombre}(${e.args.map(texto).join(", ")})`
    case "un": {
      const p = e.op === "NO" ? 3 : 7
      const dentro = precedencia(e.e) < p ? `(${texto(e.e)})` : texto(e.e)
      return e.op === "NO" ? `NO ${dentro}` : `${e.op}${dentro}`
    }
    case "bin": {
      const p = precedencia(e)
      // Todos los operadores asocian a izquierda: el de la derecha con la
      // misma precedencia lleva paréntesis.
      const l = precedencia(e.l) < p ? `(${texto(e.l)})` : texto(e.l)
      const r = precedencia(e.r) <= p ? `(${texto(e.r)})` : texto(e.r)
      return `${l} ${e.op} ${r}`
    }
  }
}

const NOMBRE_TIPO: Record<string, string> = {
  entero: "Entero",
  real: "Real",
  caracter: "Caracter",
  logico: "Logico",
}

function destino(d: { nombre: string; indices: Expr[] | null }): string {
  return d.indices ? `${d.nombre}[${d.indices.map(texto).join(", ")}]` : d.nombre
}

// ── Construcción ─────────────────────────────────────────────────────────

interface Pendiente {
  desde: string
  etiqueta: string
  /** Polilínea hasta ahora; termina en la salida del bloque. */
  puntos: PuntoDiagrama[]
}

/**
 * Un bloque ubicado en coordenadas locales: el eje está en `x = 0`, puede
 * extenderse a izquierda (`izq`, negativo) y derecha (`der`). Se entra por
 * `(0, entradaY)` hacia el nodo `entrada`, y se sale por `(0, alto)` con las
 * flechas `pendientes`, que se completan al conocer el nodo siguiente.
 */
interface Bloque {
  izq: number
  der: number
  alto: number
  entrada: string
  entradaY: number
  nodos: NodoDiagrama[]
  aristas: AristaDiagrama[]
  pendientes: Pendiente[]
}

function moverPunto(p: PuntoDiagrama, dx: number, dy: number): PuntoDiagrama {
  return { x: p.x + dx, y: p.y + dy }
}

function mover(b: Bloque, dx: number, dy: number): Bloque {
  return {
    izq: b.izq + dx,
    der: b.der + dx,
    alto: b.alto + dy,
    entrada: b.entrada,
    entradaY: b.entradaY + dy,
    nodos: b.nodos.map((n) => ({ ...n, x: n.x + dx, y: n.y + dy })),
    aristas: b.aristas.map((a) => ({ ...a, puntos: a.puntos.map((p) => moverPunto(p, dx, dy)) })),
    pendientes: b.pendientes.map((p) => ({
      ...p,
      puntos: p.puntos.map((q) => moverPunto(q, dx, dy)),
    })),
  }
}

/** Cierra las pendientes llevándolas a `hasta`, agregando los puntos dados. */
function cerrar(pendientes: Pendiente[], hasta: string, extra: PuntoDiagrama[]): AristaDiagrama[] {
  return pendientes.map((p) => ({
    desde: p.desde,
    hasta,
    etiqueta: p.etiqueta,
    puntos: [...p.puntos, ...extra],
  }))
}

function extender(pendientes: Pendiente[], extra: PuntoDiagrama[]): Pendiente[] {
  return pendientes.map((p) => ({ ...p, puntos: [...p.puntos, ...extra] }))
}

class Constructor {
  private contador = 0
  /** Nodos en el orden del fuente (el orden de la lista accesible). */
  orden: string[] = []

  constructor(private lineas: string[]) {}

  private nodo(tipo: TipoNodo, etiqueta: string, linea: number, alto = ALTO_CAJA): NodoDiagrama {
    const id = `n${this.contador++}`
    this.orden.push(id)
    const ancho = anchoDe(tipo, etiqueta)
    // Centrado en el eje del bloque.
    return { id, tipo, etiqueta, linea, x: -ancho / 2, y: 0, ancho, alto }
  }

  simple(tipo: TipoNodo, etiqueta: string, linea: number): Bloque {
    const n = this.nodo(tipo, etiqueta, linea)
    return {
      izq: n.x,
      der: n.x + n.ancho,
      alto: n.alto,
      entrada: n.id,
      entradaY: 0,
      nodos: [n],
      aristas: [],
      pendientes: [{ desde: n.id, etiqueta: "", puntos: [{ x: 0, y: n.alto }] }],
    }
  }

  /** Apila bloques sobre el mismo eje. `null` si no hay ninguno. */
  secuencia(bloques: Bloque[]): Bloque | null {
    if (bloques.length === 0) return null
    let acumulado = bloques[0]!
    for (const siguiente of bloques.slice(1)) {
      const b = mover(siguiente, 0, acumulado.alto + GAP_V)
      acumulado = {
        izq: Math.min(acumulado.izq, b.izq),
        der: Math.max(acumulado.der, b.der),
        alto: b.alto,
        entrada: acumulado.entrada,
        entradaY: acumulado.entradaY,
        nodos: [...acumulado.nodos, ...b.nodos],
        aristas: [
          ...acumulado.aristas,
          ...cerrar(acumulado.pendientes, b.entrada, [{ x: 0, y: b.entradaY }]),
          ...b.aristas,
        ],
        pendientes: b.pendientes,
      }
    }
    return acumulado
  }

  cuerpo(instrs: Instr[]): Bloque | null {
    return this.secuencia(instrs.map((i) => this.instruccion(i)))
  }

  instruccion(i: Instr): Bloque {
    switch (i.k) {
      case "definir":
        return this.simple(
          "proceso",
          `Definir ${i.vars.map((v) => v.nombre).join(", ")} Como ${NOMBRE_TIPO[i.tipo]}`,
          i.linea,
        )
      case "dimension":
        return this.simple(
          "proceso",
          `Dimension ${i.decls.map((d) => `${d.nombre}[${d.dims.map(texto).join(", ")}]`).join(", ")}`,
          i.linea,
        )
      case "asignar":
        return this.simple("proceso", `${destino(i.destino)} <- ${texto(i.e)}`, i.linea)
      case "leer":
        return this.simple("entrada", `Leer ${i.destinos.map(destino).join(", ")}`, i.linea)
      case "escribir":
        return this.simple(
          "salida",
          `Escribir ${i.exprs.map(texto).join(", ")}${i.saltar ? "" : " Sin Saltar"}`,
          i.linea,
        )
      case "llamada":
        return this.simple("llamada", `${i.nombre}(${i.args.map(texto).join(", ")})`, i.linea)
      case "nada":
        // `LimpiarPantalla`, `Esperar…`: se muestra la línea tal como está.
        return this.simple("proceso", this.textoDeLinea(i.linea) || "(sin efecto)", i.linea)
      case "si":
        return this.si(i)
      case "mientras":
        return this.cicloArriba(
          this.nodo("decision", texto(i.cond), i.linea, ALTO_ROMBO),
          i.cuerpo,
          true,
        )
      case "para": {
        const paso = i.paso ? ` Con Paso ${texto(i.paso)}` : ""
        const cab = this.nodo(
          "para",
          `${i.nombre} <- ${texto(i.desde)} Hasta ${texto(i.hasta)}${paso}`,
          i.linea,
        )
        return this.cicloArriba(cab, i.cuerpo, false)
      }
      case "repetir":
        return this.repetir(i)
      case "segun":
        return this.segun(i)
    }
  }

  private textoDeLinea(linea: number): string {
    return (this.lineas[linea - 1] ?? "")
      .replace(/\/\/.*$/, "")
      .trim()
      .replace(/;$/, "")
      .trim()
  }

  /**
   * `Si`: rombo con F a la izquierda y V a la derecha (como PSeInt). Las dos
   * ramas bajan y se juntan debajo, sobre el eje.
   */
  private si(i: Extract<Instr, { k: "si" }>): Bloque {
    const rombo = this.nodo("decision", texto(i.cond), i.linea, ALTO_ROMBO)
    const v = this.cuerpo(i.entonces)
    const f = i.sino ? this.cuerpo(i.sino) : null
    const medio = rombo.alto / 2
    const yRamas = rombo.alto + GAP_V / 2
    const mitad = rombo.ancho / 2
    // Ejes de cada rama: afuera de las puntas del rombo y sin pisarse entre sí.
    const ejeF = -Math.max(mitad + CARRIL, (f ? f.der : ANCHO_RAMA_VACIA / 2) + GAP_H / 2)
    const ejeV = Math.max(mitad + CARRIL, (v ? -v.izq : ANCHO_RAMA_VACIA / 2) + GAP_H / 2)
    const ramaF = f ? mover(f, ejeF, yRamas) : null
    const ramaV = v ? mover(v, ejeV, yRamas) : null
    const yUnion = yRamas + Math.max(ramaF ? f!.alto : 0, ramaV ? v!.alto : 0) + GAP_V / 2

    const nodos = [rombo, ...(ramaV?.nodos ?? []), ...(ramaF?.nodos ?? [])]
    const aristas: AristaDiagrama[] = []
    const pendientes: Pendiente[] = []
    const rama = (b: Bloque | null, eje: number, etiqueta: "V" | "F") => {
      const salida = { x: etiqueta === "V" ? mitad : -mitad, y: medio }
      const codo = { x: eje, y: medio }
      const union = [
        { x: eje, y: yUnion },
        { x: 0, y: yUnion },
      ]
      if (b) {
        aristas.push({
          desde: rombo.id,
          hasta: b.entrada,
          etiqueta,
          puntos: [salida, codo, { x: eje, y: b.entradaY }],
        })
        aristas.push(...b.aristas)
        pendientes.push(...extender(b.pendientes, union))
      } else {
        pendientes.push({ desde: rombo.id, etiqueta, puntos: [salida, codo, ...union] })
      }
    }
    rama(ramaV, ejeV, "V")
    rama(ramaF, ejeF, "F")
    return {
      izq: Math.min(-mitad, ramaF ? ramaF.izq : ejeF - ANCHO_RAMA_VACIA / 2),
      der: Math.max(mitad, ramaV ? ramaV.der : ejeV + ANCHO_RAMA_VACIA / 2),
      alto: yUnion,
      entrada: rombo.id,
      entradaY: 0,
      nodos,
      aristas,
      pendientes,
    }
  }

  /**
   * `Mientras` y `Para`: la cabecera arriba, el cuerpo abajo y la vuelta por
   * el carril izquierdo hasta la punta izquierda de la cabecera. La salida
   * del ciclo sale por la derecha, baja por su carril y vuelve al eje.
   */
  private cicloArriba(cab: NodoDiagrama, instrs: Instr[], conVF: boolean): Bloque {
    const c = this.cuerpo(instrs)
    const medio = cab.alto / 2
    const mitad = cab.ancho / 2
    const yCuerpo = cab.alto + GAP_V
    const cuerpo = c ? mover(c, 0, yCuerpo) : null
    const yVuelta = (cuerpo ? cuerpo.alto : cab.alto) + GAP_V / 2
    const yFin = yVuelta + GAP_V / 2
    const xIzq = Math.min(-mitad, cuerpo ? cuerpo.izq : 0) - CARRIL
    const xDer = Math.max(mitad, cuerpo ? cuerpo.der : 0) + CARRIL
    const vuelta = [
      { x: 0, y: yVuelta },
      { x: xIzq, y: yVuelta },
      { x: xIzq, y: medio },
      { x: -mitad, y: medio },
    ]
    const aristas: AristaDiagrama[] = []
    if (cuerpo) {
      aristas.push({
        desde: cab.id,
        hasta: cuerpo.entrada,
        etiqueta: conVF ? "V" : "",
        puntos: [
          { x: 0, y: cab.alto },
          { x: 0, y: cuerpo.entradaY },
        ],
      })
      aristas.push(...cuerpo.aristas)
      aristas.push(...cerrar(cuerpo.pendientes, cab.id, vuelta))
    } else {
      // Cuerpo vacío: la vuelta sale y entra en la misma cabecera.
      aristas.push({
        desde: cab.id,
        hasta: cab.id,
        etiqueta: conVF ? "V" : "",
        puntos: [{ x: 0, y: cab.alto }, ...vuelta],
      })
    }
    return {
      izq: xIzq,
      der: xDer,
      alto: yFin,
      entrada: cab.id,
      entradaY: 0,
      nodos: [cab, ...(cuerpo?.nodos ?? [])],
      aristas,
      pendientes: [
        {
          desde: cab.id,
          etiqueta: conVF ? "F" : "",
          puntos: [
            { x: mitad, y: medio },
            { x: xDer, y: medio },
            { x: xDer, y: yFin },
            { x: 0, y: yFin },
          ],
        },
      ],
    }
  }

  /**
   * `Repetir…Hasta Que`: el cuerpo arriba y el rombo abajo. Con `Hasta Que`
   * se repite por F; con `Mientras Que`, por V. La vuelta sube por el carril
   * izquierdo y entra al cuerpo desde arriba.
   */
  private repetir(i: Extract<Instr, { k: "repetir" }>): Bloque {
    const c = this.cuerpo(i.cuerpo)
    const rombo = this.nodo("decision", texto(i.cond), i.cond.linea, ALTO_ROMBO)
    const repite = i.hastaQue ? "F" : "V"
    const sale = i.hastaQue ? "V" : "F"
    const yArriba = GAP_V / 4
    const yCuerpo = GAP_V / 2
    const cuerpo = c ? mover(c, 0, yCuerpo) : null
    const yRombo = cuerpo ? cuerpo.alto + GAP_V : yCuerpo
    const r = { ...rombo, y: yRombo }
    const mitad = r.ancho / 2
    const medio = yRombo + r.alto / 2
    const xIzq = Math.min(-mitad, cuerpo ? cuerpo.izq : 0) - CARRIL
    const aristas: AristaDiagrama[] = []
    if (cuerpo) {
      aristas.push(...cuerpo.aristas)
      aristas.push(...cerrar(cuerpo.pendientes, r.id, [{ x: 0, y: yRombo }]))
    }
    aristas.push({
      desde: r.id,
      hasta: cuerpo ? cuerpo.entrada : r.id,
      etiqueta: repite,
      puntos: [
        { x: -mitad, y: medio },
        { x: xIzq, y: medio },
        { x: xIzq, y: yArriba },
        { x: 0, y: yArriba },
        { x: 0, y: cuerpo ? cuerpo.entradaY : yRombo },
      ],
    })
    return {
      izq: xIzq,
      der: Math.max(mitad, cuerpo ? cuerpo.der : 0),
      alto: yRombo + r.alto,
      entrada: cuerpo ? cuerpo.entrada : r.id,
      entradaY: cuerpo ? cuerpo.entradaY : yRombo,
      nodos: [...(cuerpo?.nodos ?? []), r],
      aristas,
      pendientes: [{ desde: r.id, etiqueta: sale, puntos: [{ x: 0, y: yRombo + r.alto }] }],
    }
  }

  /**
   * `Segun`: del rombo baja un tronco que se reparte en una rama por caso,
   * más "De Otro Modo" (vacía si el fuente no la tiene: si ningún caso
   * coincide, el algoritmo sigue de largo). Las ramas se juntan debajo.
   */
  private segun(i: Extract<Instr, { k: "segun" }>): Bloque {
    const rombo = this.nodo("decision", texto(i.e), i.linea, ALTO_ROMBO)
    const ramas: { etiqueta: string; b: Bloque | null }[] = i.casos.map((c) => ({
      etiqueta: c.valores.map(texto).join(", "),
      b: this.cuerpo(c.cuerpo),
    }))
    ramas.push({ etiqueta: "De Otro Modo", b: i.otro ? this.cuerpo(i.otro) : null })

    // Ejes de izquierda a derecha, después se centra la fila bajo el rombo.
    const ejes: number[] = []
    let x = 0
    for (const [k, r] of ramas.entries()) {
      const izq = r.b ? -r.b.izq : ANCHO_RAMA_VACIA / 2
      const der = r.b ? r.b.der : ANCHO_RAMA_VACIA / 2
      // La etiqueta del caso va al lado del eje: se le deja lugar.
      const lugar = Math.max(der, r.etiqueta.length * CARACTER + 8)
      if (k > 0) x += izq
      ejes.push(x)
      x += lugar + GAP_H
    }
    const corrimiento = (ejes[0]! + ejes[ejes.length - 1]!) / 2
    const ejesCentrados = ejes.map((e) => e - corrimiento)

    const yTronco = rombo.alto + GAP_V / 2
    const yRamas = rombo.alto + GAP_V
    const ubicadas = ramas.map((r, k) => (r.b ? mover(r.b, ejesCentrados[k]!, yRamas) : null))
    const yUnion =
      yRamas + Math.max(0, ...ubicadas.map((b, k) => (b ? ramas[k]!.b!.alto : 0))) + GAP_V / 2

    const nodos = [rombo]
    const aristas: AristaDiagrama[] = []
    const pendientes: Pendiente[] = []
    let izq = -rombo.ancho / 2
    let der = rombo.ancho / 2
    for (const [k, r] of ramas.entries()) {
      const eje = ejesCentrados[k]!
      const b = ubicadas[k]!
      const tronco = [
        { x: 0, y: rombo.alto },
        { x: 0, y: yTronco },
        { x: eje, y: yTronco },
      ]
      const union = [
        { x: eje, y: yUnion },
        { x: 0, y: yUnion },
      ]
      if (b) {
        nodos.push(...b.nodos)
        aristas.push({
          desde: rombo.id,
          hasta: b.entrada,
          etiqueta: r.etiqueta,
          puntos: [...tronco, { x: eje, y: b.entradaY }],
        })
        aristas.push(...b.aristas)
        pendientes.push(...extender(b.pendientes, union))
        izq = Math.min(izq, b.izq)
        der = Math.max(der, b.der)
      } else {
        pendientes.push({ desde: rombo.id, etiqueta: r.etiqueta, puntos: [...tronco, ...union] })
        izq = Math.min(izq, eje - ANCHO_RAMA_VACIA / 2)
        der = Math.max(der, eje + ANCHO_RAMA_VACIA / 2)
      }
      der = Math.max(der, eje + r.etiqueta.length * CARACTER + 8)
    }
    return { izq, der, alto: yUnion, entrada: rombo.id, entradaY: 0, nodos, aristas, pendientes }
  }
}

/** Quita puntos repetidos y los intermedios de un tramo recto. */
function limpiar(puntos: PuntoDiagrama[]): PuntoDiagrama[] {
  const sinRepetir: PuntoDiagrama[] = []
  for (const p of puntos) {
    const u = sinRepetir[sinRepetir.length - 1]
    if (!u || u.x !== p.x || u.y !== p.y) sinRepetir.push(p)
  }
  const salida: PuntoDiagrama[] = []
  for (const [k, p] of sinRepetir.entries()) {
    const a = salida[salida.length - 1]
    const b = sinRepetir[k + 1]
    if (a && b && ((a.x === p.x && p.x === b.x) || (a.y === p.y && p.y === b.y))) continue
    salida.push(p)
  }
  if (salida.length === 1) salida.push({ ...salida[0]! })
  return salida
}

function redondear(v: number): number {
  return Math.round(v * 10) / 10
}

/** Lleva todo a coordenadas positivas con margen y fija el tamaño total. */
function terminar(nombre: string, b: Bloque, orden: string[]): Diagrama {
  const xs: number[] = []
  const ys: number[] = []
  for (const n of b.nodos) {
    xs.push(n.x, n.x + n.ancho)
    ys.push(n.y, n.y + n.alto)
  }
  for (const a of b.aristas) {
    for (const p of a.puntos) {
      xs.push(p.x)
      ys.push(p.y)
    }
  }
  const dx = MARGEN - Math.min(...xs)
  const dy = MARGEN - Math.min(...ys)
  const pos = new Map(orden.map((id, k) => [id, k]))
  const nodos = b.nodos
    .map((n) => ({
      ...n,
      x: redondear(n.x + dx),
      y: redondear(n.y + dy),
      ancho: redondear(n.ancho),
      alto: redondear(n.alto),
    }))
    .sort((p, q) => (pos.get(p.id) ?? 0) - (pos.get(q.id) ?? 0))
  const aristas = b.aristas.map((a) => ({
    ...a,
    puntos: limpiar(a.puntos.map((p) => ({ x: redondear(p.x + dx), y: redondear(p.y + dy) }))),
  }))
  return {
    nombre,
    nodos,
    aristas,
    ancho: Math.ceil(Math.max(...xs) + dx + MARGEN),
    alto: Math.ceil(Math.max(...ys) + dy + MARGEN),
  }
}

function lineaDeCierre(lineas: string[], desde: number, cierre: RegExp): number {
  for (let k = desde; k < lineas.length; k++) {
    if (cierre.test(lineas[k]!.trim())) return k + 1
  }
  return desde + 1
}

function diagramaDe(
  lineas: string[],
  nombre: string,
  inicio: string,
  fin: string,
  linea: number,
  cuerpo: Instr[],
): Diagrama {
  const c = new Constructor(lineas)
  const bloques = [c.simple("inicio", inicio, linea)]
  bloques.push(...cuerpo.map((i) => c.instruccion(i)))
  const lineaFin = lineaDeCierre(
    lineas,
    linea,
    /^Fin(Algoritmo|Proceso|Funcion|SubProceso|SubAlgoritmo)\b/i,
  )
  bloques.push(c.simple("fin", fin, lineaFin))
  return terminar(nombre, c.secuencia(bloques)!, c.orden)
}

function cabeceraDeFuncion(f: Funcion, lineas: string[]): { inicio: string; fin: string } {
  const palabra = /^\s*(SubProceso|SubAlgoritmo)\b/i.exec(lineas[f.linea - 1] ?? "")
  const clase = palabra
    ? palabra[1]!.toLowerCase() === "subproceso"
      ? "SubProceso"
      : "SubAlgoritmo"
    : "Funcion"
  const params = f.params
    .map(
      (p) =>
        p.nombre +
        (p.porReferencia === true
          ? " Por Referencia"
          : p.porReferencia === false
            ? " Por Valor"
            : ""),
    )
    .join(", ")
  const retorno = f.retorno ? `${f.retorno.nombre} <- ` : ""
  return { inicio: `${clase} ${retorno}${f.nombre}(${params})`, fin: `Fin${clase}` }
}

/**
 * Arma un diagrama por algoritmo: primero el `Algoritmo`/`Proceso` principal
 * y después cada `Funcion`/`SubProceso` en el orden del fuente. Con un error
 * de sintaxis no dibuja nada y devuelve el error (línea y mensaje).
 */
export function construirDiagramas(fuente: string): ResultadoDiagrama {
  const { programa, error } = parsear(fuente)
  if (!programa) {
    return {
      ok: false,
      error: { linea: error?.linea ?? 1, mensaje: error?.mensaje ?? "Error de sintaxis." },
    }
  }
  const lineas = fuente.replace(/\r\n?/g, "\n").split("\n")
  const esProceso = /^\s*Proceso\b/i.test(lineas[programa.linea - 1] ?? "")
  const clase = esProceso ? "Proceso" : "Algoritmo"
  const diagramas = [
    diagramaDe(
      lineas,
      programa.nombre,
      `${clase} ${programa.nombre}`,
      `Fin${clase}`,
      programa.linea,
      programa.cuerpo,
    ),
  ]
  // `funciones` es un Map: conserva el orden en que aparecen en el fuente.
  for (const f of programa.funciones.values()) {
    const { inicio, fin } = cabeceraDeFuncion(f, lineas)
    diagramas.push(diagramaDe(lineas, f.nombre, inicio, fin, f.linea, f.cuerpo))
  }
  return { ok: true, diagramas }
}
