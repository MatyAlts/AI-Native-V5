/**
 * Intérprete de PSeInt (HU-030): recorre el árbol del parser.
 *
 * Está escrito con generadores: cada `Leer` hace `yield LEER` y el que maneja
 * la ejecución (`correr`) espera el dato con `await` y lo devuelve con
 * `next(valor)`. Así el mismo intérprete sirve para el `Leer` interactivo del
 * navegador (un diálogo por dato) y para la entrada por adelantado de Probar y
 * del servidor. Cada tanto también hace `yield CEDER` para devolverle el
 * control al event loop y no congelar la página en un ciclo largo.
 */

import { type Valor, formatear, formatearNumero } from "./formato"
import {
  type Destino,
  type Expr,
  type Funcion,
  type Instr,
  PREDEFINIDAS,
  type Programa,
  type Tipo,
} from "./parser"

export const LEER = Symbol("leer")
export const CEDER = Symbol("ceder")
type Pedido = typeof LEER | typeof CEDER
type Gen<T> = Generator<Pedido, T, string | undefined>

/** Cada cuántos pasos se cede el control al event loop. */
const PASOS_POR_CESION = 20_000
/** Más llamadas anidadas que esto es casi seguro una recursión sin caso base. */
const PROFUNDIDAD_MAXIMA = 1_000
/** Tolerancia de las comparaciones entre números, como PSeInt (`0.1+0.2 = 0.3`). */
const EPSILON = 1e-11
/** Las variables Enteras de PSeInt son de 32 bits. */
const ENTERO_MAXIMO = 2_147_483_647
const NUMERO = /^[+-]?(\d+\.?\d*|\.\d+)$/
const ENTERO = /^[+-]?\d+$/

export class ErrorEjecucion extends Error {
  constructor(
    public linea: number,
    public mensaje: string,
  ) {
    super(mensaje)
  }
}

export class LimiteExcedido extends Error {
  constructor(public linea: number) {
    super("limite")
  }
}

class Variable {
  arreglo: { dims: number[]; datos: (Valor | undefined)[] } | null = null
  constructor(
    public nombre: string,
    public tipo: Tipo | null,
    public valor: Valor | undefined,
  ) {}
}

/** Un elemento de arreglo pasado Por Referencia. */
class RefElemento {
  constructor(
    public variable: Variable,
    public pos: number,
    public nombre: string,
  ) {}
}

type Celda = Variable | RefElemento
type Marco = Map<string, Celda>

const NOMBRE_TIPO: Record<Tipo, string> = {
  entero: "Entero",
  real: "Real",
  caracter: "Caracter",
  logico: "Logico",
}

function porDefecto(tipo: Tipo): Valor {
  if (tipo === "caracter") return ""
  if (tipo === "logico") return false
  return 0
}

function tipoDe(v: Valor): Tipo {
  if (typeof v === "number") return "real"
  if (typeof v === "boolean") return "logico"
  return "caracter"
}

function describir(v: Valor): string {
  if (typeof v === "number") return "un número"
  if (typeof v === "boolean") return "un valor lógico"
  return "un texto"
}

export class Interprete {
  pasos = 0
  linea = 0
  salida = ""
  private profundidad = 0
  /** Variables de control de un `Para` en curso: no se pueden modificar. */
  private bloqueadas = new Set<Variable>()

  constructor(
    private programa: Programa,
    private emitir: (texto: string) => void,
    private maxPasos: number,
  ) {}

  *principal(): Gen<void> {
    yield* this.bloque(this.programa.cuerpo, new Map())
  }

  private error(linea: number, mensaje: string): never {
    throw new ErrorEjecucion(linea, mensaje)
  }

  /** Cuenta un paso. Devuelve `true` cuando toca ceder el control. */
  private contar(linea: number): boolean {
    this.linea = linea
    this.pasos++
    if (this.pasos > this.maxPasos) throw new LimiteExcedido(linea)
    return this.pasos % PASOS_POR_CESION === 0
  }

  private *bloque(instrs: Instr[], marco: Marco): Gen<void> {
    for (const s of instrs) yield* this.instr(s, marco)
  }

