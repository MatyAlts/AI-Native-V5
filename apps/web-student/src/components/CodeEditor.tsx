import { Modal } from "@platform/ui"
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
 *  - Ejecución sincrónica en el main thread: un bucle infinito congela la
 *    pestaña, pero el watchdog (sys.settrace + deadline de 3s) lo corta con
 *    TimeoutError. Solo cubre loops a nivel Python — una única llamada C
 *    larga (ej. 10**10**8) no dispara trace events y no es interrumpible.
 */
import { FlaskConical, Maximize2, Minimize2, Minus, Plus, RotateCcw } from "lucide-react"
import type * as Monaco from "monaco-editor"
import type { editor as MonacoEditor } from "monaco-editor"
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react"
import { Group, Panel, Separator } from "react-resizable-panels"
import {
  DEFAULT_LANGUAGE,
  ExecutionQuotaError,
  type ExecutionResult,
  ExecutionUnavailableError,
  LANGUAGE_LABELS,
  LANGUAGE_PLACEHOLDER,
  type Language,
  type TestCasePublic,
  type TokenGetter,
} from "../lib/api"
import { salidaCoincide } from "../lib/comparacionSalida"
import { resolverEdicionPendiente } from "../lib/edicionPendiente"
import { parseJavaError } from "../lib/javaError"
import { registerJavaSnippets } from "../lib/javaSnippets"
import { extractPyodideErrorLine, extractPyodideErrorLineNumber } from "../lib/pyodideError"
import { registerPythonSnippets } from "../lib/pythonSnippets"
import { runRemote } from "../lib/runRemote"

type PyodideAPI = {
  runPythonAsync(code: string): Promise<unknown>
  setStdout(opts: { batched: (text: string) => void }): void
  setStderr(opts: { batched: (text: string) => void }): void
  setStdin(opts: { stdin: () => string | null }): void
  globals: { set(name: string, value: unknown): void }
}

type PyodideLoader = (options?: { indexURL?: string }) => Promise<PyodideAPI>

declare global {
  interface Window {
    loadPyodide?: PyodideLoader
  }
}

