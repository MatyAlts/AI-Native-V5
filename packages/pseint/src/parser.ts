/**
 * Parser de PSeInt (HU-030): de tokens a árbol de sintaxis.
 *
 * Todo error de sintaxis se detecta acá, ANTES de ejecutar (C04): un programa
 * con un error no ejecuta ninguna instrucción. Los mensajes están pensados
 * para el alumno y llevan la línea del fuente. Cuando falta cerrar una
 * estructura (`Si` sin `FinSi`), la línea es la de la estructura abierta,
 * igual que PSeInt oficial.
 */

import { type Token, analizar } from "./lexer"

export type Tipo = "entero" | "real" | "caracter" | "logico"

export type Expr =
  | { k: "num"; v: number; linea: number }
  | { k: "str"; v: string; linea: number }
  | { k: "bool"; v: boolean; linea: number }
  | { k: "var"; nombre: string; clave: string; linea: number }
  | { k: "idx"; nombre: string; clave: string; indices: Expr[]; linea: number }
  | { k: "call"; nombre: string; clave: string; args: Expr[]; linea: number }
  | { k: "un"; op: "-" | "+" | "NO"; e: Expr; linea: number }
  | { k: "bin"; op: string; l: Expr; r: Expr; linea: number }

export interface Destino {
  nombre: string
  clave: string
  indices: Expr[] | null
  linea: number
}

export type Instr =
  | { k: "definir"; vars: { nombre: string; clave: string }[]; tipo: Tipo; linea: number }
  | { k: "dimension"; decls: { nombre: string; clave: string; dims: Expr[] }[]; linea: number }
  | { k: "asignar"; destino: Destino; e: Expr; linea: number }
  | { k: "leer"; destinos: Destino[]; linea: number }
  | { k: "escribir"; exprs: Expr[]; saltar: boolean; linea: number }
  | { k: "si"; cond: Expr; entonces: Instr[]; sino: Instr[] | null; linea: number }
  | {
      k: "segun"
      e: Expr
      casos: { valores: Expr[]; cuerpo: Instr[] }[]
      otro: Instr[] | null
      linea: number
    }
  | { k: "mientras"; cond: Expr; cuerpo: Instr[]; linea: number }
  | { k: "repetir"; cuerpo: Instr[]; cond: Expr; hastaQue: boolean; linea: number }
  | {
      k: "para"
      nombre: string
      clave: string
      desde: Expr
      hasta: Expr
      paso: Expr | null
      cuerpo: Instr[]
      linea: number
    }
  | { k: "llamada"; nombre: string; clave: string; args: Expr[]; linea: number }
  | { k: "nada"; linea: number }

export interface Parametro {
  nombre: string
  clave: string
  /** `true` = Por Referencia, `false` = Por Valor, `null` = sin indicar. */
  porReferencia: boolean | null
}

export interface Funcion {
  nombre: string
  clave: string
  linea: number
  retorno: { nombre: string; clave: string } | null
  params: Parametro[]
  cuerpo: Instr[]
}

export interface Programa {
  nombre: string
  clave: string
  linea: number
  cuerpo: Instr[]
  funciones: Map<string, Funcion>
}

export class ErrorSintaxis extends Error {
  constructor(
    public linea: number,
    public mensaje: string,
  ) {
    super(mensaje)
  }
}

/** Funciones predefinidas: nombre normalizado → cantidad de argumentos. */
export const PREDEFINIDAS: Record<string, number> = {
  TRUNC: 1,
  REDON: 1,
  RAIZ: 1,
  RC: 1,
  ABS: 1,
  LN: 1,
  EXP: 1,
  SEN: 1,
  COS: 1,
  TAN: 1,
  ASEN: 1,
  ACOS: 1,
  ATAN: 1,
  AZAR: 1,
  ALEATORIO: 2,
  LONGITUD: 1,
  SUBCADENA: 3,
  MAYUSCULAS: 1,
  MINUSCULAS: 1,
  CONCATENAR: 2,
  CONVERTIRANUMERO: 1,
  CONVERTIRATEXTO: 1,
}

const TIPOS: Record<string, Tipo> = {
  ENTERO: "entero",
  ENTERA: "entero",
  REAL: "real",
  NUMERO: "real",
  NUMERICO: "real",
  NUMERICA: "real",
  CARACTER: "caracter",
  CARACTERES: "caracter",
  TEXTO: "caracter",
  CADENA: "caracter",
  LOGICO: "logico",
  LOGICA: "logico",
}

