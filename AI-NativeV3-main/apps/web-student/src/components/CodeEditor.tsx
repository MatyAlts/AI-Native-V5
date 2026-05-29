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
  setStdin(opts: { stdin: () => string | null }): void
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
  /** Disparado cuando el alumno intenta pegar. La accion fue bloqueada
   * por el editor — solo registrar en CTR + mostrar feedback. */
  onPasteAttempt?: (payload: {
    contenidoLongitud: number
    contenidoPreview: string
    metodo: "shortcut" | "menu_contextual" | "drag_drop"
  }) => void
  /** Disparado cuando el alumno intenta copiar. La accion fue bloqueada. */
  onCopyAttempt?: (payload: {
    seleccionChars: number
    metodo: "shortcut" | "menu_contextual"
  }) => void
  language?: "python" // en F6+ extendible a más lenguajes
}

const EDIT_DEBOUNCE_MS = 1000

export function CodeEditor({
  initialCode = "# Escribí tu código Python acá\n\ndef factorial(n):\n    pass\n",
  onCodeExecuted,
  onEditDebounced,
  onPasteAttempt,
  onCopyAttempt,
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
  // Toast naranja cuando el alumno intenta copiar/pegar; auto-oculta en 4s.
  const [clipboardWarning, setClipboardWarning] = useState<string | null>(null)
  // Refs estables para los callbacks de clipboard (evita re-mount del editor).
  const onPasteAttemptRef = useRef<typeof onPasteAttempt>(onPasteAttempt)
  const onCopyAttemptRef = useRef<typeof onCopyAttempt>(onCopyAttempt)
  // Ref a runCode para que el shortcut Ctrl+Enter del editor Monaco
  // (registrado una sola vez al mount) llame siempre a la version mas
  // reciente sin re-mountear el editor.
  const runCodeRef = useRef<() => void>(() => {})
  useEffect(() => {
    onPasteAttemptRef.current = onPasteAttempt
  }, [onPasteAttempt])
  useEffect(() => {
    onCopyAttemptRef.current = onCopyAttempt
  }, [onCopyAttempt])

  function flashClipboardWarning(message: string) {
    setClipboardWarning(message)
    window.setTimeout(() => setClipboardWarning(null), 4000)
  }

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

      // ── Bloqueo de clipboard (paste/copy/cut) ──────────────────────────
      // Sobrescribir los keybindings nativos de Monaco. addCommand reemplaza
      // el handler default. Codigos en https://microsoft.github.io/monaco-editor/
      const ctrl = monaco.KeyMod.CtrlCmd
      // Ctrl+V → paste bloqueado
      editor.addCommand(ctrl | monaco.KeyCode.KeyV, () => {
        onPasteAttemptRef.current?.({
          contenidoLongitud: 0,
          contenidoPreview: "",
          metodo: "shortcut",
        })
        flashClipboardWarning("Pegar está bloqueado. Escribí el código vos mismo. Quedó registrado.")
      })
      // Ctrl+C → copy bloqueado
      editor.addCommand(ctrl | monaco.KeyCode.KeyC, () => {
        const seleccion = editor.getModel()?.getValueInRange(editor.getSelection()!) ?? ""
        onCopyAttemptRef.current?.({
          seleccionChars: seleccion.length,
          metodo: "shortcut",
        })
        flashClipboardWarning("Copiar está bloqueado. Quedó registrado en la trazabilidad.")
      })
      // Ctrl+X → cut bloqueado (es copy + delete, lo tratamos como copy)
      editor.addCommand(ctrl | monaco.KeyCode.KeyX, () => {
        const seleccion = editor.getModel()?.getValueInRange(editor.getSelection()!) ?? ""
        onCopyAttemptRef.current?.({
          seleccionChars: seleccion.length,
          metodo: "shortcut",
        })
        flashClipboardWarning("Cortar está bloqueado. Quedó registrado.")
      })
      // Ctrl/Cmd+Enter → ejecutar codigo (Etapa 1.7). Shortcut estandar de
      // IDEs ("Run" en VSCode/JetBrains). Llamamos via ref para mantener
      // la captura sincronizada con el render actual.
      editor.addCommand(ctrl | monaco.KeyCode.Enter, () => {
        runCodeRef.current?.()
      })

      // Listeners DOM para cubrir menu contextual y eventos no atrapados
      // por addCommand (drag&drop, paste via clipboard API en algunos browsers).
      const containerEl = editorContainerRef.current
      if (containerEl) {
        const onPasteDom = (ev: ClipboardEvent) => {
          ev.preventDefault()
          ev.stopPropagation()
          const text = ev.clipboardData?.getData("text") ?? ""
          onPasteAttemptRef.current?.({
            contenidoLongitud: text.length,
            contenidoPreview: text.slice(0, 200),
            metodo: "menu_contextual",
          })
          flashClipboardWarning("Pegar está bloqueado. Quedó registrado en la trazabilidad.")
        }
        const onCopyDom = (ev: ClipboardEvent) => {
          const sel = window.getSelection()?.toString() ?? ""
          ev.preventDefault()
          ev.stopPropagation()
          onCopyAttemptRef.current?.({
            seleccionChars: sel.length,
            metodo: "menu_contextual",
          })
          flashClipboardWarning("Copiar está bloqueado. Quedó registrado.")
        }
        const onCutDom = (ev: ClipboardEvent) => {
          ev.preventDefault()
          ev.stopPropagation()
          onCopyAttemptRef.current?.({
            seleccionChars: 0,
            metodo: "menu_contextual",
          })
          flashClipboardWarning("Cortar está bloqueado. Quedó registrado.")
        }
        const onContextMenu = (_ev: MouseEvent) => {
          // No bloqueamos el menu (Monaco lo necesita) — solo registramos
          // que esta proximo a usarlo. Los listeners de paste/copy van a
          // capturar la accion final.
        }
        containerEl.addEventListener("paste", onPasteDom, true)
        containerEl.addEventListener("copy", onCopyDom, true)
        containerEl.addEventListener("cut", onCutDom, true)
        containerEl.addEventListener("contextmenu", onContextMenu)
        ;(editor as unknown as { __clipboardListeners?: () => void }).__clipboardListeners = () => {
          containerEl.removeEventListener("paste", onPasteDom, true)
          containerEl.removeEventListener("copy", onCopyDom, true)
          containerEl.removeEventListener("cut", onCutDom, true)
          containerEl.removeEventListener("contextmenu", onContextMenu)
        }
      }

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
      // Cleanup de los listeners DOM de clipboard (instalados en el effect).
      const cleanup = (
        editorRef.current as unknown as { __clipboardListeners?: () => void } | null
      )?.__clipboardListeners
      cleanup?.()
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

      // Capturar stdout/stderr con saltos de línea
      py.setStdout({
        batched: (text: string) => setOutput((prev) => prev + text + "\n"),
      })
      py.setStderr({
        batched: (text: string) => setOutput((prev) => prev + text + "\n"),
      })
      // Soporte para input(): usa prompt() del browser
      py.setStdin({
        stdin: () => {
          const value = window.prompt("El programa pide un dato (input):")
          return value ?? ""
        },
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

  // Mantenemos el ref de runCode sincronizado para el shortcut Ctrl+Enter
  // registrado al mount del editor.
  useEffect(() => {
    runCodeRef.current = runCode
  })

  // Atajo platform-aware para el hint visible en el boton.
  const isMac = typeof navigator !== "undefined" && /mac/i.test(navigator.platform)
  const shortcutLabel = isMac ? "⌘↵" : "Ctrl+↵"

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex items-center justify-between border-b border-border-soft px-4 py-2.5">
        <h2 className="text-sm font-medium">Código ({language})</h2>
        <button
          type="button"
          onClick={runCode}
          disabled={loading || running}
          aria-keyshortcuts="Control+Enter Meta+Enter"
          aria-label={running ? "Ejecutando codigo" : "Ejecutar codigo Python"}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 disabled:bg-border-strong disabled:cursor-not-allowed text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
        >
          {/* Icono Play SVG inline (evita dep extra de lucide para este botón). */}
          {loading || running ? (
            <svg
              aria-hidden="true"
              className="h-4 w-4 animate-spin"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="3"
                strokeOpacity="0.25"
              />
              <path
                d="M22 12a10 10 0 0 0-10-10"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </svg>
          ) : (
            <svg
              aria-hidden="true"
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="currentColor"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path d="M8 5v14l11-7L8 5z" />
            </svg>
          )}
          <span>
            {loading ? "Cargando Python..." : running ? "Ejecutando..." : "Ejecutar"}
          </span>
          {!loading && !running && (
            <kbd className="hidden sm:inline-flex items-center rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[11px] font-mono font-medium leading-none">
              {shortcutLabel}
            </kbd>
          )}
        </button>
      </div>

      {/* Toast naranja cuando se intenta usar el clipboard (auto-oculta en 4s). */}
      {clipboardWarning && (
        <div
          role="alert"
          data-testid="clipboard-blocked-toast"
          className="absolute top-12 left-1/2 -translate-x-1/2 z-20 bg-amber-500 text-amber-950 px-4 py-2 rounded-lg shadow-lg text-sm font-medium border border-amber-700"
        >
          🚫 {clipboardWarning}
        </div>
      )}

      <div ref={editorContainerRef} className="flex-1 min-h-[200px]" />

      <div className="border-t border-border-soft bg-ink text-surface font-mono text-xs p-3 min-h-[100px] max-h-[200px] overflow-y-auto">
        {output && <pre className="whitespace-pre-wrap">{output}</pre>}
        {error && <pre className="whitespace-pre-wrap text-danger">{error}</pre>}
        {!output && !error && !running && (
          <span className="text-muted">
            {loading
              ? "Cargando runtime Python en el navegador (primera vez ~6 MB)..."
              : `Ejecutá tu código (${shortcutLabel}) para ver el output acá.`}
          </span>
        )}
      </div>
    </div>
  )
}
