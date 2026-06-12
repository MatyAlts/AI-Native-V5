/**
 * Cliente API del web-teacher.
 *
 * F8: usa OIDC real con useAuthenticatedFetch. Todas las funciones toman
 * un TokenGetter como primer parámetro.
 */

// Categorias canonicas (Protocolo B — etiqueta oficial del classifier).
export type AppropriationCanonical =
  | "delegacion_pasiva"
  | "apropiacion_superficial"
  | "apropiacion_reflexiva"

// Subgrupos diagnosticos (capa de analisis sobre episodios ya clasificados).
// Deben coincidir con classifier-service/services/subgrupo.py.
export type AppropriationSubgroup =
  | "autonomo_competente"
  | "autonomo_trabado"
  | "escribe_sin_validar"
  | "desenganchado"
  | "colaborador_reflexivo"
  | "colaborador_funcional"
  | "dependiente"
  | "indeterminado"

// Niveles cognitivos del Protocolo A.
export type CognitiveLevelLabel = "N1" | "N2" | "N3" | "N4"

// La etiqueta OFICIAL del classifier es SIEMPRE una de las 3 canonicas.
// (classification.appropriation, trajectories, displays, etc. usan este tipo).
export type AppropriationLabel = AppropriationCanonical

// Etiqueta para RATING inter-rater (kappa): ademas de las 3 canonicas admite
// subgrupos diagnosticos y niveles N1-N4 (protocolos configurables).
export type RatingLabel =
  | AppropriationCanonical
  | AppropriationSubgroup
  | CognitiveLevelLabel

export interface TrajectoryPoint {
  episode_id: string
  classified_at: string
  appropriation: AppropriationLabel
}

export interface StudentTrajectory {
  student_pseudonym: string
  n_episodes: number
  first_classification: AppropriationLabel | null
  last_classification: AppropriationLabel | null
  max_appropriation_reached: AppropriationLabel | null
  progression_label: "mejorando" | "estable" | "empeorando" | "insuficiente"
  tercile_means: [number, number, number] | null
  points: TrajectoryPoint[]
}

export interface CohortProgression {
  comision_id: string
  n_students: number
  n_students_with_enough_data: number
  mejorando: number
  estable: number
  empeorando: number
  insuficiente: number
  net_progression_ratio: number
  trajectories: StudentTrajectory[]
}

export interface KappaRating {
  episode_id: string
  rater_a: RatingLabel
  rater_b: RatingLabel
}

export interface KappaResult {
  kappa: number
  n_episodes: number
  observed_agreement: number
  expected_agreement: number
  interpretation: string
  per_class_agreement: Record<string, number>
  confusion_matrix: Record<string, Record<string, number>>
  // Estadisticos adicionales (defensa ante paradoja de prevalencia).
  ac1: number
  ac1_interpretation: string
  kappa_se: number
  kappa_ci_95: [number, number]
}

