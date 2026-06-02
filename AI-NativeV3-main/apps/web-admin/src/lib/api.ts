/**
 * Cliente HTTP tipado hacia el api-gateway.
 *
 * Usa fetch con el JWT inyectado automáticamente desde auth-client.
 */

export interface ApiError {
  status: number
  title: string
  detail?: string
}

export interface ListMeta {
  cursor_next: string | null
  total: number | null
}

export interface ListResponse<T> {
  data: T[]
  meta: ListMeta
}

export class HttpError extends Error {
  constructor(
    public status: number,
    public title: string,
    public detail?: string,
  ) {
    super(title)
  }
}

const API_BASE = "/api/v1"

async function request<T>(
  path: string,
  init: RequestInit = {},
  getToken?: () => Promise<string | null>,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has("Content-Type") && init.method && init.method !== "GET") {
    headers.set("Content-Type", "application/json")
  }

  if (getToken) {
    const token = await getToken()
    if (token) headers.set("Authorization", `Bearer ${token}`)
  }
  // En dev, los headers X-User-Id / X-Tenant-Id / X-User-Email / X-User-Roles
  // los inyecta el proxy de Vite (`vite.config.ts`). El tenant se resuelve
  // dinamicamente desde el `x-selected-tenant` que el monkey-patch de
  // `main.tsx` agrega leyendo `localStorage.selectedTenantId`.

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })

  if (!response.ok) {
    const raw = await response.text()
    let detail = raw
    try {
      const body = JSON.parse(raw)
      detail = body.detail ?? body.title ?? raw
    } catch {
      /* not JSON, use raw text */
    }
    throw new HttpError(response.status, response.statusText, detail)
  }

  if (response.status === 204) return undefined as T

  return response.json()
}

// ── Universidades ────────────────────────────────────────────────────

export interface Universidad {
  id: string
  nombre: string
  codigo: string
  dominio_email: string | null
  keycloak_realm: string
  config: Record<string, unknown>
  created_at: string
}

export interface UniversidadCreate {
  nombre: string
  codigo: string
  dominio_email?: string
  keycloak_realm: string
}

export const universidadesApi = {
  list: (params?: { cursor?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.cursor) qs.set("cursor", params.cursor)
    if (params?.limit) qs.set("limit", String(params.limit))
    const query = qs.toString()
    return request<ListResponse<Universidad>>(`/universidades${query ? `?${query}` : ""}`)
  },
  get: (id: string) => request<Universidad>(`/universidades/${id}`),
  create: (data: UniversidadCreate) =>
    request<Universidad>("/universidades", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<UniversidadCreate>) =>
    request<Universidad>(`/universidades/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/universidades/${id}`, { method: "DELETE" }),
}

// ── Carreras ─────────────────────────────────────────────────────────

export interface Carrera {
  id: string
  tenant_id: string
  universidad_id: string
  facultad_id: string
  nombre: string
  codigo: string
  duracion_semestres: number
  modalidad: "presencial" | "virtual" | "hibrida"
  director_user_id: string | null
  created_at: string
}

export interface CarreraCreate {
  facultad_id: string
  nombre: string
  codigo: string
  duracion_semestres?: number
  modalidad?: "presencial" | "virtual" | "hibrida"
}

export const carrerasApi = {
  list: (params?: { universidad_id?: string; cursor?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.universidad_id) qs.set("universidad_id", params.universidad_id)
    if (params?.cursor) qs.set("cursor", params.cursor)
    if (params?.limit) qs.set("limit", String(params.limit))
    const query = qs.toString()
    return request<ListResponse<Carrera>>(`/carreras${query ? `?${query}` : ""}`)
  },
  get: (id: string) => request<Carrera>(`/carreras/${id}`),
  create: (data: CarreraCreate) =>
    request<Carrera>("/carreras", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<CarreraCreate>) =>
    request<Carrera>(`/carreras/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/carreras/${id}`, { method: "DELETE" }),
}

// ── Planes de estudio ────────────────────────────────────────────────

export interface Plan {
  id: string
  tenant_id: string
  carrera_id: string
  version: string
  año_inicio: number
  ordenanza: string | null
  vigente: boolean
  created_at: string
  deleted_at: string | null
}

export interface PlanCreate {
  carrera_id: string
  version: string
  año_inicio: number
  ordenanza?: string
  vigente?: boolean
}

