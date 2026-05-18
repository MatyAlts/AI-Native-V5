/**
 * Editor de código con Monaco + ejecución Python en Pyodide.
 *
 * Pyodide corre Python completo en el navegador vía WebAssembly. Se
 * carga desde CDN la primera vez (~6 MB) y queda cacheado.
 *
 * Ventajas respecto a ejecución backend:
 *  - Cero costo por ejecución (no consume budget de LLM ni infra)
 *  - Cero riesgo de abuso (cada alumno tiene su propia VM en el browser)
 *  - Latencia mínima tras el primer load
 *
 * Limitaciones:
 *  - Network calls bloqueadas (Pyodide corre en worker aislado)
 *  - Stdlib completa, pero paquetes PyPI requieren micropip
 *  - Ejecución sincrónica; para loops largos el navegador se cuelga
 */
import type { editor as MonacoEditor } from "monaco-editor"
import { type ReactNode, useEffect, useRef, useState } from "react"

type PyodideAPI = {
  runPythonAsync(code: string): Promise<unknown>
  setStdout(opts: { batched: (text: string) => void }): void
  setStderr(opts: { batched: (text: string) => void }): void
}

type PyodideLoader = (options?: { indexURL?: string }) => Promise<PyodideAPI>

declare global {
  interface Window {
    loadPyodide?: PyodideLoader
  }
}