/** Palabras que no pueden ser nombres de variables ni de funciones. */
export const RESERVADAS = new Set([
  "ALGORITMO",
  "FINALGORITMO",
  "PROCESO",
  "FINPROCESO",
  "DEFINIR",
  "COMO",
  "DIMENSION",
  "LEER",
  "ESCRIBIR",
  "IMPRIMIR",
  "MOSTRAR",
  "SINSALTAR",
  "SI",
  "ENTONCES",
  "SINO",
  "FINSI",
  "SEGUN",
  "HACER",
  "DEOTROMODO",
  "FINSEGUN",
  "MIENTRAS",
  "FINMIENTRAS",
  "REPETIR",
  "HASTAQUE",
  "MIENTRASQUE",
  "PARA",
  "HASTA",
  "CONPASO",
  "FINPARA",
  "FUNCION",
  "FINFUNCION",
  "SUBPROCESO",
  "FINSUBPROCESO",
  "SUBALGORITMO",
  "FINSUBALGORITMO",
  "PORREFERENCIA",
  "PORVALOR",
  "Y",
  "O",
  "NO",
  "MOD",
  "VERDADERO",
  "FALSO",
  "PI",
  "LIMPIARPANTALLA",
  "ESPERARTECLA",
  ...Object.keys(TIPOS),
])

/** Palabras que cierran un bloque (o lo parten, como `SiNo`). */
const CIERRES = new Set([
  "FINALGORITMO",
  "FINPROCESO",
  "FINSI",
  "SINO",
  "FINSEGUN",
  "DEOTROMODO",
  "FINMIENTRAS",
  "HASTAQUE",
  "MIENTRASQUE",
  "FINPARA",
  "FINFUNCION",
  "FINSUBPROCESO",
  "FINSUBALGORITMO",
])

const CIERRES_DE_NIVEL_SUPERIOR = new Set([
  "FINALGORITMO",
  "FINPROCESO",
  "FINFUNCION",
  "FINSUBPROCESO",
  "FINSUBALGORITMO",
])

const INICIOS_FUNCION: Record<string, string[]> = {
  FUNCION: ["FINFUNCION", "FINSUBPROCESO", "FINSUBALGORITMO"],
  SUBPROCESO: ["FINSUBPROCESO", "FINFUNCION", "FINSUBALGORITMO"],
  SUBALGORITMO: ["FINSUBALGORITMO", "FINFUNCION", "FINSUBPROCESO"],
}

interface Uso {
  clave: string
  nombre: string
  linea: number
  /** Si se usa como función (llamada) en vez de como variable. */
  llamada: boolean
}

class Parser {
  private i = 0
  /** Cada identificador usado como variable o llamada, en orden de aparición. */
  usos: Uso[] = []

  constructor(private toks: Token[]) {}

  private get act(): Token {
    return this.toks[this.i]!
  }

  private sig(n = 1): Token {
    return this.toks[Math.min(this.i + n, this.toks.length - 1)]!
  }

  private avanzar(): Token {
    const t = this.act
    if (t.t === "err") throw new ErrorSintaxis(t.linea, t.v)
    if (t.t !== "eof") this.i++
    return t
  }

  /** Revisa el token actual; un token de error léxico se informa acá. */
  private es(clave: string): boolean {
    const t = this.act
    if (t.t === "err") throw new ErrorSintaxis(t.linea, t.v)
    return (t.t === "id" && t.k === clave) || (t.t === "op" && t.v === clave)
  }

  private finDeInstruccion(): boolean {
    const t = this.act
    if (t.t === "err") throw new ErrorSintaxis(t.linea, t.v)
    return t.t === "nl" || t.t === "eof" || (t.t === "op" && t.v === ";")
  }

  private esperar(clave: string, mensaje: string): Token {
    if (!this.es(clave)) throw new ErrorSintaxis(this.act.linea, mensaje)
    return this.avanzar()
  }

  private opcional(clave: string): void {
    if (this.es(clave)) this.avanzar()
  }

  private saltarSeparadores(): void {
    while (this.act.t === "nl" || (this.act.t === "op" && this.act.v === ";")) this.i++
  }

  /** Después de una instrucción solo puede venir fin de línea o `;`. */
  private cerrarInstruccion(): void {
    if (this.act.t === "id" && CIERRES.has(this.act.k)) return
    if (!this.finDeInstruccion()) {
      throw new ErrorSintaxis(
        this.act.linea,
        `Sobra algo al final de la instrucción: "${this.act.v}". Cada instrucción va en su propia línea.`,
      )
    }
  }

