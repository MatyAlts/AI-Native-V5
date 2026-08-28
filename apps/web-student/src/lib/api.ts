/**
 * Cliente de API del web-student.
 *
 * F6: reemplazado headers X-* dev por flow OIDC real. El token viene
 * del AuthContext (keycloak-js) y se agrega como Authorization: Bearer.
 *
 * El proxy de Vite (vite.config.ts) redirige /api/* al api-gateway.
 */

import type { ArtefactoDraft } from "./artefactos"

export interface OpenEpisodeRequest {
  comision_id: string
  problema_id: string
  curso_config_hash: string
  classifier_config_hash: string
  /**
   * UUID del Ejercicio reusable del banco standalone (ADR-047).
   * None / undefined = TP monolítica sin ejercicio específico.
   */
  ejercicio_id?: string | null
}

export interface OpenEpisodeResponse {
  episode_id: string
}

// Subgrupo (modo sombra B1 Fase 2): el classifier lo calcula y lo deja en
// features['subgrupo']. Es la fuente narrativa principal del feedback al
// alumno (8 perfiles), alineada con lo que ve el docente. Espejo del tipo en
// web-teacher/lib/api.ts.
export interface Subgrupo {
  key: string
  label: string
  eje: string
  dimensiones: {
    autonomia: number
    experimentacion: number
    persistencia: number
    foco: number
  }
  accion_docente: string
}

export interface Classification {
  episode_id: string
  comision_id: string
  classifier_config_hash: string
  appropriation: "delegacion_pasiva" | "apropiacion_superficial" | "apropiacion_reflexiva"
  appropriation_reason: string
  ct_summary: number | null
  ccd_mean: number | null
  ccd_orphan_ratio: number | null
  cii_stability: number | null
  cii_evolution: number | null
  is_current: boolean
  // null en classifications viejas (pre-modo-sombra) → feedback cae al eje.
  subgrupo?: Subgrupo | null
}

export type TokenGetter = () => Promise<string | null>

async function authHeaders(getToken?: TokenGetter): Promise<Record<string, string>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (getToken) {
    const token = await getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  return headers
}

export async function openEpisode(
  req: OpenEpisodeRequest,
  getToken?: TokenGetter,
): Promise<OpenEpisodeResponse> {
  const r = await fetch("/api/v1/episodes", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(`open episode failed: ${r.status}`)
  return r.json()
}

export interface ConfigHashes {
  comision_id: string
  curso_config_hash: string
  classifier_config_hash: string
}

/**
 * Bootstrap minimo F9: resolver los hashes vigentes para abrir un episodio.
 *
 * Reemplaza los hashes hardcoded del piloto ("c"*64 / "d"*64). El endpoint
 * los deriva deterministicamente de la config de la comision (curso) y de
 * `compute_classifier_config_hash` del classifier-service.
 *
 * Si falla, el caller deberia caer al fallback hardcoded para no bloquear
 * la apertura del episodio (best-effort).
 */
export async function fetchConfigHashes(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<ConfigHashes> {
  const r = await fetch(`/api/v1/comisiones/${comisionId}/config-hashes`, {
    method: "GET",
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`fetch config-hashes failed: ${r.status}`)
  return r.json()
}

export async function closeEpisode(
  episodeId: string,
  reason = "student_closed",
  getToken?: TokenGetter,
): Promise<void> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/close`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify({ reason }),
  })
  if (!r.ok) throw new Error(`close episode failed: ${r.status}`)
}

/**
 * Emite EpisodioAbandonado al CTR (ADR-025, G10-A).
 *
 * Idempotente: si el episodio ya fue cerrado/abandonado/expirado en el
 * backend, devuelve 204 sin emitir. Diseñada para ejecutarse en
 * `beforeunload` (cierre de pestaña / navegación), donde el browser
 * puede matar el fetch a mitad de camino.
 *
 * `navigator.sendBeacon` es preferible en `beforeunload`: es el unico
 * mecanismo garantizado para enviar un POST que sobrevive el unload.
 * Caveat: NO permite headers personalizados (Authorization). En dev
 * mode el proxy de Vite inyecta `X-User-Id` automáticamente, así que
 * funciona; en prod con OIDC real va a haber que firmar la URL u otra
 * estrategia (cookie con el JWT). Por ahora caemos a `fetch` con
 * `keepalive: true` cuando hay token, y a `sendBeacon` cuando no.
 */
export async function emitEpisodioAbandonado(
  episodeId: string,
  payload: { reason: "beforeunload" | "explicit"; last_activity_seconds_ago: number },
  getToken?: TokenGetter,
): Promise<void> {
  const url = `/api/v1/episodes/${episodeId}/abandoned`
  const body = JSON.stringify(payload)

  // Si tenemos getToken, usamos fetch con keepalive (mantiene la request
  // vivat después del unload hasta cierto budget). En navegadores que no
  // soportan keepalive cae al sendBeacon abajo.
  if (getToken) {
    try {
      const headers = await authHeaders(getToken)
      // keepalive es necesario para que la request sobreviva al unload.
      const r = await fetch(url, { method: "POST", headers, body, keepalive: true })
      if (r.ok || r.status === 204) return
      // Si el server rechaza por auth/payload, NO reintentar sendBeacon —
      // el usuario ya se está yendo y no podemos resolverlo.
      return
    } catch {
      // Fall through al sendBeacon.
    }
  }

  // Fallback: sendBeacon (sin Authorization header). En dev mode el proxy
  // de Vite inyecta los X-* headers, así que funciona. En prod sin token
  // el backend rechazaría con 401 (esperado).
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([body], { type: "application/json" })
    navigator.sendBeacon(url, blob)
  }
}

/**
 * Estado serializable de un episodio para recuperación post-refresh.
 * Backend: GET /api/v1/episodes/{episode_id}.
 *
 * 404 = episodio inexistente, 403 = cross-tenant. El caller distingue ambos
 * por `EpisodeStateError.status` para decidir si limpia sessionStorage o
 * sólo notifica al usuario.
 */
export interface EpisodeStateResponse {
  episode_id: string
  tarea_practica_id: string
  comision_id: string
  estado: "open" | "closed" | "paused"
  opened_at: string
  closed_at: string | null
  last_code_snapshot: string | null
  messages: Array<{ role: "user" | "assistant"; content: string; ts: string }>
  notes: Array<{ contenido: string; ts: string }>
  /** Ejercicio del banco asociado (null = TP monolítica). ADR-049/055. */
  ejercicio_id: string | null
  ejercicio_orden: number | null
}

/**
 * Reanuda un episodio pausado por abandono (ADR-055, fix 2026-06-10 #2).
 *
 * El backend reconstruye la sesión Redis desde la cadena CTR (seq,
 * conversación, último código) sin emitir eventos nuevos — el episodio
 * vuelve a "open" con el primer evento posterior. Idempotente.
 *
 * Errores: 404 episodio/TP inexistente, 403 episodio ajeno, 409 episodio
 * cerrado o TP fuera de plazo.
 */
export interface ResumeEpisodeResponse {
  episode_id: string
  problema_id: string | null
  comision_id: string
  ejercicio_id: string | null
  ejercicio_orden: number | null
}

export async function resumeEpisode(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<ResumeEpisodeResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/resume`, {
    method: "POST",
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new EpisodeStateError(r.status, `resume episode failed: ${r.status}`)
  return r.json()
}

export class EpisodeStateError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = "EpisodeStateError"
  }
}

export async function getEpisodeState(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<EpisodeStateResponse> {
  // Retry con backoff exponencial sobre 404. El POST /episodes vuelve apenas
  // hace XADD al stream Redis; el worker ctr-service drena async y persiste
  // en Postgres con ~1s de delay. Si pedimos el GET justo después del POST,
  // pegamos contra esa ventana y recibimos 404 aunque el episodio exista.
  // Para los demás status codes (401/403/500) tiramos al toque sin retry.
  const delays = [0, 200, 400, 800, 1600]
  for (let i = 0; i < delays.length; i++) {
    const delay = delays[i] ?? 0
    if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay))
    const r = await fetch(`/api/v1/episodes/${episodeId}`, {
      headers: await authHeaders(getToken),
    })
    if (r.ok) return (await r.json()) as EpisodeStateResponse
    if (r.status !== 404 || i === delays.length - 1) {
      throw new EpisodeStateError(r.status, `get episode state failed: ${r.status}`)
    }
  }
  throw new EpisodeStateError(404, "get episode state failed: 404 after retries")
}

