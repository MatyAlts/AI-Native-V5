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
import { HelpButton, MarkdownRenderer } from "@platform/ui"
import { Bot, BookOpen, Code2, LogOut, MessageSquare, Send, ShieldAlert, Sparkles, User } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from "react-resizable-panels"
import { CodeEditor } from "../components/CodeEditor"
import { ReflectionModal } from "../components/ReflectionModal"
import {
  type AvailableTarea,
  type Classification,
  EpisodeStateError,
  classifyEpisode,
  closeEpisode,
  emitCodigoEjecutado,
  emitCopiaIntentada,
  emitEdicionCodigo,
  emitEpisodioAbandonado,
  emitLecturaEnunciado,
  emitPegaIntentada,
  emitPestanaPerdida,
  emitPestanaRecuperada,
  getEpisodeState,
  getTareaById,
  listEjerciciosTp,
  markEjercicioCompleted,
  resumeEpisode,
  sendMessage,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

const ACTIVE_EPISODE_KEY = "active-episode-id"

interface Message {
  role: "user" | "tutor"
  content: string
  ts: number
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

export function EpisodeView({ episodeId, onExit, ejercicioContext }: EpisodeViewProps) {
  const [tarea, setTarea] = useState<AvailableTarea | null>(null)
  // Default neutro: si el ejercicio trae `inicial_codigo` se usa eso (ver
  // resolveCodigoInicial); este fallback NO debe sugerir una consigna concreta
  // (antes mostraba `def factorial` para TODOS los ejercicios — NEW-002 QA).
  const [code, setCode] = useState<string>("# Escribí tu código Python acá\n")
  const [messages, setMessages] = useState<Message[]>([])
  // Indicador de ACTIVIDAD en curso (no es la clasificacion final del classifier,
  // que se deriva post-cierre — ADR-020). Refleja el nivel de la accion que el
  // alumno esta haciendo ahora, segun el mapeo del labeler: lectura=N1,
  // edicion=N2, ejecucion=N3. Arranca en 1 y solo sube (NEW-003 QA).
  const [maxActividad, setMaxActividad] = useState<1 | 2 | 3>(1)
  const [input, setInput] = useState<string>("")
  const [streaming, setStreaming] = useState(false)
  const [classification, setClassification] = useState<Classification | null>(null)
  const [classificationFailed, setClassificationFailed] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [hydrating, setHydrating] = useState<boolean>(true)
  const [closed, setClosed] = useState<boolean>(false)
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
  const tabExitCountRef = useRef(0)
  const hiddenAtRef = useRef<number | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

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
      void emitEpisodioAbandonado(episodeId, {
        reason: "beforeunload",
        last_activity_seconds_ago: 0,
      })
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [episodeId, closed])

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
        void emitPestanaPerdida(episodeId, { trigger: "visibilitychange" }).catch((e) =>
          console.warn("emit pestana_perdida failed:", e),
        )
        return
      }
      // El alumno volvió a la pestaña.
      const hiddenAt = hiddenAtRef.current
      if (hiddenAt == null) return
      hiddenAtRef.current = null
      const secondsAway = Math.max(0, Math.round((Date.now() - hiddenAt) / 1000))
      void emitPestanaRecuperada(episodeId, {
        tiempo_fuera_segundos: secondsAway,
      }).catch((e) => console.warn("emit pestana_recuperada failed:", e))
      tabExitCountRef.current += 1
      setTabExit({ count: tabExitCountRef.current, secondsAway })
    }

    document.addEventListener("visibilitychange", onVisibility)
    return () => document.removeEventListener("visibilitychange", onVisibility)
  }, [episodeId, closed])

  // Hydration on-mount. El episodeId viene del path param, no del state.
  useEffect(() => {
    let cancelled = false
    setHydrating(true)
    setError(null)
    ;(async () => {
      try {
        const state = await getEpisodeState(episodeId)
        if (cancelled) return
        if (state.estado === "closed") {
          window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
          onExit()
          return
        }
        if (state.estado === "paused") {
          // ADR-055 (fix 2026-06-10 #2): el episodio fue abandonado (cierre de
          // pestaña o timeout) — reconstruir la sesión del tutor antes de
          // seguir, sino todo evento posterior rebota contra sesión inexistente.
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
        if (state.last_code_snapshot) {
          setCode(state.last_code_snapshot)
        } else {
          // ADR-047: el codigo inicial del ejercicio vive en el banco, no en la
          // TP. Si venimos de un ejercicio, lo traemos via /tareas-practicas/{id}/
          // ejercicios y lo matcheamos por orden. Fallback al de la TP (monoliticas).
          let initialCode = resolveCodigoInicial(t)
          if (!initialCode && ejercicioContext) {
            try {
              const tpEjs = await listEjerciciosTp(state.tarea_practica_id)
              const match = tpEjs.find((te) => te.orden === ejercicioContext.ejercicioOrden)
              initialCode = match?.ejercicio?.inicial_codigo ?? null
            } catch {
              // best-effort: si falla, el editor cae a su default
            }
          }
          if (initialCode) setCode(initialCode)
        }
        setMessages(
          state.messages.map((m) => ({
            role: m.role === "assistant" ? "tutor" : "user",
            content: m.content,
            ts: Date.parse(m.ts) || Date.now(),
          })),
        )
      } catch (e) {
        if (cancelled) return
        if (e instanceof EpisodeStateError && (e.status === 404 || e.status === 403)) {
          window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
          onExit()
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
  }, [episodeId, onExit, ejercicioOrden])

  async function handleSend() {
    if (!input.trim() || streaming) return
    const userMessage = input.trim()
    setInput("")
    setMessages((m) => [...m, { role: "user", content: userMessage, ts: Date.now() }])
    setStreaming(true)

    const tutorMessage: Message = { role: "tutor", content: "", ts: Date.now() }
    setMessages((m) => [...m, tutorMessage])

    try {
      for await (const event of sendMessage(episodeId, userMessage)) {
        if (event.type === "chunk") {
          tutorMessage.content += event.content
          setMessages((m) => [...m.slice(0, -1), { ...tutorMessage }])
          scrollToBottom()
        } else if (event.type === "error") {
          const msg = event.message ?? ""
          if (/no existe|expir|cerrad/i.test(msg)) {
            setError(
              'Tu episodio se cerró automáticamente por inactividad. Hacé clic en "Salir" para volver al inicio y abrir uno nuevo.',
            )
            setClosed(true)
            window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
          } else {
            setError(`Tutor error: ${msg}`)
          }
          break
        } else if (event.type === "done") {
          console.debug("chunks_used_hash:", event.chunks_used_hash)
        }
      }
    } catch (e) {
      const msg = String(e)
      if (msg.includes("404") || msg.includes("409")) {
        setError(
          'Tu episodio se cerró automáticamente por inactividad. Hacé clic en "Salir" para volver al inicio y abrir uno nuevo.',
        )
        setClosed(true)
        window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
      } else {
        setError(`Error en streaming: ${e}`)
      }
    } finally {
      setStreaming(false)
    }
  }

  async function handleClose() {
    setError(null)
    try {
      await closeEpisode(episodeId, "student_finished")
    } catch (e) {
      const msg = String(e)
      if (msg.includes("404")) {
        window.sessionStorage.removeItem(ACTIVE_EPISODE_KEY)
        onExit()
        return
      }
      setError(`Error cerrando: ${e}`)
      return
    }
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
          if (ejercicioContext) {
            try {
              await markEjercicioCompleted(
                ejercicioContext.entregaId,
                ejercicioContext.ejercicioOrden,
                episodeId,
                ejercicioContext.ejercicioId,
              )
            } catch {
              // Best-effort: no bloquear la navegacion si falla.
            }
          }
          onExit()
        }}
      />
    )
  }

  // Fallback: el episodio cerró pero la clasificación falló. Mejor mostrar
  // un panel explícito que dejar al alumno en limbo viendo la UI del
  // episodio activo (con `closed=true` pero sin feedback ni CTA claro).
  if (classificationFailed && reflectionTargetId === null) {
    return <ClassificationFallbackPanel onReset={onExit} />
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
            onClick={onExit}
            className="mt-4 px-4 py-2 rounded text-sm font-medium text-white"
            style={{ backgroundColor: "var(--color-accent-brand)" }}
          >
            Volver a mis materias
          </button>
        </div>
      </div>
    )
  }

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
        <span className="text-muted font-mono tabular-nums">
          {formatElapsed(elapsedSeconds)}
        </span>
        <span className="text-muted-soft">·</span>
        {(() => {
          const act = {
            1: { txt: "N1 · lectura activa", cls: "bg-level-n1/10 border-level-n1/30 text-level-n1", dot: "var(--color-level-n1)" },
            2: { txt: "N2 · edición activa", cls: "bg-level-n2/10 border-level-n2/30 text-level-n2", dot: "var(--color-level-n2)" },
            3: { txt: "N3 · ejecución activa", cls: "bg-level-n3/10 border-level-n3/30 text-level-n3", dot: "var(--color-level-n3)" },
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
        <div className="ml-auto flex items-center gap-1">
          <HelpButton title="Tutor Socratico" content={helpContent.episode} />
          <button
            type="button"
            onClick={handleClose}
            data-testid="close-episode-button"
            className="press-shrink inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded-md text-body hover:bg-danger-soft hover:border-danger/30 hover:text-danger transition-colors"
          >
            <LogOut className="h-3 w-3" />
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
              onExit()
            }}
            className="press-shrink ml-4 px-3 py-1 text-xs font-medium bg-danger text-white rounded hover:bg-danger/90"
          >
            Salir
          </button>
        </div>
      )}

      {/* ═══ 3 PANELES REDIMENSIONABLES: Consigna · Editor · Tutor ═══════ */}
      <PanelGroup
        orientation="horizontal"
        className="flex-1 p-4 min-h-0"
      >
        <Panel defaultSize={33} minSize={15} className="flex">
        {/* Panel 1 — Consigna (N1) */}
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
        </section>
        </Panel>

        <PanelResizeHandle className="group relative w-2 mx-0.5 flex items-center justify-center cursor-col-resize">
          <span className="block h-12 w-0.5 rounded-full bg-border-soft group-hover:bg-accent-brand group-data-[resize-handle-active]:bg-accent-brand transition-colors" />
        </PanelResizeHandle>

        <Panel defaultSize={34} minSize={15} className="flex">
        {/* Panel 2 — Editor (N3) */}
        <section
          className="animate-fade-in-up animate-delay-100 flex-1 flex flex-col rounded-xl border border-border bg-surface overflow-hidden shadow-[0_1px_3px_-1px_rgba(0,0,0,0.04)]"
          aria-label="Editor de código"
        >
          <PanelHeader
            level="N3"
            label="Editor de código"
            icon={<Code2 className="h-3.5 w-3.5" />}
            colorVar="var(--color-level-n3)"
            badge="Python"
          />
          <CodeEditor
            initialCode={code}
            onCodeExecuted={(result) => {
              setCode(result.code)
              setMaxActividad((a) => (a < 3 ? 3 : a))
              // P0 (QA 2026-05-29): emitir codigo_ejecutado al CTR. Sin esto el
              // classifier no distingue N3/N4 y todo cae a apropiacion_superficial.
              void emitCodigoEjecutado(episodeId, {
                code: result.code,
                stdout: result.output,
                stderr: result.error ?? "",
                duration_ms: Math.round(result.durationMs),
              }).catch((e) => {
                console.warn("emit codigo_ejecutado failed:", e)
              })
            }}
            onEditDebounced={(snapshot, diffChars, origin) => {
              setMaxActividad((a) => (a < 2 ? 2 : a))
              void emitEdicionCodigo(episodeId, {
                snapshot,
                diff_chars: Math.abs(diffChars),
                language: "python",
                origin,
              }).catch((e) => {
                console.warn("emit edicion_codigo failed:", e)
              })
            }}
            onPasteAttempt={(payload) => {
              void emitPegaIntentada(episodeId, {
                contenido_longitud: payload.contenidoLongitud,
                contenido_preview: payload.contenidoPreview,
                metodo: payload.metodo,
              }).catch((e) => {
                console.warn("emit pega_intentada failed:", e)
              })
            }}
            onCopyAttempt={(payload) => {
              void emitCopiaIntentada(episodeId, {
                seleccion_chars: payload.seleccionChars,
                metodo: payload.metodo,
              }).catch((e) => {
                console.warn("emit copia_intentada failed:", e)
              })
            }}
          />
        </section>
        </Panel>

        <PanelResizeHandle className="group relative w-2 mx-0.5 flex items-center justify-center cursor-col-resize">
          <span className="block h-12 w-0.5 rounded-full bg-border-soft group-hover:bg-accent-brand group-data-[resize-handle-active]:bg-accent-brand transition-colors" />
        </PanelResizeHandle>

        <Panel defaultSize={33} minSize={15} className="flex">
        {/* Panel 3 — Tutor (N4) */}
        <section
          className="animate-fade-in-up animate-delay-150 flex-1 flex flex-col rounded-xl border border-border bg-surface overflow-hidden shadow-[0_1px_3px_-1px_rgba(0,0,0,0.04)]"
          aria-label="Tutor socrático"
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
                    <Sparkles
                      className="h-4 w-4"
                      style={{ color: "var(--color-level-n4)" }}
                    />
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
                    {isUser ? (
                      <User className="h-3.5 w-3.5" />
                    ) : (
                      <Bot className="h-3.5 w-3.5" />
                    )}
                  </div>
                  {/* Burbuja */}
                  <div className={`flex flex-col gap-1 max-w-[80%] ${isUser ? "items-end" : ""}`}>
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-muted">
                      {isUser ? "Vos" : "Tutor"}
                    </span>
                    <div
                      data-testid={isLastTutor ? "tutor-message-last" : undefined}
                      className={`rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
                        isUser
                          ? "bg-accent-brand text-white rounded-tr-sm"
                          : "bg-surface-alt text-body border border-border-soft rounded-tl-sm"
                      }`}
                    >
                      {m.content ||
                        (m.role === "tutor" && streaming ? (
                          <span className="inline-flex gap-1 items-center text-muted">
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted animate-pulse-soft" />
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted animate-pulse-soft animate-delay-150" />
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted animate-pulse-soft animate-delay-300" />
                          </span>
                        ) : (
                          ""
                        ))}
                    </div>
                  </div>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>

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
                onClick={handleSend}
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
        </Panel>
      </PanelGroup>

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
              window.localStorage.setItem(
                `episode_${episodeId}_reflection_skipped`,
                "1",
              )
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
            if (ejercicioContext) {
              try {
                await markEjercicioCompleted(
                  ejercicioContext.entregaId,
                  ejercicioContext.ejercicioOrden,
                  episodeId,
                  ejercicioContext.ejercicioId,
                )
              } catch {
                // Best-effort: la TP queda con el ejercicio sin marcar pero
                // el alumno puede volver a entrar y completar.
              }
            }
            onExit()
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
                <h2
                  id="tab-exit-title"
                  className="text-lg font-semibold leading-snug text-ink"
                >
                  Saliste de la evaluación
                </h2>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">
                  Mientras resolvés un episodio no podés cambiar de pestaña ni de
                  ventana. Esta salida quedó registrada en la trazabilidad del
                  episodio y tu docente puede verla.
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
              autoFocus
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
        <h2 className="text-sm font-semibold text-ink leading-tight tracking-tight">
          {label}
        </h2>
      </div>
      {badge && (
        <span
          className={`shrink-0 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface border border-border-soft text-[10px] font-medium text-muted ${
            badgePulse ? "animate-pulse-soft" : ""
          }`}
        >
          {badgePulse && (
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-success" />
          )}
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
            : [
                "Cuando termines un ejercicio, repasá qué aprendiste y contátelo al tutor.",
              ],
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
      <div
        className={`rounded-2xl border p-7 mb-8 ${tonoStyles[feedback.tono]}`}
      >
        <p className="text-xs font-mono uppercase tracking-[0.15em] opacity-70 mb-2">
          {skippedReflection ? "Cierre del ejercicio · sin reflexion" : "Cierre del ejercicio"}
        </p>
        <h2 className="font-serif text-3xl font-medium leading-tight">
          {feedback.titulo}
        </h2>
        <p className="mt-4 text-base leading-relaxed opacity-90">
          {feedback.mensaje}
        </p>
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
          Tu trabajo quedó registrado criptográficamente. La clasificación
          pedagógica no se pudo calcular en este momento — el sistema la
          va a procesar más tarde y vas a poder verla en{" "}
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