export const planesApi = {
  list: (params?: { carrera_id?: string; cursor?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.carrera_id) qs.set("carrera_id", params.carrera_id)
    if (params?.cursor) qs.set("cursor", params.cursor)
    if (params?.limit) qs.set("limit", String(params.limit))
    const query = qs.toString()
    return request<ListResponse<Plan>>(`/planes${query ? `?${query}` : ""}`)
  },
  get: (id: string) => request<Plan>(`/planes/${id}`),
  create: (data: PlanCreate) =>
    request<Plan>("/planes", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<PlanCreate>) =>
    request<Plan>(`/planes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/planes/${id}`, { method: "DELETE" }),
}

// ── Materias ─────────────────────────────────────────────────────────

export interface Materia {
  id: string
  tenant_id: string
  plan_id: string
  nombre: string
  codigo: string
  horas_totales: number
  cuatrimestre_sugerido: number
  objetivos: string | null
  correlativas_cursar: string[]
  correlativas_rendir: string[]
  created_at: string
  deleted_at: string | null
}

export interface MateriaCreate {
  plan_id: string
  nombre: string
  codigo: string
  horas_totales?: number
  cuatrimestre_sugerido?: number
  objetivos?: string
  correlativas_cursar?: string[]
  correlativas_rendir?: string[]
}

export const materiasApi = {
  list: (params?: { plan_id?: string; cursor?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.plan_id) qs.set("plan_id", params.plan_id)
    if (params?.cursor) qs.set("cursor", params.cursor)
    if (params?.limit) qs.set("limit", String(params.limit))
    const query = qs.toString()
    return request<ListResponse<Materia>>(`/materias${query ? `?${query}` : ""}`)
  },
  get: (id: string) => request<Materia>(`/materias/${id}`),
  create: (data: MateriaCreate) =>
    request<Materia>("/materias", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Omit<MateriaCreate, "plan_id">>) =>
    request<Materia>(`/materias/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/materias/${id}`, { method: "DELETE" }),
}

// ── Periodos ─────────────────────────────────────────────────────────

export interface Periodo {
  id: string
  tenant_id: string
  codigo: string
  nombre: string
  fecha_inicio: string
  fecha_fin: string
  estado: "abierto" | "cerrado"
  created_at: string
}

export interface PeriodoCreate {
  codigo: string
  nombre: string
  fecha_inicio: string
  fecha_fin: string
  estado?: "abierto" | "cerrado"
}

export interface PeriodoUpdate {
  nombre?: string
  fecha_inicio?: string
  fecha_fin?: string
  estado?: "abierto" | "cerrado"
}

export const periodosApi = {
  list: (params?: { cursor?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.cursor) qs.set("cursor", params.cursor)
    if (params?.limit) qs.set("limit", String(params.limit))
    const query = qs.toString()
    return request<ListResponse<Periodo>>(`/periodos${query ? `?${query}` : ""}`)
  },
  create: (data: PeriodoCreate) =>
    request<Periodo>("/periodos", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: PeriodoUpdate) =>
    request<Periodo>(`/periodos/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/periodos/${id}`, { method: "DELETE" }),
}

// ── Comisiones ───────────────────────────────────────────────────────

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

export interface ComisionCreate {
  materia_id: string
  periodo_id: string
  codigo: string
  nombre: string
  cupo_maximo?: number
  horario?: Record<string, unknown>
  ai_budget_monthly_usd?: string | number
}

export interface ComisionUpdate {
  cupo_maximo?: number
  horario?: Record<string, unknown>
  ai_budget_monthly_usd?: string | number
}