export async function* sendMessage(
  episodeId: string,
  content: string,
  idempotencyKey?: string,
  getToken?: TokenGetter,
): AsyncGenerator<
  | { type: "chunk"; content: string }
  | { type: "done"; chunks_used_hash: string; seqs: Record<string, number> }
  | { type: "error"; message: string },
  void,
  unknown
> {
  const headers = await authHeaders(getToken)
  // FIX B: clave estable por turno del alumno. En el "Reintentar" de UI-8
  // EpisodePage reusa el MISMO valor, asi el server deduplica el prompt_enviado
  // (mismo seq, sin re-publicar) y no genera prompts huerfanos.
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey
  const response = await fetch(`/api/v1/episodes/${episodeId}/message`, {
    method: "POST",
    headers: { ...headers, Accept: "text/event-stream" },
    body: JSON.stringify({ content }),
  })
  if (!response.ok || !response.body) throw new Error(`message failed: ${response.status}`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      try {
        yield JSON.parse(line.slice(6))
      } catch {
        /* ignore */
      }
    }
  }
}

export async function classifyEpisode(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<Classification> {
  const r = await fetch(`/api/v1/classify_episode/${episodeId}`, {
    method: "POST",
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`classify failed: ${r.status}`)
  return r.json()
}

export async function getClassification(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<Classification> {
  const r = await fetch(`/api/v1/classifications/${episodeId}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get classification failed: ${r.status}`)
  return r.json()
}

/** Respuesta común de los endpoints de emisión de eventos CTR.
 * El tutor-service agrega seq + chain_hash y persiste el evento; el cliente
 * recibe únicamente el seq asignado para correlación si lo necesitase.
 */
export interface EventEmitResponse {
  seq: number
}

/** Emite un evento codigo_ejecutado al CTR via tutor-service.
 * El tutor-service agrega seq + chain_hash + persiste el evento.
 */
export async function emitCodigoEjecutado(
  episodeId: string,
  payload: { code: string; stdout: string; stderr: string; duration_ms: number },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/codigo_ejecutado`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`emit codigo_ejecutado failed: ${r.status}`)
  return (await r.json()) as EventEmitResponse
}

/** Emite tests_ejecutados al CTR (F1 "probar mi codigo"), via tutor-service.
 *
 * El cliente Pyodide corre los test cases PUBLICOS sobre el codigo del alumno
 * y manda SOLO conteos agregados — nunca la lista detallada por test ni el
 * codigo (defensa de privacidad + cardinalidad del CTR). `tests_hidden`
 * viaja siempre 0 (los ocultos NO se ejecutan client-side en piloto-1). El
 * backend valida `passed + failed == total` (422 si no) y que la sesion siga
 * viva (409 si el episodio esta cerrado/expirado). Endpoint distinto de los
 * otros emit*: `POST /episodes/{id}/run-tests` (202 Accepted).
 */
export async function emitTestsEjecutados(
  episodeId: string,
  payload: {
    test_count_total: number
    test_count_passed: number
    test_count_failed: number
    tests_publicos: number
    ejecucion_ms: number
  },
  getToken?: TokenGetter,
): Promise<{ status: string; seq: string }> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/run-tests`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify({ ...payload, tests_hidden: 0 }),
  })
  if (!r.ok) throw new Error(`emit tests_ejecutados failed: ${r.status}`)
  return (await r.json()) as { status: string; seq: string }
}

// ── Ejecución server-side (ADR-059, epic java-execution-engine) ───────

/** Estado de una corrida en el execution-service. */
export type ExecutionState = "queued" | "running" | "done"

/**
 * Resultado de la CORRIDA, distinto del resultado de los casos.
 *
 * `infrastructure_failure` existe para que una caída del sandbox NO se lea como
 * el alumno fallando los tests. La UI lo muestra distinto y el backend además
 * no emite evento de trazabilidad en ese caso.
 */
export type ExecutionOutcome = "completed" | "compilation_error" | "infrastructure_failure"

/** Un caso de prueba ejecutado. Misma forma que produce el runner de Pyodide,
 * para que la vista de resultados se reuse sin cambios.
 *
 * En los casos OCULTOS el backend manda `input`, `expected`, `got` y `error` en
 * `null` a propósito: el alumno ve que existen y si los pasó, no qué evalúan. */
export interface ExecutionCase {
  id: string
  name: string
  type: string
  status: "pass" | "fail" | "error" | "skipped"
  is_public: boolean
  input: string | null
  expected: string | null
  got: string | null
  error: string | null
  weight: number
}

export interface ExecutionResult {
  /** Presente solo en modo libre. La salida del programa, sin evaluar nada.
   *
   * En modo tests la salida vive en `cases[n].got` porque cada caso tiene la
   * suya; en libre no hay casos y el programa corrio una vez. */
  stdout?: string
  stderr?: string
  exit_code?: number
  timed_out?: boolean
  /** `true` cuando el lenguaje no tiene runtime server-side. No es un fallo
   * del alumno ni de la infraestructura: no hay donde ejecutarlo. */
  sin_runtime?: boolean
  modo?: "tests" | "libre"
  outcome: ExecutionOutcome
  total: number
  passed: number
  failed: number
  cases: ExecutionCase[]
  compile_output: string
}

export interface ExecutionStatus {
  execution_id: string
  state: ExecutionState
  result: ExecutionResult | null
}

/** Error de cuota agotada: el alumno se pasó del límite de ejecuciones. */
export class ExecutionQuotaError extends Error {}

/** El servicio de ejecución no está disponible.
 *
 * Incluye el caso de cuota que falla CERRADA (503): si el contador no responde
 * no se ejecuta, porque cada corrida cuesta CPU y dinero. No es culpa del
 * alumno y el mensaje se lo dice. */
export class ExecutionUnavailableError extends Error {}

/**
 * Pide una ejecución. Responde de inmediato con un identificador — compilar y
 * arrancar una JVM no es instantáneo, así que el resultado se consulta aparte.
 */
export async function requestExecution(
  payload: {
    ejercicio_id: string
    source_code: string
    episode_id?: string
    /** `"tests"` corre los casos del ejercicio; `"libre"` corre el programa
     * una vez con `stdin` y devuelve su salida, sin evaluar nada.
     *
     * Ausente = `"tests"`, que es como se comportaba antes de que existiera el
     * campo: ningun llamador viejo cambia de significado. */
    modo?: "tests" | "libre"
    /** Entrada del programa, entera y por adelantado. En Python el `input()`
     * se intercepta acá en el navegador y se le pregunta al alumno en el
     * momento; el contenedor de Java corre hasta terminar sin canal de vuelta,
     * asi que lo que vaya a leer tiene que viajar con la request. */
    stdin?: string
    /** Comision del episodio. La usa la habilitacion progresiva del
     * execution-service (`EXECUTION_ENABLED_COMISIONES`, tarea 9.3). Sin esto el
     * backend recibe `None`, la lista no matchea con nada y **nadie puede
     * ejecutar** — con un 503 que dice "no esta habilitada para esta comision",
     * o sea apuntando al lugar equivocado. La feature figuraba cerrada y estaba
     * cableada de un solo lado; detectado el 2026-08-05. */
    comision_id?: string
  },
  getToken?: TokenGetter,
): Promise<{ execution_id: string; quota_remaining: number }> {
  const r = await fetch("/api/v1/executions", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (r.status === 429) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new ExecutionQuotaError(body.detail ?? "Alcanzaste el limite de ejecuciones.")
  }
  if (r.status === 503) {
    const body = (await r.json().catch(() => ({}))) as { detail?: string }
    throw new ExecutionUnavailableError(
      body.detail ?? "El servicio de ejecucion no esta disponible.",
    )
  }
  if (!r.ok) throw new ExecutionUnavailableError(`No se pudo pedir la ejecucion (${r.status})`)
  return (await r.json()) as { execution_id: string; quota_remaining: number }
}

/** Consulta el estado de una ejecución. */
export async function getExecution(
  executionId: string,
  getToken?: TokenGetter,
): Promise<ExecutionStatus> {
  const r = await fetch(`/api/v1/executions/${executionId}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new ExecutionUnavailableError(`No se pudo consultar la ejecucion (${r.status})`)
  return (await r.json()) as ExecutionStatus
}

/**
 * Procedencia de una edicion del editor. Espeja el `Literal` de
 * `EdicionCodigoPayload.origin` en `packages/contracts` — si agregas un valor
 * aca, agregalo alla o el backend rechaza el evento.
 *
 * `snippet_expanded` = ceremonia expandida por el editor (ver
 * `lib/javaSnippets.ts`). No es tipeo del alumno, pero tampoco interaccion con
 * IA: el labeler NO le aplica override a N4.
 */
export type EdicionCodigoOrigin =
  | "student_typed"
  | "copied_from_tutor"
  | "pasted_external"
  | "snippet_expanded"

/** Emite un evento edicion_codigo al CTR. Disparado por el editor con
 * debouncing (1s) — el snapshot es el estado actual del buffer y diff_chars
 * el delta de caracteres respecto a la última emisión.
 *
 * F6: `origin` opcional indica de dónde vino el cambio (tipeo / copia /
 * paste). Lo usa el clasificador para distinguir delegación pasiva de
 * apropiación reflexiva sin depender solo de inferencia temporal.
 */
export async function emitEdicionCodigo(
  episodeId: string,
  payload: {
    snapshot: string
    diff_chars: number
    language: string
    origin?: EdicionCodigoOrigin | null
  },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/edicion_codigo`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`emit edicion_codigo failed: ${r.status}`)
  return (await r.json()) as EventEmitResponse
}

/** Emite un evento lectura_enunciado al CTR (F5).
 *
 * `duration_seconds` es el delta acumulado desde la última emisión
 * (no el total del episodio). El frontend lo mide con IntersectionObserver
 * + visibilitychange en el panel del enunciado y flushea cada ~30s o
 * al cerrar el episodio.
 */
export async function emitLecturaEnunciado(
  episodeId: string,
  payload: { duration_seconds: number },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/lectura_enunciado`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`emit lectura_enunciado failed: ${r.status}`)
  return (await r.json()) as EventEmitResponse
}

/** Emite pestana_perdida al CTR cuando el alumno cambia de pestaña o pierde
 * foco del browser. El worker server-side decide si cerrar el episodio. */
export async function emitPestanaPerdida(
  episodeId: string,
  payload: { trigger: "visibilitychange" | "blur" },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/pestana_perdida`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`emit pestana_perdida failed: ${r.status}`)
  return (await r.json()) as EventEmitResponse
}