  private identificador(que: string): { nombre: string; clave: string; linea: number } {
    const t = this.act
    if (t.t === "err") throw new ErrorSintaxis(t.linea, t.v)
    if (t.t !== "id") throw new ErrorSintaxis(t.linea, `Falta el nombre de ${que}.`)
    if (RESERVADAS.has(t.k)) {
      throw new ErrorSintaxis(
        t.linea,
        `"${t.v}" es una palabra reservada de PSeInt y no se puede usar como nombre de ${que}.`,
      )
    }
    this.i++
    return { nombre: t.v, clave: t.k, linea: t.linea }
  }

  private usarVariable(nombre: string, clave: string, linea: number): void {
    this.usos.push({ nombre, clave, linea, llamada: false })
  }

  // ── Programa ──────────────────────────────────────────────────────────

  programa(): Programa {
    let principal: Programa | null = null
    const funciones = new Map<string, Funcion>()
    for (;;) {
      this.saltarSeparadores()
      const t = this.act
      if (t.t === "eof") break
      if (this.es("ALGORITMO") || this.es("PROCESO")) {
        if (principal) {
          throw new ErrorSintaxis(t.linea, "Solo puede haber un Algoritmo por archivo.")
        }
        this.avanzar()
        const id = this.identificador("el algoritmo")
        this.cerrarInstruccion()
        const cuerpo = this.bloque(
          ["FINALGORITMO", "FINPROCESO"],
          "Falta FinAlgoritmo para cerrar el Algoritmo.",
          t.linea,
        )
        this.avanzar()
        this.cerrarInstruccion()
        principal = { nombre: id.nombre, clave: id.clave, linea: t.linea, cuerpo, funciones }
        continue
      }
      const cierres = t.t === "id" ? INICIOS_FUNCION[t.k] : undefined
      if (cierres) {
        const f = this.funcion(cierres)
        if (funciones.has(f.clave)) {
          throw new ErrorSintaxis(f.linea, `Ya hay otra función llamada ${f.nombre}.`)
        }
        funciones.set(f.clave, f)
        continue
      }
      throw new ErrorSintaxis(
        t.linea,
        "Esta instrucción está fuera del Algoritmo. Todo tiene que ir entre Algoritmo y FinAlgoritmo.",
      )
    }
    if (!principal) {
      throw new ErrorSintaxis(
        1,
        "Falta el Algoritmo principal (Algoritmo nombre ... FinAlgoritmo).",
      )
    }
    return principal
  }

  private funcion(cierres: string[]): Funcion {
    const inicio = this.avanzar()
    let retorno: { nombre: string; clave: string } | null = null
    // `Funcion r <- nombre(...)`: el primer identificador es la variable de retorno.
    if (
      this.act.t === "id" &&
      (this.sig().v === "<-" || this.sig().v === "=" || this.sig().v === ":=")
    ) {
      const r = this.identificador("la variable de retorno")
      this.avanzar()
      retorno = { nombre: r.nombre, clave: r.clave }
    }
    const id = this.identificador("la función")
    const params: Parametro[] = []
    if (this.es("(")) {
      this.avanzar()
      if (!this.es(")")) {
        for (;;) {
          const p = this.identificador("un parámetro")
          let porReferencia: boolean | null = null
          if (this.es("PORREFERENCIA")) {
            this.avanzar()
            porReferencia = true
          } else if (this.es("PORVALOR")) {
            this.avanzar()
            porReferencia = false
          }
          params.push({ nombre: p.nombre, clave: p.clave, porReferencia })
          if (!this.es(",")) break
          this.avanzar()
        }
      }
      this.esperar(")", "Falta cerrar el paréntesis de los parámetros.")
    }
    this.cerrarInstruccion()
    const cuerpo = this.bloque(
      cierres,
      `Falta FinFuncion para cerrar la función ${id.nombre}.`,
      inicio.linea,
    )
    this.avanzar()
    this.cerrarInstruccion()
    return { nombre: id.nombre, clave: id.clave, linea: inicio.linea, retorno, params, cuerpo }
  }