  // ── Variables ─────────────────────────────────────────────────────────

  private verificarTipo(tipo: Tipo | null, v: Valor, nombre: string, linea: number): void {
    if (tipo === null) return
    if (tipo === "entero" || tipo === "real") {
      if (typeof v !== "number") {
        this.error(
          linea,
          `No coinciden los tipos: ${nombre} es ${NOMBRE_TIPO[tipo]} y se le quiere asignar ${describir(v)}.`,
        )
      }
      if (tipo === "entero" && !Number.isInteger(v)) {
        this.error(
          linea,
          `No coinciden los tipos: ${nombre} es Entero y el valor a asignar (${formatearNumero(v)}) no es entero.`,
        )
      }
      if (tipo === "entero" && (v > ENTERO_MAXIMO || v < -ENTERO_MAXIMO - 1)) {
        this.error(
          linea,
          `El valor ${formatearNumero(v)} es demasiado grande para la variable Entera ${nombre}.`,
        )
      }
      return
    }
    if (tipoDe(v) !== tipo) {
      this.error(
        linea,
        `No coinciden los tipos: ${nombre} es ${NOMBRE_TIPO[tipo]} y se le quiere asignar ${describir(v)}.`,
      )
    }
  }

  private sinValor(nombre: string, linea: number): never {
    this.error(
      linea,
      `La variable ${nombre} se usa sin tener un valor: asignale uno con <- o con Leer antes de usarla.`,
    )
  }

  private posicion(v: Variable, indices: Valor[], nombre: string, linea: number): number {
    const arr = v.arreglo
    if (!arr)
      this.error(
        linea,
        `${nombre} no es un arreglo: hay que dimensionarlo con Dimension antes de usar subíndices.`,
      )
    if (indices.length !== arr.dims.length) {
      this.error(
        linea,
        `El arreglo ${nombre} tiene ${arr.dims.length} dimensión(es) y se usaron ${indices.length} subíndice(s).`,
      )
    }
    let pos = 0
    for (let d = 0; d < arr.dims.length; d++) {
      const i = indices[d]!
      if (typeof i !== "number" || !Number.isInteger(i)) {
        this.error(linea, `El subíndice de ${nombre} tiene que ser un número entero.`)
      }
      const tam = arr.dims[d]!
      if (i < 1 || i > tam) {
        this.error(
          linea,
          `Subíndice (${formatearNumero(i)}) fuera de rango (1...${tam}) en el arreglo ${nombre}.`,
        )
      }
      pos = pos * tam + (i - 1)
    }
    return pos
  }

  private *indices(es: Expr[], marco: Marco): Gen<Valor[]> {
    const vs: Valor[] = []
    for (const e of es) vs.push(yield* this.ev(e, marco))
    return vs
  }

  private arregloDe(marco: Marco, clave: string, nombre: string, linea: number): Variable {
    const c = marco.get(clave)
    if (!(c instanceof Variable) || !c.arreglo) {
      this.error(
        linea,
        `${nombre} no es un arreglo: hay que dimensionarlo con Dimension antes de usar subíndices.`,
      )
    }
    return c
  }

  private leerCelda(c: Celda | undefined, nombre: string, linea: number): Valor {
    if (c instanceof RefElemento) {
      const v = c.variable.arreglo!.datos[c.pos]
      if (v === undefined) this.sinValor(nombre, linea)
      return v
    }
    if (!c) this.sinValor(nombre, linea)
    if (c.arreglo) this.error(linea, `Faltan los subíndices del arreglo ${nombre}.`)
    if (c.valor === undefined) this.sinValor(nombre, linea)
    return c.valor
  }