/** Emite pestana_recuperada al CTR cuando el alumno vuelve a la pestaña. */
export async function emitPestanaRecuperada(
  episodeId: string,
  payload: { tiempo_fuera_segundos: number },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/pestana_recuperada`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`emit pestana_recuperada failed: ${r.status}`)
  return (await r.json()) as EventEmitResponse
}

/** Emite copia_intentada al CTR (el editor Monaco bloquea la accion). */
export async function emitCopiaIntentada(
  episodeId: string,
  payload: { seleccion_chars: number; metodo: "shortcut" | "menu_contextual" },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/copia_intentada`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`emit copia_intentada failed: ${r.status}`)
  return (await r.json()) as EventEmitResponse
}

/** Emite pega_intentada al CTR (el editor Monaco bloquea la accion). */
export async function emitPegaIntentada(
  episodeId: string,
  payload: {
    contenido_longitud: number
    contenido_preview: string
    metodo: "shortcut" | "menu_contextual" | "drag_drop"
  },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/pega_intentada`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`emit pega_intentada failed: ${r.status}`)
  return (await r.json()) as EventEmitResponse
}

/** Emite un evento anotacion_creada al CTR. El backend valida que
 * `contenido` tenga entre 1 y 5000 chars (responde 422 si no).
 */
export async function emitAnotacionCreada(
  episodeId: string,
  payload: { contenido: string },
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/events/anotacion_creada`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) {
    // Propagamos el status para que el caller pueda distinguir 422 (validación).
    const err = new Error(`emit anotacion_creada failed: ${r.status}`)
    ;(err as Error & { status?: number }).status = r.status
    throw err
  }
  return (await r.json()) as EventEmitResponse
}