export const comisionesApi = {
  list: (params?: {
    materia_id?: string
    periodo_id?: string
    cursor?: string
    limit?: number
  }) => {
    const qs = new URLSearchParams()
    if (params?.materia_id) qs.set("materia_id", params.materia_id)
    if (params?.periodo_id) qs.set("periodo_id", params.periodo_id)
    if (params?.cursor) qs.set("cursor", params.cursor)
    if (params?.limit) qs.set("limit", String(params.limit))
    const query = qs.toString()
    return request<ListResponse<Comision>>(`/comisiones${query ? `?${query}` : ""}`)
  },
  get: (id: string) => request<Comision>(`/comisiones/${id}`),
  create: (data: ComisionCreate) =>
    request<Comision>("/comisiones", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: ComisionUpdate) =>
    request<Comision>(`/comisiones/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/comisiones/${id}`, { method: "DELETE" }),
  // Asigna un docente a la comision POR EMAIL. El user_id se resuelve cuando
  // el docente se loguea con Clerk (matching por email en el backend).
  addDocente: (comisionId: string, data: UsuarioComisionCreate) =>
    request<UsuarioComisionOut>(`/comisiones/${comisionId}/docentes`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
}

// ── Facultades ───────────────────────────────────────────────────────

export interface Facultad {
  id: string
  tenant_id: string
  universidad_id: string
  nombre: string
  codigo: string
  decano_user_id: string | null
  created_at: string
  deleted_at: string | null
}

export interface FacultadCreate {
  universidad_id: string
  nombre: string
  codigo: string
  decano_user_id?: string
}

export interface FacultadUpdate {
  nombre?: string
  decano_user_id?: string
}

export const facultadesApi = {
  list: (params?: {
    universidad_id?: string
    cursor?: string
    limit?: number
  }) => {
    const qs = new URLSearchParams()
    if (params?.universidad_id) qs.set("universidad_id", params.universidad_id)
    if (params?.cursor) qs.set("cursor", params.cursor)
    if (params?.limit) qs.set("limit", String(params.limit))
    const query = qs.toString()
    return request<ListResponse<Facultad>>(`/facultades${query ? `?${query}` : ""}`)
  },
  get: (id: string) => request<Facultad>(`/facultades/${id}`),
  create: (data: FacultadCreate) =>
    request<Facultad>("/facultades", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: FacultadUpdate) =>
    request<Facultad>(`/facultades/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/facultades/${id}`, { method: "DELETE" }),
}

// ── UsuarioComision ──────────────────────────────────────────────────

export interface UsuarioComisionOut {
  id: string
  tenant_id: string
  comision_id: string
  // null hasta que el docente se loguea con Clerk (asignado por email).
  user_id: string | null
  email: string | null
  rol: "titular" | "adjunto" | "jtp" | "ayudante" | "corrector"
  permisos_extra: string[]
  fecha_desde: string
  fecha_hasta: string | null
  created_at: string
  deleted_at: string | null
}

export interface UsuarioComisionCreate {
  // El admin asigna por email; el docente todavia no tiene user_id.
  email: string
  rol?: "titular" | "adjunto" | "jtp" | "ayudante" | "corrector"
  fecha_desde?: string
  fecha_hasta?: string
}

// ── Inscripcion (individual) ─────────────────────────────────────────

export interface InscripcionOut {
  id: string
  tenant_id: string
  comision_id: string
  student_pseudonym: string
  rol: "regular" | "oyente" | "reinscripcion"
  estado: "activa" | "cursando" | "aprobado" | "desaprobado" | "abandono"
  fecha_inscripcion: string
  // sprint 2026-05-17: backend ahora serializa `nota_final` como `float | null`
  // (mismo fix que CalificacionOut en evaluation-service). El workaround
  // `string | null` ya no aplica.
  nota_final: number | null
  fecha_cierre: string | null
  created_at: string
}

export interface InscripcionCreate {
  student_pseudonym: string
  rol?: "regular" | "oyente" | "reinscripcion"
  estado?: "activa" | "cursando" | "aprobado" | "desaprobado" | "abandono"
  fecha_inscripcion: string
  // Pydantic acepta number en su field `Decimal` (validación numérica de input
  // con `ge=0, le=10` en el backend). Antes era `string` para evitar issues
  // de serialización en el response — ese workaround ya no aplica.
  nota_final?: number
  fecha_cierre?: string
}

// ── BYOK Keys ────────────────────────────────────────────────────────

export interface ByokKey {
  id: string
  tenant_id: string
  scope_type: "tenant" | "materia" | "facultad"
  scope_id: string | null
  provider: string
  fingerprint_last4: string
  monthly_budget_usd: number | null
  created_at: string
  created_by: string
  last_used_at: string | null
  revoked_at: string | null
}

export interface ByokKeyCreate {
  scope_type: "tenant" | "materia" | "facultad"
  scope_id?: string
  provider: "anthropic" | "gemini" | "mistral" | "openai"
  plaintext_value: string
  monthly_budget_usd?: number
}

export interface ByokKeyUsage {
  key_id: string
  yyyymm: string
  tokens_input_total: number
  tokens_output_total: number
  cost_usd_total: number
  request_count: number
}

// ── Bulk import (multipart) ──────────────────────────────────────────

export interface BulkImportRowError {
  row_number: number
  column: string | null
  message: string
}

export interface BulkImportReport {
  total_rows: number
  valid_rows: number
  invalid_rows: number
  errors: BulkImportRowError[]
}

export interface BulkImportCommitResult {
  created_count: number
  created_ids: string[]
}

/**
 * Subida multipart al api-gateway. No usa `request()` porque éste setea
 * `Content-Type: application/json` por default — para multipart hay que
 * dejar que el browser arme el boundary solo.
 */
async function multipartUpload<T>(
  path: string,
  file: File,
  getToken?: () => Promise<string | null>,
): Promise<T> {
  const headers = new Headers()

  if (getToken) {
    const token = await getToken()
    if (token) headers.set("Authorization", `Bearer ${token}`)
  }
  // En dev, headers X-* los inyecta el proxy de Vite (ver request() arriba).

  const body = new FormData()
  body.append("file", file)

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body,
  })

  if (!response.ok) {
    const raw = await response.text()
    let detail: unknown = raw
    try {
      const parsed = JSON.parse(raw)
      detail = parsed.detail ?? parsed.title ?? raw
    } catch {
      /* not JSON */
    }
    // 422 con dry-run report estructurado: lo serializamos a string para
    // que HttpError no se pierda la info — la página lo re-parsea.
    const detailStr = typeof detail === "string" ? detail : JSON.stringify(detail)
    throw new HttpError(response.status, response.statusText, detailStr)
  }

  if (response.status === 204) return undefined as T
  return response.json()
}