  /** Guarda un valor en una celda escalar, controlando el tipo. */
  private guardarEnCelda(
    marco: Marco,
    clave: string,
    nombre: string,
    v: Valor,
    linea: number,
    forzar = false,
  ): void {
    let c = marco.get(clave)
    if (c instanceof RefElemento) {
      const va = c.variable
      this.verificarTipo(va.tipo, v, nombre, linea)
      if (va.tipo === null) va.tipo = tipoDe(v)
      va.arreglo!.datos[c.pos] = v
      return
    }
    if (!c) {
      c = new Variable(nombre, null, undefined)
      marco.set(clave, c)
    }
    if (c.arreglo) this.error(linea, `Faltan los subíndices del arreglo ${nombre}.`)
    if (!forzar && this.bloqueadas.has(c)) {
      this.error(
        linea,
        `No se puede modificar la variable ${nombre} dentro del Para que la usa como contador.`,
      )
    }
    this.verificarTipo(c.tipo, v, nombre, linea)
    if (c.tipo === null) c.tipo = tipoDe(v)
    c.valor = v
  }

  private *asignarDestino(d: Destino, v: Valor, marco: Marco, linea: number): Gen<void> {
    if (!d.indices) {
      this.guardarEnCelda(marco, d.clave, d.nombre, v, linea)
      return
    }
    const va = this.arregloDe(marco, d.clave, d.nombre, linea)
    const pos = this.posicion(va, yield* this.indices(d.indices, marco), d.nombre, linea)
    this.verificarTipo(va.tipo, v, d.nombre, linea)
    if (va.tipo === null) va.tipo = tipoDe(v)
    va.arreglo!.datos[pos] = v
  }

  private tipoDestino(d: Destino, marco: Marco, linea: number): Tipo | null {
    const c = marco.get(d.clave)
    if (d.indices) return this.arregloDe(marco, d.clave, d.nombre, linea).tipo
    if (c instanceof RefElemento) return c.variable.tipo
    return c?.tipo ?? null
  }

  private convertirEntrada(tipo: Tipo | null, texto: string, nombre: string, linea: number): Valor {
    switch (tipo) {
      case "entero":
        if (texto === "") return 0
        if (ENTERO.test(texto)) return Number(texto)
        if (NUMERO.test(texto)) {
          this.error(
            linea,
            `No coinciden los tipos: ${nombre} es Entero y el valor ingresado (${texto}) no es un entero.`,
          )
        }
        return this.error(
          linea,
          `No coinciden los tipos: ${nombre} es Entero y el valor ingresado (${texto}) no es un número.`,
        )
      case "real":
        if (texto === "") return 0
        if (NUMERO.test(texto)) return Number(texto)
        return this.error(
          linea,
          `No coinciden los tipos: ${nombre} es Real y el valor ingresado (${texto}) no es un número.`,
        )
      case "logico": {
        const t = texto.toUpperCase()
        if (t === "" || t === "FALSO" || t === "F" || t === "0") return false
        if (t === "VERDADERO" || t === "V" || t === "1") return true
        return this.error(
          linea,
          `No coinciden los tipos: ${nombre} es Logico; se esperaba Verdadero o Falso.`,
        )
      }
      case "caracter":
        return texto
      default:
        return NUMERO.test(texto) ? Number(texto) : texto
    }
  }

  // ── Instrucciones ─────────────────────────────────────────────────────

  private *condicion(e: Expr, marco: Marco, que: string, linea: number): Gen<boolean> {
    const v = yield* this.ev(e, marco)
    if (typeof v !== "boolean") {
      this.error(
        linea,
        `La condición del ${que} tiene que ser verdadera o falsa (una expresión lógica).`,
      )
    }
    return v
  }

