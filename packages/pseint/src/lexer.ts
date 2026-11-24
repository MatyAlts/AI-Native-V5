/**
 * Analizador léxico de PSeInt (HU-030).
 *
 * PSeInt es un lenguaje de líneas: cada línea termina en un token `nl`. Las
 * palabras clave no distinguen mayúsculas ni tildes (`Según` = `SEGUN`), y las
 * que se escriben en dos palabras (`Fin Si`, `Sin Saltar`, `Hasta Que`,
 * `De Otro Modo`, `Con Paso`, `Por Referencia`) se juntan en un solo token.
 *
 * Un error léxico (comillas sin cerrar, carácter no válido) no corta el
 * análisis: deja un token `err` que el parser levanta cuando llega a él, así
 * el primer error que se informa es el primero del archivo.
 */

export type TipoToken = "num" | "str" | "id" | "op" | "nl" | "eof" | "err"

export interface Token {
  t: TipoToken
  /** Texto tal como se escribió (para `id`, `op`, `str` es el contenido). */
  v: string
  /** Clave normalizada: mayúsculas y sin tildes (solo `id`). */
  k: string
  /** Valor numérico (solo `num`). */
  n: number
  linea: number
}

/** Mayúsculas sin tildes, conservando la Ñ. */
export function clave(s: string): string {
  let r = ""
  for (const c of s.toUpperCase()) r += c === "Ñ" ? c : c.normalize("NFD").replace(/\p{M}/gu, "")
  return r
}

const OPERADORES = [
  "<-",
  ":=",
  "<=",
  ">=",
  "<>",
  "==",
  "!=",
  "<",
  ">",
  "=",
  "+",
  "-",
  "*",
  "/",
  "^",
  "%",
  "&",
  "|",
  "~",
  "(",
  ")",
  "[",
  "]",
  ",",
  ":",
  ";",
]

const ES_LETRA = /[\p{L}_]/u
const ES_LETRA_O_DIGITO = /[\p{L}\p{N}_]/u

function token(t: TipoToken, v: string, linea: number, n = 0): Token {
  return { t, v, k: t === "id" ? clave(v) : v, n, linea }
}

/** Pares de palabras que forman una sola palabra clave. */
const COMPUESTAS: Record<string, Record<string, string>> = {
  FIN: {
    ALGORITMO: "FINALGORITMO",
    PROCESO: "FINPROCESO",
    SI: "FINSI",
    PARA: "FINPARA",
    MIENTRAS: "FINMIENTRAS",
    SEGUN: "FINSEGUN",
    FUNCION: "FINFUNCION",
    SUBPROCESO: "FINSUBPROCESO",
    SUBALGORITMO: "FINSUBALGORITMO",
  },
  SIN: { SALTAR: "SINSALTAR", BAJAR: "SINSALTAR" },
  HASTA: { QUE: "HASTAQUE" },
  MIENTRAS: { QUE: "MIENTRASQUE" },
  CON: { PASO: "CONPASO" },
  POR: { REFERENCIA: "PORREFERENCIA", VALOR: "PORVALOR" },
  LIMPIAR: { PANTALLA: "LIMPIARPANTALLA" },
  BORRAR: { PANTALLA: "LIMPIARPANTALLA" },
  ESPERAR: { TECLA: "ESPERARTECLA" },
}

/** Sinónimos de una sola palabra. */
const SINONIMOS: Record<string, string> = {
  SINBAJAR: "SINSALTAR",
  SINSALTAR: "SINSALTAR",
}

function juntarCompuestas(tokens: Token[]): Token[] {
  const salida: Token[] = []
  for (let i = 0; i < tokens.length; i++) {
    const a = tokens[i]!
    if (a.t === "id") {
      const sig = tokens[i + 1]
      // `De Otro Modo` son tres palabras.
      if (a.k === "DE" && sig?.t === "id" && sig.k === "OTRO") {
        const ter = tokens[i + 2]
        if (ter?.t === "id" && ter.k === "MODO" && ter.linea === a.linea) {
          salida.push({ ...a, v: "De Otro Modo", k: "DEOTROMODO" })
          i += 2
          continue
        }
      }
      const unida = sig?.t === "id" && sig.linea === a.linea ? COMPUESTAS[a.k]?.[sig.k] : undefined
      if (unida) {
        salida.push({ ...a, v: `${a.v} ${sig!.v}`, k: unida })
        i += 1
        continue
      }
      const sinonimo = SINONIMOS[a.k]
      if (sinonimo) {
        salida.push({ ...a, k: sinonimo })
        continue
      }
    }
    salida.push(a)
  }
  return salida
}

export function analizar(fuente: string): Token[] {
  const tokens: Token[] = []
  const lineas = fuente.replace(/\r\n?/g, "\n").split("\n")
  for (let idx = 0; idx < lineas.length; idx++) {
    const linea = idx + 1
    const texto = lineas[idx]!
    let i = 0
    while (i < texto.length) {
      const c = texto[i]!
      if (c === " " || c === "\t" || c === " ") {
        i++
        continue
      }
      if (c === "/" && texto[i + 1] === "/") break
      if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(texto[i + 1] ?? ""))) {
        const m = /^(\d+\.?\d*|\.\d+)/.exec(texto.slice(i))!
        tokens.push(token("num", m[0], linea, Number(m[0])))
        i += m[0].length
        continue
      }
      if (c === '"' || c === "'" || c === "“" || c === "”") {
        const cierre = c === "“" ? "”" : c
        const fin = texto.indexOf(cierre, i + 1)
        if (fin < 0) {
          tokens.push(token("err", "Falta cerrar las comillas de este texto.", linea))
          i = texto.length
          continue
        }
        tokens.push(token("str", texto.slice(i + 1, fin), linea))
        i = fin + 1
        continue
      }
      if (ES_LETRA.test(c)) {
        let j = i + 1
        while (j < texto.length && ES_LETRA_O_DIGITO.test(texto[j]!)) j++
        tokens.push(token("id", texto.slice(i, j), linea))
        i = j
        continue
      }
      const op = OPERADORES.find((o) => texto.startsWith(o, i))
      if (op) {
        tokens.push(token("op", op, linea))
        i += op.length
        continue
      }
      tokens.push(token("err", `Hay un carácter que PSeInt no reconoce: ${c}`, linea))
      i = texto.length
    }
    tokens.push(token("nl", "", linea))
  }
  tokens.push(token("eof", "", lineas.length))
  return juntarCompuestas(tokens)
}