/**
 * Envia la reflexion metacognitiva post-cierre del episodio (ADR-035).
 *
 * Es OPCIONAL y NO BLOQUEANTE — el cierre del episodio ya fue appendeado
 * al CTR antes de que se llame esta funcion. El backend valida que el
 * episodio este en estado=closed (responde 409 si no) y que cada campo
 * sea <=500 chars (responde 422 si no).
 *
 * Cada campo puede ir vacio (el alumno puede dejar uno o varios en blanco).
 */
export async function submitReflection(
  episodeId: string,
  payload: {
    que_aprendiste: string
    dificultad_encontrada: string
    que_haria_distinto: string
    prompt_version: string
    tiempo_completado_ms: number
  },
  idempotencyKey?: string,
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const headers = await authHeaders(getToken)
  // Clave estable por apertura del modal. El reintento tras un error de red
  // reusa el MISMO valor: sin eso, un POST que el server SI persistio y cuyo
  // ACK se perdio termina emitiendo dos `reflexion_completada` con el mismo
  // seq (post-cierre no hay sesion Redis, el seq sale de `events_count`), y el
  // segundo manda a la DLQ un episodio ya cerrado y completado.
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey
  const r = await fetch(`/api/v1/episodes/${episodeId}/reflection`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  })
  if (!r.ok) {
    const err = new Error(`submit reflection failed: ${r.status}`)
    ;(err as Error & { status?: number }).status = r.status
    throw err
  }
  return (await r.json()) as EventEmitResponse
}

// ── Tareas Prácticas (TPs) disponibles para el estudiante ─────────────

/**
 * Test case PUBLICO de un ejercicio / TP (A0.3, F1 "probar mi codigo").
 *
 * El backend sanea por rol (`content_visibility.py`): al ALUMNO solo le
 * llegan los `is_public=true`. Los ocultos (con su `expected`) nunca viajan
 * al cliente. Shape alineado con `TestCaseSchema` del contrato; los campos
 * van opcionales porque en TPs monoliticas el JSONB puede venir incompleto.
 *
 *  - `stdin_stdout`: `code` es el stdin que se le pasa al programa y
 *    `expected` la salida esperada (se compara stdout, trim a ambos lados).
 *  - `pytest_assert`: `code` es un snippet de asercion que corre contra los
 *    nombres definidos por el alumno; pasa si no levanta excepcion.
 *  - `junit_assert`: el equivalente de Java. No hay runtime que lo ejecute
 *    todavia (`java-execution-engine`), asi que el editor lo reporta como no
 *    ejecutable en vez de correrlo contra el runner de Python.
 */
export interface TestCasePublic {
  id?: string
  name?: string
  type?: "stdin_stdout" | "pytest_assert" | "junit_assert"
  code?: string
  expected?: string | null
  is_public?: boolean
  weight?: number
}

/**
 * Lenguaje en que se resuelve un ejercicio o una TP.
 *
 * Espeja `Language` de `platform_contracts.academic.ejercicio`. El backend lo
 * persiste como texto libre a proposito (sin CHECK en la DB): agregar un
 * lenguaje no deberia pedir una migracion. La union de acá es el contrato de
 * la UI, no el de la base.
 */
export type Language = "python" | "java"

/** Lo que el backend asume cuando una fila no declara lenguaje. */
export const DEFAULT_LANGUAGE: Language = "python"

/** Etiqueta legible de cada lenguaje. Sin color asociado a proposito: el
 * sistema reserva el color para lo que tiene carga semantica (severidad,
 * niveles N1-N4, apropiacion). Ver DESIGN.md, The One-Accent Rule. */
export const LANGUAGE_LABELS: Record<Language, string> = {
  python: "Python",
  java: "Java",
}

/**
 * Buffer inicial cuando el ejercicio no trae `inicial_codigo` ni hay snapshot.
 *
 * Es un andamio neutro, NO una consigna: no debe sugerir un enfoque concreto
 * (antes mostraba `def factorial` para TODOS los ejercicios — NEW-002 QA). Pero
 * tampoco puede estar fijo en un lenguaje: un comentario `#` en un ejercicio
 * Java es sintaxis invalida, y el alumno arranca con el archivo roto.
 */
export const LANGUAGE_PLACEHOLDER: Record<Language, string> = {
  python: "# Escribí tu código Python acá\n",
  java: "public class Main {\n    public static void main(String[] args) {\n        // Escribí tu código Java acá\n    }\n}\n",
}

/**
 * Vista read-only de una TP publicada.
 *
 * El estudiante sólo ve TPs en estado=published dentro de la ventana
 * fecha_inicio..fecha_fin (el backend valida la ventana al abrir episodio).
 */