  private *instr(s: Instr, marco: Marco): Gen<void> {
    if (this.contar(s.linea)) yield CEDER
    switch (s.k) {
      case "definir":
        for (const v of s.vars) this.definir(marco, v.clave, v.nombre, s.tipo, s.linea)
        return
      case "dimension":
        for (const d of s.decls) {
          const dims: number[] = []
          for (const e of d.dims) {
            const n = yield* this.ev(e, marco)
            if (typeof n !== "number" || !Number.isInteger(n) || n < 1) {
              this.error(
                s.linea,
                `El tamaño del arreglo ${d.nombre} tiene que ser un entero mayor que cero.`,
              )
            }
            dims.push(n)
          }
          let c = marco.get(d.clave)
          if (c instanceof RefElemento) this.error(s.linea, `${d.nombre} no se puede dimensionar.`)
          if (!c) {
            c = new Variable(d.nombre, null, undefined)
            marco.set(d.clave, c)
          }
          if (c.arreglo) this.error(s.linea, `El arreglo ${d.nombre} ya fue dimensionado.`)
          const total = dims.reduce((a, b) => a * b, 1)
          const ini = c.tipo ? porDefecto(c.tipo) : undefined
          c.arreglo = { dims, datos: new Array<Valor | undefined>(total).fill(ini) }
          c.valor = undefined
        }
        return
      case "asignar": {
        const v = yield* this.ev(s.e, marco)
        yield* this.asignarDestino(s.destino, v, marco, s.linea)
        return
      }
      case "leer":
        for (const d of s.destinos) {
          const tipo = this.tipoDestino(d, marco, s.linea)
          const texto = yield LEER
          if (texto === undefined) {
            this.error(s.linea, "Leer pidió un dato y no hay más datos de entrada.")
          }
          const v = this.convertirEntrada(tipo, texto, d.nombre, s.linea)
          yield* this.asignarDestino(d, v, marco, s.linea)
        }
        return
      case "escribir": {
        let texto = ""
        for (const e of s.exprs) texto += formatear(yield* this.ev(e, marco))
        if (s.saltar) texto += "\n"
        this.salida += texto
        this.emitir(texto)
        return
      }
      case "si":
        if (yield* this.condicion(s.cond, marco, "Si", s.linea))
          yield* this.bloque(s.entonces, marco)
        else if (s.sino) yield* this.bloque(s.sino, marco)
        return
      case "segun": {
        const v = yield* this.ev(s.e, marco)
        for (const caso of s.casos) {
          for (const e of caso.valores) {
            const cv = yield* this.ev(e, marco)
            if (typeof cv === typeof v && this.iguales(v, cv)) {
              yield* this.bloque(caso.cuerpo, marco)
              return
            }
          }
        }
        if (s.otro) yield* this.bloque(s.otro, marco)
        return
      }
      case "mientras":
        for (;;) {
          if (!(yield* this.condicion(s.cond, marco, "Mientras", s.linea))) return
          yield* this.bloque(s.cuerpo, marco)
          if (this.contar(s.linea)) yield CEDER
        }
      case "repetir":
        for (;;) {
          yield* this.bloque(s.cuerpo, marco)
          if (this.contar(s.linea)) yield CEDER
          const c = yield* this.condicion(s.cond, marco, "Repetir", s.linea)
          if (s.hastaQue ? c : !c) return
        }
      case "para":
        yield* this.para(s, marco)
        return
      case "llamada": {
        const f = this.programa.funciones.get(s.clave)
        if (!f) {
          this.error(
            s.linea,
            `${s.nombre} es una función predefinida: su resultado se usa en una expresión, por ejemplo  x <- ${s.nombre}(...)`,
          )
        }
        yield* this.llamar(f, s.args, marco, s.linea)
        return
      }
      case "nada":
        return
    }
  }

  private definir(marco: Marco, clave: string, nombre: string, tipo: Tipo, linea: number): void {
    const c = marco.get(clave)
    if (c instanceof RefElemento) {
      const v = c.variable.arreglo!.datos[c.pos]
      if (v !== undefined) this.verificarTipo(tipo, v, nombre, linea)
      return
    }
    if (!c) {
      marco.set(clave, new Variable(nombre, tipo, porDefecto(tipo)))
      return
    }
    if (c.arreglo) {
      c.tipo = tipo
      const datos = c.arreglo.datos
      for (let i = 0; i < datos.length; i++) {
        const v = datos[i]
        if (v === undefined) datos[i] = porDefecto(tipo)
        else this.verificarTipo(tipo, v, nombre, linea)
      }
      return
    }
    if (c.valor !== undefined) this.verificarTipo(tipo, c.valor, nombre, linea)
    else c.valor = porDefecto(tipo)
    c.tipo = tipo
  }