export const bulkApi = {
  dryRun: (entity: string, file: File) =>
    multipartUpload<BulkImportReport>(`/bulk/${encodeURIComponent(entity)}?dry_run=true`, file),
  commit: (entity: string, file: File) =>
    multipartUpload<BulkImportCommitResult>(
      `/bulk/${encodeURIComponent(entity)}?dry_run=false`,
      file,
    ),
}

// ── Auditoria CTR (ADR-031, D.4) ───────────────────────────────────────────

/**
 * Resultado de la verificacion de integridad de la cadena CTR de un episodio.
 * Mismo shape que `ChainVerificationResult` del ctr-service Pydantic schema.
 *
 * `valid=true` significa que TODOS los `self_hash` y `chain_hash` recomputados
 * coinciden con los persistidos. `valid=false` con `failing_seq=N` apunta al
 * primer evento donde la integridad se rompio.
 *
 * `integrity_compromised` es un flag persistente de Episode; si fue marcado
 * por el integrity-checker en background, queda `true` aunque la verificacion
 * on-demand pase (caso edge del que el endpoint distingue).
 */
export interface ChainVerificationResult {
  episode_id: string
  valid: boolean
  events_count: number
  failing_seq: number | null
  integrity_compromised: boolean
  message: string
}

export interface EpisodeWithEvents {
  id: string
  tenant_id: string
  comision_id: string
  problema_id: string
  student_pseudonym: string
  estado: string
  opened_at: string
  closed_at: string | null
  total_events: number
  final_chain_hash: string | null
  integrity_compromised: boolean
}

/**
 * Helper para audit del CTR. Pega a los aliases publicos `/api/v1/audit/...`
 * que se rutean al ctr-service via el ROUTE_MAP del api-gateway (ADR-031).
 *
 * NO usar `/api/v1/episodes/...` directo — ese prefix esta tomado por el
 * tutor-service. Los aliases del audit_router en ctr-service apuntan al
 * mismo handler legacy (verificado por tests del ctr-service).
 */
export const auditApi = {
  /** GET /api/v1/audit/episodes/{id} — episodio con eventos. */
  getEpisode: (episodeId: string) =>
    request<EpisodeWithEvents>(`/audit/episodes/${encodeURIComponent(episodeId)}`),

  /** POST /api/v1/audit/episodes/{id}/verify — recomputa hashes y compara. */
  verifyEpisode: (episodeId: string) =>
    request<ChainVerificationResult>(`/audit/episodes/${encodeURIComponent(episodeId)}/verify`, {
      method: "POST",
    }),
}

// ── Governance Events (epic ai-native-completion / Sec 12) ────────────

/**
 * Vista institucional cross-cohort de eventos `intento_adverso_detectado`
 * (ADR-019, RN-129). Consume `/api/v1/analytics/governance/events`.
 */