const PYODIDE_VERSION = "0.26.3"
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`

// Fix plataforma 2026-06-10 #1: presupuesto de ejecución del código del
// alumno. Pasado este tiempo, el watchdog Python (sys.settrace) aborta la
// corrida con TimeoutError — protege contra bucles infinitos sin mover
// Pyodide a un Web Worker (que rompería input() vía window.prompt y
// exigiría COOP/COEP para SharedArrayBuffer).
//
// IMPORTANTE: es presupuesto de CÓMPUTO, no de tiempo real. Mientras el
// programa espera input() (tiempo humano), el watchdog se pausa por completo
// y al volver arranca un presupuesto fresco (ver __tutor_input). Antes el
// reloj corría durante el input y, si el alumno tardaba > timeout en tipear,
// lo mataba con un falso "bucle infinito" (bug reportado por alumnos 2026-06).
const EXECUTION_TIMEOUT_SECONDS = 5

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
   * indica de dónde vinieron los cambios desde la última emisión: tipeo
   * directo, paste del clipboard, o expansión de un snippet de ceremonia
   * del editor. Pensado para alimentar el evento CTR `edicion_codigo` sin
   * saturar al backend con cada tecla.
   */
  onEditDebounced?: (
    snapshot: string,
    diffChars: number,
    origin: "student_typed" | "pasted_external" | "snippet_expanded",
  ) => void
  /** Espejo del buffer en el caller, en CADA cambio (sin debounce).
   *
   * Monaco posee el buffer y este componente lo siembra UNA sola vez con
   * `initialCode`. Si el caller no sigue el buffer, todo re-montaje re-siembra
   * con un valor viejo y el alumno pierde lo tipeado — pasa al cruzar el
   * breakpoint mobile, porque el editor vive en dos subarboles distintos.
   *
   * NO es un evento de trazabilidad: no dispara nada al CTR. El evento
   * `edicion_codigo` sigue saliendo por `onEditDebounced`, con su debounce.
   */
  onCodeChange?: (code: string) => void
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
  /** F1: test cases PUBLICOS del ejercicio/TP. Si trae al menos uno, se
   * muestra el boton "Probar" que corre el codigo contra ellos en Pyodide.
   * El alumno NUNCA recibe los ocultos (el backend sanea por rol, A0.3). */
  testCases?: TestCasePublic[]
  /** F1: notifica el resultado agregado de una corrida de tests (conteos) para
   * que el caller emita el evento CTR `tests_ejecutados`. No incluye la lista
   * detallada ni el codigo — solo conteos (privacidad + cardinalidad CTR). */
  onTestsRun?: (result: {
    total: number
    passed: number
    failed: number
    failedNames: string[]
    durationMs: number
  }) => void
  /** ED-1: cuando se define, muestra el boton de maximizar/restaurar el
   * editor. El caller (EpisodePage) controla el layout de paneles; este
   * componente solo dispara el toggle. Sin este prop (o undefined en mobile)
   * el boton no aparece. */
  onToggleMaximize?: (() => void) | undefined
  /** ED-1: estado actual de maximizacion (para el icono del boton). */
  isMaximized?: boolean
  /** Lenguaje del ejercicio. Determina el modo de Monaco, el rotulo accesible
   * de los controles y por donde se ejecuta (navegador o servidor). */
  language?: Language
  /** UUID del Ejercicio del banco. Necesario para la ejecucion server-side: el
   * servicio lee su definicion completa (con los casos ocultos) para correrlos.
   * Sin esto, un lenguaje remoto no puede ejecutarse. */
  ejercicioId?: string | undefined
  /** Episodio de la corrida. Viaja al execution-service para que pueda
   * emitir `tests_ejecutados` al CTR: sin esto el evento no se emite y el
   * episodio queda sin la señal que el labeler usa para N3/N4. */
  episodeId?: string | undefined
  /** Comision del episodio. Viaja al execution-service para la habilitacion
   * progresiva (`EXECUTION_ENABLED_COMISIONES`): sin esto, con una lista de
   * comisiones configurada el backend rechaza TODAS las corridas de alumno. */
  comisionId?: string | undefined
  /** Para autenticar contra el execution-service. */
  getToken?: TokenGetter | undefined
}

/**
 * Lenguajes que corren EN EL NAVEGADOR (Pyodide). Instantaneos y gratis.
 *
 * Python sigue acá y no se toca: no hay razon para mandarlo al servidor.
 */
const LANGUAGES_RUNTIME_LOCAL: readonly Language[] = ["python"]

/**
 * Lenguajes que corren EN EL SERVIDOR (ADR-059).
 *
 * No hay forma de correr una JVM en el navegador, asi que Java pasa por el
 * execution-service. Diferencia que el alumno percibe: la espera ocurre en
 * CADA corrida, no solo la primera — por eso el indicador de espera es propio
 * y explica que se esta compilando en el servidor.
 */
const LANGUAGES_RUNTIME_REMOTO: readonly Language[] = ["java"]

const EDIT_DEBOUNCE_MS = 1000

/**
 * Config de autocompletado del editor. No es cosmetica: con los defaults de
 * Monaco no se puede escribir un f-string de Python.
 *
 * `acceptSuggestionOnCommitCharacter` viene en `true` por default y hace que
 * cualquier "caracter de commit" acepte la sugerencia resaltada. El alumno
 * tipea `f`, Monaco abre la lista de sugerencias con alguna palabra que empieza
 * con f (`for`, `float`, `filter`) resaltada, y la comilla siguiente commitea
 * esa sugerencia en vez de insertarse: la `f` se convierte en otra cosa y el
 * f-string nunca se escribe. Es el primer formateo de strings que se ensena en
 * la cursada, asi que el editor volvia inusable justo el ejercicio tipico.
 *
 * `quickSuggestions` apagado dentro de strings y comentarios por el mismo
 * motivo: prosa en castellano no debe disparar la lista. Se deja prendido en
 * `other` (codigo) y se conserva `suggestOnTriggerCharacters` para que el
 * autocompletado siga existiendo donde ayuda — el fix no es "apagar
 * IntelliSense", es que deje de robar teclas.
 */
export const SUGERENCIAS_OPTIONS = {
  acceptSuggestionOnCommitCharacter: false,
  quickSuggestions: { other: true, comments: false, strings: false },
  suggestOnTriggerCharacters: true,
} as const

// ED-3: control de tamano de fuente del editor. Persistido en localStorage
// para que el alumno no lo re-ajuste en cada episodio.
const FONT_SIZE_KEY = "web-student.editor.fontSize"
const FONT_SIZE_MIN = 11
const FONT_SIZE_MAX = 24
const FONT_SIZE_DEFAULT = 14

function readStoredFontSize(): number {
  if (typeof window === "undefined") return FONT_SIZE_DEFAULT
  const raw = Number.parseInt(window.localStorage.getItem(FONT_SIZE_KEY) ?? "", 10)
  if (!Number.isFinite(raw)) return FONT_SIZE_DEFAULT
  return Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, raw))
}

// ED-7: historial de corridas. Guardamos las ultimas N (no solo la ultima)
// con su salida/error para que el alumno pueda repasar corridas previas.
const MAX_RUN_HISTORY = 8

interface RunHistoryEntry {
  id: number
  ok: boolean
  durationMs: number
  output: string
  error: string | null
  at: number
}

/** Resultado por caso de una corrida de tests (F1). Espejo del dict que arma
 * el runner Python `__tutor_run_tests`. */
interface TestCaseResult {
  id: string | null
  name: string | null
  type: "stdin_stdout" | "pytest_assert"
  passed: boolean
  expected: string | null
  actual: string
  stdin: string
  error: string | null
}

export function CodeEditor({
  // Sin `initialCode` el buffer arranca en el andamio del lenguaje por omision.
  // El caller (EpisodePage) normalmente pasa uno ya resuelto por lenguaje.
  initialCode = LANGUAGE_PLACEHOLDER[DEFAULT_LANGUAGE],
  onCodeExecuted,
  onEditDebounced,
  onCodeChange,
  onPasteAttempt,
  onCopyAttempt,
  testCases,
  onTestsRun,
  onToggleMaximize,
  isMaximized = false,
  language = DEFAULT_LANGUAGE,
  ejercicioId,
  episodeId,
  comisionId,
  getToken,
}: CodeEditorProps): ReactNode {
  // Un solo lugar decide POR DONDE se ejecuta. Todo lo que dependa de eso
  // (carga de Pyodide, estado de los controles, rotulos accesibles) sale de
  // acá, para que no vuelva a pasar que el efecto salga temprano y el boton
  // quede habilitado igual.
  const isLocal = LANGUAGES_RUNTIME_LOCAL.includes(language)
  // Un lenguaje remoto sin `ejercicioId` NO es ejecutable: el servicio necesita
  // la definicion del ejercicio para inyectar los casos ocultos.
  const isRemoto = LANGUAGES_RUNTIME_REMOTO.includes(language) && Boolean(ejercicioId)
  const hasRuntime = isLocal || isRemoto
  const languageLabel = LANGUAGE_LABELS[language]
  // Texto de espera de la corrida remota. La espera pasa en CADA corrida, no
  // solo la primera: el alumno tiene que saber que se esta compilando en el
  // servidor y no que se colgo.
  const [remoteWait, setRemoteWait] = useState<string | null>(null)
  const editorContainerRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<MonacoEditor.IStandaloneCodeEditor | null>(null)
  // ED-4: guardamos el modulo monaco para poder pintar markers de error en la
  // linea exacta (setModelMarkers) sin re-importarlo.
  const monacoRef = useRef<typeof Monaco | null>(null)
  const pyodideRef = useRef<PyodideAPI | null>(null)
  // Espejo síncrono de `output`: window.prompt() bloquea el event loop, así que
  // React no alcanza a repintar el panel con los print() previos antes de que
  // aparezca la ventanita de input(). Leemos de este ref para mostrarle al
  // alumno los mensajes que orientan qué dato ingresar.
  const outputBufferRef = useRef<string>("")

  const [code, setCode] = useState(initialCode)
  const [output, setOutput] = useState<string>("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  // ED-8: segundos transcurridos cargando Pyodide (para mostrar progreso vivo
  // en vez de una pantalla muerta durante los ~6 MB del primer load).
  const [loadSeconds, setLoadSeconds] = useState(0)
  // ED-3: tamano de fuente del editor (persistido).
  const [fontSize, setFontSize] = useState<number>(readStoredFontSize)
  // F1: estado de la corrida de tests y sus resultados por caso.
  const [testing, setTesting] = useState(false)
  const [testResults, setTestResults] = useState<TestCaseResult[] | null>(null)
  // Panel de salida (ED-6): pestana activa consola vs pruebas.
  const [outputTab, setOutputTab] = useState<"consola" | "pruebas">("consola")
  // ED-7: historial de corridas + cual se esta viendo (null = la corrida viva).
  const [runHistory, setRunHistory] = useState<RunHistoryEntry[]>([])
  const [viewingRunId, setViewingRunId] = useState<number | null>(null)
  const runCounterRef = useRef(0)
  // ED-5: confirmacion antes de restaurar la plantilla inicial (destructivo).
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  // Refs estables para callbacks que cambian por render (evita re-mount).
  const onTestsRunRef = useRef<typeof onTestsRun>(onTestsRun)
  useEffect(() => {
    onTestsRunRef.current = onTestsRun
  }, [onTestsRun])
  const publicTestCases = (testCases ?? []).filter((tc) => tc.is_public !== false)
  const hasTests = publicTestCases.length > 0
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
  // Mismo mecanismo que el paste, para las expansiones de snippets de
  // ceremonia. Sin esto una expansión de 8 líneas entra al CTR como
  // `student_typed` — mentira invisible: el evento se ve igual y un diff
  // grande no llama la atención.
  const snippetSinceLastFlushRef = useRef<boolean>(false)
  const onEditDebouncedRef = useRef<typeof onEditDebounced>(onEditDebounced)
  useEffect(() => {
    onEditDebouncedRef.current = onEditDebounced
  }, [onEditDebounced])
  const onCodeChangeRef = useRef<typeof onCodeChange>(onCodeChange)
  useEffect(() => {
    onCodeChangeRef.current = onCodeChange
  }, [onCodeChange])
  // Plantilla original del ejercicio, congelada al montar. Con `onCodeChange`
  // cableado, `initialCode` deja de ser "la plantilla" y pasa a ser el ultimo
  // buffer conocido: sin esta copia, "Restaurar plantilla inicial" restauraria
  // el codigo del alumno sobre si mismo, o sea nada.
  const plantillaRef = useRef<string>(initialCode)

  /**
   * Emite YA la edicion que el debounce tiene pendiente, y cancela el timer.
   *
   * Existe por el ORDEN de la cadena CTR. `codigo_ejecutado` /
   * `tests_ejecutados` salen en el instante en que el alumno aprieta el boton,
   * pero el `edicion_codigo` del MISMO snapshot puede seguir esperando hasta un
   * segundo en el debounce — y llegar despues. La linea de tiempo del episodio
   * queda entonces mostrando una ejecucion antes de la edicion que la produjo,
   * que es una imposibilidad causal, y es sobre esa linea de tiempo que se
   * calculan CCD (codigo-discurso) y CII (inter-iteracion).
   *
   * Solo toca refs, asi que es estable: se puede llamar desde el efecto de
   * montaje sin re-crear el editor.
   */
  const flushEdicionPendiente = useCallback(() => {
    if (editTimeoutRef.current !== null) {
      window.clearTimeout(editTimeoutRef.current)
      editTimeoutRef.current = null
    }
    const editor = editorRef.current
    const cb = onEditDebouncedRef.current
    if (!editor || !cb) return
    const pendiente = resolverEdicionPendiente(editor.getValue(), lastFiredSnapshotRef.current, {
      paste: pasteSinceLastFlushRef.current,
      snippet: snippetSinceLastFlushRef.current,
    })
    // Sin nada que emitir NO se limpian las marcas: siguen describiendo la
    // ventana en curso (mismo criterio que tenia el debounce).
    if (!pendiente) return
    lastFiredSnapshotRef.current = pendiente.snapshot
    pasteSinceLastFlushRef.current = false
    snippetSinceLastFlushRef.current = false
    cb(pendiente.snapshot, pendiente.diffChars, pendiente.origin)
  }, [])

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
      monacoRef.current = monaco

      const editor = monaco.editor.create(editorContainerRef.current, {
        value: code,
        language,
        theme: "vs-dark",
        fontSize: readStoredFontSize(),
        minimap: { enabled: false },
        automaticLayout: true,
        scrollBeyondLastLine: false,
        renderWhitespace: "selection",
        tabSize: 4,
        insertSpaces: true,
        // El código largo fluye a la línea siguiente en vez de escaparse
        // horizontal a la derecha — clave para principiantes que pierden de
        // vista lo que escriben fuera del viewport.
        wordWrap: "on",
        wrappingIndent: "indent",
        ...SUGERENCIAS_OPTIONS,
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
        flashClipboardWarning(
          "Pegar está bloqueado. Escribí el código vos mismo. Quedó registrado.",
        )
      })
      // Ctrl+C → copy bloqueado
      editor.addCommand(ctrl | monaco.KeyCode.KeyC, () => {
        const selection = editor.getSelection()
        const seleccion = selection ? (editor.getModel()?.getValueInRange(selection) ?? "") : ""
        onCopyAttemptRef.current?.({
          seleccionChars: seleccion.length,
          metodo: "shortcut",
        })
        flashClipboardWarning("Copiar está bloqueado. Quedó registrado en la trazabilidad.")
      })
      // Ctrl+X → cut bloqueado (es copy + delete, lo tratamos como copy)
      editor.addCommand(ctrl | monaco.KeyCode.KeyX, () => {
        const selection = editor.getSelection()
        const seleccion = selection ? (editor.getModel()?.getValueInRange(selection) ?? "") : ""
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
        // Espejo en el caller para que un re-montaje re-siembre con ESTE buffer
        // y no con el de hace media hora. Se dispara SOLO desde un cambio real
        // del modelo: la siembra de `editor.create` no pasa por aca, asi que un
        // re-montaje no puede inventar un `edicion_codigo` que el alumno no hizo.
        onCodeChangeRef.current?.(value)

        // Reseteamos el timer en cada keystroke; emitimos sólo cuando el
        // alumno hizo una pausa de EDIT_DEBOUNCE_MS. Capturamos el snapshot
        // dentro del setTimeout para emitir el último estado, no el actual.
        if (editTimeoutRef.current !== null) {
          window.clearTimeout(editTimeoutRef.current)
        }
        editTimeoutRef.current = window.setTimeout(() => {
          // Mismas reglas que el flush forzado antes de una corrida — una sola
          // implementacion, en `resolverEdicionPendiente`.
          flushEdicionPendiente()
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
      const cleanup = (editorRef.current as unknown as { __clipboardListeners?: () => void } | null)
        ?.__clipboardListeners
      cleanup?.()
      editorRef.current?.dispose?.()
    }
  }, [language, flushEdicionPendiente])

  // Snippets de ceremonia. Java: System.out.println, getters/setters,
  // constructores, overrides, import del Scanner. Python: print, input y la
  // guarda `if __name__ == "__main__"`. Effect propio con deps vacías a
  // propósito: los proveedores se registran a nivel del *lenguaje* en Monaco,
  // no del editor, así que sobreviven los re-montajes del effect de arriba sin
  // duplicarse. Monaco consulta cada uno solo sobre modelos de su lenguaje, por
  // eso no hace falta gatearlos por `language`.
  //
  // Ambos comparten el MISMO `onAccept`: la marca que distingue
  // `snippet_expanded` de `student_typed` es del buffer, no del lenguaje. Si un
  // proveedor se registrara sin ella, el código que inserta el editor entraría
  // a la cadena CTR como tipeado por el alumno.
  useEffect(() => {
    const disposables: { dispose: () => void }[] = []
    let cancelled = false
    ;(async () => {
      const monaco = await import(/* @vite-ignore */ "monaco-editor")
      if (cancelled) return
      const marcarSnippet = () => {
        snippetSinceLastFlushRef.current = true
      }
      disposables.push(registerJavaSnippets(monaco, marcarSnippet))
      disposables.push(registerPythonSnippets(monaco, marcarSnippet))
    })()
    return () => {
      cancelled = true
      for (const d of disposables) d.dispose()
    }
  }, [])

  // ED-3: aplicar el tamano de fuente al editor + persistir. updateOptions no
  // re-crea el editor (preserva cursor/undo/buffer).
  useEffect(() => {
    editorRef.current?.updateOptions({ fontSize })
    if (typeof window !== "undefined") {
      window.localStorage.setItem(FONT_SIZE_KEY, String(fontSize))
    }
  }, [fontSize])

  // ED-8: mientras Pyodide carga, contamos segundos para el progreso visible.
  useEffect(() => {
    if (!loading) return
    const t = window.setInterval(() => setLoadSeconds((s) => s + 1), 1000)
    return () => window.clearInterval(t)
  }, [loading])

  // 2. Cargar Pyodide en background — SOLO para lenguajes que corren local.
  //    Un lenguaje remoto no necesita los ~6 MB de Pyodide en el navegador.
  useEffect(() => {
    if (!isLocal) {
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

      // Capturar stdout/stderr con saltos de línea. Mantenemos el espejo
      // síncrono (outputBufferRef) además del state de React.
      py.setStdout({
        batched: (text: string) => {
          outputBufferRef.current += `${text}\n`
          setOutput((prev) => `${prev}${text}\n`)
        },
      })
      py.setStderr({
        batched: (text: string) => {
          outputBufferRef.current += `${text}\n`
          setOutput((prev) => `${prev}${text}\n`)
        },
      })
      // Soporte para input(). Pyodide manda el prompt inline de input("texto")
      // a stdout SIN salto de línea, así que el handler `batched` lo bufferea y
      // no llega a la ventanita a tiempo. Para no depender de stdout,
      // interceptamos input() en Python (override de builtins.input) y recibimos
      // el texto del prompt como argumento, explícito.
      const askForInput = (promptText: string): string => {
        const raw = promptText ?? ""
        const inline = raw.trim()
        // El prompt inline de input("...") manda; si no hay, mostramos lo que el
        // programa ya imprimió con print() (los mensajes que orientan al alumno).
        const guia = inline || outputBufferRef.current.trim()
        const mensaje = guia
          ? `${guia}\n\n↳ Ingresá el dato que pide el programa:`
          : "El programa pide un dato de entrada (input):"
        const value = window.prompt(mensaje) ?? ""
        // Echo del prompt inline (que no pasó por stdout) + el valor, para que la
        // terminal muestre la interacción completa, como una consola real.
        const echo = `${raw}${value}\n`
        outputBufferRef.current += echo
        setOutput((prev) => `${prev}${echo}`)
        return value
      }
      py.globals.set("__tutor_ask_input", askForInput)

      // Watchdog de ejecución (fix 2026-06-10 #1, endurecido 2026-06-19):
      // sys.settrace chequea un deadline en cada trace event y aborta con una
      // BaseException propia (un `except Exception:` del alumno no la traga).
      // El límite es de 5s de cómputo CONTINUO entre inputs (NO acumulado en
      // toda la sesión): mientras el programa espera input() —que bloquea en
      // window.prompt, tiempo humano— el watchdog se pausa (deadline=None) y al
      // volver arranca un presupuesto fresco. Así una sesión interactiva larga
      // (muchos input, el alumno tardando lo que quiera en tipear) NO da falso
      // positivo; solo se corta una ráfaga de cómputo ininterrumpida > 5s.
      //
      // Refuerzo 2026-06-19: tracing por OPCODE (f_trace_opcodes). Sin esto
      // settrace solo dispara al CAMBIAR de línea, y un loop apretado de una
      // sola línea (ej. `while True: pass`) nunca re-invocaba el watchdog → no
      // cortaba. Con opcodes dispara en cada bytecode y corta igual.
      // (Sigue sin cubrir una única llamada C eterna —ej. time.sleep(1e9)—:
      // eso requeriría mover Pyodide a un Web Worker con terminate().)
      // `exec(..., globals())` preserva que las variables persistan entre corridas.
      await py.runPythonAsync(`