  private *para(s: Extract<Instr, { k: "para" }>, marco: Marco): Gen<void> {
    const numero = (v: Valor, que: string): number => {
      if (typeof v !== "number")
        this.error(s.linea, `El valor ${que} del Para tiene que ser un número.`)
      return v
    }
    const desde = numero(yield* this.ev(s.desde, marco), "inicial")
    const hasta = numero(yield* this.ev(s.hasta, marco), "final")
    // Sin `Con Paso`, si el inicio es mayor que el final cuenta hacia atrás.
    const paso = s.paso
      ? numero(yield* this.ev(s.paso, marco), "del paso")
      : desde <= hasta
        ? 1
        : -1
    this.guardarEnCelda(marco, s.clave, s.nombre, desde, s.linea)
    const celda = marco.get(s.clave)
    const variable = celda instanceof Variable ? celda : null
    if (variable) this.bloqueadas.add(variable)
    try {
      for (let v = desde; paso >= 0 ? v <= hasta : v >= hasta; v += paso) {
        if (this.contar(s.linea)) yield CEDER
        this.guardarEnCelda(marco, s.clave, s.nombre, v, s.linea, true)
        yield* this.bloque(s.cuerpo, marco)
      }
    } finally {
      if (variable) this.bloqueadas.delete(variable)
    }
    // PSeInt oficial deja la variable de control en 0 al terminar el Para.
    this.guardarEnCelda(marco, s.clave, s.nombre, 0, s.linea, true)
  }

  private *llamar(f: Funcion, args: Expr[], marco: Marco, linea: number): Gen<Valor | undefined> {
    if (args.length !== f.params.length) {
      this.error(
        linea,
        `${f.nombre} espera ${f.params.length} dato(s) y se le pasaron ${args.length}.`,
      )
    }
    const nuevo: Marco = new Map()
    for (let i = 0; i < args.length; i++) {
      const p = f.params[i]!
      const a = args[i]!
      const celdaArg = a.k === "var" ? marco.get(a.clave) : undefined
      const esArreglo = celdaArg instanceof Variable && celdaArg.arreglo !== null
      const porReferencia = p.porReferencia ?? esArreglo
      if (porReferencia) {
        if (a.k === "var") {
          let c = celdaArg
          if (!c) {
            c = new Variable(a.nombre, null, undefined)
            marco.set(a.clave, c)
          }
          nuevo.set(p.clave, c)
        } else if (a.k === "idx") {
          const va = this.arregloDe(marco, a.clave, a.nombre, linea)
          const pos = this.posicion(va, yield* this.indices(a.indices, marco), a.nombre, linea)
          nuevo.set(p.clave, new RefElemento(va, pos, `${a.nombre}[...]`))
        } else {
          this.error(
            linea,
            `El parámetro ${p.nombre} de ${f.nombre} es Por Referencia: hay que pasarle una variable.`,
          )
        }
      } else if (esArreglo) {
        const original = celdaArg as Variable
        const copia = new Variable(p.nombre, original.tipo, undefined)
        copia.arreglo = { dims: [...original.arreglo!.dims], datos: [...original.arreglo!.datos] }
        nuevo.set(p.clave, copia)
      } else {
        const v = yield* this.ev(a, marco)
        nuevo.set(p.clave, new Variable(p.nombre, tipoDe(v), v))
      }
    }
    if (f.retorno && !nuevo.has(f.retorno.clave)) {
      nuevo.set(f.retorno.clave, new Variable(f.retorno.nombre, null, undefined))
    }
    this.profundidad++
    if (this.profundidad > PROFUNDIDAD_MAXIMA) {
      this.error(linea, "Demasiadas llamadas anidadas: revisá que la recursión tenga un caso base.")
    }
    try {
      yield* this.bloque(f.cuerpo, nuevo)
    } finally {
      this.profundidad--
    }
    if (!f.retorno) return undefined
    const c = nuevo.get(f.retorno.clave)
    const v = c instanceof RefElemento ? c.variable.arreglo!.datos[c.pos] : c?.valor
    if (v === undefined) {
      this.error(linea, `${f.nombre} terminó sin asignarle un valor a ${f.retorno.nombre}.`)
    }
    return v
  }