export interface GovernanceEvent {
  episode_id: string
  student_pseudonym: string
  comision_id: string
  ts: string
  category: string
  severity: number
  pattern_id: string
  matched_text: string
}

export interface GovernanceEventsResponse {
  events: GovernanceEvent[]
  cursor_next: string | null
  n_total_estimate: number
  counts_by_category: Record<string, number>
  counts_by_severity: Record<string, number>
  filters_applied: Record<string, string | null>
}

export interface GovernanceEventsFilters {
  facultad_id?: string
  materia_id?: string
  periodo_id?: string
  severity_min?: number
  severity_max?: number
  category?: string
  cursor?: string
  limit?: number
}

export const governanceApi = {
  listEvents: (filters: GovernanceEventsFilters = {}) => {
    const qs = new URLSearchParams()
    if (filters.facultad_id) qs.set("facultad_id", filters.facultad_id)
    if (filters.materia_id) qs.set("materia_id", filters.materia_id)
    if (filters.periodo_id) qs.set("periodo_id", filters.periodo_id)
    if (filters.severity_min !== undefined) qs.set("severity_min", String(filters.severity_min))
    if (filters.severity_max !== undefined) qs.set("severity_max", String(filters.severity_max))
    if (filters.category) qs.set("category", filters.category)
    if (filters.cursor) qs.set("cursor", filters.cursor)
    if (filters.limit !== undefined) qs.set("limit", String(filters.limit))
    const query = qs.toString()
    return request<GovernanceEventsResponse>(
      `/analytics/governance/events${query ? `?${query}` : ""}`,
    )
  },
}

// ── BYOK Keys ────────────────────────────────────────────────────────

export const byokApi = {
  list: (params?: { scope_type?: string; scope_id?: string }) => {
    const qs = new URLSearchParams()
    if (params?.scope_type) qs.set("scope_type", params.scope_type)
    if (params?.scope_id) qs.set("scope_id", params.scope_id)
    const query = qs.toString()
    return request<ByokKey[]>(`/byok/keys${query ? `?${query}` : ""}`)
  },
  create: (data: ByokKeyCreate) => {
    const { scope_id, monthly_budget_usd, ...rest } = data
    const clean = {
      ...rest,
      ...(scope_id ? { scope_id } : {}),
      ...(monthly_budget_usd != null ? { monthly_budget_usd } : {}),
    }
    return request<ByokKey>("/byok/keys", {
      method: "POST",
      body: JSON.stringify(clean),
    })
  },
  rotate: (id: string, plaintext_value: string) =>
    request<ByokKey>(`/byok/keys/${id}/rotate`, {
      method: "POST",
      body: JSON.stringify({ plaintext_value }),
    }),
  revoke: (id: string) =>
    request<void>(`/byok/keys/${id}/revoke`, { method: "POST" }),
  // El backend devuelve un single object (uso del mes actual o agregado mensual
  // si se pasa ?yyyymm=). NO es array. Si querés historial multi-mes hay que
  // hacer múltiples calls con yyyymm distinto (deuda pendiente v1.1).
  usage: (id: string, yyyymm?: string) => {
    const qs = yyyymm ? `?yyyymm=${yyyymm}` : ""
    return request<ByokKeyUsage>(`/byok/keys/${id}/usage${qs}`)
  },
}

// ── Comision Docentes ─────────────────────────────────────────────────

export const comisionDocentesApi = {
  list: (comisionId: string) =>
    request<ListResponse<UsuarioComisionOut>>(`/comisiones/${comisionId}/docentes`),
  create: (comisionId: string, data: UsuarioComisionCreate) =>
    request<UsuarioComisionOut>(`/comisiones/${comisionId}/docentes`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delete: (comisionId: string, ucId: string) =>
    request<void>(`/comisiones/${comisionId}/docentes/${ucId}`, { method: "DELETE" }),
}

// ── Comision Inscripciones ────────────────────────────────────────────

export const comisionInscripcionesApi = {
  list: (comisionId: string) =>
    request<ListResponse<InscripcionOut>>(`/comisiones/${comisionId}/inscripciones`),
  create: (comisionId: string, data: InscripcionCreate) =>
    request<InscripcionOut>(`/comisiones/${comisionId}/inscripciones`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delete: (comisionId: string, inscId: string) =>
    request<void>(`/comisiones/${comisionId}/inscripciones/${inscId}`, { method: "DELETE" }),
}