export interface AvailableTarea {
  id: string
  codigo: string
  titulo: string
  enunciado: string // markdown
  fecha_inicio: string | null // ISO 8601
  fecha_fin: string | null
  peso: string // decimal serializado como string
  estado: "published"
  version: number
  /** Plantilla de código inicial opcional (ej. firma de funciones, scaffold).
   * Si el docente no la define, viene null y el editor cae a su default.
   */
  inicial_codigo: string | null
  /** Unidad temática a la que pertenece la TP (null si está sin asignar).
   * Opcional para backwards-compat con endpoints que no la populan. */
  unidad_id?: string | null
  /** El docente decide si el alumno puede pausar/retomar episodios de esta TP.
   * Opcional para backwards-compat: undefined se trata como permitido (true). */
  permite_pausa?: boolean
  /** Lenguaje de la TP. El backend lo garantiza NOT NULL, pero va opcional por
   * el mismo motivo que sus vecinos: fixtures y endpoints viejos que no lo
   * populan. Resolver siempre con `?? DEFAULT_LANGUAGE`, nunca asumir Python
   * en el sitio de uso. */
  language?: Language
  /** Test cases PUBLICOS de la TP monolitica (A0.3, F1). El backend ya filtra
   * los ocultos via `sanitize_tarea_practica_for_student`. Opcional: solo lo
   * populan los endpoints que devuelven la TP saneada (get/list). Para TPs
   * multi-ejercicio los tests viven en cada ejercicio del banco. */
  test_cases?: TestCasePublic[]
  /** Ejercicios asociados (banco reusable, ADR-047). Opcional — solo presente
   * cuando el endpoint los popula via `?include=ejercicios`. */
  ejercicios?: Array<{
    orden: number
    titulo: string
    enunciado_md: string
    inicial_codigo: string | null
    peso: number
  }>
}

// ── Unidades temáticas (navegación intermedia materia → unidad → TP) ─

export interface Unidad {
  id: string
  comision_id: string
  nombre: string
  descripcion: string | null
  orden: number
}

export async function listUnidades(comisionId: string, getToken?: TokenGetter): Promise<Unidad[]> {
  const r = await fetch(`/api/v1/unidades?comision_id=${encodeURIComponent(comisionId)}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list unidades failed: ${r.status}`)
  const body = (await r.json()) as { data: Unidad[] }
  return body.data
}

/**
 * Página de TPs disponibles devuelta por el backend.
 *
 * `next_cursor` es el id (uuid) desde el cual continuar; null cuando no
 * hay más páginas.
 */
export interface AvailableTareasPage {
  data: AvailableTarea[]
  meta: { cursor_next: string | null }
}

/**
 * Lista una página de TPs publicadas para una comisión.
 *
 * Usa el endpoint compartido GET /api/v1/tareas-practicas filtrado por
 * estado=published. Soporta paginación cursor-based: pasá el `cursor`
 * recibido en la página anterior para traer la siguiente. Cuando
 * `next_cursor` viene null, no hay más páginas.
 */
export async function listAvailableTareas(
  comisionId: string,
  cursor?: string,
  getToken?: TokenGetter,
): Promise<AvailableTareasPage> {
  const qs = new URLSearchParams({
    comision_id: comisionId,
    estado: "published",
  })
  if (cursor) qs.set("cursor", cursor)
  const r = await fetch(`/api/v1/tareas-practicas?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list tareas failed: ${r.status}`)
  return (await r.json()) as AvailableTareasPage
}

/**
 * Trae una TP por id. Usado por el flujo de recuperación post-refresh
 * para rehidratar `selectedTarea` a partir del `tarea_practica_id` que
 * vuelve en `EpisodeStateResponse`.
 *
 * Devuelve null si la TP fue despublicada/borrada (404), para que el
 * caller pueda limpiar sessionStorage y volver al selector.
 */
export async function getTareaById(
  tareaId: string,
  getToken?: TokenGetter,
): Promise<AvailableTarea | null> {
  const r = await fetch(`/api/v1/tareas-practicas/${tareaId}`, {
    headers: await authHeaders(getToken),
  })
  if (r.status === 404) return null
  if (!r.ok) throw new Error(`get tarea failed: ${r.status}`)
  return (await r.json()) as AvailableTarea
}

export const tareasPracticasApi = {
  listAvailable: listAvailableTareas,
  getById: getTareaById,
}

// ── Episodios historicos del estudiante (drill-down nav, ADR-022) ────

/**
 * Episodio cerrado del estudiante con classification asociada.
 *
 * El backend (analytics-service) joinea CTR + Classification + TareaPractica
 * y devuelve el `template_id` para agrupar TPs analogas — necesario para
 * la "trayectoria N4 historica" del TareaSelector.
 */
export interface StudentEpisode {
  episode_id: string
  problema_id: string
  /** "closed" | "paused" — paused = abandonado, retomable via resumeEpisode (ADR-055). */
  estado: string
  tarea_codigo: string | null
  tarea_titulo: string | null
  template_id: string | null
  opened_at: string | null
  closed_at: string | null
  events_count: number
  appropriation: "delegacion_pasiva" | "apropiacion_superficial" | "apropiacion_reflexiva" | null
  classified_at: string | null
}

export interface StudentEpisodesResponse {
  student_pseudonym: string
  comision_id: string
  n_episodes: number
  episodes: StudentEpisode[]
}

/**
 * Trae los episodios cerrados del PROPIO alumno en una comision. Usado por
 * el TareaSelector para mostrar la trayectoria N4 historica en TPs analogas
 * (mismo `template_id`).
 *
 * Usa el endpoint `/student/me/episodes`: el backend deriva el alumno del JWT
 * (X-User-Id) — NO se pasa el pseudonym por la URL. Antes pegaba al endpoint de
 * docente `/student/{id}/episodes`, que le daba 403 al alumno y le exponia el
 * UUID en la URL (F-08).
 */