import sys as _tutor_wd_sys
import time as _tutor_time

_TUTOR_TIMEOUT_SECONDS = ${EXECUTION_TIMEOUT_SECONDS}.0


class _TutorTimeout(BaseException):
    pass


_tutor_watchdog = {"deadline": None}


def _tutor_trace(frame, event, arg):
    # Tracing por opcode: dispara en cada bytecode, no solo al cambiar de
    # línea, para cortar también loops apretados de una sola línea.
    frame.f_trace_opcodes = True
    deadline = _tutor_watchdog["deadline"]
    if deadline is not None and _tutor_time.monotonic() > deadline:
        raise _TutorTimeout()
    return _tutor_trace


def _tutor_pause_deadline():
    # Suspende el watchdog mientras input() bloquea en window.prompt (tiempo
    # humano): con deadline=None, _tutor_trace nunca aborta.
    _tutor_watchdog["deadline"] = None


def _tutor_reset_deadline():
    # Presupuesto de cómputo fresco. Se llama al volver de un input(): el tiempo
    # que el alumno tardó en tipear no cuenta, y el tramo de cómputo siguiente
    # arranca con _TUTOR_TIMEOUT_SECONDS completos.
    _tutor_watchdog["deadline"] = _tutor_time.monotonic() + _TUTOR_TIMEOUT_SECONDS


