/**
 * Cliente de API del web-student.
 *
 * F6: reemplazado headers X-* dev por flow OIDC real. El token viene
 * del AuthContext (keycloak-js) y se agrega como Authorization: Bearer.
 *
 * El proxy de Vite (vite.config.ts) redirige /api/* al api-gateway.
 */

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
}

type TokenGetter = () => Promise<string | null>

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
  estado: "open" | "closed"
  opened_at: string
  closed_at: string | null
  last_code_snapshot: string | null
  messages: Array<{ role: "user" | "assistant"; content: string; ts: string }>
  notes: Array<{ contenido: string; ts: string }>
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
    if (delays[i] > 0) await new Promise((resolve) => setTimeout(resolve, delays[i]))
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
  getToken?: TokenGetter,
): AsyncGenerator<
  | { type: "chunk"; content: string }
  | { type: "done"; chunks_used_hash: string; seqs: Record<string, number> }
  | { type: "error"; message: string },
  void,
  unknown
> {
  const headers = await authHeaders(getToken)
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

export type EdicionCodigoOrigin = "student_typed" | "copied_from_tutor" | "pasted_external"

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
  getToken?: TokenGetter,
): Promise<EventEmitResponse> {
  const r = await fetch(`/api/v1/episodes/${episodeId}/reflection`, {
    method: "POST",
    headers: await authHeaders(getToken),
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
  /** Unidad temática a la que pertenece la TP (null si está sin asignar). */
  unidad_id: string | null
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
 * Trae los episodios cerrados del estudiante en una comision. Usado por
 * el TareaSelector para mostrar la trayectoria N4 historica en TPs
 * analogas (mismo `template_id`).
 *
 * `studentPseudonym` = UUID del estudiante autenticado. En dev mode el
 * proxy de Vite inyecta `x-user-id`; en prod viene del JWT.
 */
export async function listStudentEpisodes(
  studentPseudonym: string,
  comisionId: string,
  getToken?: TokenGetter,
): Promise<StudentEpisodesResponse> {
  const qs = new URLSearchParams({ comision_id: comisionId })
  const r = await fetch(`/api/v1/analytics/student/${studentPseudonym}/episodes?${qs.toString()}`, {
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
  unidad_tematica: "secuenciales" | "condicionales" | "repetitivas" | "mixtos"
  dificultad: "basica" | "intermedia" | "avanzada" | null
  test_cases: unknown[]
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
export async function submitEntrega(entregaId: string, getToken?: TokenGetter): Promise<Entrega> {
  const r = await fetch(`/api/v1/entregas/${entregaId}/submit`, {
    method: "POST",
    headers: await authHeaders(getToken),
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