  /**
   * Lee instrucciones hasta encontrar alguno de `fin` (sin consumirlo). Si
   * aparece otro cierre o el archivo se termina, falta cerrar la estructura
   * que empezó en `lineaApertura`.
   */
  private bloque(
    fin: string[],
    faltaCerrar: string,
    lineaApertura: number,
    enSegun = false,
  ): Instr[] {
    const cuerpo: Instr[] = []
    for (;;) {
      this.saltarSeparadores()
      const t = this.act
      if (t.t === "err") throw new ErrorSintaxis(t.linea, t.v)
      if (t.t === "id" && fin.includes(t.k)) return cuerpo
      if (
        t.t === "eof" ||
        (t.t === "id" && (t.k in INICIOS_FUNCION || t.k === "ALGORITMO" || t.k === "PROCESO"))
      ) {
        throw new ErrorSintaxis(lineaApertura, faltaCerrar)
      }
      if (t.t === "id" && CIERRES.has(t.k)) {
        // Como PSeInt oficial: si llega el fin del algoritmo o de la función,
        // falta cerrar esta estructura (se informa donde empieza); cualquier
        // otro cierre está mal colocado (se informa donde está).
        if (CIERRES_DE_NIVEL_SUPERIOR.has(t.k)) throw new ErrorSintaxis(lineaApertura, faltaCerrar)
        throw new ErrorSintaxis(
          t.linea,
          `${t.v} mal colocado: no cierra ninguna estructura abierta acá.`,
        )
      }
      if (enSegun && this.lineaEsCaso()) return cuerpo
      cuerpo.push(this.instruccion())
    }
  }

  /** En un `Segun`, una línea con `:` (fuera de paréntesis) es una opción. */
  private lineaEsCaso(): boolean {
    let prof = 0
    for (let j = this.i; j < this.toks.length; j++) {
      const t = this.toks[j]!
      if (t.t === "nl" || t.t === "eof") return false
      if (t.t !== "op") continue
      if (t.v === "(" || t.v === "[") prof++
      else if (t.v === ")" || t.v === "]") prof--
      else if (t.v === ":" && prof === 0) return true
      else if (t.v === ";" || t.v === "<-" || t.v === ":=") return false
    }
    return false
  }

  // ── Instrucciones ─────────────────────────────────────────────────────

  private instruccion(): Instr {
    const t = this.act
    const linea = t.linea
    if (t.t !== "id") {
      throw new ErrorSintaxis(linea, "Instrucción no válida.")
    }
    switch (t.k) {
      case "DEFINIR":
        return this.definir()
      case "DIMENSION":
        return this.dimension()
      case "LEER": {
        this.avanzar()
        const destinos: Destino[] = []
        do {
          if (destinos.length) this.avanzar()
          destinos.push(this.destino("Leer"))
        } while (this.es(","))
        this.cerrarInstruccion()
        return { k: "leer", destinos, linea }
      }
      case "ESCRIBIR":
      case "IMPRIMIR":
      case "MOSTRAR":
        return this.escribir()
      case "SI":
        return this.si()
      case "SEGUN":
        return this.segun()
      case "MIENTRAS": {
        this.avanzar()
        const cond = this.expresion()
        this.opcional("HACER")
        this.cerrarInstruccion()
        const cuerpo = this.bloque(
          ["FINMIENTRAS"],
          "Falta FinMientras para cerrar este Mientras.",
          linea,
        )
        this.avanzar()
        this.cerrarInstruccion()
        return { k: "mientras", cond, cuerpo, linea }
      }
      case "REPETIR": {
        this.avanzar()
        this.cerrarInstruccion()
        const cuerpo = this.bloque(
          ["HASTAQUE", "MIENTRASQUE"],
          "Falta Hasta Que para cerrar este Repetir.",
          linea,
        )
        const hastaQue = this.avanzar().k === "HASTAQUE"
        const cond = this.expresion()
        this.cerrarInstruccion()
        return { k: "repetir", cuerpo, cond, hastaQue, linea }
      }
      case "PARA":
        return this.para()
      case "LIMPIARPANTALLA":
      case "ESPERARTECLA":
        this.avanzar()
        this.cerrarInstruccion()
        return { k: "nada", linea }
      case "ESPERAR":
        // `Esperar n Segundos`: no se espera de verdad (como `--fortest`).
        while (!this.finDeInstruccion()) this.avanzar()
        return { k: "nada", linea }
      default:
        break
    }
    if (RESERVADAS.has(t.k)) {
      if (CIERRES.has(t.k)) {
        throw new ErrorSintaxis(linea, `${t.v} sin la estructura que lo abre.`)
      }
      throw new ErrorSintaxis(linea, "Instrucción no válida.")
    }
    const s = this.sig()
    if (s.t === "op" && (s.v === "<-" || s.v === ":=" || s.v === "[")) {
      const destino = this.destino("la asignación")
      if (this.es("=") || this.es("==")) {
        throw new ErrorSintaxis(linea, "Para asignar un valor se usa <-, no =. Por ejemplo: x <- 3")
      }
      if (!this.es("<-") && !this.es(":=")) {
        throw new ErrorSintaxis(linea, "Instrucción no válida: falta <- para asignar.")
      }
      this.avanzar()
      const e = this.expresion()
      this.cerrarInstruccion()
      return { k: "asignar", destino, e, linea }
    }
    if (s.t === "op" && (s.v === "=" || s.v === "==")) {
      throw new ErrorSintaxis(linea, "Para asignar un valor se usa <-, no =. Por ejemplo: x <- 3")
    }
    if (s.t === "nl" || s.t === "eof" || (s.t === "op" && (s.v === "(" || s.v === ";"))) {
      this.avanzar()
      let args: Expr[] = []
      if (this.es("(")) {
        this.avanzar()
        args = this.argumentos()
      }
      this.usos.push({ nombre: t.v, clave: t.k, linea, llamada: true })
      this.cerrarInstruccion()
      return { k: "llamada", nombre: t.v, clave: t.k, args, linea }
    }
    throw new ErrorSintaxis(linea, "Instrucción no válida.")
  }