  // ── Expresiones ───────────────────────────────────────────────────────

  private iguales(a: Valor, b: Valor): boolean {
    if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < EPSILON
    return a === b
  }

  private *ev(e: Expr, marco: Marco): Gen<Valor> {
    switch (e.k) {
      case "num":
      case "str":
      case "bool":
        return e.v
      case "var":
        return this.leerCelda(marco.get(e.clave), e.nombre, e.linea)
      case "idx": {
        const va = this.arregloDe(marco, e.clave, e.nombre, e.linea)
        const pos = this.posicion(va, yield* this.indices(e.indices, marco), e.nombre, e.linea)
        const v = va.arreglo!.datos[pos]
        if (v === undefined) {
          this.error(e.linea, `El elemento del arreglo ${e.nombre} se usa sin tener un valor.`)
        }
        return v
      }
      case "call":
        return yield* this.llamada(e, marco)
      case "un": {
        const v = yield* this.ev(e.e, marco)
        if (e.op === "NO") {
          if (typeof v !== "boolean")
            this.error(e.linea, "NO se aplica a valores lógicos (Verdadero o Falso).")
          return !v
        }
        if (typeof v !== "number") this.error(e.linea, `El signo ${e.op} se aplica a números.`)
        return e.op === "-" ? -v : v
      }
      case "bin":
        return yield* this.binaria(e, marco)
    }
  }

  private *binaria(e: Extract<Expr, { k: "bin" }>, marco: Marco): Gen<Valor> {
    const linea = e.linea
    if (e.op === "Y" || e.op === "O") {
      // Cortocircuito, como PSeInt: `i <= n Y v[i] <> x` no evalúa v[i] de más.
      const l = yield* this.ev(e.l, marco)
      if (typeof l !== "boolean")
        this.error(linea, `Los operandos de ${e.op} tienen que ser lógicos.`)
      if (e.op === "Y" && !l) return false
      if (e.op === "O" && l) return true
      const r = yield* this.ev(e.r, marco)
      if (typeof r !== "boolean")
        this.error(linea, `Los operandos de ${e.op} tienen que ser lógicos.`)
      return r
    }
    const l = yield* this.ev(e.l, marco)
    const r = yield* this.ev(e.r, marco)
    switch (e.op) {
      case "+":
        if (typeof l === "number" && typeof r === "number") return l + r
        if (typeof l === "string" && typeof r === "string") return l + r
        return this.error(
          linea,
          `No coinciden los tipos: no se puede sumar ${describir(l)} con ${describir(r)}.`,
        )
      case "-":
      case "*":
      case "/":
      case "^":
      case "MOD": {
        if (typeof l !== "number" || typeof r !== "number") {
          this.error(linea, `No coinciden los tipos: el operador ${e.op} se aplica a números.`)
        }
        if (e.op === "-") return l - r
        if (e.op === "*") return l * r
        if (e.op === "/") {
          if (r === 0) this.error(linea, "División por cero.")
          return l / r
        }
        if (e.op === "^") return l ** r
        if (!Number.isInteger(l) || !Number.isInteger(r)) {
          this.error(linea, "Los operandos de MOD tienen que ser enteros.")
        }
        if (r === 0) this.error(linea, "El segundo operando de MOD no puede ser cero.")
        return l % r
      }
      default:
        return this.comparar(e.op, l, r, linea)
    }
  }

  private comparar(op: string, l: Valor, r: Valor, linea: number): boolean {
    if (typeof l !== typeof r) {
      this.error(
        linea,
        `No se pueden comparar valores de distinto tipo (${describir(l)} con ${describir(r)}).`,
      )
    }
    if (typeof l === "boolean" && op !== "=" && op !== "<>") {
      this.error(linea, `Los valores lógicos solo se comparan con = o <>, no con ${op}.`)
    }
    const igual = this.iguales(l, r)
    switch (op) {
      case "=":
        return igual
      case "<>":
        return !igual
      case "<":
        return !igual && l < r
      case ">":
        return !igual && l > r
      case "<=":
        return igual || l < r
      default:
        return igual || l > r
    }
  }

