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
  /**
   * true si el LCS se salteo por tamano (ver clamp en `diffLines`). Cuando es
   * true, `lines` viene vacio y `stats` en 0 — la UI debe mostrar "diff no
   * disponible" en vez de intentar renderizar el diff.
   */
  truncated: boolean
}

// Clamp de tamano (L-2): el LCS es O(n*m) en tiempo y en memoria (asigna un
// Int32Array de (n+1)*(m+1) celdas = 4 bytes c/u). Para snapshots normales de
// ejercicios (decenas-cientos de lineas) es trivial, pero un intento
// patologicamente grande dispararia una asignacion cuadratica que puede congelar
// u OOM-ear la pestana. Cortamos por el PRODUCTO n*m (lo que realmente acota
// memoria/tiempo) y ademas por lineas-por-lado como short-circuit barato.
//
// - MAX_DIFF_LINES = 5000 por lado: ~2 ordenes de magnitud sobre cualquier
//   snapshot de codigo real; un archivo de 5000 lineas ya es una anomalia.
// - MAX_LCS_CELLS = 4_000_000: techo del Int32Array en ~16 MB (4M * 4 bytes) y
//   ~4M iteraciones del doble loop — instantaneo en la practica. Por encima de
//   esto la asignacion/tiempo dejan de ser seguros para el hilo de UI.
const MAX_DIFF_LINES = 5000
const MAX_LCS_CELLS = 4_000_000

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

  // L-2: clamp de tamano antes de asignar la tabla LCS. Devolvemos un resultado
  // degradado seguro (sin lineas, sin stats) con `truncated: true` para que la
  // UI muestre "diff no disponible" en vez de correr un LCS cuadratico gigante.
  if (n > MAX_DIFF_LINES || m > MAX_DIFF_LINES || n * m > MAX_LCS_CELLS) {
    return { lines: [], stats: { added: 0, removed: 0 }, truncated: true }
  }

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

  return { lines, stats: { added, removed }, truncated: false }
}