  private definir(): Instr {
    const linea = this.avanzar().linea
    const vars: { nombre: string; clave: string }[] = []
    for (;;) {
      const id = this.identificador("una variable")
      this.usarVariable(id.nombre, id.clave, id.linea)
      vars.push({ nombre: id.nombre, clave: id.clave })
      if (!this.es(",")) break
      this.avanzar()
    }
    if (!this.es("COMO") && !this.es("ES")) {
      throw new ErrorSintaxis(
        linea,
        "Falta Como y el tipo de dato (Entero, Real, Caracter o Logico).",
      )
    }
    this.avanzar()
    const t = this.act
    const tipo = t.t === "id" ? TIPOS[t.k] : undefined
    if (!tipo) {
      throw new ErrorSintaxis(
        linea,
        "Falta el tipo de dato o no es válido: usá Entero, Real, Caracter o Logico.",
      )
    }
    this.avanzar()
    this.cerrarInstruccion()
    return { k: "definir", vars, tipo, linea }
  }

  private dimension(): Instr {
    const linea = this.avanzar().linea
    const decls: { nombre: string; clave: string; dims: Expr[] }[] = []
    for (;;) {
      const id = this.identificador("un arreglo")
      this.usarVariable(id.nombre, id.clave, id.linea)
      if (!this.es("[") && !this.es("(")) {
        throw new ErrorSintaxis(
          linea,
          `Falta el tamaño del arreglo ${id.nombre}, por ejemplo: Dimension ${id.nombre}[10]`,
        )
      }
      const cierre = this.avanzar().v === "[" ? "]" : ")"
      const dims = this.listaExpr()
      this.esperar(cierre, `Falta cerrar ${cierre} en el tamaño del arreglo.`)
      decls.push({ nombre: id.nombre, clave: id.clave, dims })
      if (!this.es(",")) break
      this.avanzar()
    }
    this.cerrarInstruccion()
    return { k: "dimension", decls, linea }
  }

  private destino(que: string): Destino {
    const t = this.act
    if (t.t !== "id" || RESERVADAS.has(t.k)) {
      if (t.t === "err") throw new ErrorSintaxis(t.linea, t.v)
      throw new ErrorSintaxis(t.linea, `Falta una variable en ${que}.`)
    }
    this.avanzar()
    this.usarVariable(t.v, t.k, t.linea)
    let indices: Expr[] | null = null
    if (this.es("[")) {
      this.avanzar()
      indices = this.listaExpr()
      this.esperar("]", "Falta cerrar ] en el subíndice.")
    }
    return { nombre: t.v, clave: t.k, indices, linea: t.linea }
  }

  private escribir(): Instr {
    const linea = this.avanzar().linea
    let saltar = true
    if (this.es("SINSALTAR")) {
      this.avanzar()
      saltar = false
    }
    if (this.finDeInstruccion()) {
      throw new ErrorSintaxis(linea, "Falta qué escribir después de Escribir.")
    }
    const exprs = this.listaExpr()
    if (this.es("SINSALTAR")) {
      this.avanzar()
      saltar = false
    }
    this.cerrarInstruccion()
    return { k: "escribir", exprs, saltar, linea }
  }