  private *llamada(e: Extract<Expr, { k: "call" }>, marco: Marco): Gen<Valor> {
    const f = this.programa.funciones.get(e.clave)
    if (f) {
      if (!f.retorno) {
        this.error(
          e.linea,
          `${f.nombre} no devuelve ningún valor, así que no se puede usar en una expresión.`,
        )
      }
      return (yield* this.llamar(f, e.args, marco, e.linea)) as Valor
    }
    const aridad = PREDEFINIDAS[e.clave]!
    if (e.args.length !== aridad) {
      this.error(e.linea, `${e.nombre} espera ${aridad} dato(s) y se le pasaron ${e.args.length}.`)
    }
    const args: Valor[] = []
    for (const a of e.args) args.push(yield* this.ev(a, marco))
    return this.predefinida(e.clave, e.nombre, args, e.linea)
  }

  private predefinida(clave: string, nombre: string, args: Valor[], linea: number): Valor {
    const num = (i: number): number => {
      const v = args[i]!
      if (typeof v !== "number")
        this.error(
          linea,
          `Tipo de dato incorrecto en el dato ${i + 1} de ${nombre}: se esperaba un número.`,
        )
      return v
    }
    const ent = (i: number): number => {
      const v = num(i)
      if (!Number.isInteger(v))
        this.error(
          linea,
          `Tipo de dato incorrecto en el dato ${i + 1} de ${nombre}: se esperaba un entero.`,
        )
      return v
    }
    const txt = (i: number): string => {
      const v = args[i]!
      if (typeof v !== "string")
        this.error(
          linea,
          `Tipo de dato incorrecto en el dato ${i + 1} de ${nombre}: se esperaba un texto.`,
        )
      return v
    }
    switch (clave) {
      case "TRUNC":
        return Math.trunc(num(0))
      case "REDON": {
        const x = num(0)
        return Math.sign(x) * Math.round(Math.abs(x))
      }
      case "RAIZ":
      case "RC": {
        const x = num(0)
        if (x < 0) this.error(linea, "Raíz cuadrada de un número negativo.")
        return Math.sqrt(x)
      }
      case "ABS":
        return Math.abs(num(0))
      case "LN": {
        const x = num(0)
        if (x <= 0) this.error(linea, "Logaritmo de cero o de un número negativo.")
        return Math.log(x)
      }
      case "EXP":
        return Math.exp(num(0))
      case "SEN":
        return Math.sin(num(0))
      case "COS":
        return Math.cos(num(0))
      case "TAN":
        return Math.tan(num(0))
      case "ASEN":
        return Math.asin(num(0))
      case "ACOS":
        return Math.acos(num(0))
      case "ATAN":
        return Math.atan(num(0))
      case "AZAR": {
        const n = ent(0)
        if (n < 1) this.error(linea, "azar necesita un número mayor que cero.")
        return Math.floor(Math.random() * n)
      }
      case "ALEATORIO": {
        let a = ent(0)
        let b = ent(1)
        if (a > b) [a, b] = [b, a]
        return a + Math.floor(Math.random() * (b - a + 1))
      }
      case "LONGITUD":
        return txt(0).length
      case "SUBCADENA": {
        const s = txt(0)
        const desde = ent(1)
        const hasta = ent(2)
        if (hasta < desde) return ""
        return s.slice(Math.max(desde - 1, 0), Math.max(hasta, 0))
      }
      case "MAYUSCULAS":
        return txt(0).toUpperCase()
      case "MINUSCULAS":
        return txt(0).toLowerCase()
      case "CONCATENAR":
        return txt(0) + txt(1)
      case "CONVERTIRANUMERO": {
        const s = txt(0)
        if (!NUMERO.test(s)) this.error(linea, `El texto ("${s}") no representa un número.`)
        return Number(s)
      }
      case "CONVERTIRATEXTO":
        return formatearNumero(num(0))
      default:
        return this.error(linea, `No existe la función ${nombre}.`)
    }
  }
}
