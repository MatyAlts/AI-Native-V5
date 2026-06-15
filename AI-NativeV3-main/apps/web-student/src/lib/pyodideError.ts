/**
 * Extrae el mensaje de error pedagógico de un traceback crudo de Pyodide.
 *
 * Pyodide tira el traceback COMPLETO (frames internos como
 * `__tutor_run_student_code` o `/lib/python312.zip/_pyodide/_base.py`) — al
 * alumno solo le sirve la última línea de excepción (`NombreError: mensaje`).
 * Recorremos las líneas no vacías desde el final y devolvemos la primera que
 * matchee el header de una excepción Python; fallback a la última línea no
 * vacía (nunca el traceback entero). El caso `TimeoutError` se prefija con ⏱.
 *
 * Vive en lib/ (no en CodeEditor.tsx) para ser testeable sin arrastrar el
 * import de `monaco-editor`, que en test no resuelve (se carga por CDN).
 * Fix QA 2026-06-15 #8.
 */
export function extractPyodideErrorLine(raw: string): string {
  const lines = raw.split("\n").filter((line) => line.trim() !== "")
  const excRe = /^[\w.]+(Error|Exception|Warning|Interrupt|KeyboardInterrupt):/
  let excLine: string | undefined
  for (let i = lines.length - 1; i >= 0; i--) {
    const candidate = lines[i]?.trimStart()
    if (candidate && excRe.test(candidate)) {
      excLine = candidate
      break
    }
  }
  const lastLine = excLine ?? lines[lines.length - 1] ?? raw
  return lastLine.startsWith("TimeoutError:")
    ? lastLine.replace("TimeoutError: ", "⏱ ")
    : lastLine
}
