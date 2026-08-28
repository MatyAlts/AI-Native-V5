/**
 * Vista del episodio activo (post-craft Fase 2).
 *
 * Este componente NO es ya la "page" raiz del web-student. Vive como vista
 * embebida dentro de la ruta `/episodio/$id` (TanStack Router file-based).
 * Recibe `episodeId` por prop (no por state) y un callback `onExit` que la
 * ruta usa para volver a "/" cuando el alumno cierra o sale.
 *
 * El selector de comisión / selector de TP YA NO viven acá — el flujo nuevo
 * es: home (/) -> /materia/:id (TareaSelector) -> /episodio/:id (esta vista).
 *
 * Hidratacion on-mount: pegamos a GET /api/v1/episodes/{id} para traer la TP,
 * mensajes y codigo. Si el episodio cerro / no existe / es cross-tenant,
 * limpiamos sessionStorage y llamamos onExit().
 */
import { CTRClient } from "@platform/ctr-client"
import { HelpButton, MarkdownRenderer } from "@platform/ui"
import {
  BookOpen,
  Bot,
  Clock,
  Code2,
  LogOut,
  MessageSquare,
  PauseCircle,
  RotateCcw,
  Send,
  ShieldAlert,
  Sparkles,
  User,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Panel,
  Group as PanelGroup,
  type PanelImperativeHandle,
  Separator as PanelResizeHandle,
} from "react-resizable-panels"
import { CodeEditor } from "../components/CodeEditor"
import { NotesPanel } from "../components/NotesPanel"
import { ReflectionModal } from "../components/ReflectionModal"
import { useMediaQuery } from "../hooks/useMediaQuery"
import { type LatchAbandono, crearLatchAbandono } from "../lib/abandonLatch"
import {
  type AvailableTarea,
  type Classification,
  DEFAULT_LANGUAGE,
  EpisodeStateError,
  LANGUAGE_LABELS,
  LANGUAGE_PLACEHOLDER,
  type Language,
  type TestCasePublic,
  classifyEpisode,
  closeEpisode,
  emitCodigoEjecutado,
  emitCopiaIntentada,
  emitEdicionCodigo,
  emitEpisodioAbandonado,
  emitLecturaEnunciado,
  emitPegaIntentada,
  emitTestsEjecutados,
  getEpisodeState,
  getTareaById,
  listEjerciciosTp,
  markEjercicioCompleted,
  resumeEpisode,
  sendMessage,
} from "../lib/api"
import { MONOLITHIC_ORDEN, saveArtefactoDraft } from "../lib/artefactos"
import { guardarCodigoPrevio, leerCodigoPrevio } from "../lib/codigoPrevio"
import { helpContent } from "../utils/helpContent"

const ACTIVE_EPISODE_KEY = "active-episode-id"
// ED-2: clave de persistencia del layout de los 3 paneles del episodio.
const PANELS_STORAGE_KEY = "web-student.episode.panels.v1"

/** F8: cita del RAG — material que fundamenta la respuesta del tutor. */
interface Citation {
  material: string
}

interface Message {
  role: "user" | "tutor"
  content: string
  ts: number
  /** F8: materiales del RAG citados en esta respuesta del tutor (si hubo). */
  citations?: Citation[]
}

/** Contexto de ejercicio activo para TPs multi-ejercicio (ADR-047). */
export interface EjercicioContext {
  entregaId: string
  ejercicioId: string
  ejercicioOrden: number
}

export interface EpisodeViewProps {
  episodeId: string
  /** Disparado cuando el alumno cierra el episodio o el recovery falla. */
  onExit: () => void
  /** Si viene de un ejercicio especifico, contiene entregaId y orden. */
  ejercicioContext?: EjercicioContext
  /**
   * Token getter de Clerk (via router context). Con esto el emit de abandono
   * usa fetch(keepalive) con `Authorization: Bearer` en vez de sendBeacon —
   * que no lleva el header y rebota 401 en prod (ver emitEpisodioAbandonado).
   * En dev sin Clerk devuelve null y se cae a sendBeacon (proxy Vite inyecta
   * los X-* headers). Fix QA 2026-06-15 #9.
   */
  getToken?: () => Promise<string | null>
}

/**
 * Resuelve el codigo_inicial de la TP (caso monolitico). Para TPs
 * multi-ejercicio (ADR-047) el codigo inicial vive en el ejercicio del banco y
 * se resuelve aparte via listEjerciciosTp (ver hydration). Si nada aplica, el
 * editor cae a su default.
 */
function resolveCodigoInicial(tarea: AvailableTarea): string | null {
  return tarea.inicial_codigo ?? null
}