export async function listStudentEpisodes(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<StudentEpisodesResponse> {
  const qs = new URLSearchParams({ comision_id: comisionId })
  const r = await fetch(`/api/v1/analytics/student/me/episodes?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list student episodes failed: ${r.status}`)
  return (await r.json()) as StudentEpisodesResponse
}

// ── Historial de reflexiones del estudiante (ADR-035) ────────────────

/**
 * Una reflexion completada vinculada a su episodio + TP de origen.
 *
 * Backend: GET /api/v1/analytics/student/me/reflections (analytics-service).
 * El filtro por student_pseudonym lo hace el endpoint usando X-User-Id —
 * el estudiante SOLO ve sus propias reflexiones.
 */
export interface ReflectionEntry {
  episode_id: string
  problema_id: string
  tarea_codigo: string | null
  tarea_titulo: string | null
  closed_at: string | null // ISO 8601 (cierre del episodio)
  reflected_at: string // ISO 8601 (envio de la reflexion, post-cierre)
  prompt_version: string // ej. "reflection/v1.0.0"
  tiempo_completado_ms: number
  answers: {
    que_aprendiste: string
    dificultad_encontrada: string
    que_haria_distinto: string
  }
}

export interface MyReflectionsResponse {
  student_pseudonym: string
  n_returned: number
  has_more: boolean
  cursor_next: string | null
  reflections: ReflectionEntry[]
}

/**
 * Lista las reflexiones metacognitivas del estudiante autenticado (ADR-035).
 *
 * Backend cierra el gap historico: hasta hoy la reflexion solo era visible
 * inmediatamente post-cierre dentro de EpisodePage. Este endpoint devuelve
 * todas las reflexiones pasadas con metadata de la TP/episodio.
 *
 * Pagination keyset por `reflected_at` (orden DESC, mas recientes primero).
 * Para la siguiente pagina pasar el `cursor_next` recibido.
 */
export async function getMyReflections(
  limit = 20,
  cursor?: string,
  getToken?: TokenGetter,
): Promise<MyReflectionsResponse> {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (cursor) qs.set("cursor", cursor)
  const r = await fetch(`/api/v1/analytics/student/me/reflections?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list my reflections failed: ${r.status}`)
  return (await r.json()) as MyReflectionsResponse
}

// ── Comisiones ────────────────────────────────────────────────────────

export interface Comision {
  id: string
  tenant_id: string
  materia_id: string
  periodo_id: string
  codigo: string
  cupo_maximo: number
  horario: Record<string, unknown>
  ai_budget_monthly_usd: string
  curso_config_hash: string | null
  created_at: string
  deleted_at: string | null
}

/**
 * Devuelve las comisiones donde el estudiante tiene asignación activa.
 * Backend: `GET /api/v1/comisiones/mis`. Normalizamos `{data, meta}` →
 * `{items, next_cursor}` para alinearlo con el resto de los listados.
 *
 * NOTA: el endpoint `/comisiones/mis` joinea contra `usuarios_comision`
 * (docentes/JTP), por lo que devuelve [] para estudiantes (gap B.2 documentado
 * en CLAUDE.md). Para el flujo del web-student usar `listMisMaterias()`
 * que lee de `inscripciones`. Esta función queda solo para casos legacy /
 * forward-compat con el claim `comisiones_activas` del JWT cuando F9 cierre.
 *
 * El fallback previo a `/api/v1/comisiones` (sin /mis) era un BUG: devolvía
 * TODAS las comisiones del tenant en vez de las del alumno. Eliminado.
 */
export async function listMyComisiones(
  getToken?: TokenGetter,
): Promise<{ items: Comision[]; next_cursor: string | null }> {
  const r = await fetch("/api/v1/comisiones/mis", {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list mis comisiones failed: ${r.status}`)
  const body = (await r.json()) as {
    data: Comision[]
    meta: { cursor_next: string | null }
  }
  return { items: body.data, next_cursor: body.meta.cursor_next }
}

export const comisionesApi = {
  listMine: listMyComisiones,
}

// ── Materias del estudiante (shape principal del web-student) ─────────

/**
 * Vista flatten de una materia en la que el estudiante esta inscripto.
 *
 * Combina datos de Inscripcion + Comision + Materia + Periodo en una sola
 * fila por inscripcion activa. Es el shape que usa la home: el alumno elige
 * MATERIA (no comisión); la comisión queda como metadata implícita.
 *
 * Coincide bit-a-bit con `MateriaInscripta` del academic-service
 * (`apps/academic-service/src/academic_service/schemas/inscripcion.py`).
 */
export interface MateriaInscripta {
  materia_id: string
  codigo: string
  nombre: string
  comision_id: string
  comision_codigo: string
  comision_nombre: string | null
  horario_resumen: string | null
  periodo_id: string
  periodo_codigo: string
  inscripcion_id: string
  fecha_inscripcion: string // ISO 8601 (YYYY-MM-DD)
}

/**
 * Lista las materias en las que el estudiante autenticado esta inscripto.
 *
 * Backend: `GET /api/v1/materias/mias` (academic-service). El filtro por
 * `student_pseudonym` lo hace el endpoint usando el header `X-User-Id`
 * inyectado por el api-gateway. Sin paginación (alumnos típicos tienen
 * <10 materias por cuatrimestre).
 *
 * Devuelve `[]` honestamente si el alumno no tiene inscripciones activas
 * (la home muestra mensaje literal del gap B.2 en ese caso). NO cae a un
 * fallback que devuelva data ajena.
 */
export async function listMisMaterias(getToken?: TokenGetter): Promise<MateriaInscripta[]> {
  const r = await fetch("/api/v1/materias/mias", {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list mis materias failed: ${r.status}`)
  const body = (await r.json()) as {
    data: MateriaInscripta[]
    meta: { total?: number | null }
  }
  return body.data
}

export const materiasApi = {
  listMine: listMisMaterias,
}

// ── Entregas y Ejercicios (tp-entregas-correccion) ────────────────────

/**
 * Ejercicio del banco standalone (ADR-047 + ADR-048).
 * El shape completo incluye campos pedagógicos PID-UTN pero el alumno solo
 * consume el subset visible (titulo, enunciado, codigo inicial, tests publicos).
 */
export interface Ejercicio {
  id: string
  titulo: string
  enunciado_md: string
  inicial_codigo: string | null
  unidad_tematica: string
  dificultad: "basica" | "intermedia" | "avanzada" | null
  /** Lenguaje del ejercicio. Sobrevive el saneado para alumno: el sanitizer usa
   * `model_copy(update=...)` y no lista este campo. Ver `content_visibility.py`. */
  language?: Language
  /** Solo los PUBLICOS al alumno (backend `sanitize_ejercicio_for_student`). */
  test_cases: TestCasePublic[]
}

/**
 * Asociación TP ↔ Ejercicio devuelta por GET /tareas-practicas/{id}/ejercicios.
 * Incluye el `Ejercicio` embebido para que la UI no necesite un roundtrip más.
 */
export interface TpEjercicio {
  id: string
  tarea_practica_id: string
  ejercicio_id: string
  orden: number
  peso_en_tp: string
  ejercicio: Ejercicio
}

/**
 * Estado de un ejercicio dentro de una entrega (ADR-047).
 * `ejercicio_id` es la identidad permanente; `orden` se preserva como
 * snapshot del momento de la entrega.
 */
export interface EjercicioEstado {
  ejercicio_id: string | null
  orden: number
  completado: boolean
  episode_id: string | null
  completado_at: string | null
}

export type EntregaEstado = "draft" | "submitted" | "graded" | "returned"

/**
 * Una entrega de TP del estudiante.
 * El campo `ejercicio_estados` es un array paralelo a los ejercicios de la TP.
 */
export interface Entrega {
  id: string
  tenant_id: string
  tarea_practica_id: string
  comision_id: string
  student_pseudonym: string
  estado: EntregaEstado
  ejercicio_estados: EjercicioEstado[]
  submitted_at: string | null
  created_at: string
  updated_at: string
}

export interface CalificacionCriterio {
  nombre: string
  puntaje: number
  peso: number
  comentario: string | null
}

export interface Calificacion {
  id: string
  entrega_id: string
  nota_final: number
  feedback_general: string
  detalle_criterios: CalificacionCriterio[]
  graded_at: string
  graded_by: string
}

/**
 * Crea o recupera una entrega en draft para el estudiante en una TP.
 * Idempotente: si ya existe, devuelve la existente.
 */
export async function createOrGetEntrega(
  payload: { tarea_practica_id: string; comision_id: string },
  getToken?: TokenGetter,
): Promise<Entrega> {
  const r = await fetch("/api/v1/entregas", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`create entrega failed: ${r.status}`)
  return (await r.json()) as Entrega
}

/**
 * Envia la entrega (draft → submitted). Requiere que todos los ejercicios
 * esten completados. Emite CTR tp_entregada.
 */
export async function submitEntrega(
  entregaId: string,
  artefactos: ArtefactoDraft[] = [],
  getToken?: TokenGetter,
): Promise<Entrega> {
  const r = await fetch(`/api/v1/entregas/${entregaId}/submit`, {
    method: "POST",
    headers: { ...(await authHeaders(getToken)), "Content-Type": "application/json" },
    body: JSON.stringify({ artefactos }),
  })
  if (!r.ok) {
    const body = await r.text()
    throw new Error(`submit entrega failed: ${r.status} ${body}`)
  }
  return (await r.json()) as Entrega
}

/**
 * Trae los ejercicios asociados a una TP (ADR-047).
 *
 * Backend devuelve `TpEjercicio[]` ordenado por `orden`, cada item con el
 * `Ejercicio` embebido. Sin esto la UI tendría que pedir ejercicio por ejercicio.
 */
export async function listEjerciciosTp(
  tareaId: string,
  getToken?: TokenGetter,
): Promise<TpEjercicio[]> {
  const r = await fetch(`/api/v1/tareas-practicas/${tareaId}/ejercicios`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list ejercicios failed: ${r.status}`)
  return (await r.json()) as TpEjercicio[]
}

/**
 * Trae la calificacion de una entrega. 404 si aun no fue calificada.
 * Devuelve null si no hay calificacion todavia.
 */
export async function getCalificacion(
  entregaId: string,
  getToken?: TokenGetter,
): Promise<Calificacion | null> {
  const r = await fetch(`/api/v1/entregas/${entregaId}/calificacion`, {
    headers: await authHeaders(getToken),
  })
  if (r.status === 404) return null
  if (!r.ok) throw new Error(`get calificacion failed: ${r.status}`)
  return (await r.json()) as Calificacion
}

/**
 * Trae las entregas del estudiante para una TP, filtrado por comision.
 * Devuelve null si no hay entrega todavia.
 *
 * Backend devuelve envelope `{data, meta}`. Sin desempaquetar `data`, el
 * indexado `[0]` cae siempre en undefined → el alumno nunca ve su entrega.
 */
/**
 * Relee UNA entrega por su id, fresca del servidor.
 *
 * Existe para los guards que no pueden confiar en el estado que quedo en
 * memoria. `ExerciseListView` monta su entrega con un `useEffect` que corre una
 * sola vez y nunca repolla: una pestana vieja sigue diciendo "draft" horas
 * despues de que el docente devolvio la entrega, y re-enviarla ahi le borra al
 * alumno la devolucion que fue a leer.
 */
export async function getEntregaById(entregaId: string, getToken?: TokenGetter): Promise<Entrega> {
  const r = await fetch(`/api/v1/entregas/${entregaId}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get entrega failed: ${r.status}`)
  return (await r.json()) as Entrega
}

export async function getEntregaForTp(
  tareaId: string,
  comisionId: string,
  getToken?: TokenGetter,
): Promise<Entrega | null> {
  const qs = new URLSearchParams({ tarea_practica_id: tareaId, comision_id: comisionId })
  const r = await fetch(`/api/v1/entregas?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get entrega failed: ${r.status}`)
  const body = (await r.json()) as { data: Entrega[]; meta: unknown }
  return body.data[0] ?? null
}

/**
 * Lista TODAS las entregas del estudiante en una comision.
 *
 * Mismo endpoint que `getEntregaForTp`, sin el filtro por TP: el backend
 * (`evaluation-service/routes/entregas.py::list_entregas`) tiene ambos query
 * params opcionales y para un usuario sin rol docente fuerza
 * `student_pseudonym = user.id`, asi que un alumno solo puede ver las propias.
 *
 * La usa el onboarding progresivo para responder "¿entrego alguna vez?" sin
 * pedir una TP por vez ni agregar un endpoint nuevo.
 */
export async function listMisEntregas(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<Entrega[]> {
  const qs = new URLSearchParams({ comision_id: comisionId, limit: "50" })
  const r = await fetch(`/api/v1/entregas?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list mis entregas failed: ${r.status}`)
  const body = (await r.json()) as { data: Entrega[]; meta: unknown }
  return body.data
}

/**
 * Marca un ejercicio como completado dentro de una entrega (ADR-047).
 * Llamado despues de cerrar el episodio del ejercicio correspondiente.
 * PATCH /api/v1/entregas/{id}/ejercicio/{orden}
 *
 * Pasa `ejercicio_id` en el body para que el backend matchee por UUID
 * (mas robusto que orden ante reordenamientos futuros). El `orden` en el
 * path param queda por compat con el shape del endpoint.
 */
export async function markEjercicioCompleted(
  entregaId: string,
  orden: number,
  episodeId: string,
  ejercicioId: string,
  getToken?: TokenGetter,
): Promise<Entrega> {
  const r = await fetch(`/api/v1/entregas/${entregaId}/ejercicio/${orden}`, {
    method: "PATCH",
    headers: await authHeaders(getToken),
    body: JSON.stringify({
      completado: true,
      episode_id: episodeId,
      ejercicio_id: ejercicioId,
    }),
  })
  if (!r.ok) throw new Error(`mark ejercicio completed failed: ${r.status}`)
  return (await r.json()) as Entrega
}

export const entregasApi = {
  createOrGet: createOrGetEntrega,
  submit: submitEntrega,
  getForTp: getEntregaForTp,
  getById: getEntregaById,
  listMine: listMisEntregas,
  getCalificacion,
  listEjerciciosTp,
  markEjercicioCompleted,
}

// ============================================================================
// INSTRUMENTOS DEL DISENO CUASI-EXPERIMENTAL (ADR-053)
// P2-1 (pretest), P2-2 (cuestionario IA), P2-3 (transferencia) del PlanMejora.md.
// Contenido pendiente de validacion coautoral con Ana Garis + comite etico UTN.
// ============================================================================

export interface InstrumentoCatalogoItem {
  id: string
  text: string
  type:
    | "likert"
    | "single_choice"
    | "multiple_choice"
    | "code"
    | "multiple_choice_with_justification"
  options?: string[]
  scale_min?: number
  scale_max?: number
  scale_labels?: Record<string, string>
  subscale?: string
  required?: boolean
}

export interface InstrumentoCatalogo {
  instrument_version: string
  items: InstrumentoCatalogoItem[]
  draft_notice: string
  scale?: { min: number; max: number; type: string }
}

export interface CuestionarioIAResponse {
  id: string
  tenant_id: string
  comision_id: string
  student_pseudonym: string
  instrument_version: string
  responses: Record<string, unknown>
  submitted_at: string
  created_at: string
}

export interface PretestAutoeficaciaResponse extends CuestionarioIAResponse {
  total_score: number | null
  subscale_scores: Record<string, number> | null
}

export interface TestTransferenciaProblem {
  test_id: string
  title: string
  description: string
  expected_type: string
  options?: string[]
  max_time_seconds: number
}

export interface TestTransferenciaCatalogo {
  instrument_version: string
  problems: TestTransferenciaProblem[]
  draft_notice: string
}

export interface TestTransferenciaResponse {
  id: string
  tenant_id: string
  comision_id: string
  student_pseudonym: string
  instrument_version: string
  group_assignment: "experimental" | "comparison"
  test_id: string
  correct_answer: boolean
  time_taken_seconds: number
  response_detail: Record<string, unknown>
  submitted_at: string
  created_at: string
}

// ─── Cuestionario IA (P2-2) ──────────────────────────────────────────────

export async function getCuestionarioIACatalogo(
  getToken?: TokenGetter,
): Promise<InstrumentoCatalogo> {
  const r = await fetch("/api/v1/instrumentos/cuestionario-ia/catalogo", {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get cuestionario-ia catalogo failed: ${r.status}`)
  return r.json()
}

export async function submitCuestionarioIA(
  body: {
    comision_id: string
    student_pseudonym: string
    instrument_version?: string
    responses: Record<string, unknown>
  },
  getToken?: TokenGetter,
): Promise<CuestionarioIAResponse> {
  const r = await fetch("/api/v1/instrumentos/cuestionario-ia", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const detail = await r.text()
    throw new Error(`submit cuestionario-ia failed: ${r.status} ${detail}`)
  }
  return r.json()
}

export async function getMyCuestionarioIA(
  comisionId: string,
  instrumentVersion = "cuestionario-ia-v0.1.0-draft",
  getToken?: TokenGetter,
): Promise<CuestionarioIAResponse | null> {
  const params = new URLSearchParams({
    comision_id: comisionId,
    instrument_version: instrumentVersion,
  })
  const r = await fetch(`/api/v1/instrumentos/cuestionario-ia/me?${params}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get my cuestionario-ia failed: ${r.status}`)
  return r.json()
}

// ─── Pretest Autoeficacia (P2-1) ─────────────────────────────────────────

export async function getPretestCatalogo(getToken?: TokenGetter): Promise<InstrumentoCatalogo> {
  const r = await fetch("/api/v1/instrumentos/pretest-autoeficacia/catalogo", {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get pretest catalogo failed: ${r.status}`)
  return r.json()
}

export async function submitPretestAutoeficacia(
  body: {
    comision_id: string
    student_pseudonym: string
    instrument_version?: string
    responses: Record<string, number>
  },
  getToken?: TokenGetter,
): Promise<PretestAutoeficaciaResponse> {
  const r = await fetch("/api/v1/instrumentos/pretest-autoeficacia", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const detail = await r.text()
    throw new Error(`submit pretest failed: ${r.status} ${detail}`)
  }
  return r.json()
}

export async function getMyPretestAutoeficacia(
  comisionId: string,
  instrumentVersion = "lishinski-2016-es-utn-v0.1.0-draft",
  getToken?: TokenGetter,
): Promise<PretestAutoeficaciaResponse | null> {
  const params = new URLSearchParams({
    comision_id: comisionId,
    instrument_version: instrumentVersion,
  })
  const r = await fetch(`/api/v1/instrumentos/pretest-autoeficacia/me?${params}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get my pretest failed: ${r.status}`)
  return r.json()
}

// ─── Test de Transferencia (P2-3) ────────────────────────────────────────

export async function getTransferenciaCatalogo(
  getToken?: TokenGetter,
): Promise<TestTransferenciaCatalogo> {
  const r = await fetch("/api/v1/instrumentos/transferencia/catalogo", {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get transferencia catalogo failed: ${r.status}`)
  return r.json()
}

export async function submitTransferencia(
  body: {
    comision_id: string
    student_pseudonym: string
    instrument_version?: string
    group_assignment: "experimental" | "comparison"
    test_id: string
    time_taken_seconds: number
    response_detail: Record<string, unknown>
  },
  getToken?: TokenGetter,
): Promise<TestTransferenciaResponse> {
  const r = await fetch("/api/v1/instrumentos/transferencia", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const detail = await r.text()
    throw new Error(`submit transferencia failed: ${r.status} ${detail}`)
  }
  return r.json()
}

export async function listMyTransferencia(
  comisionId: string,
  instrumentVersion = "transfer-test-v0.1.0-draft",
  getToken?: TokenGetter,
): Promise<TestTransferenciaResponse[]> {
  const params = new URLSearchParams({
    comision_id: comisionId,
    instrument_version: instrumentVersion,
  })
  const r = await fetch(`/api/v1/instrumentos/transferencia/me?${params}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`list my transferencia failed: ${r.status}`)
  return r.json()
}

export const instrumentosApi = {
  cuestionarioIA: {
    catalogo: getCuestionarioIACatalogo,
    submit: submitCuestionarioIA,
    me: getMyCuestionarioIA,
  },
  pretest: {
    catalogo: getPretestCatalogo,
    submit: submitPretestAutoeficacia,
    me: getMyPretestAutoeficacia,
  },
  transferencia: {
    catalogo: getTransferenciaCatalogo,
    submit: submitTransferencia,
    me: listMyTransferencia,
  },
}
