// Diff linea-a-linea entre dos snapshots de codigo (intentos del alumno en el
// timeline del episodio). Algoritmo LCS clasico O(n*m) sobre lineas: suficiente
// para snapshots de ejercicios de programacion (decenas-cientos de lineas) y sin
// dependencias externas (el repo no tiene lib de diff — F6).

export type DiffLineType = "equal" | "add" | "remove"

export interface DiffLine {
  type: DiffLineType
  text: string
  /** Numero de linea en A (base). null en lineas agregadas. */
  aLine: number | null
  /** Numero de linea en B (nuevo). null en lineas quitadas. */
  bLine: number | null
}

export interface DiffStats {
  added: number
  removed: number
}

export interface DiffResult {
  lines: DiffLine[]
  stats: DiffStats
}

/**
 * Diff por lineas via LCS. Devuelve la secuencia alineada de lineas
 * (equal/add/remove) mas el conteo de agregadas/quitadas. La tabla LCS usa
 * `Int32Array` (indexado que TS tipa como `number`, no `number | undefined`)
 * para convivir limpio con `noUncheckedIndexedAccess`.
 */
export function diffLines(a: string, b: string): DiffResult {
  const aLines = a.length === 0 ? [] : a.split("\n")
  const bLines = b.length === 0 ? [] : b.split("\n")
  const n = aLines.length
  const m = bLines.length
  const width = m + 1

  // lcs[i*width + j] = longitud de la subsecuencia comun mas larga de
  // aLines[i:] y bLines[j:]. `at` normaliza el `number | undefined` que TS
  // infiere para el indexado bajo `noUncheckedIndexedAccess` (en runtime el
  // Int32Array nunca devuelve undefined dentro de rango).
  const lcs = new Int32Array((n + 1) * width)
  const at = (i: number, j: number): number => lcs[i * width + j] ?? 0
  for (let i = n - 1; i >= 0; i--) {
    const ai = aLines[i] ?? ""
    for (let j = m - 1; j >= 0; j--) {
      const bj = bLines[j] ?? ""
      lcs[i * width + j] = ai === bj ? at(i + 1, j + 1) + 1 : Math.max(at(i + 1, j), at(i, j + 1))
    }
  }

  const lines: DiffLine[] = []
  let added = 0
  let removed = 0
  let i = 0
  let j = 0
  while (i < n && j < m) {
    const ai = aLines[i] ?? ""
    const bj = bLines[j] ?? ""
    if (ai === bj) {
      lines.push({ type: "equal", text: ai, aLine: i + 1, bLine: j + 1 })
      i++
      j++
    } else if (at(i + 1, j) >= at(i, j + 1)) {
      lines.push({ type: "remove", text: ai, aLine: i + 1, bLine: null })
      removed++
      i++
    } else {
      lines.push({ type: "add", text: bj, aLine: null, bLine: j + 1 })
      added++
      j++
    }
  }
  while (i < n) {
    lines.push({ type: "remove", text: aLines[i] ?? "", aLine: i + 1, bLine: null })
    removed++
    i++
  }
  while (j < m) {
    lines.push({ type: "add", text: bLines[j] ?? "", aLine: null, bLine: j + 1 })
    added++
    j++
  }

  return { lines, stats: { added, removed } }
}