  private si(): Instr {
    const linea = this.avanzar().linea
    const cond = this.expresion()
    // `Entonces` puede ir en la línea siguiente, o faltar (PSeInt lo acepta).
    const antes = this.i
    this.saltarSeparadores()
    if (this.es("ENTONCES")) this.avanzar()
    else this.i = antes
    this.cerrarInstruccion()
    const faltaFinSi = "Falta FinSi para cerrar este Si."
    const entonces = this.bloque(["SINO", "FINSI"], faltaFinSi, linea)
    let sino: Instr[] | null = null
    if (this.avanzar().k === "SINO") {
      this.cerrarInstruccion()
      sino = this.bloque(["FINSI"], faltaFinSi, linea)
      this.avanzar()
    }
    this.cerrarInstruccion()
    return { k: "si", cond, entonces, sino, linea }
  }

  private segun(): Instr {
    const linea = this.avanzar().linea
    const e = this.expresion()
    this.opcional("HACER")
    this.cerrarInstruccion()
    const faltaFin = "Falta FinSegun para cerrar este Segun."
    const casos: { valores: Expr[]; cuerpo: Instr[] }[] = []
    let otro: Instr[] | null = null
    for (;;) {
      this.saltarSeparadores()
      if (this.es("FINSEGUN")) {
        this.avanzar()
        break
      }
      if (this.es("DEOTROMODO")) {
        this.avanzar()
        this.esperar(":", "Falta : después de De Otro Modo.")
        otro = this.bloque(["FINSEGUN"], faltaFin, linea)
        continue
      }
      if (this.act.t === "eof" || (this.act.t === "id" && CIERRES.has(this.act.k))) {
        throw new ErrorSintaxis(linea, faltaFin)
      }
      if (!this.lineaEsCaso()) {
        throw new ErrorSintaxis(
          this.act.linea,
          "En un Segun cada opción empieza con un valor y dos puntos, por ejemplo  1:",
        )
      }
      const valores = this.listaExpr()
      this.esperar(":", "Falta : después del valor de la opción.")
      const cuerpo = this.bloque(["FINSEGUN", "DEOTROMODO"], faltaFin, linea, true)
      casos.push({ valores, cuerpo })
    }
    this.cerrarInstruccion()
    return { k: "segun", e, casos, otro, linea }
  }

  private para(): Instr {
    const linea = this.avanzar().linea
    const id = this.identificador("la variable del Para")
    this.usarVariable(id.nombre, id.clave, id.linea)
    if (!this.es("<-") && !this.es(":=")) {
      throw new ErrorSintaxis(linea, `Falta <- para darle el valor inicial a ${id.nombre}.`)
    }
    this.avanzar()
    const desde = this.expresion()
    this.esperar("HASTA", "Falta Hasta en el Para.")
    const hasta = this.expresion()
    let paso: Expr | null = null
    if (this.es("CONPASO")) {
      this.avanzar()
      paso = this.expresion()
    }
    this.opcional("HACER")
    this.cerrarInstruccion()
    const cuerpo = this.bloque(["FINPARA"], "Falta FinPara para cerrar este Para.", linea)
    this.avanzar()
    this.cerrarInstruccion()
    return { k: "para", nombre: id.nombre, clave: id.clave, desde, hasta, paso, cuerpo, linea }
  }

  // ── Expresiones ───────────────────────────────────────────────────────

  private listaExpr(): Expr[] {
    const lista = [this.expresion()]
    while (this.es(",")) {
      this.avanzar()
      lista.push(this.expresion())
    }
    return lista
  }

  private argumentos(): Expr[] {
    if (this.es(")")) {
      this.avanzar()
      return []
    }
    const args = this.listaExpr()
    this.esperar(")", "Falta cerrar el paréntesis.")
    return args
  }

  /**
   * Arma una operación binaria. Si los dos operandos son de un tipo que ya se
   * conoce sin ejecutar (literales), un choque de tipos es error de sintaxis,
   * como en PSeInt oficial (`"a" + 1`, `3 Y Verdadero`, `7.5 MOD 2`).
   */
  private binaria(op: string, l: Expr, r: Expr, linea: number): Expr {
    const tl = tipoEstatico(l)
    const tr = tipoEstatico(r)
    if (tl !== null && tr !== null) {
      const choque = (mensaje: string): never => {
        throw new ErrorSintaxis(linea, `No coinciden los tipos: ${mensaje}`)
      }
      if (op === "Y" || op === "O") {
        if (tl !== "bool" || tr !== "bool") choque(`los operandos de ${op} tienen que ser lógicos.`)
      } else if (op === "+") {
        if (tl !== tr || tl === "bool")
          choque("los dos operandos de + tienen que ser números o los dos textos.")
      } else if (["-", "*", "/", "^", "MOD"].includes(op)) {
        if (tl !== "num" || tr !== "num") choque(`el operador ${op} se aplica a números.`)
        if (
          op === "MOD" &&
          l.k === "num" &&
          r.k === "num" &&
          (!Number.isInteger(l.v) || !Number.isInteger(r.v))
        ) {
          throw new ErrorSintaxis(linea, "Los operandos de MOD tienen que ser enteros.")
        }
      } else if (tl !== tr) {
        choque("no se pueden comparar valores de distinto tipo.")
      }
    }
    return { k: "bin", op, l, r, linea }
  }