const PYODIDE_VERSION = "0.26.3"
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`

export interface CodeEditorProps {
  initialCode?: string
  onCodeExecuted?: (result: {
    code: string
    output: string
    error: string | null
    durationMs: number
  }) => void
  /** Callback de edición con debouncing de 1s. Recibe el snapshot actual
   * del buffer, `diffChars` = delta de caracteres respecto a la última
   * emisión (positivo si agregó, negativo si borró), y `origin` (F6) que
   * indica si los cambios desde la última emisión vinieron de tipeo
   * directo o de un paste del clipboard. Pensado para alimentar el evento
   * CTR `edicion_codigo` sin saturar al backend con cada tecla.
   */
  onEditDebounced?: (
    snapshot: string,
    diffChars: number,
    origin: "student_typed" | "pasted_external",
  ) => void
  language?: "python" // en F6+ extendible a más lenguajes
}

const EDIT_DEBOUNCE_MS = 1000

export function CodeEditor({
  initialCode = "# Escribí tu código Python acá\n\ndef factorial(n):\n    pass\n",
  onCodeExecuted,
  onEditDebounced,
  language = "python",
}: CodeEditorProps): ReactNode {
  const editorContainerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<MonacoEditor.IStandaloneCodeEditor | null>(null)
  const pyodideRef = useRef<PyodideAPI | null>(null)

  const [code, setCode] = useState(initialCode)
  const [output, setOutput] = useState<string>("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)

  // Debounce de edicion_codigo: timeout pendiente + último snapshot emitido.
  // El delta se calcula como (len(snapshotActual) - len(snapshotEmitidoAnterior)),
  // arrancando contra `initialCode` para que la primera emisión refleje lo
  // que el alumno tipeó después del template.
  const editTimeoutRef = useRef<number | null>(null)
  const lastFiredSnapshotRef = useRef<string>(initialCode)
  // F6: si el usuario hizo paste antes del flush, marcamos el origin como
  // "pasted_external"; sino default a "student_typed". Una vez emitido el
  // evento, reseteamos para no contaminar la siguiente ventana.
  const pasteSinceLastFlushRef = useRef<boolean>(false)
  const onEditDebouncedRef = useRef<typeof onEditDebounced>(onEditDebounced)
  useEffect(() => {
    onEditDebouncedRef.current = onEditDebounced
  }, [onEditDebounced])

  // 1. Cargar Monaco dinámicamente (evita tamaño inicial del bundle).
  // `code` se usa sólo como valor inicial del editor — Monaco luego posee
  // el buffer. Agregarlo al array de deps re-crearía el editor en cada
  // keystroke, desbaratando cursor/undo y saturando al GC.
  // biome-ignore lint/correctness/useExhaustiveDependencies: code — seed-only; ver comentario arriba.
  useEffect(() => {
    if (!editorContainerRef.current) return
    if (editorRef.current) return // ya cargado

    let disposed = false
    ;(async () => {
      const monaco = await import(/* @vite-ignore */ "monaco-editor")
      if (disposed || !editorContainerRef.current) return

      const editor = monaco.editor.create(editorContainerRef.current, {
        value: code,
        language,
        theme: "vs-dark",
        fontSize: 14,
        minimap: { enabled: false },
        automaticLayout: true,
        scrollBeyondLastLine: false,
        renderWhitespace: "selection",
        tabSize: 4,
        insertSpaces: true,
      })

      // F6: detectar paste del clipboard. Monaco dispara onDidPaste *antes*
      // de onDidChangeModelContent, así marcamos el flag y lo lee el flush.
      editor.onDidPaste(() => {
        pasteSinceLastFlushRef.current = true
      })

      editor.onDidChangeModelContent(() => {
        const value = editor.getValue()
        setCode(value)

        // Reseteamos el timer en cada keystroke; emitimos sólo cuando el
        // alumno hizo una pausa de EDIT_DEBOUNCE_MS. Capturamos el snapshot
        // dentro del setTimeout para emitir el último estado, no el actual.
        if (editTimeoutRef.current !== null) {
          window.clearTimeout(editTimeoutRef.current)
        }
        editTimeoutRef.current = window.setTimeout(() => {
          editTimeoutRef.current = null
          const cb = onEditDebouncedRef.current
          if (!cb) return
          const snapshot = editor.getValue()
          const diffChars = snapshot.length - lastFiredSnapshotRef.current.length
          // Si el contenido no cambió respecto a la última emisión (p.ej.
          // tecla → undo dentro del debounce), no disparamos.
          if (snapshot === lastFiredSnapshotRef.current) return
          lastFiredSnapshotRef.current = snapshot
          const origin: "pasted_external" | "student_typed" = pasteSinceLastFlushRef.current
            ? "pasted_external"
            : "student_typed"
          pasteSinceLastFlushRef.current = false
          cb(snapshot, diffChars, origin)
        }, EDIT_DEBOUNCE_MS)
      })

      editorRef.current = editor
    })()

    return () => {
      disposed = true
      if (editTimeoutRef.current !== null) {
        window.clearTimeout(editTimeoutRef.current)
        editTimeoutRef.current = null
      }
      editorRef.current?.dispose?.()
    }
  }, [language])

  // 2. Cargar Pyodide en background (solo Python)
  useEffect(() => {
    if (language !== "python") {
      setLoading(false)
      return
    }
    if (pyodideRef.current) {
      setLoading(false)
      return
    }

    let cancelled = false
    ;(async () => {
      if (!window.loadPyodide) {
        // Inyectar el script de Pyodide del CDN
        await new Promise<void>((resolve, reject) => {
          const script = document.createElement("script")
          script.src = `${PYODIDE_URL}pyodide.js`
          script.onload = () => resolve()
          script.onerror = () => reject(new Error("Failed to load Pyodide"))
          document.head.appendChild(script)
        })
      }

      if (cancelled || !window.loadPyodide) return
      const py = await window.loadPyodide({ indexURL: PYODIDE_URL })
      if (cancelled) return

      // Capturar stdout/stderr
      py.setStdout({
        batched: (text: string) => setOutput((prev) => prev + text),
      })
      py.setStderr({
        batched: (text: string) => setOutput((prev) => prev + text),
      })

      pyodideRef.current = py
      setLoading(false)
    })().catch((e: unknown) => {
      if (!cancelled) {
        setError(`Error cargando Pyodide: ${String(e)}`)
        setLoading(false)
      }
    })

    return () => {
      cancelled = true
    }
  }, [language])

  const runCode = async () => {
    if (!pyodideRef.current || running) return
    setRunning(true)
    setOutput("")
    setError(null)
    const started = performance.now()

    try {
      await pyodideRef.current.runPythonAsync(code)
      const elapsed = performance.now() - started
      onCodeExecuted?.({ code, output, error: null, durationMs: elapsed })
    } catch (e) {
      const errMsg = String(e)
      setError(errMsg)
      const elapsed = performance.now() - started
      onCodeExecuted?.({ code, output, error: errMsg, durationMs: elapsed })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b border-border-soft px-4 py-2">
        <h2 className="text-sm font-medium">Código ({language})</h2>
        <button
          type="button"
          onClick={runCode}
          disabled={loading || running}
          className="px-3 py-1 text-xs rounded bg-green-600 hover:bg-green-700 disabled:bg-border-strong text-white font-medium"
        >
          {loading ? "Cargando Python..." : running ? "Ejecutando..." : "▶ Ejecutar"}
        </button>
      </div>

      <div ref={editorContainerRef} className="flex-1 min-h-[200px]" />

      <div className="border-t border-border-soft bg-ink text-surface font-mono text-xs p-3 min-h-[100px] max-h-[200px] overflow-y-auto">
        {output && <pre className="whitespace-pre-wrap">{output}</pre>}
        {error && <pre className="whitespace-pre-wrap text-danger">{error}</pre>}
        {!output && !error && !running && (
          <span className="text-muted">
            {loading
              ? "Cargando runtime Python en el navegador (primera vez ~6 MB)..."
              : "Presioná Ejecutar para correr el código."}
          </span>
        )}
      </div>
    </div>
  )
}