def __tutor_run_student_code(code):
    _tutor_watchdog["deadline"] = _tutor_time.monotonic() + _TUTOR_TIMEOUT_SECONDS
    _tutor_wd_sys.settrace(_tutor_trace)
    try:
        exec(compile(code, "<editor>", "exec"), globals())
    except _TutorTimeout:
        raise TimeoutError(
            f"La ejecucion supero los {int(_TUTOR_TIMEOUT_SECONDS)} segundos y fue interrumpida. "
            "Revisa si tenes un bucle infinito (por ejemplo, un while cuya condicion nunca cambia)."
        ) from None
    finally:
        _tutor_wd_sys.settrace(None)
        _tutor_watchdog["deadline"] = None
`)

      await py.runPythonAsync(
        "import builtins as __tutor_builtins\n" +
          "def __tutor_input(prompt=''):\n" +
          "    # Pausamos el watchdog mientras el alumno tipea (tiempo humano):\n" +
          "    # sin esto, si tardaba mas que el timeout lo mataba con un falso\n" +
          "    # 'bucle infinito'. Al volver, presupuesto de computo fresco.\n" +
          "    _tutor_pause_deadline()\n" +
          "    try:\n" +
          "        return __tutor_ask_input(str(prompt))\n" +
          "    finally:\n" +
          "        _tutor_reset_deadline()\n" +
          "__tutor_builtins.input = __tutor_input\n",
      )
      // Fallback para sys.stdin.read() crudo (sin prompt inline).
      py.setStdin({ stdin: () => askForInput("") })

      // FIX-22 (F-13): sandbox del editor. En Pyodide `import js` le da al
      // código del alumno acceso al navegador (DOM, cookies, localStorage).
      // Lo cerramos con un finder que rechaza js / pyodide_js + lo sacamos de
      // sys.modules (sino `import js` devuelve la copia cacheada sin pasar por
      // el finder). Los imports normales (math, random, etc.) no se tocan.
      await py.runPythonAsync(`
import sys as _tutor_sys

_TUTOR_BLOCKED = {"js", "pyodide_js"}


class _TutorImportGuard:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _TUTOR_BLOCKED:
            raise ImportError("El acceso al navegador esta bloqueado en este editor")
        return None


_tutor_sys.meta_path.insert(0, _TutorImportGuard())
for _m in [k for k in list(_tutor_sys.modules) if k.split(".")[0] in _TUTOR_BLOCKED]:
    del _tutor_sys.modules[_m]
`)

      // F1: runner de test cases publicos. Corre el codigo del alumno contra
      // cada caso en un NAMESPACE FRESCO (aislado entre casos) capturando su
      // propia stdout (no toca la terminal interactiva) y alimentando input()
      // desde el `code` del caso (NO window.prompt). Reusa el mismo watchdog de
      // computo (_tutor_trace) que la corrida interactiva. Dos tipos:
      //   - stdin_stdout: compara stdout (trim) contra `expected`.
      //   - pytest_assert: corre el snippet de asercion tras el codigo; pasa si
      //     no levanta excepcion.
      // Devuelve JSON (lista de dicts) para que el lado JS lo parsee.
      await py.runPythonAsync(`
import io as _tutor_io
import json as _tutor_json
import contextlib as _tutor_contextlib


def __tutor_run_tests(student_code, cases_json):
    cases = _tutor_json.loads(cases_json)
    results = []
    for case in cases:
        ctype = case.get("type") or "stdin_stdout"
        stdin_text = (case.get("code") or "") if ctype == "stdin_stdout" else ""
        assert_code = (case.get("code") or "") if ctype == "pytest_assert" else ""
        expected = case.get("expected")
        _lines = iter(stdin_text.split("\\n"))

        def _feed(prompt="", _it=_lines):
            try:
                return next(_it)
            except StopIteration:
                raise EOFError(
                    "El programa pidio mas datos (input) de los que este test provee."
                )

        buf = _tutor_io.StringIO()
        ns = {"__name__": "__main__", "input": _feed}
        error = None
        passed = False
        actual = ""
        _tutor_watchdog["deadline"] = _tutor_time.monotonic() + _TUTOR_TIMEOUT_SECONDS
        _tutor_wd_sys.settrace(_tutor_trace)
        try:
            with _tutor_contextlib.redirect_stdout(buf):
                exec(compile(student_code, "<editor>", "exec"), ns)
                if ctype == "pytest_assert":
                    exec(compile(assert_code, "<test>", "exec"), ns)
            actual = buf.getvalue()
            if ctype == "stdin_stdout":
                # JAVA-1: la comparacion NO se decide aca. La resuelve
                # salidaCoincide() de comparacionSalida.ts, del lado JS, que es
                # el gemelo exacto de la que aplica el execution-service para
                # Java. Un solo criterio por runtime: dos implementaciones de
                # la misma regla se separan con el tiempo y el mismo codigo
                # termina aprobando en un lenguaje y fallando en el otro.
                # Este False es un placeholder que el lado JS pisa.
                passed = False
            else:
                passed = True
        except _TutorTimeout:
            actual = buf.getvalue()
            error = "La ejecucion supero el limite de tiempo (posible bucle infinito)."
        except AssertionError as _e:
            actual = buf.getvalue()
            _msg = str(_e)
            error = "La comprobacion no se cumplio" + (": " + _msg if _msg else "")
        except BaseException as _e:
            actual = buf.getvalue()
            error = type(_e).__name__ + ": " + str(_e)
        finally:
            _tutor_wd_sys.settrace(None)
            _tutor_watchdog["deadline"] = None
        results.append({
            "id": case.get("id"),
            "name": case.get("name"),
            "type": ctype,
            "passed": passed,
            "expected": expected,
            "actual": actual,
            "stdin": stdin_text,
            "error": error,
        })
    return _tutor_json.dumps(results)