  expresion(): Expr {
    return this.o()
  }

  private o(): Expr {
    let l = this.y()
    while (this.es("O") || this.es("|")) {
      const linea = this.avanzar().linea
      l = this.binaria("O", l, this.y(), linea)
    }
    return l
  }

  private y(): Expr {
    let l = this.no()
    while (this.es("Y") || this.es("&")) {
      const linea = this.avanzar().linea
      l = this.binaria("Y", l, this.no(), linea)
    }
    return l
  }

  private no(): Expr {
    if (this.es("NO") || this.es("~")) {
      const linea = this.avanzar().linea
      const e = this.no()
      if (tipoEstatico(e) !== null && tipoEstatico(e) !== "bool") {
        throw new ErrorSintaxis(
          linea,
          "No coinciden los tipos: NO se aplica a valores lógicos (Verdadero o Falso).",
        )
      }
      return { k: "un", op: "NO", e, linea }
    }
    return this.relacional()
  }

  private relacional(): Expr {
    let l = this.suma()
    for (;;) {
      const t = this.act
      if (t.t !== "op" || !["=", "==", "<>", "!=", "<", ">", "<=", ">="].includes(t.v)) return l
      this.avanzar()
      const op = t.v === "==" ? "=" : t.v === "!=" ? "<>" : t.v
      l = this.binaria(op, l, this.suma(), t.linea)
    }
  }

  private suma(): Expr {
    let l = this.producto()
    while (this.es("+") || this.es("-")) {
      const t = this.avanzar()
      l = this.binaria(t.v, l, this.producto(), t.linea)
    }
    return l
  }

  private producto(): Expr {
    let l = this.unario()
    while (this.es("*") || this.es("/") || this.es("MOD") || this.es("%")) {
      const t = this.avanzar()
      const op = t.v === "*" || t.v === "/" ? t.v : "MOD"
      l = this.binaria(op, l, this.unario(), t.linea)
    }
    return l
  }

  /** El menos unario liga menos que `^`: `-2^2` es -4, como en PSeInt. */
  private unario(): Expr {
    if (this.es("-") || this.es("+")) {
      const t = this.avanzar()
      const e = this.unario()
      if (tipoEstatico(e) !== null && tipoEstatico(e) !== "num") {
        throw new ErrorSintaxis(
          t.linea,
          `No coinciden los tipos: el signo ${t.v} se aplica a números.`,
        )
      }
      return { k: "un", op: t.v as "-" | "+", e, linea: t.linea }
    }
    return this.potencia()
  }

  /** `^` asocia a izquierda: `2^3^2` es 64, como en PSeInt. */
  private potencia(): Expr {
    let l = this.primario()
    while (this.es("^")) {
      const t = this.avanzar()
      l = this.binaria("^", l, this.primario(), t.linea)
    }
    return l
  }