export function EpisodeView({ episodeId, onExit, ejercicioContext, getToken }: EpisodeViewProps) {
  // El editor deja acá su flush. Salir del episodio dispara, en la TP
  // monolítica, la creación y el envío de la entrega — y eso pasa ANTES de
  // que el editor se desmonte. Sin forzar el flush acá, lo que se entrega es
  // lo que el alumno tenía hace hasta un segundo, no lo último que escribió.
  const flushEditorRef = useRef<(() => void) | null>(null)
  const salir = useCallback(() => {
    flushEditorRef.current?.()
    onExit()
  }, [onExit])

  const [tarea, setTarea] = useState<AvailableTarea | null>(null)
  // Sale del estado del episodio, no de un selector: el alumno puede estar
  // inscripto en varias comisiones y la que manda es la del episodio abierto.
  // Viaja al execution-service para la habilitacion progresiva (tarea 9.3).
  const [comisionId, setComisionId] = useState<string | null>(null)
  // Default neutro: si el ejercicio trae `inicial_codigo` se usa eso (ver
  // resolveCodigoInicial); este fallback NO debe sugerir una consigna concreta
  // (antes mostraba `def factorial` para TODOS los ejercicios — NEW-002 QA).
  // Arranca en el lenguaje por omision y se corrige abajo cuando se resuelve el
  // del ejercicio: un comentario `#` en un ejercicio Java no compila, y el
  // alumno abriria el editor con el archivo ya roto.
  const [code, setCode] = useState<string>(LANGUAGE_PLACEHOLDER[DEFAULT_LANGUAGE])
  // Si el alumno todavia no escribio nada y el ejercicio no trae scaffold, el
  // placeholder tiene que seguir al lenguaje. `usedPlaceholderRef` evita pisar
  // codigo real: solo se reemplaza lo que seguimos considerando andamio.
  const usedPlaceholderRef = useRef(true)

  /** Fija el lenguaje y, si el buffer sigue siendo el andamio por omision,
   * lo reemplaza por el del lenguaje resuelto. Nunca pisa codigo real: el
   * snapshot del alumno y el `inicial_codigo` del ejercicio bajan el flag. */
  const applyLanguage = useCallback((lang: Language) => {
    setLanguage(lang)
    if (usedPlaceholderRef.current) setCode(LANGUAGE_PLACEHOLDER[lang])
  }, [])
  // F1: test cases PUBLICOS resueltos en la hidratacion (del ejercicio del
  // banco si es multi-ejercicio, o de la TP monolitica). Solo publicos — el
  // backend sanea por rol (A0.3). Se pasan al CodeEditor para "Probar".
  const [testCases, setTestCases] = useState<TestCasePublic[]>([])
  // Lenguaje del episodio. Sale del ejercicio del banco si la TP es
  // multi-ejercicio, y de la TP si es monolitica — el backend garantiza que
  // coinciden (una TP admite un solo lenguaje, validado al agregar y al
  // publicar). Alimenta el modo de Monaco, el badge, los rotulos accesibles y
  // el payload del evento CTR de edicion.
  const [language, setLanguage] = useState<Language>(DEFAULT_LANGUAGE)
  // UUID del Ejercicio del banco. Lo necesita la ejecucion server-side: el
  // execution-service lee su definicion completa para inyectar los casos
  // ocultos. Arranca del contexto de navegacion y se re-resuelve en la
  // hidratacion, porque al recargar la pagina ese contexto se pierde.
  const [ejercicioId, setEjercicioId] = useState<string | null>(
    ejercicioContext?.ejercicioId ?? null,
  )
  // ED-4: orden del ejercicio dentro de la TP, ya resuelto. Sale del contexto
  // de navegacion y, si no vino (F5, link directo), del estado del episodio —
  // la misma cascada que usa la hidratacion. `null` = TP monolitica. Lo
  // necesitamos tambien FUERA del effect: al salir hay que dejar el buffer
  // guardado para el ejercicio siguiente.
  const [ejercicioOrdenEfectivo, setEjercicioOrdenEfectivo] = useState<number | null>(
    ejercicioContext?.ejercicioOrden ?? null,
  )
  const [messages, setMessages] = useState<Message[]>([])
  // Indicador de ACTIVIDAD en curso (no es la clasificacion final del classifier,
  // que se deriva post-cierre — ADR-020). Refleja el CANAL de actividad que el
  // alumno esta usando ahora: lectura=N1, edicion=N2, ejecucion=N3, dialogo con
  // el tutor=N4 (mismo canal que pinta el panel N4). Arranca en 1 y solo sube
  // (NEW-003 QA). Presentacion NO-reificante (ADR-053): describe la actividad
  // del momento, NO un puntaje ni un atributo del alumno (ver tooltip del chip).
  const [maxActividad, setMaxActividad] = useState<1 | 2 | 3 | 4>(1)
  const [input, setInput] = useState<string>("")
  const [streaming, setStreaming] = useState(false)
  const [classification, setClassification] = useState<Classification | null>(null)
  const [classificationFailed, setClassificationFailed] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  // Notas del alumno (N2 "Anotacion", UI-1). Se hidratan del CTR y NotesPanel
  // appendea localmente al guardar. Cada guardado emite anotacion_creada.
  const [notes, setNotes] = useState<{ contenido: string; ts: number }[]>([])
  // UI-8: error transitorio del stream del tutor (LLM saturado / red). NO cierra
  // el episodio ni ofrece salir — mantiene al alumno DENTRO y permite reintentar
  // el mismo mensaje. Separado de `error` (que si es fatal: hidratacion/cierre).
  const [sendError, setSendError] = useState<string | null>(null)
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null)
  // FIX B: clave estable por turno del alumno. Se genera una nueva por cada
  // envio fresco y se REUSA en handleRetry, asi el server deduplica el
  // prompt_enviado (mismo seq, sin re-publicar) y no crea prompts huerfanos que
  // inflarian CCD_orphan_ratio y el conteo de prompts de la tesis.
  const messageUuidRef = useRef<string | null>(null)
  const [hydrating, setHydrating] = useState<boolean>(true)
  const [closed, setClosed] = useState<boolean>(false)
  // Guard de doble-submit (NB-11): cierre/pausa disparan requests async. Un
  // doble-click deshabilita ambos botones y evita cerrar/abandonar 2 veces.
  const [submitting, setSubmitting] = useState<boolean>(false)
  const [reflectionTargetId, setReflectionTargetId] = useState<string | null>(null)
  // Flag: true cuando el alumno cierra el modal de reflexion sin completarla
  // (boton "No quiero reflexionar ahora" o escape). Se persiste en
  // localStorage para sobrevivir F5 — la pantalla post-cierre cambia el
  // tono pedagogico en consecuencia (Etapa 1.1 / QA round 2).
  const [skippedReflection, setSkippedReflection] = useState<boolean>(() => {
    if (typeof window === "undefined") return false
    return window.localStorage.getItem(`episode_${episodeId}_reflection_skipped`) === "1"
  })
  // Integridad de foco: trackea si el alumno cambio de pestaña y por cuanto.
  // `tabExit` null = sin aviso; con valor = overlay bloqueante al volver, con
  // el numero de salida y los segundos afuera. NO cierra el episodio — la
  // salida solo se registra en el CTR (politica server-side:
  // tutor-service config.enable_distraction_worker=False).
  const [tabExit, setTabExit] = useState<{ count: number; secondsAway: number } | null>(null)
  // Mobile (< lg / 1024px): los 3 paneles redimensionables se comprimen a
  // ~130px c/u e inutilizan el episodio (fix QA #14). Bajo ese breakpoint
  // mostramos UN panel full-width a la vez via tabs. Los 3 paneles siguen
  // SIEMPRE montados (Monaco posee su buffer; el IntersectionObserver del
  // reporter de lectura de la Consigna debe seguir corriendo) — alternamos
  // visibilidad con CSS, no con render condicional.
  const isMobile = useMediaQuery("(max-width: 1023px)")
  const [activeTab, setActiveTab] = useState<"consigna" | "editor" | "tutor">("editor")
  // ED-1: maximizar el editor. Colapsa los paneles Consigna + Tutor via su API
  // imperativa (siguen MONTADOS a 0 — Monaco conserva su buffer, el observer de
  // lectura sigue en el DOM). No unmontamos nada (mismo criterio que el layout
  // mobile). Solo aplica en desktop (el PanelGroup no existe en mobile).
  const [editorMaximized, setEditorMaximized] = useState(false)
  const consignaPanelRef = useRef<PanelImperativeHandle | null>(null)
  const tutorPanelRef = useRef<PanelImperativeHandle | null>(null)
  // ED-2: persistir el tamano de los paneles (react-resizable-panels v4 no
  // tiene autoSaveId — se persiste manualmente el layout en localStorage y se
  // restaura via `defaultLayout`). Gateado por `maximizedRef` para NO guardar
  // el layout transitorio de "maximizado" (sino el alumno abriria siempre
  // maximizado).
  const maximizedRef = useRef(false)
  const savedPanelLayout = useMemo<Record<string, number> | undefined>(() => {
    if (typeof window === "undefined") return undefined
    try {
      const raw = window.localStorage.getItem(PANELS_STORAGE_KEY)
      return raw ? (JSON.parse(raw) as Record<string, number>) : undefined
    } catch {
      return undefined
    }
  }, [])
  const handlePanelLayoutChanged = useCallback((layout: Record<string, number>) => {
    if (maximizedRef.current) return // no persistir el layout maximizado
    if (typeof window === "undefined") return
    try {
      window.localStorage.setItem(PANELS_STORAGE_KEY, JSON.stringify(layout))
    } catch {
      // best-effort: si localStorage falla (modo privado, cuota), seguimos.
    }
  }, [])
  const toggleEditorMaximized = useCallback(() => {
    const next = !editorMaximized
    // Marcar ANTES de colapsar para que el onLayoutChanged del colapso no
    // persista el layout maximizado. Al restaurar, re-habilitamos el guardado y
    // expandimos a la ultima medida. Efectos FUERA del updater de estado (React
    // puede invocar el updater mas de una vez).
    maximizedRef.current = next
    if (next) {
      consignaPanelRef.current?.collapse()
      tutorPanelRef.current?.collapse()
    } else {
      consignaPanelRef.current?.expand()
      tutorPanelRef.current?.expand()
    }
    setEditorMaximized(next)
  }, [editorMaximized])
  const tabExitCountRef = useRef(0)
  const hiddenAtRef = useRef<number | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  // Guard de idempotencia local del abandono: el backend ya es idempotente por
  // estado de sesion (ADR-025), pero esto evita spamear el endpoint cuando
  // beforeunload y visibilitychange→hidden disparan en sucesion (fix QA #9).
  //
  // NO es un booleano: `beforeunload` dispara ANTES de saber si el alumno se va
  // o se queda, asi que un guard plano se envenenaba con el primer "Quedarse" y
  // el cierre real ya no emitia nunca. Ver `lib/abandonLatch.ts`.
  const [abandonLatch] = useState<LatchAbandono>(crearLatchAbandono)
  // Guard de idempotencia del marcado de ejercicio completado (NB-12): el
  // cierre del episodio puede llegar por dos caminos que corren en carrera —
  // el ClassificationPanel (onReset) cuando la clasificacion resuelve, y el
  // ReflectionModal (onClose) cuando el alumno lo cierra antes de que resuelva.
  // Sin dedupe, ambos llaman markEjercicioCompleted para el mismo ejercicio.
  const markedCompletedRef = useRef(false)
  // Guard SINCRONICO de doble-submit para cerrar/pausar (NB-11). El state
  // `submitting` (abajo) NO se actualiza sincronicamente entre dos eventos
  // rapidos, asi que un doble-click alcanzaba a disparar el segundo handler
  // antes del re-render — el mismo motivo por el que NB-10 (materia.$id.tsx)
  // usa `openingRef`. Esta ref se setea en el acto y frena el segundo click;
  // `submitting` queda solo para el estado visual (`disabled`). Compartida por
  // cerrar Y pausar: son mutuamente excluyentes (no cerrar y abandonar a la vez).
  const actionInFlightRef = useRef(false)

  // P-17: cliente CTR con cola persistente (localStorage) + reintentos con
  // backoff + preservacion de orden por episodio. Hoy solo cablea los eventos
  // `pestana_*` (side-channel de bajo riesgo, ver nota abajo). Ante una falla
  // de red el evento queda en la cola y se reintenta — no se pierde en silencio.
  // El resto de los eventos CTR sigue en `emit*` (fetch directo) a proposito:
  // codigo_ejecutado / edicion_codigo / lectura_enunciado van entrelazados con
  // el ciclo del episodio (Pyodide, debounce del editor, cierre) y su re-cableo
  // es riesgoso para el orden/semantica del CTR; se difiere. El cliente usa el
  // fetch global parcheado (interceptor P-18) => hereda el Bearer sin getToken.
  const ctrClientRef = useRef<CTRClient | null>(null)
  useEffect(() => {
    const client = new CTRClient({
      episodeId,
      // F-3: dead-letter NUNCA en silencio (el modulo lo documenta asi). Sin este
      // callback el default es no-op y un evento `pestana_*` que reciba 409
      // (episodio cerrado) o agote reintentos se perdia sin rastro. Lo logueamos
      // con el tipo de evento y la razon (`rejected` | `exhausted`) para que un
      // drop del CTR quede visible en consola/telemetria.
      onDrop: (event, reason) => {
        console.error(
          `[CTR] evento descartado (dead-letter): ${event.event_type} — razon=${reason}`,
          { episodeId, eventUuid: event.event_uuid, attempts: event.attempts, reason },
        )
      },
    })
    ctrClientRef.current = client
    return () => {
      void client.flush()
      client.dispose()
      ctrClientRef.current = null
    }
  }, [episodeId])

  /* Emite por la cola durable del CTRClient en vez de por `fetch` directo.
   *
   * El fetch directo no tenia red: un fallo terminaba en un `console.warn` y
   * el trabajo del alumno se perdia sin que nadie se enterara — es el
   * incidente del piloto ("pause y perdi lo que habia escrito"). La cola
   * persiste en localStorage, sobrevive al refresh, reintenta con backoff y
   * manda `Idempotency-Key`, que es lo que evita que un reintento avance el
   * contador de seq y abra un hueco en la cadena.
   *
   * El fallback al fetch cubre la ventana entre el primer render y el
   * useEffect que monta el cliente: ahi todavia no hay cola, y perder el
   * evento seria justamente lo que estamos evitando. */
  const emitirConCola = useCallback(
    (porCola: (client: CTRClient) => void, directo: () => Promise<unknown>, tipo: string) => {
      const client = ctrClientRef.current
      if (client) {
        porCola(client)
        return
      }
      void directo().catch((e) => {
        console.warn(`emit ${tipo} failed (sin cola):`, e)
      })
    },
    [],
  )

  const ejercicioOrden = ejercicioContext?.ejercicioOrden ?? null

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  // Persistencia en sessionStorage del episodio activo (recovery via home).
  useEffect(() => {
    if (typeof window === "undefined") return
    if (closed) {
      window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
    } else {
      window.sessionStorage.setItem(ACTIVE_EPISODE_KEY, episodeId)
    }
  }, [episodeId, closed])

  // ADR-025 G10-A: emitir EpisodioAbandonado en beforeunload.
  // Ademas, preventDefault para que el browser muestre confirm nativo
  // "¿Estas seguro que querés salir?" — evita cierres accidentales de la
  // pestaña durante un episodio activo.
  useEffect(() => {
    if (typeof window === "undefined") return
    if (closed) return
    const handler = (event: BeforeUnloadEvent) => {
      // Pasamos getToken: con el 3er arg, emitEpisodioAbandonado usa
      // fetch(keepalive) con Bearer (sobrevive el unload y lleva el token);
      // sin el, caia a sendBeacon → sin Authorization → 401 en prod → el
      // evento nunca se appendea (fix QA #9). Guard local para no spamear.
      abandonLatch.intentarPorUnload(() => {
        void emitEpisodioAbandonado(
          episodeId,
          { reason: "beforeunload", last_activity_seconds_ago: 0 },
          getToken,
        )
      })
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [episodeId, closed, getToken, abandonLatch])

  // Integridad de pestaña: detecta cuando el alumno deja de ver el episodio
  // y vuelve. Usamos SOLO `visibilitychange` (NO `window blur`): blur se
  // dispara espurio al hacer foco en el editor Monaco y daba falsos positivos
  // (por eso el tracking estuvo desactivado). El worker server-side de cierre
  // por distracción quedó apagado (config.enable_distraction_worker=False),
  // así que emitir pestana_perdida ya NO cierra el episodio: solo registra en
  // el CTR y dispara el overlay bloqueante al volver.
  useEffect(() => {
    if (typeof document === "undefined") return
    if (closed) return

    function onVisibility() {
      if (document.visibilityState === "hidden") {
        hiddenAtRef.current = Date.now()
        // P-17: via cola persistente con reintentos (antes: fetch directo que
        // perdia el evento en silencio si la red fallaba).
        ctrClientRef.current?.pestanaPerdida({ trigger: "visibilitychange" })
        // NO emitimos episodio_abandonado acá: salir de la pestaña NO debe
        // pausar el episodio (decisión de producto, ver fix/remove-tab-away-
        // autoclose). El abandono real se persiste por `beforeunload` (cierre/
        // navegación, ahora con getToken — fix QA #9) y el worker server-side
        // de timeout (30min) como red de seguridad.
        return
      }
      // El alumno volvió a la pestaña.
      const hiddenAt = hiddenAtRef.current
      if (hiddenAt == null) return
      hiddenAtRef.current = null
      const secondsAway = Math.max(0, Math.round((Date.now() - hiddenAt) / 1000))
      // P-17: via cola persistente con reintentos (idem pestana_perdida).
      ctrClientRef.current?.pestanaRecuperada({ tiempo_fuera_segundos: secondsAway })
      tabExitCountRef.current += 1
      setTabExit({ count: tabExitCountRef.current, secondsAway })
    }

    document.addEventListener("visibilitychange", onVisibility)
    return () => document.removeEventListener("visibilitychange", onVisibility)
    // `episodeId` ya no es dep: el handler lee `ctrClientRef.current` (el cliente
    // CTR del episodio vigente) al momento de disparar, no lo captura en closure.
  }, [closed])

  // Hydration on-mount. El episodeId viene del path param, no del state.
  useEffect(() => {
    let cancelled = false
    setHydrating(true)
    setError(null)
    ;(async () => {
      try {
        const state = await getEpisodeState(episodeId)
        if (cancelled) return
        setComisionId(state.comision_id ?? null)
        if (state.estado === "closed") {
          window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
          salir()
          return
        }
        if (state.estado === "paused" || state.estado === "open") {
          // ADR-055 (fix 2026-06-10 #2): el episodio fue abandonado (cierre de
          // pestaña o timeout) — reconstruir la sesión del tutor antes de
          // seguir, sino todo evento posterior rebota contra sesión inexistente.
          // 2026-06-19: tambien para `open` — un episodio REABIERTO por el docente
          // queda `open` SIN sesion viva; sin este resume el alumno entra pero no
          // puede trabajar ni cerrar. resumeEpisode es idempotente: si la sesion
          // ya existe (open normal en curso), devuelve la vigente sin rehacer nada.
          await resumeEpisode(episodeId)
          if (cancelled) return
        }
        const t = await getTareaById(state.tarea_practica_id)
        if (cancelled) return
        if (!t) {
          window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
          setError("La TP del episodio anterior ya no esta disponible.")
          return
        }
        setTarea(t)
        // Lenguaje a nivel TP. Si la TP es multi-ejercicio se refina abajo con
        // el del ejercicio concreto, que es el que el alumno tiene delante.
        // Lo espejamos en una local porque la siembra ED-4 lo necesita YA, y
        // el state de `language` recien existe en el render siguiente.
        let langEfectivo: Language = t.language ?? DEFAULT_LANGUAGE
        applyLanguage(langEfectivo)
        // El ejercicio del episodio sale del ESTADO, no del contexto de
        // navegacion: el contexto se pierde al recargar la pagina y el estado
        // no. Sin esto, un F5 dejaba la ejecucion server-side sin el id del
        // ejercicio y el boton volvia a "no disponible".
        if (state.ejercicio_id) setEjercicioId(state.ejercicio_id)

        // F1 + codigo inicial (ADR-047). Para TPs multi-ejercicio el ejercicio
        // y sus test cases PUBLICOS viven en el banco; los traemos una sola vez
        // y de ahi salen tanto los tests como el codigo inicial. Para TPs
        // monoliticas ambos vienen en la propia TP (ya saneada por rol, A0.3).
        let resolvedTests: TestCasePublic[] = []
        // El orden sale del contexto de navegacion, y si no vino (F5, link
        // directo) del propio estado del episodio, que lo persiste.
        const ordenEfectivo = ejercicioOrden ?? state.ejercicio_orden ?? null
        setEjercicioOrdenEfectivo(ordenEfectivo)
        if (ordenEfectivo != null) {
          try {
            const tpEjs = await listEjerciciosTp(state.tarea_practica_id)
            if (cancelled) return
            const match = tpEjs.find((te) => te.orden === ordenEfectivo)
            resolvedTests = (match?.ejercicio?.test_cases ?? []).filter(
              (tc) => tc.is_public !== false,
            )
            const ejLanguage = match?.ejercicio?.language
            if (ejLanguage) {
              langEfectivo = ejLanguage
              applyLanguage(ejLanguage)
            }
            if (match?.ejercicio?.id) setEjercicioId(match.ejercicio.id)
            // Codigo inicial del ejercicio del banco (solo si no hay snapshot ni
            // codigo inicial a nivel TP — mismo fallback que antes).
            if (!state.last_code_snapshot && !resolveCodigoInicial(t)) {
              const ejInicial = match?.ejercicio?.inicial_codigo ?? null
              if (ejInicial) {
                usedPlaceholderRef.current = false
                setCode(ejInicial)
              }
            }
          } catch {
            // best-effort: sin tests / sin codigo inicial del banco → default.
          }
        } else {
          resolvedTests = (t.test_cases ?? []).filter((tc) => tc.is_public !== false)
        }
        setTestCases(resolvedTests)

        if (state.last_code_snapshot) {
          usedPlaceholderRef.current = false
          setCode(state.last_code_snapshot)
        } else {
          // Scaffold a nivel TP.
          //
          // Esta rama estaba gateada por `ordenEfectivo == null` ("TP
          // monolitica") y eso dejaba un AGUJERO en la cascada: en una TP
          // MULTI-ejercicio cuya TP tiene `inicial_codigo`, la rama del
          // ejercicio del banco (arriba) esta guardada por
          // `!resolveCodigoInicial(t)` — el scaffold de la TP tiene precedencia
          // sobre el del ejercicio — y esta otra no corria. Resultado: el
          // docente escribia un scaffold y el alumno abria el editor con el
          // andamio del lenguaje.
          //
          // Se veia como un detalle cosmetico hasta que ED-4 llenó ese hueco:
          // sin este `else`, el codigo del ejercicio ANTERIOR entraba encima de
          // la consigna del docente. Y a diferencia del andamio, eso parece
          // legitimo — el alumno no tiene forma de saber que lo que ve no es lo
          // que le dejaron.
          //
          // Las dos ramas de scaffold son mutuamente excluyentes (por ese mismo
          // guard), asi que abrir el `else` NO cambia ninguna precedencia: solo
          // hace que la de la TP se aplique donde antes no se aplicaba nadie.
          const initialCode = resolveCodigoInicial(t)
          if (initialCode) {
            usedPlaceholderRef.current = false
            setCode(initialCode)
          }
        }

        // ED-4: ultimo eslabon REAL de la cascada de siembra. Solo entra si
        // nada de lo anterior aplico (`usedPlaceholderRef` sigue en true).
        //
        // La cascada completa, de mayor a menor precedencia:
        //   1. `state.last_code_snapshot` — lo que el alumno escribio en ESTE
        //      episodio. Pisarlo es borrarle trabajo.
        //   2. `inicial_codigo` de la TP — scaffold del docente.
        //   3. `inicial_codigo` del ejercicio del banco — el otro scaffold del
        //      docente, solo si la TP no trae el suyo.
        //   4. esto: el codigo del ejercicio anterior de la misma TP.
        //   5. `LANGUAGE_PLACEHOLDER` — el andamio del lenguaje.
        //
        // Que 4 vaya despues de 2 y 3 no es cosmetico: sembrar codigo de otro
        // ejercicio encima de la consigna del docente es contradecir el
        // enunciado con algo que parece legitimo.
        //
        // Esta siembra NO emite `edicion_codigo`: sale por el mismo camino que
        // `last_code_snapshot` (el `initialCode` con el que se monta
        // `CodeEditor`, que llega a Monaco por `editor.create`). El componente
        // ni siquiera esta montado todavia — mientras `hydrating` es true la
        // pagina devuelve el skeleton. Ver el test "el re-montaje NO emite un
        // edicion_codigo fantasma".
        if (usedPlaceholderRef.current && typeof window !== "undefined") {
          const previo = leerCodigoPrevio(window.sessionStorage, {
            tareaId: state.tarea_practica_id,
            ejercicioOrden: ordenEfectivo,
            language: langEfectivo,
          })
          if (previo) {
            usedPlaceholderRef.current = false
            setCode(previo)
          }
        }
        setMessages(
          state.messages.map((m) => ({
            role: m.role === "assistant" ? "tutor" : "user",
            content: m.content,
            ts: Date.parse(m.ts) || Date.now(),
          })),
        )
        // UI-1: hidratar las anotaciones previas (N2) desde el CTR.
        setNotes(
          (state.notes ?? []).map((n) => ({
            contenido: n.contenido,
            ts: Date.parse(n.ts) || Date.now(),
          })),
        )
      } catch (e) {
        if (cancelled) return
        if (e instanceof EpisodeStateError && (e.status === 404 || e.status === 403)) {
          window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
          salir()
        } else {
          console.warn("Episode hydration failed:", e)
          setError("No se pudo cargar el episodio.")
        }
      } finally {
        if (!cancelled) setHydrating(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [episodeId, salir, ejercicioOrden, applyLanguage])

  // UI-8: enviar un mensaje al tutor. Si el stream falla (LLM saturado, red,
  // sesion pausada), NO cerramos el episodio ni ofrecemos salir — un error
  // transitorio no debe romper el episodio ni la cadena CTR. Mostramos un aviso
  // "reintentá" y dejamos al alumno DENTRO. `retryMessage` reenvia el mismo
  // texto sin duplicar la burbuja del usuario.
  async function handleSend(retryMessage?: string) {
    const userMessage = (retryMessage ?? input).trim()
    if (!userMessage || streaming) return
    const isRetry = retryMessage != null
    // FIX B: envio fresco → nueva clave; reintento → reusar la misma para que el
    // server deduplique el prompt_enviado en vez de duplicarlo.
    const messageUuid =
      isRetry && messageUuidRef.current ? messageUuidRef.current : crypto.randomUUID()
    messageUuidRef.current = messageUuid
    if (!isRetry) {
      setInput("")
      setMessages((m) => [...m, { role: "user", content: userMessage, ts: Date.now() }])
    }
    // N4: dialogar con el tutor socratico es el canal N4 de la UI (mismo que
    // pinta el panel N4). Indicador de actividad del momento, no clasificacion.
    setMaxActividad((a) => (a < 4 ? 4 : a))
    setSendError(null)
    setLastFailedMessage(null)
    setStreaming(true)

    const tutorMessage: Message = { role: "tutor", content: "", ts: Date.now() }
    setMessages((m) => [...m, tutorMessage])

    try {
      for await (const event of sendMessage(episodeId, userMessage, messageUuid)) {
        if (event.type === "chunk") {
          tutorMessage.content += event.content
          setMessages((m) => [...m.slice(0, -1), { ...tutorMessage }])
          scrollToBottom()
        } else if (event.type === "error") {
          // Fallo del tutor/LLM reportado dentro del stream. Lo tratamos como
          // transitorio (UI-8): reintentable, sin cerrar el episodio.
          throw new Error(event.message ?? "tutor_error")
        } else if (event.type === "done") {
          console.debug("chunks_used_hash:", event.chunks_used_hash)
          // F8: el `done` trae las citas del RAG (campo aditivo — lib/api.ts no
          // lo tipa aun, por eso el cast). Solo las adjuntamos si hubo material.
          const citations = (event as { citations?: Citation[] }).citations
          if (citations && citations.length > 0) {
            tutorMessage.citations = citations
            setMessages((m) => [...m.slice(0, -1), { ...tutorMessage }])
          }
        }
      }
    } catch (e) {
      // UI-8: mantener al alumno DENTRO. Sacamos la burbuja del tutor de ESTE
      // intento —este o no llego ningun chunk— porque el "Reintentar" vuelve a
      // streamear una respuesta fresca; dejar la parcial huerfana confundiria al
      // alumno y quedaria colgada sin evento tutor_respondio en el CTR (el LLM
      // fallo a mitad). NO tocamos `closed` ni sessionStorage: el episodio sigue
      // abierto.
      setMessages((m) => (m.length > 0 && m[m.length - 1]?.role === "tutor" ? m.slice(0, -1) : m))
      console.warn("tutor stream failed (retryable):", e)
      setLastFailedMessage(userMessage)
      setSendError(
        "El tutor está saturado en este momento. Tu episodio sigue abierto — esperá unos segundos y reintentá.",
      )
    } finally {
      setStreaming(false)
    }
  }

  // UI-8: reintenta el ultimo mensaje que fallo. resumeEpisode es idempotente
  // (ADR-055): si la sesion sigue viva es no-op; si el episodio se pauso por
  // inactividad, la reconstruye desde el CTR. Asi un mismo boton recupera tanto
  // el caso "tutor saturado" como "sesion pausada" sin sacar al alumno.
  async function handleRetry() {
    if (!lastFailedMessage || streaming) return
    const msg = lastFailedMessage
    setSendError(null)
    try {
      await resumeEpisode(episodeId)
    } catch (e) {
      console.warn("resume on retry failed (best-effort):", e)
    }
    await handleSend(msg)
  }

  /**
   * ED-4: deja el buffer actual disponible para el ejercicio SIGUIENTE de esta
   * misma TP. Se llama en las dos salidas explicitas (cerrar y pausar): ambas
   * son el momento en que el alumno abandona este ejercicio, y `code` ya es el
   * espejo vivo del buffer de Monaco (`onCodeChange`).
   *
   * No escribe nada si el alumno no llego a escribir codigo propio: el andamio
   * por omision del lenguaje no vale la pena arrastrarlo, y el siguiente
   * ejercicio lo va a poner igual.
   *
   * No toca el CTR. Es estado de navegacion, como `active-exercise-context`.
   */
  function persistirCodigoParaElProximoEjercicio() {
    if (typeof window === "undefined") return
    const tareaId = tarea?.id
    if (!tareaId || ejercicioOrdenEfectivo == null) return
    if (code === LANGUAGE_PLACEHOLDER[language]) return
    guardarCodigoPrevio(window.sessionStorage, {
      tareaId,
      ejercicioOrden: ejercicioOrdenEfectivo,
      language,
      code,
    })
  }

  async function handleClose() {
    // Guard doble-submit (NB-11): ref SINCRONICA (no el state async) — un segundo
    // click en el mismo tick ve el flag ya seteado y aborta. Consistente con NB-10.
    if (actionInFlightRef.current) return
    actionInFlightRef.current = true
    setSubmitting(true)
    setError(null)
    try {
      await closeEpisode(episodeId, "student_finished")
    } catch (e) {
      const msg = String(e)
      if (msg.includes("404")) {
        window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
        salir()
        return
      }
      setError(`Error cerrando: ${e}`)
      // Reintentable: liberamos ambos guards (visual + sincronico) para que el
      // alumno pueda volver a intentar cerrar.
      actionInFlightRef.current = false
      setSubmitting(false)
      return
    }
    // ED-4: el episodio cerro de verdad; lo que el alumno dejo escrito es la
    // semilla del ejercicio siguiente de esta TP.
    persistirCodigoParaElProximoEjercicio()
    setClosed(true)
    setReflectionTargetId(episodeId)
    try {
      const c = await classifyEpisode(episodeId)
      setClassification(c)
    } catch (e) {
      // Best-effort: no bloqueamos el cierre si falla la clasificación,
      // pero seteamos el flag para mostrar un panel de fallback en lugar
      // de quedar en limbo silencioso (bug previo: el alumno cerraba y
      // no veía nada si el classifier estaba caído).
      console.warn("classify episode failed (best-effort):", e)
      setClassificationFailed(true)
    }
    window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
  }

  // Salir SIN cerrar: abandono explícito (reason="explicit", caller=alumno).
  // El backend lo registra en la cadena CTR y el partition_worker deja el
  // episodio en `paused` (ADR-025/055). Para retomar, el alumno entra al
  // ejercicio y toca "Continuar": ese flujo SÍ persiste el contexto del
  // ejercicio (active-exercise-context) y la hidratación reanuda con
  // resumeEpisode. NO clasificamos ni disparamos reflexión.
  //
  // BORRAMOS ACTIVE_EPISODE_KEY (igual que handleClose). Si no, el recovery del
  // home (routes/index.tsx) rebota a /episodio/:id SIN el contexto de ejercicio,
  // y el episodio se abre "como TP" en vez del ejercicio que estabas haciendo
  // (bug 2026-06-16). El guard local evita re-emitir en el beforeunload del
  // unmount (idempotente igual en backend, fix QA #9).
  async function handlePauseExit() {
    // Guard doble-submit (NB-11): ref SINCRONICA (no el state async), igual que
    // handleClose y NB-10. Frena el segundo click antes del re-render.
    if (actionInFlightRef.current) return
    actionInFlightRef.current = true
    setSubmitting(true)
    setError(null)
    // Definitivo, a diferencia del `beforeunload`: el episodio se pauso de
    // verdad y el unload posterior no debe volver a emitir.
    abandonLatch.marcarDefinitivo()
    try {
      await emitEpisodioAbandonado(
        episodeId,
        { reason: "explicit", last_activity_seconds_ago: 0 },
        getToken,
      )
    } catch (e) {
      // Best-effort: el backend es idempotente por estado de sesion (ADR-025).
      // No bloqueamos la salida por un fallo de red del emit.
      console.warn("emit episodio_abandonado (explicit) failed:", e)
    }
    // ED-4: pausar tambien es salir del ejercicio. El episodio queda `paused` y
    // el alumno puede retomarlo (ahi manda `last_code_snapshot`, no esto), pero
    // si en el medio arranca el ejercicio siguiente, hereda igual.
    persistirCodigoParaElProximoEjercicio()
    window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
    salir()
  }

  // Marca el ejercicio como completado UNA sola vez (NB-12). Serializa los dos
  // caminos que pueden dispararlo en carrera (ClassificationPanel.onReset y
  // ReflectionModal.onClose) via markedCompletedRef: el primero que entra gana,
  // el segundo es no-op. Si el marcado falla, liberamos el guard para permitir
  // que el otro camino lo reintente (best-effort — no bloquea la navegacion).
  async function markEjercicioCompletedOnce() {
    if (!ejercicioContext) return
    if (markedCompletedRef.current) return
    markedCompletedRef.current = true
    try {
      await markEjercicioCompleted(
        ejercicioContext.entregaId,
        ejercicioContext.ejercicioOrden,
        episodeId,
        ejercicioContext.ejercicioId,
      )
    } catch {
      markedCompletedRef.current = false
    }
  }

  const elapsedSeconds = useElapsedSeconds(closed ? null : episodeId)

  if (hydrating) {
    return (
      <div className="page-enter flex-1 p-6">
        <div className="max-w-7xl mx-auto space-y-4">
          {/* Header skeleton */}
          <div className="skeleton h-10 rounded-lg" />
          {/* 3-panel grid skeleton */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-200px)]">
            <div className="skeleton rounded-xl" />
            <div className="skeleton rounded-xl" />
            <div className="skeleton rounded-xl" />
          </div>
          <p className="text-center text-sm text-muted animate-pulse-soft">
            Hidratando tu episodio...
          </p>
        </div>
      </div>
    )
  }

  // Importante: gateamos por `reflectionTargetId === null` para que el
  // ReflectionModal (renderizado en el return principal, línea 566) tenga
  // tiempo de aparecer antes de saltar al ClassificationPanel. Sin este
  // guard, el classify async terminaba en ~2s y el component swap dejaba al
  // modal huérfano (montado por 1 frame y desaparecido). ADR-035 declara la
  // reflexion metacognitiva como señal canónica N4 — no opcional saltearla.
  if (classification && reflectionTargetId === null) {
    return (
      <ClassificationPanel
        classification={classification}
        skippedReflection={skippedReflection}
        isMultiExercise={ejercicioContext != null}
        onReset={async () => {
          setClassification(null)
          // NB-12: dedupe compartido con el camino del ReflectionModal.
          await markEjercicioCompletedOnce()
          salir()
        }}
      />
    )
  }

  // Fallback: el episodio cerró pero la clasificación falló. Mejor mostrar
  // un panel explícito que dejar al alumno en limbo viendo la UI del
  // episodio activo (con `closed=true` pero sin feedback ni CTA claro).
  if (classificationFailed && reflectionTargetId === null) {
    return <ClassificationFallbackPanel onReset={salir} />
  }

  if (!tarea) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-md text-center">
          <p className="text-sm font-medium text-danger mb-2">
            {error ?? "No pudimos cargar el episodio."}
          </p>
          <button
            type="button"
            onClick={salir}
            className="mt-4 px-4 py-2 rounded text-sm font-medium text-white"
            style={{ backgroundColor: "var(--color-accent-brand)" }}
          >
            Volver a mis materias
          </button>
        </div>
      </div>
    )
  }

  // Los 3 paneles como JSX compartido entre el layout desktop (PanelGroup
  // redimensionable) y el mobile (tabs). NO duplicamos la logica/markup —
  // ambos layouts renderizan estos mismos nodos. Ver fix QA #14.
  const consignaPanel = (
    <section
      className="animate-fade-in-up animate-delay-50 flex-1 flex flex-col rounded-xl border border-border bg-surface overflow-hidden shadow-[0_1px_3px_-1px_rgba(0,0,0,0.04)]"
      aria-label="Consigna del problema"
    >
      <PanelHeader
        level="N1"
        label="Consigna"
        icon={<BookOpen className="h-3.5 w-3.5" />}
        colorVar="var(--color-level-n1)"
      />
      <EnunciadoPanel
        tarea={tarea}
        episodeId={closed ? null : episodeId}
        ejercicioOrden={ejercicioContext?.ejercicioOrden ?? null}
      />
      {/* UI-1: N2 "Anotacion". El alumno anota su plan/dudas; cada guardado
          emite anotacion_creada al CTR. Oculto una vez cerrado el episodio
          (el CTR es append-only y rechaza eventos post-close con 409). */}
      {!closed && (
        <div className="shrink-0 border-t border-border-soft bg-surface-alt/30 p-3">
          <NotesPanel episodeId={episodeId} initialNotes={notes} defaultOpen={false} />
        </div>
      )}
    </section>
  )

  const editorPanel = (
    <section
      className="animate-fade-in-up animate-delay-100 flex-1 flex flex-col rounded-xl border border-border bg-surface overflow-hidden shadow-[0_1px_3px_-1px_rgba(0,0,0,0.04)]"
      aria-label="Editor de código"
      data-tour="editor-codigo"
    >
      <PanelHeader
        level="N3"
        label="Editor de código"
        icon={<Code2 className="h-3.5 w-3.5" />}
        colorVar="var(--color-level-n3)"
        badge={LANGUAGE_LABELS[language]}
      />
      <CodeEditor
        initialCode={code}
        testCases={testCases}
        language={language}
        flushRef={flushEditorRef}
        ejercicioId={ejercicioId ?? undefined}
        // Sin esto el execution-service no sabe a que cadena adjuntar
        // `tests_ejecutados`, y Java sigue sin emitirlo (ver `tutor_client.py`).
        episodeId={episodeId}
        // Sin esto, con `EXECUTION_ENABLED_COMISIONES` cargada el backend
        // rechaza TODAS las corridas de alumno con un 503 enganoso.
        comisionId={comisionId ?? undefined}
        getToken={getToken}
        isMaximized={editorMaximized}
        // ED-1: el boton maximizar solo tiene sentido en desktop (el PanelGroup
        // no existe en mobile — ahi el alumno enfoca el editor con las tabs).
        onToggleMaximize={isMobile ? undefined : toggleEditorMaximized}
        onTestsRun={(result) => {
          // F1: correr tests es actividad de EJECUCION (N3), igual que "Ejecutar".
          setMaxActividad((a) => (a < 3 ? 3 : a))
          // Emitir tests_ejecutados al CTR (conteos agregados). Va por la cola
          // durable como el resto de los eventos de codigo: es el de MAYOR
          // señal de todos — el labeler v1.2.0 deriva N3 vs N4 de aca — y era
          // justo el que quedaba por fetch pelado, sin reintentos ni
          // Idempotency-Key. Un fallo de red lo perdia en un console.warn y el
          // episodio quedaba mal nivelado en la tesis.
          const payloadTests = {
            test_count_total: result.total,
            test_count_passed: result.passed,
            test_count_failed: result.failed,
            tests_publicos: result.total,
            ejecucion_ms: Math.round(result.durationMs),
          }
          emitirConCola(
            (c) => c.testsEjecutados(payloadTests),
            () => emitTestsEjecutados(episodeId, payloadTests),
            "tests_ejecutados",
          )
        }}
        // El buffer de Monaco es del editor; este espejo existe para que el
        // re-montaje del panel (cruzar el breakpoint mobile desmonta y vuelve a
        // montar `CodeEditor`, porque vive en dos subarboles distintos) lo
        // re-siembre con lo ultimo que el alumno escribio. Antes se
        // actualizaba solo al hidratar y al Ejecutar: un cambio de zoom en el
        // medio de un ejercicio le borraba todo lo tipeado desde la ultima
        // corrida. NO emite nada al CTR — `edicion_codigo` sigue saliendo por
        // `onEditDebounced`.
        onCodeChange={setCode}
        onCodeExecuted={(result) => {
          setCode(result.code)
          setMaxActividad((a) => (a < 3 ? 3 : a))
          // P0 (QA 2026-05-29): emitir codigo_ejecutado al CTR. Sin esto el
          // classifier no distingue N3/N4 y todo cae a apropiacion_superficial.
          const payloadEjecucion = {
            code: result.code,
            stdout: result.output,
            stderr: result.error ?? "",
            duration_ms: Math.round(result.durationMs),
          }
          emitirConCola(
            (c) => c.codigoEjecutado(payloadEjecucion),
            () => emitCodigoEjecutado(episodeId, payloadEjecucion),
            "codigo_ejecutado",
          )
        }}
        onEditDebounced={(snapshot, diffChars, origin) => {
          setMaxActividad((a) => (a < 2 ? 2 : a))
          // Guardamos el snapshot para poder mandarlo en el submit. El alumno
          // entrega desde la lista de ejercicios, cuando ya salió de acá y el
          // código no está en memoria de nadie. En la TP monolítica el scope
          // es el episodio: la entrega recién se crea al salir, así que acá
          // todavía no hay un `entregaId` con el que keyear.
          if (ejercicioContext) {
            saveArtefactoDraft(ejercicioContext.entregaId, {
              orden: ejercicioContext.ejercicioOrden,
              ejercicio_id: ejercicioContext.ejercicioId,
              episode_id: episodeId,
              codigo: snapshot,
              language,
            })
          } else {
            saveArtefactoDraft(episodeId, {
              orden: MONOLITHIC_ORDEN,
              ejercicio_id: null,
              episode_id: episodeId,
              codigo: snapshot,
              language,
            })
          }
          const payloadEdicion = {
            snapshot,
            diff_chars: Math.abs(diffChars),
            language,
            origin,
          }
          emitirConCola(
            (c) => c.edicionCodigo(payloadEdicion),
            () => emitEdicionCodigo(episodeId, payloadEdicion),
            "edicion_codigo",
          )
        }}
        onPasteAttempt={(payload) => {
          const payloadPega = {
            contenido_longitud: payload.contenidoLongitud,
            contenido_preview: payload.contenidoPreview,
            metodo: payload.metodo,
          }
          emitirConCola(
            (c) => c.pegaIntentada(payloadPega),
            () => emitPegaIntentada(episodeId, payloadPega),
            "pega_intentada",
          )
        }}
        onCopyAttempt={(payload) => {
          const payloadCopia = {
            seleccion_chars: payload.seleccionChars,
            metodo: payload.metodo,
          }
          emitirConCola(
            (c) => c.copiaIntentada(payloadCopia),
            () => emitCopiaIntentada(episodeId, payloadCopia),
            "copia_intentada",
          )
        }}
      />
    </section>
  )

  const tutorPanel = (
    <section
      className="animate-fade-in-up animate-delay-150 flex-1 flex flex-col rounded-xl border border-border bg-surface overflow-hidden shadow-[0_1px_3px_-1px_rgba(0,0,0,0.04)]"
      aria-label="Tutor socrático"
      data-tour="tutor-chat"
    >
      <PanelHeader
        level="N4"
        label="Tutor socrático"
        icon={<MessageSquare className="h-3.5 w-3.5" />}
        colorVar="var(--color-level-n4)"
        badge={streaming ? "escribiendo…" : "Mistral"}
        badgePulse={streaming}
      />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div
            data-testid="chat-pedagogical-contract"
            className="animate-fade-in mx-auto max-w-prose"
          >
            <div className="rounded-xl border border-level-n4/20 bg-level-n4/5 p-5 relative overflow-hidden">
              <div
                aria-hidden="true"
                className="absolute left-0 top-0 bottom-0 w-1"
                style={{ background: "var(--color-level-n4)" }}
              />
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-4 w-4" style={{ color: "var(--color-level-n4)" }} />
                <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-muted">
                  Contrato pedagógico
                </span>
              </div>
              <p className="text-sm font-semibold text-ink mb-1.5 leading-snug">
                El tutor no te da la respuesta.
              </p>
              <p className="text-sm text-body leading-relaxed mb-3">
                Te hace preguntas para que llegues vos.
              </p>
              <p className="text-xs text-muted leading-relaxed">
                Empezás vos: contale en qué estás pensando para resolver este ejercicio.
              </p>
            </div>
          </div>
        )}
        {messages.map((m, i) => {
          const isLastTutor =
            m.role === "tutor" && messages.findLastIndex((mm) => mm.role === "tutor") === i
          const isUser = m.role === "user"
          return (
            <div
              key={`${m.ts}-${i}`}
              className={`animate-fade-in-up flex items-start gap-2.5 ${
                isUser ? "flex-row-reverse" : ""
              }`}
            >
              {/* Avatar */}
              <div
                aria-hidden="true"
                className={`shrink-0 inline-flex h-7 w-7 items-center justify-center rounded-full ${
                  isUser
                    ? "bg-accent-brand text-white"
                    : "bg-level-n4/10 text-level-n4 border border-level-n4/30"
                }`}
                style={!isUser ? { color: "var(--color-level-n4)" } : undefined}
              >
                {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
              </div>
              {/* Burbuja */}
              <div className={`flex flex-col gap-1 max-w-[80%] ${isUser ? "items-end" : ""}`}>
                <span className="text-[10px] uppercase tracking-wider font-semibold text-muted">
                  {isUser ? "Vos" : "Tutor"}
                </span>
                <div
                  data-testid={isLastTutor ? "tutor-message-last" : undefined}
                  className={`rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    isUser
                      ? "bg-accent-brand text-white rounded-tr-sm whitespace-pre-wrap"
                      : "bg-surface-alt text-body border border-border-soft rounded-tl-sm"
                  }`}
                >
                  {/* UI-3: el tutor responde en markdown → lo renderizamos (antes
                      se veian los asteriscos crudos). El mensaje del alumno queda
                      como texto plano (whitespace-pre-wrap). */}
                  {isUser ? (
                    m.content
                  ) : m.content ? (
                    <MarkdownRenderer content={m.content} />
                  ) : streaming ? (
                    <span className="inline-flex gap-1 items-center text-muted">
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted animate-pulse-soft" />
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted animate-pulse-soft animate-delay-150" />
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted animate-pulse-soft animate-delay-300" />
                    </span>
                  ) : null}
                </div>
                {/* F8: citas del RAG. Sobrio, bajo el mensaje del tutor; solo si
                    esta respuesta se fundamento en algun material. */}
                {!isUser && m.citations && m.citations.length > 0 && (
                  <div
                    data-testid="tutor-citations"
                    className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted"
                  >
                    <span className="inline-flex items-center gap-1 font-medium">
                      <BookOpen className="h-3 w-3" aria-hidden="true" />
                      Basado en:
                    </span>
                    {m.citations.map((c, ci) => (
                      <span
                        key={`${c.material}-${ci}`}
                        className="rounded-md border border-border-soft bg-surface-alt px-1.5 py-0.5"
                      >
                        {c.material}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* UI-8: aviso de tutor saturado + reintento. NO cierra el episodio ni
          ofrece salir — el alumno sigue DENTRO y reenvia el mismo mensaje. */}
      {sendError && (
        <div
          data-testid="tutor-send-error"
          className="animate-fade-in-up mx-3 mb-2 flex items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2.5 text-xs text-warning"
        >
          <span className="leading-relaxed">{sendError}</span>
          <button
            type="button"
            onClick={() => handleRetry()}
            disabled={streaming}
            data-testid="tutor-retry-button"
            className="press-shrink shrink-0 inline-flex items-center gap-1.5 rounded-md bg-warning px-2.5 py-1 font-medium text-white transition-colors hover:bg-warning/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RotateCcw className="h-3 w-3" />
            Reintentar
          </button>
        </div>
      )}

      <div className="border-t border-border-soft p-3 bg-surface-alt/40">
        <div className="flex gap-2 items-end">
          <textarea
            data-testid="tutor-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder="Escribí tu mensaje · Enter para enviar"
            rows={2}
            disabled={streaming}
            className="flex-1 px-3 py-2 text-sm rounded-lg border border-border bg-surface text-ink resize-none focus:outline-none focus:border-accent-brand focus:ring-2 focus:ring-accent-brand/20 transition-all placeholder:text-muted-soft"
          />
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={streaming || !input.trim()}
            aria-label="Enviar mensaje"
            className="press-shrink shrink-0 inline-flex items-center justify-center h-[42px] w-[42px] rounded-lg bg-accent-brand text-white hover:bg-accent-brand-deep disabled:bg-border-strong disabled:cursor-not-allowed transition-colors"
          >
            {streaming ? (
              <span className="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full motion-safe:animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </section>
  )

  // Tabs mobile: metadata declarativa (reusa los colores de nivel del header).
  const mobileTabs: {
    key: "consigna" | "editor" | "tutor"
    label: string
    icon: React.ReactNode
    colorVar: string
  }[] = [
    {
      key: "consigna",
      label: "Consigna",
      icon: <BookOpen className="h-4 w-4" />,
      colorVar: "var(--color-level-n1)",
    },
    {
      key: "editor",
      label: "Editor",
      icon: <Code2 className="h-4 w-4" />,
      colorVar: "var(--color-level-n3)",
    },
    {
      key: "tutor",
      label: "Tutor",
      icon: <MessageSquare className="h-4 w-4" />,
      colorVar: "var(--color-level-n4)",
    },
  ]

  return (
    // Wrapper de altura fija — clave para que los 3 paneles (Consigna /
    // Editor / Tutor) tengan scroll INDEPENDIENTE. Sin este wrapper, el
    // Monaco editor crece con el contenido y empuja al chat fuera del
    // viewport, obligando a hacer scroll de toda la página para alternar
    // entre código y mensaje del tutor.
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden relative">
      {/* ═══ HEADER CONTEXT — chip de episodio + tiempo + nivel + acciones ═══ */}
      <div
        data-testid="episode-context-header"
        className="animate-fade-in-down border-b border-border-soft px-6 py-2.5 bg-surface flex items-center gap-3 text-xs"
      >
        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface-alt border border-border-soft font-mono text-muted">
          <span
            aria-hidden="true"
            className="inline-block w-1.5 h-1.5 rounded-full bg-success animate-pulse-soft"
          />
          {episodeId.slice(0, 6)}…{episodeId.slice(-4)}
        </span>
        <span className="text-muted-soft">·</span>
        <span className="text-muted font-mono tabular-nums">{formatElapsed(elapsedSeconds)}</span>
        <span className="text-muted-soft">·</span>
        {(() => {
          const act = {
            1: {
              txt: "N1 · lectura activa",
              cls: "bg-level-n1/10 border-level-n1/30 text-level-n1",
              dot: "var(--color-level-n1)",
            },
            2: {
              txt: "N2 · edición activa",
              cls: "bg-level-n2/10 border-level-n2/30 text-level-n2",
              dot: "var(--color-level-n2)",
            },
            3: {
              txt: "N3 · ejecución activa",
              cls: "bg-level-n3/10 border-level-n3/30 text-level-n3",
              dot: "var(--color-level-n3)",
            },
            4: {
              txt: "N4 · diálogo con el tutor",
              cls: "bg-level-n4/10 border-level-n4/30 text-level-n4",
              dot: "var(--color-level-n4)",
            },
          }[maxActividad]
          return (
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border font-medium ${act.cls}`}
              title="Nivel de la actividad que estas haciendo ahora. NO es la clasificacion final del episodio (esa la calcula el sistema al cerrar)."
            >
              <span
                aria-hidden="true"
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: act.dot }}
              />
              {act.txt}
            </span>
          )
        })()}
        {/* UI-7: countdown discreto del plazo de la TP (solo si tiene fecha_fin). */}
        {tarea?.fecha_fin && (
          <>
            <span className="text-muted-soft">·</span>
            <DeadlineChip fechaFin={tarea.fecha_fin} />
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
          <HelpButton title="Tutor Socratico" content={helpContent.episode} />
          {/* El docente decide por TP si se puede pausar/retomar (permite_pausa).
              undefined = backwards-compat (endpoint que no lo popula) → permitido. */}
          {tarea?.permite_pausa !== false && (
            <button
              type="button"
              onClick={handlePauseExit}
              disabled={submitting}
              data-testid="pause-episode-button"
              title="Salí ahora y retomá este episodio más tarde, justo donde lo dejaste. Tu progreso queda guardado."
              className="press-shrink inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded-md text-body hover:bg-surface-alt transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <PauseCircle className="h-3 w-3" />
              Seguir después
            </button>
          )}
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            data-testid="close-episode-button"
            // ED-2: "Cerrar episodio" es la accion que TERMINA el episodio y
            // dispara la reflexion + clasificacion. A `text-xs px-3 py-1.5`
            // quedaba del tamano de los chips informativos de la barra y el
            // alumno no la encontraba (reporte de alumno). Sube al tamano `md`
            // del sistema (`text-sm` + `px-4 py-2`); "Seguir despues" se queda
            // chica a proposito: la jerarquia visual tiene que distinguir la
            // salida definitiva de la pausa.
            className="press-shrink inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium border border-border rounded-md text-body hover:bg-danger-soft hover:border-danger/30 hover:text-danger transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <LogOut className="h-4 w-4" />
            Cerrar episodio
          </button>
        </div>
      </div>

      {error && (
        <div className="animate-fade-in-down bg-danger-soft border-b border-danger/30 text-danger px-6 py-2 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => {
              window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
              salir()
            }}
            className="press-shrink ml-4 px-3 py-1 text-xs font-medium bg-danger text-white rounded hover:bg-danger/90"
          >
            Salir
          </button>
        </div>
      )}

      {/* ═══ PANELES: Consigna · Editor · Tutor ═════════════════════════
          Desktop (lg+): PanelGroup horizontal redimensionable.
          Mobile (< lg): tabs con UN panel full-width visible a la vez —
          a 390px los 3 paneles se comprimian a ~130px c/u, inusable (QA #14).
          Los 3 paneles estan SIEMPRE montados en ambos layouts: alternamos
          visibilidad con `hidden`, no con render condicional, para que Monaco
          conserve su buffer y no haya que re-medir/re-crear el editor. */}
      {isMobile ? (
        <div className="flex-1 flex flex-col min-h-0 p-3 gap-3">
          {/* Selector de tabs */}
          <div
            role="tablist"
            aria-label="Paneles del episodio"
            className="shrink-0 grid grid-cols-3 gap-1 rounded-lg border border-border-soft bg-surface-alt/60 p-1"
          >
            {mobileTabs.map((t) => {
              const active = activeTab === t.key
              return (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  data-testid={`episode-tab-${t.key}`}
                  onClick={() => setActiveTab(t.key)}
                  className={`inline-flex items-center justify-center gap-1.5 rounded-md px-2 py-2 text-xs font-medium transition-colors ${
                    active
                      ? "bg-surface text-ink shadow-[0_1px_2px_-1px_rgba(0,0,0,0.12)]"
                      : "text-muted hover:text-body"
                  }`}
                  style={active ? { color: t.colorVar } : undefined}
                >
                  <span aria-hidden="true">{t.icon}</span>
                  {t.label}
                </button>
              )
            })}
          </div>
          {/* Paneles: todos montados, solo el activo visible */}
          <div className={`flex-1 min-h-0 ${activeTab === "consigna" ? "flex" : "hidden"}`}>
            {consignaPanel}
          </div>
          <div className={`flex-1 min-h-0 ${activeTab === "editor" ? "flex" : "hidden"}`}>
            {editorPanel}
          </div>
          <div className={`flex-1 min-h-0 ${activeTab === "tutor" ? "flex" : "hidden"}`}>
            {tutorPanel}
          </div>
        </div>
      ) : (
        <PanelGroup
          orientation="horizontal"
          className="flex-1 p-4 min-h-0"
          // ED-2: restaurar + persistir el layout de paneles.
          defaultLayout={savedPanelLayout}
          onLayoutChanged={handlePanelLayoutChanged}
        >
          {/* ED-1: mas espacio default para el editor (33/40/27). Consigna y
              Tutor son colapsables para el modo "maximizar editor". */}
          <Panel
            id="ep-consigna"
            panelRef={consignaPanelRef}
            defaultSize={33}
            minSize={15}
            collapsible
            collapsedSize={0}
            className="flex"
          >
            {consignaPanel}
          </Panel>

          <PanelResizeHandle className="group relative w-2 mx-0.5 flex items-center justify-center cursor-col-resize">
            <span className="block h-12 w-0.5 rounded-full bg-border-soft group-hover:bg-accent-brand group-data-[resize-handle-active]:bg-accent-brand transition-colors" />
          </PanelResizeHandle>

          <Panel id="ep-editor" defaultSize={40} minSize={15} className="flex">
            {editorPanel}
          </Panel>

          <PanelResizeHandle className="group relative w-2 mx-0.5 flex items-center justify-center cursor-col-resize">
            <span className="block h-12 w-0.5 rounded-full bg-border-soft group-hover:bg-accent-brand group-data-[resize-handle-active]:bg-accent-brand transition-colors" />
          </PanelResizeHandle>

          <Panel
            id="ep-tutor"
            panelRef={tutorPanelRef}
            defaultSize={27}
            minSize={15}
            collapsible
            collapsedSize={0}
            className="flex"
          >
            {tutorPanel}
          </Panel>
        </PanelGroup>
      )}

      <ReflectionModal
        isOpen={reflectionTargetId !== null}
        episodeId={reflectionTargetId}
        onClose={async (submitted) => {
          setReflectionTargetId(null)
          if (!submitted) {
            // Skip explicito: persistir flag para la pantalla post-cierre
            // y para sobrevivir F5. La pantalla nueva (rama "sin reflexion"
            // del ClassificationPanel) lo lee de aca.
            setSkippedReflection(true)
            if (typeof window !== "undefined") {
              window.localStorage.setItem(`episode_${episodeId}_reflection_skipped`, "1")
            }
          }
          // Cierre/skip del modal de reflexión:
          // - Si ya hay classification cargada, el render condicional muestra
          //   ClassificationPanel (la pantalla N4) y desde ahí el alumno
          //   navega con "Siguiente ejercicio →".
          // - Si NO hay classification (classify falló silent o tardó >timeout
          //   y el user cerró el modal antes), el alumno quedaba ATASCADO en
          //   la EpisodePage con `closed=true` sin acción clara. Ahora si es
          //   multi-ejercicio marcamos el ejercicio completo + onExit; si es
          //   TP single, solo onExit (vuelve a /materia/$id).
          if (!classification) {
            // NB-12: dedupe compartido con el camino del ClassificationPanel.
            // Best-effort: si falla, la TP queda con el ejercicio sin marcar
            // pero el alumno puede volver a entrar y completar.
            await markEjercicioCompletedOnce()
            salir()
          }
        }}
      />

      {/* Overlay de integridad: bloqueante al volver de la pestaña. NO cierra
          el episodio (el alumno reconoce y sigue); la salida ya quedó en el CTR. */}
      {tabExit && (
        <div
          className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-ink/70 px-4 backdrop-blur-sm"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="tab-exit-title"
        >
          <div className="animate-scale-in w-full max-w-md rounded-xl bg-surface p-6 shadow-2xl">
            <div className="flex items-start gap-4">
              <span
                aria-hidden="true"
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-warning-soft text-warning"
              >
                <ShieldAlert className="h-6 w-6" />
              </span>
              <div className="min-w-0">
                <h2 id="tab-exit-title" className="text-lg font-semibold leading-snug text-ink">
                  Saliste de la evaluación
                </h2>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">
                  Mientras resolvés un episodio no podés cambiar de pestaña ni de ventana. Esta
                  salida quedó registrada en la trazabilidad del episodio y tu docente puede verla.
                </p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md bg-surface-alt px-3 py-2 text-xs text-muted">
              <span className="font-medium text-ink tabular-nums">
                {tabExit.count} {tabExit.count === 1 ? "salida registrada" : "salidas registradas"}
              </span>
              <span className="text-muted-soft">·</span>
              <span className="tabular-nums">{tabExit.secondsAway}s afuera</span>
            </div>

            <button
              type="button"
              onClick={() => setTabExit(null)}
              className="mt-5 w-full rounded-md bg-accent-brand px-4 py-2.5 text-sm font-medium text-surface transition-colors hover:bg-accent-brand-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand"
            >
              Entendido, volver al ejercicio
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function PanelHeader({
  level,
  label,
  icon,
  colorVar,
  badge,
  badgePulse = false,
}: {
  level: "N1" | "N2" | "N3" | "N4"
  label: string
  icon: React.ReactNode
  colorVar: string
  badge?: string
  badgePulse?: boolean
}) {
  return (
    <div
      data-testid={`section-kicker-${level.toLowerCase()}`}
      className="relative px-4 py-3 border-b border-border-soft bg-surface-alt/40 flex items-center gap-3"
    >
      {/* Banda vertical del color del nivel */}
      <div
        aria-hidden="true"
        className="absolute left-0 top-0 bottom-0 w-0.5"
        style={{ backgroundColor: colorVar }}
      />
      <div
        className="inline-flex h-6 w-6 items-center justify-center rounded-md"
        style={{
          backgroundColor: `color-mix(in oklch, ${colorVar} 12%, transparent)`,
          color: colorVar,
        }}
      >
        {icon}
      </div>
      <div className="flex flex-col gap-0 min-w-0 flex-1">
        <span
          className="text-[9px] uppercase tracking-[0.14em] font-semibold leading-none"
          style={{ color: colorVar }}
        >
          {level}
        </span>
        <h2 className="text-sm font-semibold text-ink leading-tight tracking-tight">{label}</h2>
      </div>
      {badge && (
        <span
          className={`shrink-0 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface border border-border-soft text-[10px] font-medium text-muted ${
            badgePulse ? "animate-pulse-soft" : ""
          }`}
        >
          {badgePulse && <span className="inline-block w-1.5 h-1.5 rounded-full bg-success" />}
          {badge}
        </span>
      )}
    </div>
  )
}

function useElapsedSeconds(episodeId: string | null): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!episodeId) {
      setSeconds(0)
      return
    }
    setSeconds(0)
    const interval = window.setInterval(() => {
      setSeconds((s) => s + 1)
    }, 1000)
    return () => window.clearInterval(interval)
  }, [episodeId])
  return seconds
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

function formatRemaining(ms: number): string {
  const totalMin = Math.floor(ms / 60000)
  const days = Math.floor(totalMin / 1440)
  const hours = Math.floor((totalMin % 1440) / 60)
  const mins = totalMin % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

/**
 * UI-7: chip discreto con el tiempo restante hasta el cierre de la TP.
 * Refresca cada 30s. Muted por default, warning si queda <24h, danger si vencio.
 * Solo se monta cuando la TP tiene fecha_fin (el caller lo gatea).
 */
function DeadlineChip({ fechaFin }: { fechaFin: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(t)
  }, [])
  const end = Date.parse(fechaFin)
  if (Number.isNaN(end)) return null
  const remainingMs = end - now
  const vencido = remainingMs <= 0
  const urgent = !vencido && remainingMs < 24 * 3600 * 1000
  const label = vencido ? "Plazo vencido" : `Vence en ${formatRemaining(remainingMs)}`
  const cls = vencido
    ? "bg-danger-soft border-danger/30 text-danger"
    : urgent
      ? "bg-warning-soft border-warning/30 text-warning"
      : "bg-surface-alt border-border-soft text-muted"
  return (
    <span
      title="Fecha limite de entrega de este trabajo practico."
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border font-medium ${cls}`}
    >
      <Clock aria-hidden="true" className="h-3 w-3" />
      {label}
    </span>
  )
}

/** Hook que mide tiempo de visibilidad + tab focus y emite el delta al
 * backend cada `flushMs` o al unmount. Señal observable canónica de N1. */
function useReadingTimeReporter(episodeId: string | null, enabled: boolean, flushMs = 30_000) {
  const elementRef = useRef<HTMLDivElement | null>(null)
  // Track el valor actual de enabled para que el cleanup del useEffect pueda
  // decidir si emitir el "último flush" o saltearlo. Evita 409 Conflict del
  // CTR append-only cuando el episodio se cierra y este componente transita
  // enabled=true→false: sin este guard el cleanup viejo (closure con enabled
  // viejo) emite lectura_enunciado después del close del episodio.
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  useEffect(() => {
    if (!enabled) return
    const target = elementRef.current
    if (!target) return

    let visibleInDom = false
    let tabVisible = typeof document !== "undefined" ? document.visibilityState === "visible" : true
    let accumMs = 0
    let lastTickAt: number | null = null

    function isCounting() {
      return visibleInDom && tabVisible
    }
    function tick() {
      if (lastTickAt != null) accumMs += Date.now() - lastTickAt
      lastTickAt = isCounting() ? Date.now() : null
    }

    async function flush() {
      tick()
      if (accumMs < 1000 || !episodeId) return
      const seconds = accumMs / 1000
      accumMs = 0
      // Sigue por fetch directo, a diferencia de los eventos de codigo. Este
      // hook vive en `EnunciadoPanel`, que no tiene el CTRClient a mano, y
      // `lectura_enunciado` mide tiempo de lectura: perderlo degrada una
      // metrica, no borra trabajo del alumno. La reacumulacion de `accumMs`
      // ante el fallo es la red que le corresponde.
      try {
        await emitLecturaEnunciado(episodeId, { duration_seconds: seconds })
      } catch (e) {
        accumMs += seconds * 1000
        console.warn("emit lectura_enunciado failed:", e)
      }
    }

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          tick()
          visibleInDom = entry.isIntersecting && entry.intersectionRatio >= 0.25
          if (isCounting() && lastTickAt == null) lastTickAt = Date.now()
        }
      },
      { threshold: [0, 0.25, 0.5, 1] },
    )
    io.observe(target)

    function onVisibility() {
      tick()
      tabVisible = document.visibilityState === "visible"
      if (isCounting() && lastTickAt == null) lastTickAt = Date.now()
    }
    document.addEventListener("visibilitychange", onVisibility)

    if (isCounting()) lastTickAt = Date.now()
    const flushTimer = window.setInterval(() => {
      void flush()
    }, flushMs)

    return () => {
      io.disconnect()
      document.removeEventListener("visibilitychange", onVisibility)
      window.clearInterval(flushTimer)
      // Skip el último flush si el componente se está deshabilitando
      // (típicamente: episodio cerrado). El CTR es append-only y rechaza
      // eventos post-close con 409 Conflict.
      if (enabledRef.current) {
        void flush()
      }
    }
  }, [episodeId, enabled, flushMs])

  return elementRef
}

function EnunciadoPanel({
  tarea,
  episodeId,
  ejercicioOrden,
}: {
  tarea: AvailableTarea
  episodeId: string | null
  ejercicioOrden: number | null
}) {
  // Reading time reporter: siempre activo mientras el panel está visible.
  // El toggle open/close del layout viejo de 2-cols ya no aplica — en el
  // layout 3-cols cada panel ocupa su columna entera.
  const enunciadoRef = useReadingTimeReporter(episodeId, episodeId !== null)

  // ADR-047: si es ejercicio especifico, resolvemos titulo+enunciado via la
  // tabla intermedia. Para no agregar prop drilling desde MateriaPage,
  // hacemos un fetch local. Best-effort: si falla, cae a `tarea.enunciado`.
  const [ejercicioInfo, setEjercicioInfo] = useState<{
    titulo: string
    enunciado_md: string
    total: number
  } | null>(null)
  useEffect(() => {
    if (ejercicioOrden == null) {
      setEjercicioInfo(null)
      return
    }
    let cancelled = false
    listEjerciciosTp(tarea.id)
      .then((pairs) => {
        if (cancelled) return
        const target = pairs.find((p) => p.orden === ejercicioOrden)
        if (target) {
          setEjercicioInfo({
            titulo: target.ejercicio.titulo,
            enunciado_md: target.ejercicio.enunciado_md,
            total: pairs.length,
          })
        }
      })
      .catch(() => {
        /* best-effort */
      })
    return () => {
      cancelled = true
    }
  }, [tarea.id, ejercicioOrden])

  let displayContent = tarea.enunciado
  let headerLabel = `${tarea.codigo} (v${tarea.version})`

  if (ejercicioInfo) {
    displayContent = `## ${ejercicioInfo.titulo}\n\n${ejercicioInfo.enunciado_md}`
    headerLabel = `${tarea.codigo} — Ejercicio ${ejercicioOrden} de ${ejercicioInfo.total}`
  }

  return (
    <>
      {/* Sub-header con metadata de la TP/ejercicio */}
      <div className="px-4 py-2 border-b border-border-soft bg-surface-alt/40 text-[11px] text-muted font-mono flex items-center justify-between">
        <span className="truncate">{headerLabel}</span>
      </div>
      {/* Contenido scroll fluido — ocupa toda la altura disponible del panel */}
      <div
        ref={enunciadoRef}
        className="flex-1 overflow-y-auto px-5 py-4 text-sm text-body leading-relaxed"
      >
        <MarkdownRenderer content={displayContent} />
      </div>
    </>
  )
}

/**
 * Mapea la clasificación N4 (técnica, para investigación) a feedback
 * pedagógico (humano, accionable). Sin jerga "CT/CCD/CII", sin hash,
 * sin porcentajes sueltos. La data técnica sigue persistida en el CTR
 * para el análisis del docente/investigador, pero al alumno le mostramos
 * UN feedback constructivo + 1-3 sugerencias concretas para la próxima vez.
 */
/**
 * Pantalla post-cierre cuando el alumno saltea la reflexion metacognitiva
 * (boton "No quiero reflexionar ahora" en el ReflectionModal).
 *
 * No es positiva ni de atencion — es factual. La reflexion es opcional
 * por ADR-035, pero la UI no debe mentir diciendo "Buen trabajo /
 * Resolviste el ejercicio" como en la rama apropiacion_superficial.
 * Honestidad tecnica como asset academico (PRODUCT.md §"Design Principles" #5).
 */
function buildSinReflexionFeedback(): {
  tono: "positivo" | "neutro" | "atencion"
  titulo: string
  mensaje: string
  sugerencias: string[]
} {
  return {
    tono: "neutro",
    titulo: "Tu trabajo quedo registrado",
    mensaje:
      "Cerraste el episodio sin pasar por la reflexion final. Esa instancia es opcional pero es donde el modelo N4 captura la apropiacion reflexiva del trabajo que hiciste. La proxima vez, si tenes 2 minutos, dedicalos a contestar las 3 preguntas — sirve mas para vos que para el sistema.",
    sugerencias: [],
  }
}

// Feedback al alumno POR SUBGRUPO (8 perfiles, modo sombra). Es la fuente
// narrativa principal: cuenta la MISMA historia que ve el docente sobre este
// episodio, en segunda persona. Marcador anti-reificacion: describe lo que paso
// "en este episodio", no atributos del alumno (PRODUCT.md + ADR-053). El tono
// hereda del eje (reflexiva=positivo, superficial=neutro, delegacion=atencion).
const FEEDBACK_SUBGRUPO: Record<
  string,
  { tono: "positivo" | "neutro" | "atencion"; titulo: string; mensaje: string }
> = {
  autonomo_competente: {
    tono: "positivo",
    titulo: "¡Muy bien!",
    mensaje:
      "Resolviste por tu cuenta, sin apoyarte en el tutor: mostraste autonomia y la sostuviste hasta llegar a la solucion. Asi se construye criterio propio.",
  },
  colaborador_reflexivo: {
    tono: "positivo",
    titulo: "¡Muy bien!",
    mensaje:
      "Usaste el tutor para pensar, no para que te resuelva: preguntaste, probaste por tu cuenta y seguiste elaborando sobre lo que te devolvia. Ese es el uso que mas te hace aprender.",
  },
  autonomo_trabado: {
    tono: "neutro",
    titulo: "Vas por buen camino",
    mensaje:
      "Insististe por tu cuenta un buen rato, pero te quedaste trabado sin llegar a destrabarte. Intentar solo esta perfecto; cuando te frenes mucho, pedile una pista al tutor para avanzar sin que te de la solucion.",
  },
  escribe_sin_validar: {
    tono: "neutro",
    titulo: "Buen avance",
    mensaje:
      "Escribiste bastante codigo, pero casi no lo ejecutaste para comprobar si hacia lo que esperabas. Correr lo que vas armando seguido te muestra los errores temprano y te ahorra vueltas.",
  },
  colaborador_funcional: {
    tono: "neutro",
    titulo: "Buen trabajo",
    mensaje:
      "Usaste el tutor para avanzar y llegaste a una solucion, aunque probaste poco por tu cuenta. La proxima, antes de preguntar, tira tu propia idea: aunque falle, te hace pensar mas.",
  },
  desenganchado: {
    tono: "neutro",
    titulo: "Quedo a mitad de camino",
    mensaje:
      "En este episodio hubo poca actividad sobre el problema: ni trabajo sostenido sobre el codigo ni dialogo con el tutor. Cuando tengas un rato sin apuro, retomalo y dale una vuelta tranquilo.",
  },
  dependiente_delegador: {
    tono: "atencion",
    titulo: "Hay algo importante que repasar",
    mensaje:
      "En este episodio, la mayor parte del trabajo lo hizo el tutor, no vos. La IA esta para ayudarte a pensar, no para reemplazarte. La proxima, pone TU idea primero (aunque este incompleta) y usa al tutor para discutirla, no para que te de la respuesta.",
  },
  indeterminado: {
    tono: "neutro",
    titulo: "Episodio corto",
    mensaje:
      "La sesion fue demasiado corta para evaluar como trabajaste. Proba un episodio mas largo, donde puedas trabajar el problema y dialogar con el tutor.",
  },
}

function buildPedagogicalFeedback(c: Classification): {
  tono: "positivo" | "neutro" | "atencion"
  titulo: string
  mensaje: string
  sugerencias: string[]
} {
  const sugerencias: string[] = []

  // Reglas accionables basadas en cada coherencia específica.
  // Las metricas son `number | null` cuando no hay datos suficientes — `??`
  // los trata como neutros (0.5 = ni alto ni bajo) y evita falsos positivos.
  if ((c.ccd_orphan_ratio ?? 0) > 0.5) {
    sugerencias.push(
      "Cuando vayas a ejecutar el código, contale al tutor qué esperás que pase ANTES de correrlo. Te ayuda a anticipar errores.",
    )
  }
  if ((c.ccd_mean ?? 1) < 0.3) {
    sugerencias.push(
      "Hablá más con el tutor mientras trabajás. La IA está para ordenarte el pensamiento, no para resolverte el ejercicio.",
    )
  }
  if ((c.ct_summary ?? 1) < 0.3) {
    sugerencias.push(
      "Trabajaste de forma intermitente. Sesiones más continuas (sin tantas pausas) te van a rendir mejor.",
    )
  }
  if ((c.cii_stability ?? 1) < 0.3 && (c.cii_evolution ?? 1) < 0.3) {
    sugerencias.push(
      "Cambiaste mucho de estrategia entre intentos. Probá quedarte con una idea y refinarla, en lugar de empezar de cero.",
    )
  }

  // El SUBGRUPO manda la narrativa (misma historia que el docente). Las
  // coherencias de arriba quedan como sugerencias accionables subordinadas.
  // Sin subgrupo (classifications viejas) cae al switch por eje de abajo.
  const porSubgrupo = c.subgrupo?.key ? FEEDBACK_SUBGRUPO[c.subgrupo.key] : undefined
  if (porSubgrupo) {
    return {
      tono: porSubgrupo.tono,
      titulo: porSubgrupo.titulo,
      mensaje: porSubgrupo.mensaje,
      sugerencias:
        sugerencias.length > 0
          ? sugerencias
          : porSubgrupo.tono === "positivo"
            ? ["Proba un ejercicio mas desafiante para seguir creciendo."]
            : [],
    }
  }

  switch (c.appropriation) {
    case "apropiacion_reflexiva":
      return {
        tono: "positivo",
        titulo: "¡Muy bien!",
        mensaje:
          "Mostraste un trabajo reflexivo. Tomaste decisiones con criterio y fuiste verbalizando tu razonamiento. Seguí así.",
        sugerencias:
          sugerencias.length > 0
            ? sugerencias
            : ["Probá un ejercicio más desafiante para seguir creciendo."],
      }
    case "apropiacion_superficial":
      return {
        tono: "neutro",
        titulo: "Buen trabajo",
        mensaje:
          "Resolviste el ejercicio. Para la próxima vez, intentá profundizar en el porqué de cada decisión, no solo en hacer que funcione.",
        sugerencias:
          sugerencias.length > 0
            ? sugerencias
            : ["Cuando termines un ejercicio, repasá qué aprendiste y contátelo al tutor."],
      }
    case "delegacion_pasiva":
      return {
        tono: "atencion",
        titulo: "Hay algo importante que repasar",
        mensaje:
          "Cerraste el episodio, pero el sistema detectó que la mayor parte del trabajo cognitivo lo hizo el tutor — no vos. La IA está acá para ayudarte a pensar, no para reemplazarte. Para la próxima, intentá poner TU idea primero (aunque esté incompleta) y usá al tutor para discutirla, no para que te dé la respuesta.",
        sugerencias:
          sugerencias.length > 0
            ? sugerencias
            : [
                "Cuando arranques el próximo ejercicio, escribí en el chat 'Mi idea es X' antes de pedir cualquier ayuda. Eso ya empieza a construir tu razonamiento.",
              ],
      }
    default: {
      // Defensa contra `appropriation` desconocido (clasificador con
      // categoría nueva, valor null, etc.). Sin este default la función
      // retornaba undefined y rompía el ClassificationPanel en runtime.
      return {
        tono: "neutro",
        titulo: "Episodio cerrado",
        mensaje:
          "Cerramos tu episodio. La clasificación pedagógica no pudo determinar un nivel claro de apropiación esta vez — puede deberse a un episodio muy corto o con datos insuficientes para evaluar las coherencias.",
        sugerencias:
          sugerencias.length > 0
            ? sugerencias
            : ["Probá un episodio más largo donde puedas dialogar con el tutor."],
      }
    }
  }
}

function ClassificationPanel({
  classification,
  skippedReflection,
  isMultiExercise,
  onReset,
}: {
  classification: Classification
  // Etapa 1.1: si el alumno cerro sin completar la reflexion, el feedback
  // debe ser honesto al respecto en lugar de mostrar el "Buen trabajo /
  // Resolviste el ejercicio" que la rama apropiacion_superficial muestra.
  // La honestidad tecnica es asset academico (PRODUCT.md §"Design Principles").
  skippedReflection?: boolean
  isMultiExercise?: boolean
  onReset: () => void
}) {
  const feedback = skippedReflection
    ? buildSinReflexionFeedback()
    : buildPedagogicalFeedback(classification)

  const tonoStyles: Record<typeof feedback.tono, string> = {
    positivo: "bg-success-soft border-success/40 text-success",
    neutro: "bg-accent-brand-soft border-accent-brand/30 text-accent-brand",
    atencion: "bg-warning-soft border-warning/40 text-warning",
  }

  return (
    <div className="flex-1 p-6 overflow-y-auto max-w-3xl mx-auto w-full">
      {/* Header empático, sin etiqueta diagnóstica técnica. */}
      <div className={`rounded-2xl border p-7 mb-8 ${tonoStyles[feedback.tono]}`}>
        <p className="text-xs font-mono uppercase tracking-[0.15em] opacity-70 mb-2">
          {skippedReflection ? "Cierre del ejercicio · sin reflexion" : "Cierre del ejercicio"}
        </p>
        <h2 className="font-serif text-3xl font-medium leading-tight">{feedback.titulo}</h2>
        <p className="mt-4 text-base leading-relaxed opacity-90">{feedback.mensaje}</p>
      </div>

      {/* Sugerencias concretas y accionables — vacias si fue skip de reflexion. */}
      {feedback.sugerencias.length > 0 && (
        <section className="mb-8">
          <h3 className="text-xs font-mono uppercase tracking-[0.15em] text-muted mb-4">
            Para la próxima vez
          </h3>
          <ul className="space-y-3">
            {feedback.sugerencias.map((s) => (
              <li
                key={s}
                className="flex items-start gap-3 rounded-lg border border-border-soft bg-surface p-4"
              >
                <span
                  aria-hidden="true"
                  className="mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-accent-brand"
                />
                <span className="text-sm leading-relaxed text-body">{s}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* CTA único, claro. Sin hash, sin metadata técnica. */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onReset}
          className="press-shrink px-5 py-2.5 bg-accent-brand hover:bg-accent-brand-deep text-white rounded-lg text-sm font-medium transition-colors"
        >
          {isMultiExercise ? "Siguiente ejercicio →" : "Volver a mis materias"}
        </button>
      </div>
    </div>
  )
}

function ClassificationFallbackPanel({ onReset }: { onReset: () => void }) {
  // Panel mínimo cuando el cierre fue OK pero `classifyEpisode` falló.
  // Antes de este componente, el alumno quedaba en limbo: `closed=true`
  // pero sin classification, la UI seguía mostrando el episodio activo.
  return (
    <div className="flex-1 p-6 overflow-y-auto max-w-2xl mx-auto w-full">
      <div className="rounded-2xl border border-border-soft bg-surface p-7 mb-6">
        <p className="text-xs font-mono uppercase tracking-[0.15em] text-muted mb-2">
          Cierre del ejercicio
        </p>
        <h2 className="font-serif text-3xl font-medium leading-tight text-ink">
          Cerramos tu episodio
        </h2>
        <p className="mt-4 text-base leading-relaxed text-body">
          Tu trabajo quedó registrado criptográficamente. La clasificación pedagógica no se pudo
          calcular en este momento — el sistema la va a procesar más tarde y vas a poder verla en{" "}
          <strong>Mis reflexiones</strong>.
        </p>
      </div>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onReset}
          className="press-shrink px-5 py-2.5 bg-accent-brand hover:bg-accent-brand-deep text-white rounded-lg text-sm font-medium transition-colors"
        >
          Volver a mis materias
        </button>
      </div>
    </div>
  )
}

// CoherenceCard fue removido — codigo muerto (no se usa en ningun lado de
// EpisodePage.tsx ni en el flow del alumno post-cierre actual). El render de
// metricas por coherencia se hace ahora via buildPedagogicalFeedback() arriba.

// Meter y CoherenceCard removidos — eran codigo muerto (sin callers).
// Ver git history si se necesitan otra vez.

// Default export para retro-compat con `App.tsx` viejo (queda como referencia
// no utilizada cuando main.tsx usa RouterProvider). NO romper si alguien
// importa `EpisodePage`.
export default EpisodeView