`)

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
  }, [isLocal])

  // ED-4: pintar / limpiar markers de error en la linea exacta del editor.
  function clearErrorMarkers() {
    const model = editorRef.current?.getModel()
    if (model && monacoRef.current) {
      monacoRef.current.editor.setModelMarkers(model, "pyodide-run", [])
    }
  }
  /**
   * Marca UNA linea del editor. Compartida por el camino local y el remoto: la
   * diferencia entre ambos es de donde sale el numero de linea, no como se
   * pinta.
   *
   * Si la linea no existe en el buffer (por ejemplo, el alumno borro codigo
   * despues de la corrida) se limpia en vez de marcar cualquier cosa.
   */
  function setErrorMarkerAtLine(line: number, message: string) {
    const model = editorRef.current?.getModel()
    const monaco = monacoRef.current
    if (!model || !monaco) return
    if (line < 1 || line > model.getLineCount()) {
      monaco.editor.setModelMarkers(model, "pyodide-run", [])
      return
    }
    monaco.editor.setModelMarkers(model, "pyodide-run", [
      {
        startLineNumber: line,
        endLineNumber: line,
        startColumn: 1,
        endColumn: model.getLineMaxColumn(line),
        message,
        severity: monaco.MarkerSeverity.Error,
      },
    ])
  }

  function setErrorMarker(rawError: string, message: string) {
    const line = extractPyodideErrorLineNumber(rawError)
    if (line == null) {
      clearErrorMarkers()
      return
    }
    setErrorMarkerAtLine(line, message)
  }

  // ED-7: registra la corrida en el historial (cap MAX_RUN_HISTORY).
  function pushRunHistory(ok: boolean, durationMs: number, out: string, err: string | null) {
    runCounterRef.current += 1
    const entry: RunHistoryEntry = {
      id: runCounterRef.current,
      ok,
      durationMs,
      output: out,
      error: err,
      at: Date.now(),
    }
    setRunHistory((prev) => [entry, ...prev].slice(0, MAX_RUN_HISTORY))
  }

  /**
   * Corrida server-side (tarea 6.1). El resultado tiene la MISMA forma que el
   * de Pyodide, asi que la vista de resultados y el evento CTR no cambian.
   */
  const runCodeRemoto = async () => {
    if (!ejercicioId) return
    setRunning(true)
    setOutput("")
    outputBufferRef.current = ""
    setError(null)
    setViewingRunId(null)
    setOutputTab("consola")
    clearErrorMarkers()
    setRemoteWait("Enviando al servidor...")
    const started = performance.now()

    let result: ExecutionResult
    try {
      result = await runRemote({
        ejercicioId,
        sourceCode: code,
        ...(episodeId ? { episodeId } : {}),
        ...(comisionId ? { comisionId } : {}),
        getToken,
        onStateChange: (state) => {
          setRemoteWait(
            state === "queued"
              ? "En cola en el servidor..."
              : `Compilando y ejecutando ${languageLabel} en el servidor...`,
          )
        },
      })
    } catch (e) {
      // Tarea 6.6: "no hay entorno" NO se confunde con "tu codigo falla". El
      // alumno tiene que poder distinguir si el problema es suyo o nuestro.
      const esNuestro = e instanceof ExecutionUnavailableError || e instanceof ExecutionQuotaError
      const msg = esNuestro
        ? (e as Error).message
        : `No se pudo ejecutar: ${e instanceof Error ? e.message : String(e)}`
      setError(msg)
      setRunning(false)
      setRemoteWait(null)
      return
    } finally {
      setRemoteWait(null)
    }

    const elapsed = performance.now() - started

    if (result.outcome === "infrastructure_failure") {
      // Fallo NUESTRO. No se emite `codigo_ejecutado` ni se cuenta como corrida
      // del alumno: la trazabilidad no debe registrar como actividad pedagogica
      // algo que no llego a ejecutarse.
      setError(
        "El servicio de ejecucion no pudo correr tu codigo. No es un error tuyo: " +
          "volve a intentar en un momento. Podes seguir con el tutor mientras tanto.",
      )
      setRunning(false)
      return
    }

    // Salida y error del primer caso: es lo que el alumno esperaba ver al
    // apretar "Ejecutar" (a diferencia de "Probar", que lista todos).
    const primero = result.cases[0]
    const salida = primero?.got ?? ""
    outputBufferRef.current = salida
    setOutput(salida)

    const javaErr =
      result.outcome === "compilation_error"
        ? parseJavaError(result.compile_output, "")
        : parseJavaError("", primero?.error ?? "")

    if (javaErr) {
      setError(javaErr.message)
      // Tarea 6.5: se marca la linea SOLO si el error la trae. Un marcador en
      // la linea equivocada manda al alumno a buscar donde no esta.
      if (javaErr.line !== null) setErrorMarkerAtLine(javaErr.line, javaErr.message)
    }

    pushRunHistory(!javaErr, elapsed, salida, javaErr?.message ?? null)
    onCodeExecuted?.({
      code,
      output: salida,
      error: javaErr?.message ?? null,
      durationMs: elapsed,
    })
    setRunning(false)
  }

  const runCode = async () => {
    // El boton esta deshabilitado sin runtime, pero el atajo de teclado no pasa
    // por el boton: sin esto, Ctrl+Enter en un ejercicio Java volveria a ser un
    // no-op silencioso, que es justo lo que esta change elimina.
    if (!hasRuntime) {
      setError(
        `No hay entorno de ejecucion de ${languageLabel} todavia. Podes seguir escribiendo codigo y consultando al tutor: tus ediciones se registran igual.`,
      )
      setOutputTab("consola")
      return
    }
    // Candado contra doble envio (tarea 6.3). En remoto importa mas que en
    // local: cada corrida consume cuota y dinero, y el alumno que no ve
    // respuesta inmediata tiende a apretar de nuevo.
    if (running || testing) return
    // La edicion que produjo ESTA corrida tiene que estar en la cadena ANTES
    // que la corrida. Sincrono y previo a cualquier await: el evento de edicion
    // se encola primero y la cola del CTR es FIFO.
    flushEdicionPendiente()
    if (isRemoto) {
      await runCodeRemoto()
      return
    }
    if (!pyodideRef.current) return
    setRunning(true)
    setOutput("")
    outputBufferRef.current = ""
    setError(null)
    setViewingRunId(null) // volver a la corrida viva
    setOutputTab("consola")
    clearErrorMarkers() // ED-4: limpiar markers de la corrida anterior
    const started = performance.now()

    try {
      // La corrida pasa por el watchdog Python (deadline de
      // EXECUTION_TIMEOUT_SECONDS). El código viaja por globals para no
      // tener que escapar el string dentro de un literal Python.
      pyodideRef.current.globals.set("__tutor_student_code", code)
      await pyodideRef.current.runPythonAsync("__tutor_run_student_code(__tutor_student_code)")
      const elapsed = performance.now() - started
      // outputBufferRef (no el state `output`, que es stale por el closure)
      // tiene la salida real acumulada que viaja en el evento CTR codigo_ejecutado.
      pushRunHistory(true, elapsed, outputBufferRef.current, null)
      onCodeExecuted?.({ code, output: outputBufferRef.current, error: null, durationMs: elapsed })
    } catch (e) {
      // Mostramos SOLO la última línea de excepción del traceback (ver
      // extractPyodideErrorLine), nunca el stack completo de Pyodide. El CTR
      // registra lo mismo que ve el alumno (errMsg viaja al evento de abajo).
      const errMsg = extractPyodideErrorLine(String(e))
      setError(errMsg)
      setErrorMarker(String(e), errMsg) // ED-4: marca la linea del traceback
      const elapsed = performance.now() - started
      pushRunHistory(false, elapsed, outputBufferRef.current, errMsg)
      onCodeExecuted?.({
        code,
        output: outputBufferRef.current,
        error: errMsg,
        durationMs: elapsed,
      })
    } finally {
      setRunning(false)
    }
  }

  /** "Probar" para lenguajes remotos: los casos los corre el execution-service.
   *
   * NO llama a `onTestsRun`, y eso es a proposito: el evento `tests_ejecutados`
   * lo emite el BACKEND (ver `tutor_client.py` del execution-service). Si lo
   * emitieran los dos, cada corrida de Java dejaria el evento duplicado en la
   * cadena del CTR.
   *
   * El reparto queda asi:
   *   - Python (Pyodide, local): emite el frontend — el backend no ve la corrida.
   *   - Java (remoto): emite el backend — es quien corrio los casos y el unico
   *     que sabe cuales eran ocultos.
   */
  const runTestsRemoto = async () => {
    if (!ejercicioId) return
    setTesting(true)
    setOutputTab("pruebas")
    clearErrorMarkers()
    setError(null)
    try {
      const result = await runRemote({
        ejercicioId,
        sourceCode: code,
        getToken,
        ...(episodeId ? { episodeId } : {}),
        ...(comisionId ? { comisionId } : {}),
        onStateChange: (state) => {
          setRemoteWait(
            state === "queued"
              ? "En cola en el servidor..."
              : "Compilando y corriendo las pruebas en el servidor...",
          )
        },
      })
      setTestResults(
        result.cases.map((c) => ({
          id: c.id,
          name: c.name,
          // El backend tipa `type` como string libre; el panel solo entiende
          // estos dos. `pytest_assert` no aplica a Java, asi que el fallback
          // razonable es el otro.
          type: c.type === "pytest_assert" ? ("pytest_assert" as const) : ("stdin_stdout" as const),
          // Solo `pass` es aprobado. `error` (no compila, timeout, crash) NO es
          // aprobado — el mismo criterio que `RunResult.failed` aplica del lado
          // del servidor.
          passed: c.status === "pass",
          expected: c.expected ?? null,
          actual: c.got ?? "",
          stdin: c.input ?? "",
          error: c.error ?? null,
        })),
      )
      // Un error de compilacion no produce casos: sin esto el alumno ve el panel
      // de pruebas vacio y sin explicacion.
      if (result.compile_output && result.cases.length === 0) {
        setError(result.compile_output)
        setOutputTab("consola")
      }
    } catch (e) {
      // Distinguir "no hay entorno / te pasaste de cuota" de "tu codigo falla"
      // es justo lo que la tarea 6.6 pide no confundir.
      setError(e instanceof Error ? e.message : "No se pudieron correr las pruebas.")
      setOutputTab("consola")
    } finally {
      setRemoteWait(null)
      setTesting(false)
    }
  }

  // F1: corre el codigo del alumno contra los test cases PUBLICOS. NO emite
  // codigo_ejecutado (eso es "Ejecutar"); notifica conteos via onTestsRun para
  // que el caller emita `tests_ejecutados`. Aislado de la terminal interactiva:
  // el runner Python captura su propia stdout.
  const runTests = async () => {
    if (!hasRuntime) {
      setError(`No hay entorno de ejecucion de ${languageLabel} todavia.`)
      setOutputTab("consola")
      return
    }
    if (running || testing || !hasTests) return
    // Igual que en "Ejecutar": `tests_ejecutados` no puede preceder al
    // `edicion_codigo` del snapshot que se esta probando.
    flushEdicionPendiente()
    // Lenguaje remoto: los casos los corre el servidor. Antes esta funcion era
    // Pyodide-only y salia en silencio — el boton quedaba habilitado (hasRuntime
    // es true para Java) y no pasaba absolutamente nada al apretarlo.
    if (isRemoto) {
      await runTestsRemoto()
      return
    }
    if (!pyodideRef.current) return
    setTesting(true)
    setOutputTab("pruebas")
    clearErrorMarkers()
    const started = performance.now()
    try {
      pyodideRef.current.globals.set("__tutor_test_code", code)
      pyodideRef.current.globals.set(
        "__tutor_test_cases_json",
        JSON.stringify(
          publicTestCases.map((tc) => ({
            id: tc.id ?? null,
            name: tc.name ?? null,
            type: tc.type ?? "stdin_stdout",
            code: tc.code ?? "",
            expected: tc.expected ?? null,
          })),
        ),
      )
      const raw = await pyodideRef.current.runPythonAsync(
        "__tutor_run_tests(__tutor_test_code, __tutor_test_cases_json)",
      )
      // JAVA-1: el runner Python devuelve la salida cruda; el veredicto de los
      // casos `stdin_stdout` lo da acá `salidaCoincide`, la misma normalizacion
      // que el execution-service aplica a Java. Los casos que ya murieron con
      // error (excepcion, timeout, EOF) no se re-evaluan: fallaron por otra
      // razon y su `actual` esta truncado.
      const parsed = (JSON.parse(String(raw)) as TestCaseResult[]).map((r) =>
        r.type === "stdin_stdout" && r.error === null
          ? { ...r, passed: salidaCoincide(r.actual, r.expected) }
          : r,
      )
      setTestResults(parsed)
      const durationMs = performance.now() - started
      const passed = parsed.filter((r) => r.passed).length
      onTestsRunRef.current?.({
        total: parsed.length,
        passed,
        failed: parsed.length - passed,
        failedNames: parsed.filter((r) => !r.passed).map((r) => r.name ?? r.id ?? "test"),
        durationMs,
      })
    } catch (e) {
      // Fallo del runner mismo (no de un test) — lo mostramos como un unico
      // "caso" en error para no dejar al alumno sin feedback.
      setTestResults([
        {
          id: "runner",
          name: "No se pudieron correr las pruebas",
          type: "stdin_stdout",
          passed: false,
          expected: null,
          actual: "",
          stdin: "",
          error: extractPyodideErrorLine(String(e)),
        },
      ])
    } finally {
      setTesting(false)
    }
  }

  // ED-5: restaurar la plantilla inicial (destructivo — pisa el buffer actual).
  function restoreTemplate() {
    // `plantillaRef`, no `initialCode`: ver el comentario donde se declara.
    const plantilla = plantillaRef.current
    const editor = editorRef.current
    if (editor) {
      editor.setValue(plantilla)
      editor.focus()
    }
    setCode(plantilla)
    clearErrorMarkers()
    setShowResetConfirm(false)
  }

  function changeFontSize(delta: number) {
    setFontSize((s) => Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, s + delta)))
  }

  // Mantenemos el ref de runCode sincronizado para el shortcut Ctrl+Enter
  // registrado al mount del editor.
  useEffect(() => {
    runCodeRef.current = runCode
  })

  // Atajo platform-aware para el hint visible en el boton.
  const isMac = typeof navigator !== "undefined" && /mac/i.test(navigator.platform)
  const shortcutLabel = isMac ? "⌘↵" : "Ctrl+↵"

  // ED-7: si el alumno esta viendo una corrida vieja, mostramos SU salida; sino
  // la corrida viva (output/error del state).
  const viewingRun =
    viewingRunId != null ? (runHistory.find((r) => r.id === viewingRunId) ?? null) : null
  const consoleOutput = viewingRun ? viewingRun.output : output
  const consoleError = viewingRun ? viewingRun.error : error
  const testsPassed = testResults ? testResults.filter((r) => r.passed).length : 0
  const testsTotal = testResults ? testResults.length : 0
  const iconBtn =
    "inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-soft text-muted hover:text-ink hover:bg-surface-alt disabled:opacity-40 disabled:cursor-not-allowed transition-colors"

  return (
    <div className="flex flex-col h-full relative">
      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-2 border-b border-border-soft px-3 py-2">
        <h2 className="text-sm font-medium text-ink shrink-0">Código</h2>
        <div className="flex items-center gap-1.5">
          {/* ED-3: tamano de fuente */}
          <div className="hidden sm:inline-flex items-center rounded-md border border-border-soft bg-surface-alt overflow-hidden">
            <button
              type="button"
              onClick={() => changeFontSize(-1)}
              disabled={fontSize <= FONT_SIZE_MIN}
              aria-label="Reducir tamano de fuente"
              title="Reducir tamano de fuente"
              className="inline-flex h-7 w-7 items-center justify-center text-muted hover:text-ink hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="px-1 text-[11px] font-mono tabular-nums text-muted select-none">
              {fontSize}
            </span>
            <button
              type="button"
              onClick={() => changeFontSize(1)}
              disabled={fontSize >= FONT_SIZE_MAX}
              aria-label="Aumentar tamano de fuente"
              title="Aumentar tamano de fuente"
              className="inline-flex h-7 w-7 items-center justify-center text-muted hover:text-ink hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* ED-5: restaurar plantilla inicial (con confirmacion) */}
          <button
            type="button"
            onClick={() => setShowResetConfirm(true)}
            disabled={loading}
            aria-label="Restaurar plantilla inicial"
            title="Restaurar plantilla inicial"
            data-testid="restore-template-button"
            className={iconBtn}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>

          {/* ED-1: maximizar / restaurar el editor (solo si el caller lo cablea) */}
          {onToggleMaximize && (
            <button
              type="button"
              onClick={onToggleMaximize}
              aria-pressed={isMaximized}
              aria-label={isMaximized ? "Restaurar tamano del editor" : "Maximizar editor"}
              title={isMaximized ? "Restaurar tamano del editor" : "Maximizar editor"}
              data-testid="maximize-editor-button"
              className={iconBtn}
            >
              {isMaximized ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </button>
          )}

          <span className="mx-0.5 hidden h-5 w-px bg-border-soft sm:block" aria-hidden="true" />

          {/* Ejecucion no disponible: se dice, no se insinua. Un control que al
              accionarse no produce ningun efecto es peor que uno deshabilitado
              con motivo. */}
          {!hasRuntime && (
            <span className="text-xs text-muted" data-testid="sin-runtime-aviso">
              Ejecutar {languageLabel} todavia no esta disponible. El tutor si.
            </span>
          )}

          {/* F1: Probar mi codigo contra los test cases publicos */}
          {hasTests && (
            <button
              type="button"
              onClick={runTests}
              disabled={!hasRuntime || loading || running || testing}
              data-testid="run-tests-button"
              title={
                hasRuntime ? undefined : `No hay entorno de ejecucion de ${languageLabel} todavia`
              }
              aria-label={
                hasRuntime
                  ? "Probar mi codigo contra los tests del ejercicio"
                  : `Probar no disponible: no hay entorno de ejecucion de ${languageLabel} todavia`
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-accent-brand/40 bg-accent-brand/5 px-3 py-1.5 text-sm font-medium text-accent-brand transition-colors hover:bg-accent-brand/10 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand/40"
            >
              {testing ? (
                <span className="inline-block h-4 w-4 rounded-full border-2 border-accent-brand/30 border-t-accent-brand motion-safe:animate-spin" />
              ) : (
                <FlaskConical className="h-4 w-4" />
              )}
              <span>{testing ? "Probando..." : "Probar"}</span>
            </button>
          )}

          {/* Ejecutar (corrida interactiva — emite codigo_ejecutado) */}
          <button
            type="button"
            onClick={runCode}
            disabled={!hasRuntime || loading || running || testing}
            data-tour="ejecutar-codigo"
            aria-keyshortcuts="Control+Enter Meta+Enter"
            title={
              hasRuntime ? undefined : `No hay entorno de ejecucion de ${languageLabel} todavia`
            }
            aria-label={
              !hasRuntime
                ? `Ejecutar no disponible: no hay entorno de ejecucion de ${languageLabel} todavia`
                : running
                  ? `Ejecutando codigo ${languageLabel}`
                  : `Ejecutar codigo ${languageLabel}`
            }
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 disabled:bg-border-strong disabled:cursor-not-allowed text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
          >
            {/* Icono Play SVG inline (evita dep extra para este botón). */}
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
              {loading
                ? `Cargando Python... (${loadSeconds}s)`
                : running
                  ? "Ejecutando..."
                  : "Ejecutar"}
            </span>
            {!loading && !running && (
              <kbd className="hidden sm:inline-flex items-center rounded border border-white/30 bg-white/10 px-1.5 py-0.5 text-[11px] font-mono font-medium leading-none">
                {shortcutLabel}
              </kbd>
            )}
          </button>
        </div>
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

      {/* ED-6: editor + salida como panel vertical redimensionable real. */}
      <Group orientation="vertical" className="flex-1 min-h-0">
        <Panel id="editor-code" defaultSize={62} minSize={25} className="flex flex-col min-h-0">
          <div ref={editorContainerRef} className="flex-1 min-h-[140px]" />
        </Panel>

        <Separator className="group relative my-0.5 flex h-2 items-center justify-center cursor-row-resize">
          <span className="block h-0.5 w-12 rounded-full bg-border-soft transition-colors group-hover:bg-accent-brand group-data-[resize-handle-active]:bg-accent-brand" />
        </Separator>

        <Panel
          id="editor-output"
          defaultSize={38}
          minSize={14}
          className="flex flex-col min-h-0 bg-ink"
        >
          {/* Header del panel de salida: pestanas + historial de corridas */}
          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-white/5">
            <div
              role="tablist"
              aria-label="Vista de salida"
              className="inline-flex items-center gap-0.5 rounded-md bg-white/5 p-0.5"
            >
              <button
                type="button"
                role="tab"
                aria-selected={outputTab === "consola"}
                onClick={() => setOutputTab("consola")}
                className={`rounded px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider transition-colors ${
                  outputTab === "consola"
                    ? "bg-white/10 text-surface"
                    : "text-muted hover:text-surface"
                }`}
              >
                Salida
              </button>
              {hasTests && (
                <button
                  type="button"
                  role="tab"
                  aria-selected={outputTab === "pruebas"}
                  onClick={() => setOutputTab("pruebas")}
                  data-testid="tests-tab"
                  className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider transition-colors ${
                    outputTab === "pruebas"
                      ? "bg-white/10 text-surface"
                      : "text-muted hover:text-surface"
                  }`}
                >
                  Pruebas
                  {testResults && (
                    <span
                      className={`inline-flex items-center rounded-full px-1.5 py-px text-[10px] font-bold tabular-nums ${
                        testsPassed === testsTotal
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-danger/20 text-danger"
                      }`}
                    >
                      {testsPassed}/{testsTotal}
                    </span>
                  )}
                </button>
              )}
            </div>

            {/* ED-7: historial de corridas (solo en la pestana Salida) */}
            {outputTab === "consola" && runHistory.length > 0 && (
              <div className="ml-auto flex items-center gap-1 overflow-x-auto">
                <span className="shrink-0 text-[10px] uppercase tracking-wider text-muted-soft">
                  Historial
                </span>
                {runHistory.map((h) => {
                  const active = viewingRunId === h.id
                  return (
                    <button
                      key={h.id}
                      type="button"
                      onClick={() => setViewingRunId((cur) => (cur === h.id ? null : h.id))}
                      title={`Corrida ${h.id} · ${h.ok ? "sin error" : "con error"} · ${Math.round(h.durationMs)} ms`}
                      className={`shrink-0 inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] tabular-nums transition-colors ${
                        active
                          ? "bg-accent-brand text-white"
                          : h.ok
                            ? "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
                            : "bg-danger/15 text-danger hover:bg-danger/25"
                      }`}
                    >
                      {h.ok ? "✓" : "✗"}
                      {h.id}
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* Cuerpo del panel */}
          <div className="flex-1 min-h-0 overflow-auto">
            {outputTab === "consola" ? (
              // `status` + `aria-live` para que un error de ejecucion (o el aviso
              // de que el lenguaje no tiene runtime) se anuncie solo. Antes habia
              // que navegar hasta acá para enterarse de que algo fallo.
              <output
                aria-live="polite"
                aria-atomic="false"
                className="block p-4 font-mono text-sm leading-relaxed text-surface"
              >
                {viewingRun && (
                  <div className="mb-2 flex items-center gap-2 text-[11px] text-muted">
                    <span>Viendo la corrida {viewingRun.id} (historial).</span>
                    <button
                      type="button"
                      onClick={() => setViewingRunId(null)}
                      className="rounded bg-white/10 px-1.5 py-0.5 font-sans font-medium text-surface hover:bg-white/20"
                    >
                      Ver corrida actual
                    </button>
                  </div>
                )}
                {/* Espera de la corrida remota. La local no lo necesita: es
                    instantanea salvo la carga inicial de Pyodide. */}
                {remoteWait && (
                  <div className="flex items-center gap-2 text-muted">
                    <span className="inline-block h-3 w-3 shrink-0 rounded-full border-2 border-muted/30 border-t-muted motion-safe:animate-spin" />
                    <span>{remoteWait}</span>
                  </div>
                )}
                {consoleOutput && <pre className="whitespace-pre-wrap">{consoleOutput}</pre>}
                {consoleError && (
                  <pre className="whitespace-pre-wrap text-danger">{consoleError}</pre>
                )}
                {!consoleOutput && !consoleError && !running && (
                  <span className="text-muted">
                    {!hasRuntime
                      ? `Todavía no hay entorno de ejecución de ${languageLabel}. Podés escribir código y trabajarlo con el tutor: tus ediciones se registran igual.`
                      : loading
                        ? `Cargando runtime Python en el navegador (primera vez ~6 MB)... (${loadSeconds}s)`
                        : isRemoto
                          ? `Ejecutá tu código (${shortcutLabel}). Se compila y corre en el servidor, así que tarda unos segundos cada vez.`
                          : `Ejecutá tu código (${shortcutLabel}) para ver el output acá.`}
                  </span>
                )}
              </output>
            ) : (
              <TestResultsView results={testResults} testing={testing} />
            )}
          </div>
        </Panel>
      </Group>

      {/* ED-5: confirmacion de restauracion de plantilla (destructivo) */}
      <Modal
        isOpen={showResetConfirm}
        onClose={() => setShowResetConfirm(false)}
        title="Restaurar plantilla inicial"
        size="sm"
        variant="light"
      >
        <p className="text-sm text-body leading-relaxed">
          Esto reemplaza tu código actual por la plantilla inicial del ejercicio. Vas a perder lo
          que escribiste en el editor. ¿Seguro?
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setShowResetConfirm(false)}
            className="rounded-md border border-border px-3 py-2 text-sm font-medium text-body transition-colors hover:bg-surface-alt"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={restoreTemplate}
            data-testid="confirm-restore-template"
            className="rounded-md bg-danger px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-danger/90"
          >
            Restaurar
          </button>
        </div>
      </Modal>
    </div>
  )
}

/**
 * F1: render de los resultados por caso de la corrida de tests. Muestra, por
 * cada caso publico: pasa/falla, entrada (stdin), esperado vs obtenido
 * (stdin_stdout) o el error de la comprobacion (pytest_assert).
 */
function TestResultsView({
  results,
  testing,
}: {
  results: TestCaseResult[] | null
  testing: boolean
}): ReactNode {
  if (testing && !results) {
    return <div className="p-4 text-sm text-muted">Corriendo las pruebas de tu código...</div>
  }
  if (!results) {
    return (
      <div className="p-4 text-sm text-muted">
        Tocá <span className="font-medium text-surface">Probar</span> para correr tu código contra
        los casos de prueba del ejercicio.
      </div>
    )
  }
  const passed = results.filter((r) => r.passed).length
  const total = results.length
  const allPassed = passed === total
  return (
    <div className="p-3">
      <div
        className={`mb-3 rounded-lg border px-3 py-2 text-sm font-medium ${
          allPassed
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
            : "border-danger/30 bg-danger/10 text-danger"
        }`}
      >
        {allPassed
          ? `Pasan las ${total} pruebas públicas. Buen trabajo.`
          : `Pasan ${passed} de ${total} pruebas públicas.`}
      </div>
      <ul className="space-y-2">
        {results.map((r, i) => (
          <TestResultCard key={r.id ?? `test-${i}`} result={r} index={i} />
        ))}
      </ul>
    </div>
  )
}

function TestResultCard({ result, index }: { result: TestCaseResult; index: number }): ReactNode {
  const r = result
  return (
    <li
      data-testid="test-result-card"
      data-passed={r.passed}
      className={`rounded-lg border p-3 ${
        r.passed ? "border-emerald-500/20 bg-emerald-500/5" : "border-danger/25 bg-danger/5"
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${
            r.passed ? "bg-emerald-500/25 text-emerald-300" : "bg-danger/25 text-danger"
          }`}
        >
          {r.passed ? "✓" : "✗"}
        </span>
        <span className="text-sm font-medium text-surface">{r.name ?? `Caso ${index + 1}`}</span>
        <span
          className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
            r.passed ? "bg-emerald-500/20 text-emerald-300" : "bg-danger/20 text-danger"
          }`}
        >
          {r.passed ? "Pasa" : "Falla"}
        </span>
      </div>

      {/* Detalle: solo lo mostramos si falla o si es stdin_stdout (util ver el
          esperado). Los datos son PUBLICOS (el backend nunca manda ocultos). */}
      {!r.passed && r.error && (
        <p className="mt-2 font-mono text-xs leading-relaxed text-danger">{r.error}</p>
      )}
      {r.type === "stdin_stdout" && (!r.passed || r.stdin) && (
        <dl className="mt-2 space-y-1.5 text-xs">
          {r.stdin.trim() !== "" && <TestKV label="Entrada" value={r.stdin} />}
          <TestKV label="Esperado" value={r.expected ?? ""} tone="expected" />
          {!r.passed && <TestKV label="Obtenido" value={r.actual} tone="actual" />}
        </dl>
      )}
    </li>
  )
}

function TestKV({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: "expected" | "actual"
}): ReactNode {
  const valueClass =
    tone === "expected" ? "text-emerald-300" : tone === "actual" ? "text-amber-300" : "text-surface"
  return (
    <div className="grid grid-cols-[72px_1fr] gap-2">
      <dt className="text-[10px] uppercase tracking-wider text-muted-soft pt-0.5">{label}</dt>
      <dd className={`min-w-0 whitespace-pre-wrap break-words font-mono ${valueClass}`}>
        {value === "" ? <span className="text-muted-soft italic">(vacío)</span> : value}
      </dd>
    </div>
  )
}