  private primario(): Expr {
    const t = this.act
    if (t.t === "err") throw new ErrorSintaxis(t.linea, t.v)
    if (t.t === "num") {
      this.avanzar()
      return { k: "num", v: t.n, linea: t.linea }
    }
    if (t.t === "str") {
      this.avanzar()
      return { k: "str", v: t.v, linea: t.linea }
    }
    if (t.t === "op" && t.v === "(") {
      this.avanzar()
      const e = this.expresion()
      this.esperar(")", "Falta cerrar el paréntesis.")
      return e
    }
    if (t.t === "id") {
      if (t.k === "VERDADERO" || t.k === "FALSO") {
        this.avanzar()
        return { k: "bool", v: t.k === "VERDADERO", linea: t.linea }
      }
      if (t.k === "PI") {
        this.avanzar()
        return { k: "num", v: Math.PI, linea: t.linea }
      }
      if (RESERVADAS.has(t.k)) {
        throw new ErrorSintaxis(t.linea, `Falta un valor u operando antes de "${t.v}".`)
      }
      this.avanzar()
      if (this.es("(")) {
        this.avanzar()
        const args = this.argumentos()
        this.usos.push({ nombre: t.v, clave: t.k, linea: t.linea, llamada: true })
        return { k: "call", nombre: t.v, clave: t.k, args, linea: t.linea }
      }
      this.usarVariable(t.v, t.k, t.linea)
      if (this.es("[")) {
        this.avanzar()
        const indices = this.listaExpr()
        this.esperar("]", "Falta cerrar ] en el subíndice.")
        return { k: "idx", nombre: t.v, clave: t.k, indices, linea: t.linea }
      }
      return { k: "var", nombre: t.v, clave: t.k, linea: t.linea }
    }
    if (t.t === "nl" || t.t === "eof" || (t.t === "op" && t.v === ";")) {
      throw new ErrorSintaxis(t.linea, "Falta un valor u operando al final de la expresión.")
    }
    throw new ErrorSintaxis(t.linea, `Falta un valor u operando antes de "${t.v}".`)
  }
}

/** Tipo que se conoce sin ejecutar: solo para expresiones hechas de literales. */
function tipoEstatico(e: Expr): "num" | "str" | "bool" | null {
  switch (e.k) {
    case "num":
      return "num"
    case "str":
      return "str"
    case "bool":
      return "bool"
    case "un":
      return e.op === "NO" ? "bool" : "num"
    case "bin": {
      const tl = tipoEstatico(e.l)
      const tr = tipoEstatico(e.r)
      if (tl === null || tr === null) return null
      if (["Y", "O", "=", "<>", "<", ">", "<=", ">="].includes(e.op)) return "bool"
      return e.op === "+" ? tl : "num"
    }
    default:
      return null
  }
}

/** Errores que se ven recién con el programa entero (nombres y llamadas). */
function revisarNombres(
  nombreAlgoritmo: string | null,
  funciones: Map<string, Funcion>,
  usos: Uso[],
): ErrorSintaxis[] {
  const errores: ErrorSintaxis[] = []
  for (const u of usos) {
    if (nombreAlgoritmo !== null && u.clave === nombreAlgoritmo) {
      errores.push(
        new ErrorSintaxis(
          u.linea,
          `${u.nombre} ya es el nombre del algoritmo: usá otro nombre para la variable.`,
        ),
      )
      continue
    }
    if (u.llamada && !(u.clave in PREDEFINIDAS) && !funciones.has(u.clave)) {
      errores.push(
        new ErrorSintaxis(u.linea, `No existe una función o subproceso llamado ${u.nombre}.`),
      )
      continue
    }
    if (!u.llamada && funciones.has(u.clave)) {
      errores.push(
        new ErrorSintaxis(
          u.linea,
          `${u.nombre} es el nombre de una función: usá otro nombre para la variable.`,
        ),
      )
    }
  }
  return errores
}

export interface ResultadoParseo {
  programa: Programa | null
  error: ErrorSintaxis | null
}

export function parsear(fuente: string): ResultadoParseo {
  const parser = new Parser(analizar(fuente))
  let programa: Programa | null = null
  let error: ErrorSintaxis | null = null
  try {
    programa = parser.programa()
  } catch (e) {
    if (!(e instanceof ErrorSintaxis)) throw e
    error = e
  }
  // El nombre del algoritmo se busca en el primer `Algoritmo` del archivo,
  // aunque el parseo se haya cortado antes de terminar.
  const nombreAlgoritmo = programa?.clave ?? nombreDelAlgoritmo(fuente)
  const errores = revisarNombres(
    nombreAlgoritmo,
    programa?.funciones ?? new Map(),
    parser.usos,
  ).filter(
    // Sin el programa entero no se sabe qué funciones existen.
    (e) => programa !== null || !e.mensaje.startsWith("No existe una función"),
  )
  if (error) errores.push(error)
  if (errores.length === 0) return { programa, error: null }
  errores.sort((a, b) => a.linea - b.linea)
  return { programa: null, error: errores[0]! }
}

function nombreDelAlgoritmo(fuente: string): string | null {
  const toks = analizar(fuente)
  for (let j = 0; j < toks.length - 1; j++) {
    const t = toks[j]!
    if (t.t === "id" && (t.k === "ALGORITMO" || t.k === "PROCESO")) {
      const n = toks[j + 1]!
      return n.t === "id" ? n.k : null
    }
  }
  return null
}