export interface ExportJobStatus {
  job_id: string
  status: "pending" | "running" | "succeeded" | "failed"
  comision_id: string
  requested_at: string
  period_days: number
  include_prompts: boolean
  salt_hash: string
  cohort_alias: string
  started_at: string | null
  completed_at: string | null
  error: string | null
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

async function throwIfNotOk(r: Response): Promise<void> {
  if (r.ok) return
  const raw = await r.text()
  let detail = raw
  try {
    const body = JSON.parse(raw)
    detail = body.detail ?? body.title ?? raw
  } catch {
    /* not JSON, use raw text */
  }
  throw new Error(`${r.status}: ${detail}`)
}

// ── Progression ───────────────────────────────────────────────────────

export async function getCohortProgression(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<CohortProgression> {
  const r = await fetch(`/api/v1/analytics/cohort/${comisionId}/progression`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

// ── Student profiles (auto-llenado desde Clerk via web-student) ───────

export interface StudentProfile {
  student_pseudonym: string
  full_name: string | null
  email: string | null
  updated_at: string | null
}

export async function listStudentProfiles(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<StudentProfile[]> {
  const r = await fetch(`/api/v1/comisiones/${comisionId}/students/profiles`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

// ── Kappa ─────────────────────────────────────────────────────────────

export async function computeKappa(
  ratings: KappaRating[],
  getToken?: TokenGetter,
): Promise<KappaResult> {
  const r = await fetch("/api/v1/analytics/kappa", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify({ ratings }),
  })
  await throwIfNotOk(r)
  return r.json()
}

// Episodios REALES de una comision para el inter-rater (reemplaza los demo).
export interface KappaSampleEpisode {
  episode_id: string
  clasificacion_ia: AppropriationLabel
}

export async function getKappaSample(
  comisionId: string,
  getToken?: TokenGetter,
  limit = 30,
): Promise<{ comision_id: string; episodes: KappaSampleEpisode[] }> {
  const r = await fetch(
    `/api/v1/analytics/kappa/sample?comision_id=${comisionId}&limit=${limit}`,
    { headers: await authHeaders(getToken) },
  )
  await throwIfNotOk(r)
  return r.json()
}

// ── Export dataset ────────────────────────────────────────────────────

export async function requestCohortExport(
  params: {
    comision_id: string
    period_days?: number
    include_prompts?: boolean
    salt: string
    cohort_alias?: string
  },
  getToken?: TokenGetter,
): Promise<{ job_id: string; status: string }> {
  const r = await fetch("/api/v1/analytics/cohort/export", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(params),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function getExportStatus(
  jobId: string,
  getToken?: TokenGetter,
): Promise<ExportJobStatus> {
  const r = await fetch(`/api/v1/analytics/cohort/export/${jobId}/status`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function downloadExport(jobId: string, getToken?: TokenGetter): Promise<unknown> {
  const r = await fetch(`/api/v1/analytics/cohort/export/${jobId}/download`, {
    headers: await authHeaders(getToken),
  })
  if (r.status === 425) throw new Error("Job aún no terminado")
  await throwIfNotOk(r)
  return r.json()
}

// ── Materiales (RAG) ──────────────────────────────────────────────────

export type MaterialTipo = "pdf" | "markdown" | "code_archive" | "video" | "text"
export type MaterialEstado =
  | "uploaded"
  | "extracting"
  | "chunking"
  | "embedding"
  | "indexed"
  | "failed"

export interface Material {
  id: string
  tenant_id: string
  materia_id: string | null
  comision_id: string | null // Deprecated: usar materia_id
  tipo: MaterialTipo
  nombre: string
  tamano_bytes: number
  storage_path: string
  estado: MaterialEstado
  chunks_count: number | null
  error_message: string | null
  indexed_at: string | null
  uploaded_by: string
  created_at: string
  meta?: Record<string, unknown>
}

export interface MaterialListResponse {
  data: Material[]
  meta: { cursor_next: string | null }
}

/**
 * Subida multipart al api-gateway. No usa el flujo de `authHeaders()` con
 * Content-Type JSON — para multipart hay que dejar que el browser arme el
 * boundary solo. El proxy de Vite sigue inyectando los X-* en dev.
 */
async function multipartUpload<T>(
  path: string,
  fields: Record<string, string | Blob>,
  getToken?: TokenGetter,
): Promise<T> {
  const headers = new Headers()
  if (getToken) {
    const token = await getToken()
    if (token) headers.set("Authorization", `Bearer ${token}`)
  }

  const body = new FormData()
  for (const [key, val] of Object.entries(fields)) {
    body.append(key, val)
  }

  const r = await fetch(path, { method: "POST", headers, body })
  await throwIfNotOk(r)
  if (r.status === 204) return undefined as T
  return r.json()
}

export async function listMateriales(
  params: { materia_id: string; cursor?: string; limit?: number },
  getToken?: TokenGetter,
): Promise<MaterialListResponse> {
  const qs = new URLSearchParams({ materia_id: params.materia_id })
  if (params.cursor) qs.set("cursor", params.cursor)
  if (params.limit) qs.set("limit", String(params.limit))
  const r = await fetch(`/api/v1/materiales?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function getMaterial(id: string, getToken?: TokenGetter): Promise<Material> {
  const r = await fetch(`/api/v1/materiales/${id}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function uploadMaterial(
  materiaId: string,
  file: File,
  getToken?: TokenGetter,
): Promise<Material> {
  return multipartUpload<Material>("/api/v1/materiales", { materia_id: materiaId, file }, getToken)
}

export async function deleteMaterial(id: string, getToken?: TokenGetter): Promise<void> {
  const r = await fetch(`/api/v1/materiales/${id}`, {
    method: "DELETE",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
}

export const materialesApi = {
  list: listMateriales,
  get: getMaterial,
  upload: uploadMaterial,
  delete: deleteMaterial,
}

// ── Tareas Prácticas (TPs) ────────────────────────────────────────────

export type TareaEstado = "draft" | "published" | "archived"

export interface TareaPractica {
  id: string
  tenant_id: string
  comision_id: string
  codigo: string
  titulo: string
  enunciado: string // markdown
  fecha_inicio: string | null // ISO 8601
  fecha_fin: string | null
  peso: string // decimal serializado como string
  rubrica: Record<string, unknown> | null
  estado: TareaEstado
  version: number
  parent_tarea_id: string | null
  template_id: string | null
  has_drift: boolean
  created_by: string
  created_at: string
  updated_at: string
  // ADR-034 — test cases (nullable — older TPs sin test_cases)
  test_cases?: Array<{
    id: string
    name: string
    type: string
    code: string
    expected: string | null
    is_public: boolean
    weight: number
  }> | null
  // Unidades de trazabilidad — FK nullable a la unidad de la comision (ADR-041)
  unidad_id: string | null
  // Ejercicios asociados a la TP via tp_ejercicios (banco reusable, ADR-047).
  // Opcional: solo presente en endpoints que populan la relacion (ej. GET /tareas-practicas/{id}?include=ejercicios).
  ejercicios?: Array<{
    id: string
    titulo: string
    enunciado: string
    orden: number
  }> | null
}

export interface TareaPracticaCreate {
  comision_id: string
  codigo: string
  titulo: string
  enunciado: string
  fecha_inicio?: string | null
  fecha_fin?: string | null
  peso?: string
  rubrica?: Record<string, unknown> | null
  created_via_ai?: boolean
  template_id?: string | null
}

export interface TareaPracticaUpdate {
  codigo?: string
  titulo?: string
  enunciado?: string
  fecha_inicio?: string | null
  fecha_fin?: string | null
  peso?: string
  rubrica?: Record<string, unknown> | null
  unidad_id?: string | null
}

export interface TareaPracticaListResponse {
  data: TareaPractica[]
  meta: { cursor_next: string | null }
}

export interface TareaPracticaVersionRef {
  id: string
  version: number
  estado: TareaEstado
  titulo: string
  created_at: string
  is_current: boolean
}

export async function listTareasPracticas(
  params: {
    comision_id: string
    estado?: TareaEstado
    cursor?: string
    limit?: number
  },
  getToken?: TokenGetter,
): Promise<TareaPracticaListResponse> {
  const qs = new URLSearchParams({ comision_id: params.comision_id })
  if (params.estado) qs.set("estado", params.estado)
  if (params.cursor) qs.set("cursor", params.cursor)
  if (params.limit) qs.set("limit", String(params.limit))
  const r = await fetch(`/api/v1/tareas-practicas?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function getTareaPractica(id: string, getToken?: TokenGetter): Promise<TareaPractica> {
  const r = await fetch(`/api/v1/tareas-practicas/${id}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function createTareaPractica(
  body: TareaPracticaCreate,
  getToken?: TokenGetter,
): Promise<TareaPractica> {
  const r = await fetch("/api/v1/tareas-practicas", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function updateTareaPractica(
  id: string,
  patch: TareaPracticaUpdate,
  getToken?: TokenGetter,
): Promise<TareaPractica> {
  const r = await fetch(`/api/v1/tareas-practicas/${id}`, {
    method: "PATCH",
    headers: await authHeaders(getToken),
    body: JSON.stringify(patch),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function deleteTareaPractica(id: string, getToken?: TokenGetter): Promise<void> {
  const r = await fetch(`/api/v1/tareas-practicas/${id}`, {
    method: "DELETE",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
}

export async function publishTareaPractica(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPractica> {
  const r = await fetch(`/api/v1/tareas-practicas/${id}/publish`, {
    method: "POST",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function archiveTareaPractica(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPractica> {
  const r = await fetch(`/api/v1/tareas-practicas/${id}/archive`, {
    method: "POST",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function newVersionTareaPractica(
  id: string,
  patch: TareaPracticaUpdate,
  getToken?: TokenGetter,
): Promise<TareaPractica> {
  const r = await fetch(`/api/v1/tareas-practicas/${id}/new-version`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(patch),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function listVersionsTareaPractica(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPracticaVersionRef[]> {
  const r = await fetch(`/api/v1/tareas-practicas/${id}/versions`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export const tareasPracticasApi = {
  list: listTareasPracticas,
  get: getTareaPractica,
  create: createTareaPractica,
  update: updateTareaPractica,
  delete: deleteTareaPractica,
  publish: publishTareaPractica,
  archive: archiveTareaPractica,
  newVersion: newVersionTareaPractica,
  versions: listVersionsTareaPractica,
}

// ── TP Generate con IA (ADR-036) ─────────────────────────────────────

export type DificultadIA = "basica" | "intermedia" | "avanzada"

export interface GenerateTPRequest {
  materia_id: string
  descripcion_nl: string
  num_ejercicios?: number
  dificultad?: DificultadIA
  contexto?: string
  comision_id?: string
  template_id?: string
}

export interface TestCaseIA {
  id?: string
  name?: string
  type?: string
  code?: string
  expected?: string
  is_public?: boolean
  weight?: number
}

export interface EjercicioGenerado {
  titulo: string
  enunciado: string
  inicial_codigo: string
  rubrica: Record<string, unknown>
  test_cases: TestCaseIA[]
}

export interface GenerateTPResponse {
  ejercicios: EjercicioGenerado[]
  prompt_version: string
  model_used: string
  provider_used: string
  tokens_input: number
  tokens_output: number
  rag_chunks_used: number
  rag_chunks_hash: string | null
}

export async function generateTPWithAI(
  body: GenerateTPRequest,
  getToken?: TokenGetter,
): Promise<GenerateTPResponse> {
  const r = await fetch("/api/v1/tareas-practicas/generate", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

// ── Comisiones ────────────────────────────────────────────────────────

export interface Comision {
  id: string
  tenant_id: string
  materia_id: string
  periodo_id: string
  codigo: string
  /**
   * Nombre legible de la comisión (ej. "A-Mañana"). NOT NULL en el
   * backend (`ComisionBase.nombre: str` en
   * `apps/academic-service/src/academic_service/schemas/comision.py`),
   * propagado desde el modelo SQLAlchemy `Comision.nombre` (String(100),
   * nullable=False). El contrato TS estaba en drift (faltaba el campo);
   * el frontend leía `(c as any).nombre` como escape hatch — eliminado.
   */
  nombre: string
  // Materia de la comisión (lo devuelve /comisiones/mis) — para distinguir
  // comisiones de distintas materias en la UI (Prog 1 vs Prog 2).
  materia_nombre?: string | null
  materia_codigo?: string | null
  cupo_maximo: number
  horario: Record<string, unknown>
  ai_budget_monthly_usd: string
  curso_config_hash: string | null
  created_at: string
  deleted_at: string | null
}

/**
 * Devuelve las comisiones donde el user actual tiene un rol activo
 * (docente, jtp, ayudante…) según `usuarios_comision`. Backend:
 * `GET /api/v1/comisiones/mis`.
 *
 * Respuesta: la API académica usa `{data, meta}`; lo normalizamos al
 * shape `{items, next_cursor}` que ya consumen el resto de los selectors
 * del web-teacher (materiales, TPs).
 */
export async function listMyComisiones(
  getToken?: TokenGetter,
): Promise<{ items: Comision[]; next_cursor: string | null }> {
  const r = await fetch("/api/v1/comisiones/mis", {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  const body = (await r.json()) as {
    data: Comision[]
    meta: { cursor_next: string | null }
  }
  return { items: body.data, next_cursor: body.meta.cursor_next }
}

export const comisionesApi = {
  listMine: listMyComisiones,
}

// ── Tareas Prácticas Templates (ADR-016) ──────────────────────────────

/**
 * Plantilla canonica de TP a nivel (materia, periodo). La catedra edita
 * aca; el servicio fan-out-ea `TareaPractica` (instancia) en cada comision
 * que comparte (materia, periodo). Cada instancia tiene su `problema_id`
 * estable para la cadena CTR; el template solo provee la fuente de
 * enunciado/rubrica/peso.
 */
/**
 * Plantilla = brief pedagógico (consigna + meta). NO es una copia del TP.
 * Sirve como prompt para que el docente o la IA generen el TP en cada
 * comisión. Sin fan-out automático (refactor 2026-05-12).
 */
export interface TareaPracticaTemplate {
  id: string
  tenant_id: string
  materia_id: string
  periodo_id: string
  codigo: string
  titulo: string
  consigna: string // directiva pedagógica: qué debe cubrir el TP
  peso: string // decimal serializado como string
  estado: TareaEstado
  version: number
  parent_template_id: string | null
  created_by: string
  created_at: string
  deleted_at: string | null
}

export interface TareaPracticaTemplateCreate {
  materia_id: string
  periodo_id: string
  codigo: string
  titulo: string
  consigna: string
  peso?: string
}

/**
 * Update parcial. `materia_id`, `periodo_id`, `codigo` y `version` son
 * inmutables (se versiona via new-version, no se re-ancla). `estado`
 * muta solo via publish/archive endpoints dedicados.
 */
export interface TareaPracticaTemplateUpdate {
  titulo?: string
  consigna?: string
  peso?: string
}

export interface TareaPracticaTemplateVersionRef {
  id: string
  version: number
  estado: TareaEstado
  created_at: string
  is_current: boolean
}

export interface TareaPracticaTemplateNewVersionBody {
  patch: TareaPracticaTemplateUpdate
}

export interface TareaPracticaTemplatePrompt {
  template_id: string
  codigo: string
  titulo: string
  prompt: string
}

export async function listTareasPracticasTemplates(
  params: {
    materia_id?: string
    periodo_id?: string
    estado?: TareaEstado
  },
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplate[]> {
  const qs = new URLSearchParams()
  if (params.materia_id) qs.set("materia_id", params.materia_id)
  if (params.periodo_id) qs.set("periodo_id", params.periodo_id)
  if (params.estado) qs.set("estado", params.estado)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  const r = await fetch(`/api/v1/tareas-practicas-templates${suffix}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function getTareaPracticaTemplate(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplate> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function createTareaPracticaTemplate(
  body: TareaPracticaTemplateCreate,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplate> {
  const r = await fetch("/api/v1/tareas-practicas-templates", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function updateTareaPracticaTemplate(
  id: string,
  patch: TareaPracticaTemplateUpdate,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplate> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}`, {
    method: "PATCH",
    headers: await authHeaders(getToken),
    body: JSON.stringify(patch),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function deleteTareaPracticaTemplate(
  id: string,
  getToken?: TokenGetter,
): Promise<void> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}`, {
    method: "DELETE",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
}

export async function publishTareaPracticaTemplate(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplate> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}/publish`, {
    method: "POST",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function archiveTareaPracticaTemplate(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplate> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}/archive`, {
    method: "POST",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function newVersionTareaPracticaTemplate(
  id: string,
  body: TareaPracticaTemplateNewVersionBody,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplate> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}/new-version`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function getTareaPracticaTemplateInstances(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPractica[]> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}/instances`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function listVersionsTareaPracticaTemplate(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplateVersionRef[]> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}/versions`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function exportPromptTareaPracticaTemplate(
  id: string,
  getToken?: TokenGetter,
): Promise<TareaPracticaTemplatePrompt> {
  const r = await fetch(`/api/v1/tareas-practicas-templates/${id}/prompt`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export const tareasPracticasTemplatesApi = {
  list: listTareasPracticasTemplates,
  get: getTareaPracticaTemplate,
  create: createTareaPracticaTemplate,
  update: updateTareaPracticaTemplate,
  delete: deleteTareaPracticaTemplate,
  publish: publishTareaPracticaTemplate,
  archive: archiveTareaPracticaTemplate,
  newVersion: newVersionTareaPracticaTemplate,
  instances: getTareaPracticaTemplateInstances,
  versions: listVersionsTareaPracticaTemplate,
  exportPrompt: exportPromptTareaPracticaTemplate,
}

// ── Catalogo academico (para el selector cascada Univ → ... → Periodo) ─

export interface Universidad {
  id: string
  nombre: string
  codigo: string
  dominio_email: string | null
  keycloak_realm: string
  created_at: string
  deleted_at: string | null
}

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
  deleted_at: string | null
}

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

interface ListMetaDto {
  cursor_next: string | null
}
interface ListDto<T> {
  data: T[]
  meta: ListMetaDto
}

async function fetchList<T>(path: string, getToken?: TokenGetter): Promise<T[]> {
  const r = await fetch(path, { headers: await authHeaders(getToken) })
  await throwIfNotOk(r)
  const body = (await r.json()) as ListDto<T>
  return body.data
}

export async function listUniversidades(getToken?: TokenGetter): Promise<Universidad[]> {
  return fetchList<Universidad>("/api/v1/universidades?limit=200", getToken)
}

export async function listFacultades(
  universidadId: string,
  getToken?: TokenGetter,
): Promise<Facultad[]> {
  return fetchList<Facultad>(
    `/api/v1/facultades?universidad_id=${universidadId}&limit=200`,
    getToken,
  )
}

export async function listCarreras(facultadId: string, getToken?: TokenGetter): Promise<Carrera[]> {
  return fetchList<Carrera>(`/api/v1/carreras?facultad_id=${facultadId}&limit=200`, getToken)
}

export async function listPlanes(carreraId: string, getToken?: TokenGetter): Promise<Plan[]> {
  return fetchList<Plan>(`/api/v1/planes?carrera_id=${carreraId}&limit=200`, getToken)
}

export async function listMaterias(planId: string, getToken?: TokenGetter): Promise<Materia[]> {
  const materias = await fetchList<Materia>(`/api/v1/materias?plan_id=${planId}&limit=200`, getToken)
  // Orden pedagógico para todos los dropdowns/listas del panel docente:
  // por cuatrimestre y luego por código (antes salían mezcladas).
  return materias.sort(
    (a, b) =>
      a.cuatrimestre_sugerido - b.cuatrimestre_sugerido || a.codigo.localeCompare(b.codigo),
  )
}

export async function listPeriodos(getToken?: TokenGetter): Promise<Periodo[]> {
  return fetchList<Periodo>("/api/v1/periodos?limit=200", getToken)
}

export const catalogoApi = {
  universidades: listUniversidades,
  facultades: listFacultades,
  carreras: listCarreras,
  planes: listPlanes,
  materias: listMaterias,
  periodos: listPeriodos,
}

// ── Unidades de Trazabilidad ──────────────────────────────────────────

export interface Unidad {
  id: string
  tenant_id: string
  comision_id: string
  nombre: string
  orden: number
  descripcion: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface UnidadCreate {
  comision_id: string
  nombre: string
  orden: number
  descripcion?: string | null
}

export interface UnidadUpdate {
  nombre?: string
  descripcion?: string | null
  orden?: number
}

export interface UnidadReorderItem {
  id: string
  orden: number
}

export interface UnidadListResponse {
  data: Unidad[]
  meta: { cursor_next: string | null }
}

export async function listUnidades(comisionId: string, getToken?: TokenGetter): Promise<Unidad[]> {
  const r = await fetch(`/api/v1/unidades?comision_id=${comisionId}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  const body = (await r.json()) as UnidadListResponse
  return body.data
}

export async function createUnidad(body: UnidadCreate, getToken?: TokenGetter): Promise<Unidad> {
  const r = await fetch("/api/v1/unidades", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function updateUnidad(
  id: string,
  patch: UnidadUpdate,
  getToken?: TokenGetter,
): Promise<Unidad> {
  const r = await fetch(`/api/v1/unidades/${id}`, {
    method: "PATCH",
    headers: await authHeaders(getToken),
    body: JSON.stringify(patch),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function deleteUnidad(id: string, getToken?: TokenGetter): Promise<void> {
  const r = await fetch(`/api/v1/unidades/${id}`, {
    method: "DELETE",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
}

export async function reorderUnidades(
  comisionId: string,
  order: UnidadReorderItem[],
  getToken?: TokenGetter,
): Promise<Unidad[]> {
  const r = await fetch("/api/v1/unidades/reorder", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify({ comision_id: comisionId, items: order }),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function assignTPToUnidad(
  tpId: string,
  unidadId: string | null,
  getToken?: TokenGetter,
): Promise<TareaPractica> {
  const r = await fetch(`/api/v1/tareas-practicas/${tpId}`, {
    method: "PATCH",
    headers: await authHeaders(getToken),
    body: JSON.stringify({ unidad_id: unidadId }),
  })
  await throwIfNotOk(r)
  return r.json()
}

export const unidadesApi = {
  list: listUnidades,
  create: createUnidad,
  update: updateUnidad,
  delete: deleteUnidad,
  reorder: reorderUnidades,
  assignTP: assignTPToUnidad,
}

// ── ADR-020: Distribución N1-N4 por episodio ─────────────────────────

export type NLevel = "N1" | "N2" | "N3" | "N4" | "meta"

export interface NLevelDistribution {
  episode_id: string
  labeler_version: string
  distribution_seconds: Record<NLevel, number>
  distribution_ratio: Record<NLevel, number>
  total_events_per_level: Record<NLevel, number>
}

export async function getEpisodeNLevelDistribution(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<NLevelDistribution> {
  const r = await fetch(`/api/v1/analytics/episode/${episodeId}/n-level-distribution`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

// ── Clasificación de apropiación del episodio (output del árbol N4) ──
// AppropriationLabel ya esta declarado en la cabecera del archivo (linea 8).

// Subgrupo de apropiacion (capa diagnostica fina sobre el eje oficial).
// Lo calcula el classifier y lo guarda en features['subgrupo'].
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

export interface EpisodeClassification {
  episode_id: string
  comision_id: string
  classifier_config_hash: string
  appropriation: AppropriationLabel
  appropriation_reason: string
  ct_summary: number | null
  ccd_mean: number | null
  ccd_orphan_ratio: number | null
  cii_stability: number | null
  cii_evolution: number | null
  is_current: boolean
  subgrupo: Subgrupo | null
}

export async function getEpisodeClassification(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<EpisodeClassification | null> {
  const r = await fetch(`/api/v1/classifications/${episodeId}`, {
    headers: await authHeaders(getToken),
  })
  if (r.status === 404) return null
  await throwIfNotOk(r)
  return r.json()
}

// ── ADR-018: CII evolution longitudinal por estudiante ───────────────

export interface CIIEvolutionTemplate {
  template_id: string
  n_episodes: number
  scores_ordinal: number[]
  slope: number | null
  insufficient_data: boolean
}

export interface CIIEvolutionUnidad {
  unidad_id: string
  unidad_nombre: string
  n_episodes: number
  scores_ordinal: number[]
  slope: number | null
  insufficient_data: boolean
}

export interface CIIEvolutionLongitudinal {
  student_pseudonym: string
  comision_id: string
  n_groups_evaluated: number
  n_groups_insufficient: number
  n_episodes_total: number
  evolution_per_template: CIIEvolutionTemplate[]
  evolution_per_unidad: CIIEvolutionUnidad[]
  mean_slope: number | null
  sufficient_data: boolean
  labeler_version: string
}

export async function getStudentCIIEvolution(
  studentPseudonym: string,
  comisionId: string,
  getToken?: TokenGetter,
): Promise<CIIEvolutionLongitudinal> {
  const r = await fetch(
    `/api/v1/analytics/student/${studentPseudonym}/cii-evolution-longitudinal?comision_id=${comisionId}`,
    { headers: await authHeaders(getToken) },
  )
  await throwIfNotOk(r)
  return r.json()
}

// ── ADR-019: Eventos adversos por cohorte ─────────────────────────────

export interface AdversarialRecentEvent {
  episode_id: string
  student_pseudonym: string
  ts: string
  category: string
  severity: number
  pattern_id: string
  matched_text: string
}

export interface AdversarialTopStudent {
  student_pseudonym: string
  n_events: number
}

export interface CohortAdversarialEvents {
  comision_id: string
  n_events_total: number
  counts_by_category: Record<string, number>
  counts_by_severity: Record<string, number>
  counts_by_student: Record<string, number>
  top_students_by_n_events: AdversarialTopStudent[]
  recent_events: AdversarialRecentEvent[]
}

export async function getCohortAdversarialEvents(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<CohortAdversarialEvents> {
  const r = await fetch(`/api/v1/analytics/cohort/${comisionId}/adversarial-events`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

// ── Integridad del episodio (foco + clipboard) ────────────────────────

export type IntegrityEventType =
  | "pestana_perdida"
  | "pestana_recuperada"
  | "copia_intentada"
  | "pega_intentada"

export interface IntegrityRecentEvent {
  episode_id: string
  student_pseudonym: string
  ts: string
  event_type: IntegrityEventType
  // Shape específico por event_type — el componente formatea según el tipo.
  payload: {
    trigger?: "visibilitychange" | "blur"
    tiempo_fuera_segundos?: number
    seleccion_chars?: number
    contenido_longitud?: number
    contenido_preview?: string
    metodo?: "shortcut" | "menu_contextual" | "drag_drop"
  }
}

export interface IntegrityTopStudent {
  student_pseudonym: string
  n_events: number
}

export interface CohortIntegrityEvents {
  comision_id: string
  n_events_total: number
  counts_by_type: Record<string, number>
  counts_by_student: Record<string, number>
  top_students_by_n_events: IntegrityTopStudent[]
  recent_events: IntegrityRecentEvent[]
}

export async function getCohortIntegrityEvents(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<CohortIntegrityEvents> {
  const r = await fetch(`/api/v1/analytics/cohort/${comisionId}/integrity-events`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

// ── ADR-022: drill-down navegacional + cuartiles + alertas ────────────

export interface StudentEpisode {
  episode_id: string
  problema_id: string
  /** "closed" | "paused" — paused = abandonado y retomable por el alumno (ADR-055). */
  estado: string
  tarea_codigo: string | null
  tarea_titulo: string | null
  template_id: string | null
  unidad_id: string | null
  unidad_nombre: string | null
  opened_at: string | null
  closed_at: string | null
  events_count: number
  appropriation: AppropriationLabel | null
  classified_at: string | null
}

export interface StudentEpisodesPayload {
  student_pseudonym: string
  comision_id: string
  n_episodes: number
  episodes: StudentEpisode[]
}

export async function getStudentEpisodes(
  studentPseudonym: string,
  comisionId: string,
  getToken?: TokenGetter,
): Promise<StudentEpisodesPayload> {
  const r = await fetch(
    `/api/v1/analytics/student/${studentPseudonym}/episodes?comision_id=${comisionId}`,
    { headers: await authHeaders(getToken) },
  )
  await throwIfNotOk(r)
  return r.json()
}

export interface CohortCIIQuartiles {
  comision_id: string
  labeler_version: string
  min_students_for_quartiles: number
  n_students_evaluated: number
  insufficient_data: boolean
  q1: number | null
  median: number | null
  q3: number | null
  min: number | null
  max: number | null
  mean: number | null
  stdev: number | null
}

export async function getCohortCIIQuartiles(
  comisionId: string,
  getToken?: TokenGetter,
): Promise<CohortCIIQuartiles> {
  const r = await fetch(`/api/v1/analytics/cohort/${comisionId}/cii-quartiles`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export interface CohortAlertsSummaryCounts {
  regresion_vs_cohorte: number
  bottom_quartile: number
  slope_negativo_significativo: number
  students_with_any_alert: number
}

export interface CohortAlertsSummary {
  comision_id: string
  n_students_evaluated: number
  min_students_threshold: number
  insufficient_data: boolean
  alerts_summary: CohortAlertsSummaryCounts | null
  labeler_version: string
}

/**
 * GET /api/v1/analytics/cohort/{id}/alerts-summary (ADR-022).
 *
 * Agregación a nivel cohorte de las 3 alertas pedagógicas (regresion_vs_cohorte,
 * bottom_quartile, slope_negativo_significativo). Privacy gate k-anonymity:
 * `insufficient_data=true` + `alerts_summary=null` cuando N<5 estudiantes
 * tienen mean_slope computable.
 *
 * Consumido por HomeView (KPI "alertas" del card de cohorte) — cierra el TODO
 * histórico (auditoría 2026-05-17).
 */
export async function getCohortAlertsSummary(
  comisionId: string,
  periodoId?: string,
  getToken?: TokenGetter,
): Promise<CohortAlertsSummary> {
  const qs = periodoId ? `?periodo_id=${periodoId}` : ""
  const r = await fetch(`/api/v1/analytics/cohort/${comisionId}/alerts-summary${qs}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export interface StudentAlert {
  code: string
  severity: "low" | "medium" | "high"
  title: string
  detail: string
  threshold_used: string
  z_score: number | null
}

export interface StudentAlertsPayload {
  student_pseudonym: string
  comision_id: string
  labeler_version: string
  student_slope: number | null
  cohort_stats: CohortCIIQuartiles
  quartile: "Q1" | "Q2" | "Q3" | "Q4" | null
  alerts: StudentAlert[]
  n_alerts: number
  highest_severity: "low" | "medium" | "high" | null
}

export async function getStudentAlerts(
  studentPseudonym: string,
  comisionId: string,
  getToken?: TokenGetter,
): Promise<StudentAlertsPayload> {
  const r = await fetch(
    `/api/v1/analytics/student/${studentPseudonym}/alerts?comision_id=${comisionId}`,
    { headers: await authHeaders(getToken) },
  )
  await throwIfNotOk(r)
  return r.json()
}

// ── Audit / CTR episodes (read-only para docentes) ──────────────────
// Bloque "Unidades de Trazabilidad" duplicado eliminado (vivía aquí y en línea 922).
// Las definiciones canónicas viven en el primer bloque; ambas eran idénticas
// salvo `UnidadListResponse` (export vs sin export — el primer bloque exporta).

export interface CTREvent {
  event_type: string
  seq: number
  payload: Record<string, unknown>
  ts: string
}

export interface EpisodeWithEvents {
  id: string
  estado: string
  events: CTREvent[]
}

export async function getEpisodeEvents(
  episodeId: string,
  getToken?: TokenGetter,
): Promise<EpisodeWithEvents> {
  const r = await fetch(`/api/v1/audit/episodes/${episodeId}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export function extractFinalCode(events: CTREvent[]): string | null {
  const codeEvents = events.filter((e) => e.event_type === "edicion_codigo")
  if (codeEvents.length === 0) return null
  const last = codeEvents[codeEvents.length - 1]
  return (last?.payload?.snapshot as string) ?? null
}

// ── Entregas y Calificaciones (tp-entregas-correccion) ────────────────

export type EntregaEstado = "draft" | "submitted" | "graded" | "returned"

export interface EjercicioEstado {
  orden: number
  completado: boolean
  episode_id: string | null
  completado_at: string | null
}

export interface EntregaDocente {
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

export interface EntregaListResponse {
  data: EntregaDocente[]
  meta: { cursor_next: string | null }
}

export interface CalificacionCriterio {
  nombre: string
  puntaje: number
  peso: number
  comentario: string | null
}

export interface CalificacionCreate {
  nota_final: number
  feedback_general: string
  detalle_criterios?: CalificacionCriterio[]
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

export async function listEntregas(
  params: {
    comision_id: string
    estado?: EntregaEstado
    tarea_practica_id?: string
    cursor?: string
    limit?: number
  },
  getToken?: TokenGetter,
): Promise<EntregaListResponse> {
  const qs = new URLSearchParams({ comision_id: params.comision_id })
  if (params.estado) qs.set("estado", params.estado)
  if (params.tarea_practica_id) qs.set("tarea_practica_id", params.tarea_practica_id)
  if (params.cursor) qs.set("cursor", params.cursor)
  if (params.limit) qs.set("limit", String(params.limit))
  const r = await fetch(`/api/v1/entregas?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  // Backend devuelve envelope `{data, meta}` (commit c8a4685, fix bug R1 v1.0).
  // Antes este parser asumía bare array → bug "data.map is not a function".
  const body = (await r.json()) as {
    data: EntregaDocente[]
    meta: { cursor_next: string | null; total?: number | null; limit?: number | null }
  }
  return { data: body.data, meta: body.meta }
}

export async function getEntrega(id: string, getToken?: TokenGetter): Promise<EntregaDocente> {
  const r = await fetch(`/api/v1/entregas/${id}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function calificarEntrega(
  entregaId: string,
  body: CalificacionCreate,
  getToken?: TokenGetter,
): Promise<Calificacion> {
  const r = await fetch(`/api/v1/entregas/${entregaId}/calificar`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function devolverEntrega(
  entregaId: string,
  getToken?: TokenGetter,
): Promise<EntregaDocente> {
  const r = await fetch(`/api/v1/entregas/${entregaId}/return`, {
    method: "POST",
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function getCalificacion(
  entregaId: string,
  getToken?: TokenGetter,
): Promise<Calificacion | null> {
  const r = await fetch(`/api/v1/entregas/${entregaId}/calificacion`, {
    headers: await authHeaders(getToken),
  })
  if (r.status === 404) return null
  await throwIfNotOk(r)
  return r.json()
}

export const entregasDocenteApi = {
  list: listEntregas,
  get: getEntrega,
  calificar: calificarEntrega,
  devolver: devolverEntrega,
  getCalificacion,
}

// ── TP Generation con IA: ver bloque ADR-036 al inicio del archivo (línea 477) ──
// El bloque que vivía aquí era duplicado con drift de tipos (test_cases:
// TestCaseGenerado vs TestCaseIA, materia_id nullable vs not-null,
// GenerateTPResponse con tokens_used vs sin él). Eliminado en el rediseño v2;
// el contrato canónico (que matchea con el response real verificado en QA pass)
// es el de la línea 481 — `materia_id: string`, `test_cases: TestCaseIA[]`,
// `GenerateTPResponse` con `model_used`, `provider_used`, `rag_chunks_hash`.

// ── Ejercicios reusables (ADR-047 + ADR-048) ─────────────────────────

// Texto libre: cada materia define sus unidades (no es una taxonomia fija).
export type UnidadTematica = string
export type Dificultad = "basica" | "intermedia" | "avanzada"

export interface PreguntaSocratica {
  texto: string
  senal_comprension: string
  senal_alerta: string
}

export interface BancoPreguntas {
  n1: PreguntaSocratica[]
  n2: PreguntaSocratica[]
  n3: PreguntaSocratica[]
  n4: PreguntaSocratica[]
}

export interface Misconception {
  descripcion: string
  probabilidad_estimada: number
  pregunta_diagnostica: string
}

export interface Pista {
  nivel: 1 | 2 | 3 | 4
  pista: string
}

export interface HeuristicaCierre {
  tests_min_pasados: number
  heuristica: string
}

export interface AntiPatron {
  patron: string
  descripcion: string
  mensaje_orientacion: string
}

export interface Prerequisitos {
  sintacticos: string[]
  conceptuales: string[]
}

export interface TutorRules {
  prohibido_dar_solucion: boolean
  forzar_pregunta_antes_de_hint: boolean
  nivel_socratico_minimo: 1 | 2 | 3 | 4
  instrucciones_adicionales: string | null
}

export interface CriterioRubrica {
  nombre: string
  descripcion: string
  puntaje_max: string // Decimal serializado
}

export interface RubricaEjercicio {
  criterios: CriterioRubrica[]
}

export interface TestCaseEjercicio {
  id: string
  name: string
  type: "stdin_stdout" | "pytest_assert"
  code: string
  expected: string | null
  is_public: boolean
  weight: number
}

export interface Ejercicio {
  id: string
  tenant_id: string
  titulo: string
  enunciado_md: string
  inicial_codigo: string | null
  materia_id: string | null
  unidad_tematica: UnidadTematica
  dificultad: Dificultad | null
  prerequisitos: Prerequisitos
  test_cases: TestCaseEjercicio[]
  rubrica: RubricaEjercicio | null
  tutor_rules: TutorRules | null
  banco_preguntas: BancoPreguntas | null
  misconceptions: Misconception[]
  respuesta_pista: Pista[]
  heuristica_cierre: HeuristicaCierre | null
  anti_patrones: AntiPatron[]
  created_by: string
  created_via_ai: boolean
  created_at: string
  deleted_at: string | null
}

export interface EjercicioCreate {
  titulo: string
  enunciado_md: string
  inicial_codigo?: string | null
  materia_id?: string | null
  unidad_tematica: UnidadTematica
  dificultad?: Dificultad | null
  prerequisitos?: Prerequisitos
  test_cases?: TestCaseEjercicio[]
  rubrica?: RubricaEjercicio | null
  tutor_rules?: TutorRules | null
  banco_preguntas?: BancoPreguntas | null
  misconceptions?: Misconception[]
  respuesta_pista?: Pista[]
  heuristica_cierre?: HeuristicaCierre | null
  anti_patrones?: AntiPatron[]
  created_via_ai?: boolean
}

export type EjercicioUpdate = Partial<EjercicioCreate>

export interface EjercicioListResponse {
  data: Ejercicio[]
  meta: { cursor_next: string | null }
}

export async function listEjercicios(
  params: {
    materia_id?: string
    unidad_tematica?: UnidadTematica
    dificultad?: Dificultad
    created_by?: string
    created_via_ai?: boolean
    cursor?: string
    limit?: number
  } = {},
  getToken?: TokenGetter,
): Promise<EjercicioListResponse> {
  const qs = new URLSearchParams()
  if (params.materia_id) qs.set("materia_id", params.materia_id)
  if (params.unidad_tematica) qs.set("unidad_tematica", params.unidad_tematica)
  if (params.dificultad) qs.set("dificultad", params.dificultad)
  if (params.created_by) qs.set("created_by", params.created_by)
  if (params.created_via_ai !== undefined) qs.set("created_via_ai", String(params.created_via_ai))
  if (params.cursor) qs.set("cursor", params.cursor)
  if (params.limit) qs.set("limit", String(params.limit))
  const r = await fetch(`/api/v1/ejercicios?${qs.toString()}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function getEjercicio(id: string, getToken?: TokenGetter): Promise<Ejercicio> {
  const r = await fetch(`/api/v1/ejercicios/${id}`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function createEjercicio(
  body: EjercicioCreate,
  getToken?: TokenGetter,
): Promise<Ejercicio> {
  const r = await fetch("/api/v1/ejercicios", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function updateEjercicio(
  id: string,
  body: EjercicioUpdate,
  getToken?: TokenGetter,
): Promise<Ejercicio> {
  const r = await fetch(`/api/v1/ejercicios/${id}`, {
    method: "PATCH",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function deleteEjercicio(id: string, getToken?: TokenGetter): Promise<void> {
  const r = await fetch(`/api/v1/ejercicios/${id}`, {
    method: "DELETE",
    headers: await authHeaders(getToken),
  })
  if (r.status !== 204) await throwIfNotOk(r)
}

// ── Wizard IA standalone (POST /api/v1/ejercicios/generate) ──────────

export interface EjercicioGenerateRequest {
  // materia_id es opcional: si esta vacio, el backend resuelve la primera
  // del tenant (modo demo / piloto). Ver ADR-047.
  materia_id?: string
  descripcion_nl: string
  unidad_tematica: UnidadTematica
  dificultad?: Dificultad
  contexto?: string
  comision_id?: string
}

export interface EjercicioGenerateResponse {
  borrador: EjercicioCreate
  prompt_version: string
  model_used: string
  provider_used: string
  tokens_input: number
  tokens_output: number
  rag_chunks_used: number
  rag_chunks_hash: string | null
}

export async function generateEjercicioWithAI(
  body: EjercicioGenerateRequest,
  getToken?: TokenGetter,
): Promise<EjercicioGenerateResponse> {
  const r = await fetch("/api/v1/ejercicios/generate", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

// ── Composición TP ↔ Ejercicio (tabla intermedia tp_ejercicios) ──────

export interface TpEjercicio {
  id: string
  tarea_practica_id: string
  ejercicio_id: string
  orden: number
  peso_en_tp: string // Decimal serializado
  ejercicio: Ejercicio
}

export interface TpEjercicioCreate {
  ejercicio_id: string
  orden: number
  peso_en_tp: string
}

export interface TpEjercicioUpdate {
  orden?: number
  peso_en_tp?: string
}

export async function listTpEjercicios(
  tareaPracticaId: string,
  getToken?: TokenGetter,
): Promise<TpEjercicio[]> {
  const r = await fetch(`/api/v1/tareas-practicas/${tareaPracticaId}/ejercicios`, {
    headers: await authHeaders(getToken),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function addEjercicioToTp(
  tareaPracticaId: string,
  body: TpEjercicioCreate,
  getToken?: TokenGetter,
): Promise<TpEjercicio> {
  const r = await fetch(`/api/v1/tareas-practicas/${tareaPracticaId}/ejercicios`, {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function updateTpEjercicioPair(
  tareaPracticaId: string,
  ejercicioId: string,
  body: TpEjercicioUpdate,
  getToken?: TokenGetter,
): Promise<TpEjercicio> {
  const r = await fetch(`/api/v1/tareas-practicas/${tareaPracticaId}/ejercicios/${ejercicioId}`, {
    method: "PATCH",
    headers: await authHeaders(getToken),
    body: JSON.stringify(body),
  })
  await throwIfNotOk(r)
  return r.json()
}

export async function removeEjercicioFromTp(
  tareaPracticaId: string,
  ejercicioId: string,
  getToken?: TokenGetter,
): Promise<void> {
  const r = await fetch(`/api/v1/tareas-practicas/${tareaPracticaId}/ejercicios/${ejercicioId}`, {
    method: "DELETE",
    headers: await authHeaders(getToken),
  })
  if (r.status !== 204) await throwIfNotOk(r)
}

export const ejerciciosApi = {
  list: listEjercicios,
  get: getEjercicio,
  create: createEjercicio,
  update: updateEjercicio,
  delete: deleteEjercicio,
  generate: generateEjercicioWithAI,
}

export const tpEjerciciosApi = {
  list: listTpEjercicios,
  add: addEjercicioToTp,
  updatePair: updateTpEjercicioPair,
  remove: removeEjercicioFromTp,
}

// ============================================================================
// INSTRUMENTOS COHORT SUMMARY (ADR-053)
// P2-1/2/3 del PlanMejora.md. Lectura agregada por cohorte con k-anonymity gate.
// ============================================================================

export interface InstrumentoSummary {
  insufficient_data?: boolean
  n_responses?: number
  k_anonymity_threshold: number
  message?: string
  instrument_version?: string
  by_item_distribution_status?: string
  avg_total_score?: number | null
  subscale_aggregation_status?: string
}

export interface TransferenciaSummary {
  instrument_version: string
  k_anonymity_threshold: number
  by_group: Record<
    string,
    {
      insufficient_data?: boolean
      n_students: number
      k_anonymity_threshold?: number
      n_attempts?: number
      n_correct?: number
      accuracy?: number
    }
  >
}

export async function getCuestionarioIASummary(
  comisionId: string,
  instrumentVersion = "cuestionario-ia-v0.1.0-draft",
  getToken?: TokenGetter,
): Promise<InstrumentoSummary> {
  const params = new URLSearchParams({ instrument_version: instrumentVersion })
  const r = await fetch(`/api/v1/instrumentos/cuestionario-ia/${comisionId}/summary?${params}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get cuestionario-ia summary failed: ${r.status}`)
  return r.json()
}

export async function getPretestSummary(
  comisionId: string,
  instrumentVersion = "lishinski-2016-es-utn-v0.1.0-draft",
  getToken?: TokenGetter,
): Promise<InstrumentoSummary> {
  const params = new URLSearchParams({ instrument_version: instrumentVersion })
  const r = await fetch(
    `/api/v1/instrumentos/pretest-autoeficacia/${comisionId}/summary?${params}`,
    { headers: await authHeaders(getToken) },
  )
  if (!r.ok) throw new Error(`get pretest summary failed: ${r.status}`)
  return r.json()
}

export async function getTransferenciaSummary(
  comisionId: string,
  instrumentVersion = "transfer-test-v0.1.0-draft",
  getToken?: TokenGetter,
): Promise<TransferenciaSummary> {
  const params = new URLSearchParams({ instrument_version: instrumentVersion })
  const r = await fetch(`/api/v1/instrumentos/transferencia/${comisionId}/summary?${params}`, {
    headers: await authHeaders(getToken),
  })
  if (!r.ok) throw new Error(`get transferencia summary failed: ${r.status}`)
  return r.json()
}

export const instrumentosSummaryApi = {
  cuestionarioIA: getCuestionarioIASummary,
  pretest: getPretestSummary,
  transferencia: getTransferenciaSummary,
}
