/**
 * Cliente del estudio de codificacion ciega (change `cibse-codificacion-ciega`).
 *
 * Endpoints de classifier-service bajo `/api/v1/interrater/estudios/*` (design
 * D3 a D14). El gateway ya enruta ese prefijo; no hay nada que registrar.
 *
 * Reglas que este modulo respeta y que las vistas dan por sentadas:
 *   - El panel NUNCA calcula el regimen: lo deriva el servidor con la regla del
 *     esquema y lo devuelve en cada guardado (D9). Aca solo se transporta.
 *   - Muestra y enunciados viajan como TEXTO CRUDO del archivo. El servidor
 *     calcula el sha256 sobre esos bytes (D6, D14); parsear o normalizar aca
 *     cambiaria el hash.
 *   - Los errores salen por `throwIfNotOk` con `status` y `detail`, para que la
 *     vista decida por codigo (`evidencia_alterada`, `enunciados_pendientes`...).
 *   - El email de una revocacion va en el cuerpo, no en la URL: las URLs quedan
 *     en logs de acceso y el estudio no loguea emails (D3).
 */
import { type TokenGetter, authHeaders, throwIfNotOk } from "./api"

export type { TokenGetter }

const BASE = "/api/v1/interrater/estudios"

const seg = encodeURIComponent

// ── Tipos del contrato ────────────────────────────────────────────────

export type RolEstudio = "investigador" | "codificador"

export interface Membresia {
  clave: string
  titulo: string
  rol: RolEstudio
  /** La codificacion propia ya se cerro (D10). */
  cerrada: boolean
}

/** Fila de `GET /{clave}/membresias` (pantalla del investigador). */
export interface MembresiaGestion {
  membresia_id: string
  email: string
  rol: RolEstudio
  alias: string
  estado: "activa" | "cerrada" | "revocada"
  atada: boolean
  created_at: string
  cerrada_at: string | null
  revocada_at: string | null
}

export interface Estudio {
  clave: string
  titulo: string
  traza_version: string
}

export interface DimensionEsquema {
  clave: string
  nombre: string
  valores: string[]
  /** Valores de esta dimension que exigen cita al cerrar. */
  cita_requerida_si: string[]
}

export interface RegimenEsquema {
  clave: string
  nombre: string
}

export interface AtomoRegla {
  dimension: string
  en: string[]
  con_cita?: boolean
}

export interface ReglaRegimen {
  regimen: string
  /** Conjuncion de clausulas; cada clausula es una disyuncion de atomos (D9). */
  condicion: AtomoRegla[][]
}

/** Esquema del formulario de una version del codebook (meta-esquema de D9). */
export interface EsquemaFormulario {
  dimensiones: DimensionEsquema[]
  regimenes: RegimenEsquema[]
  regimen_evidencia_insuficiente: string
  dimensiones_opcionales_si_regimen: string[]
  notas_obligatorias_si_regimen: string[]
  marca_frontera: boolean
  notas_obligatorias_si_frontera: boolean
  confianza: { valores: string[]; obligatoria: boolean } | null
  reglas_regimen: ReglaRegimen[]
  regimen_por_defecto: string | null
  regimenes_exentos: string[]
}

/**
 * El backend guarda el esquema TAL COMO SE CARGO, y en el meta-esquema
 * (`services/estudio_esquema.py`) solo `dimensiones`, `regimenes` y
 * `regimen_evidencia_insuficiente` son obligatorias. Aca se completan los
 * defaults del backend para que las vistas no lean `undefined`:
 * `regimenes_exentos` = [evidencia insuficiente], listas vacias, `false`,
 * `confianza: null`, sin reglas (el codificador elige) y sin regimen por defecto.
 */
export function normalizarEsquema(crudo: unknown): EsquemaFormulario | null {
  if (crudo === null || crudo === undefined || typeof crudo !== "object") return null
  const e = crudo as Partial<EsquemaFormulario> &
    Pick<EsquemaFormulario, "dimensiones" | "regimenes" | "regimen_evidencia_insuficiente">
  return {
    ...e,
    regimenes_exentos: e.regimenes_exentos ?? [e.regimen_evidencia_insuficiente],
    dimensiones_opcionales_si_regimen: e.dimensiones_opcionales_si_regimen ?? [],
    notas_obligatorias_si_regimen: e.notas_obligatorias_si_regimen ?? [],
    marca_frontera: e.marca_frontera ?? false,
    notas_obligatorias_si_frontera: e.notas_obligatorias_si_frontera ?? false,
    confianza: e.confianza ?? null,
    reglas_regimen: e.reglas_regimen ?? [],
    regimen_por_defecto: e.regimen_por_defecto ?? null,
  }
}

function conEsquemaNormalizado(v: CodebookVersion): CodebookVersion {
  return { ...v, esquema: normalizarEsquema(v.esquema) }
}

export type EstadoVersion = "borrador" | "congelada"

export interface CodebookVersion {
  etiqueta: string
  estado: EstadoVersion
  contenido_md: string
  esquema: EsquemaFormulario | null
  /** Solo en congeladas. */
  contenido_sha256: string | null
}

/** Ancla que dejo de valer contra el esquema guardado del borrador (verify-1, F1). */
export interface AnclaInvalida {
  item_id: string
  uso: UsoAncla
  orden: number
  motivos: string[]
}

/** Respuesta del PUT del borrador: avisa las anclas invalidas; congelar las rechaza. */
export type VersionEditada = CodebookVersion & { anclas_invalidas?: AnclaInvalida[] }

export interface VersionResumen {
  etiqueta: string
  estado: EstadoVersion
  contenido_sha256: string | null
  congelada_at: string | null
  vigente: boolean
}

export interface RespuestaDimension {
  valor: string | null
  cita: string | null
}

/** Lo que manda el codificador (etiqueta, practica o respuesta esperada). */
export interface RespuestaFormulario {
  respuestas: Record<string, RespuestaDimension>
  /** Solo regimen exento o esquema sin regla; con regla va null y lo deriva el servidor. */
  regimen: string | null
  regimen_propuesto: string | null
  es_frontera: boolean
  confianza: string | null
  /** El backend persiste `null` cuando no hay notas. */
  notas: string | null
}

/** Lo que devuelve el servidor tras guardar o al leer la etiqueta propia. */
export interface EtiquetaGuardada extends RespuestaFormulario {
  /** Lo que da la regla sobre las dimensiones, aun con regimen exento (R3-1). */
  regimen_regla: string | null
  /** Derivado por el backend: `regimen_propuesto` no nulo y distinto de `regimen`. */
  disiente_de_regla?: boolean
  updated_at: string | null
}

export type EstadoItem = "sin_empezar" | "parcial" | "completa"

export interface ItemCodificador {
  item_id: string
  posicion: number
  estado: EstadoItem
}

/** Traza ciega (D4, D14). Contrato `traza_v1`. */
export type TipoElementoTraza =
  | "inicio"
  | "lectura"
  | "mensaje_alumno"
  | "respuesta_tutor"
  | "codigo"
  | "ejecucion"
  | "prueba"
  | "nota"
  | "copia"
  | "pegado"
  | "fin_cerrado"
  | "fin_abandonado"

export interface ElementoTraza {
  /** Localizador global contiguo desde 1. */
  n: number
  tipo: TipoElementoTraza
  /** Segundos desde el inicio del episodio. */
  t_seg: number
  /** Localizador por tipo (turno k, codigo k, ejecucion k...). null si el tipo no lleva. */
  k: number | null
  /** Campos permitidos por la lista blanca para el tipo. */
  datos: Record<string, unknown>
}

export interface TrazaCiega {
  traza_version: string
  enunciado: { tp_md: string; ejercicio_md: string | null }
  elementos: ElementoTraza[]
}

export interface FaltanteEnunciado {
  tipo: "tp" | "ejercicio"
  id: string
  items_afectados: number
}

export interface Cobertura {
  requeridos: number
  cargados: number
  revisados: number
  faltantes: FaltanteEnunciado[]
  /** Cargados pero sin revisar: tambien bloquean la codificacion (D14). */
  sin_revisar: FaltanteEnunciado[]
}

export interface Enunciado {
  id: string
  tipo: "tp" | "ejercicio"
  fuente_id: string
  contenido_original_md: string
  sha256_original: string
  contenido_mostrado_md: string | null
  sha256_mostrado: string | null
  alertas: string[]
  revisado: boolean
}

export interface EstadoEnunciados {
  cobertura: Cobertura
  enunciados: Enunciado[]
}

export interface ResultadoCargaEnunciados {
  cobertura: Cobertura | null
  ignoradas: { tipo: string; id: string }[]
}

export interface ResultadoMuestra {
  items: number
  sha256: string
}

export type UsoAncla = "ejemplo" | "practica"

export interface AnclaNueva {
  episode_id: string
  uso: UsoAncla
  orden: number
  respuesta_esperada: RespuestaFormulario
  explicacion_md: string
  consensuado_por: string
}

export interface Ancla extends AnclaNueva {
  item_id: string
  /** Enunciados cargados y revisados: solo entonces se ve en el entrenamiento (D14). */
  enunciados_listos: boolean
}

/** Respuesta del alta o la edicion de un ancla: `faltantes` (codigos de
 * `faltantes_cierre`) no vacio = incompleta; se guarda, pero congelar la
 * rechaza (verify-2, O1). */
export type AnclaGuardada = Ancla & { faltantes?: string[] }

export interface ProgresoCodificador {
  alias: string
  completos: number
  parciales: number
  con_regimen_propuesto: number
  cerrada: boolean
  revocada: boolean
}

export interface EjemploEntrenamiento {
  item_id: string
  orden: number
  respuesta_esperada: RespuestaFormulario
  explicacion_md: string
}

export interface PracticaEntrenamiento {
  item_id: string
  orden: number
}

export interface Entrenamiento {
  codebook: CodebookVersion | null
  ejemplos: EjemploEntrenamiento[]
  practicas: PracticaEntrenamiento[]
}

export interface DevolucionPractica {
  regimen: string | null
  regimen_regla: string | null
  regimen_propuesto: string | null
  esperada: RespuestaFormulario
  explicacion_md: string
  /** Del servidor: regimen derivado no nulo e igual al esperado. */
  coincide: boolean
}

export type ContenidoExportacion = "etiquetas" | "entrenamiento" | "historial"
export type FormatoExportacion = "csv" | "json"

// ── Errores ───────────────────────────────────────────────────────────

/**
 * Codigo de negocio de un error del estudio. El servidor puede mandar el
 * `detail` como string (`"enunciado_pendiente"`) o como objeto con `codigo`.
 */
export function codigoDeError(e: unknown): string | null {
  if (!e || typeof e !== "object") return null
  const detail = (e as { detail?: unknown }).detail
  if (typeof detail === "string") return detail
  if (detail && typeof detail === "object") {
    const codigo = (detail as { codigo?: unknown }).codigo
    if (typeof codigo === "string") return codigo
  }
  return null
}

export function statusDeError(e: unknown): number | null {
  if (!e || typeof e !== "object") return null
  const status = (e as { status?: unknown }).status
  return typeof status === "number" ? status : null
}

// ── Transporte ────────────────────────────────────────────────────────

async function pedir<T>(
  ruta: string,
  getToken: TokenGetter | undefined,
  init: { method?: string; json?: unknown } = {},
): Promise<T> {
  const r = await fetch(ruta, {
    method: init.method ?? "GET",
    headers: await authHeaders(getToken),
    ...(init.json !== undefined ? { body: JSON.stringify(init.json) } : {}),
  })
  await throwIfNotOk(r)
  if (r.status === 204) return undefined as T
  return (await r.json()) as T
}

/**
 * Sube un archivo CRUDO. Con un `Blob`/`File` viajan los bytes exactos del archivo:
 * decodificarlo a texto en el navegador puede quitar un BOM o cambiar saltos de
 * linea, y el sha256 que calcula el servidor dejaria de coincidir con el esperado.
 */
async function subirTexto<T>(
  ruta: string,
  texto: string | Blob,
  getToken: TokenGetter | undefined,
): Promise<T> {
  const headers = await authHeaders(getToken)
  headers["Content-Type"] = "text/csv"
  const r = await fetch(ruta, { method: "POST", headers, body: texto })
  await throwIfNotOk(r)
  return (await r.json()) as T
}

const e = (clave: string) => `${BASE}/${seg(clave)}`

// ── API ───────────────────────────────────────────────────────────────

export const estudioApi = {
  misMembresias: (getToken?: TokenGetter) => pedir<Membresia[]>(`${BASE}/mis-membresias`, getToken),

  crearEstudio: (body: { clave: string; titulo: string }, getToken?: TokenGetter) =>
    pedir<Estudio>(BASE, getToken, { method: "POST", json: body }),

  asignarMembresia: (
    clave: string,
    body: { email: string; rol: RolEstudio },
    getToken?: TokenGetter,
  ) => pedir<unknown>(`${e(clave)}/membresias`, getToken, { method: "POST", json: body }),

  /** Investigador o administrador. Incluye email: es la pantalla de gestion. */
  listarMembresias: (clave: string, getToken?: TokenGetter) =>
    pedir<MembresiaGestion[]>(`${e(clave)}/membresias`, getToken),

  /** Por id y sin cuerpo: el email no viaja en la URL ni en un DELETE con cuerpo (D3). */
  revocarMembresia: (clave: string, membresiaId: string, getToken?: TokenGetter) =>
    pedir<unknown>(`${e(clave)}/membresias/${seg(membresiaId)}`, getToken, { method: "DELETE" }),

  listarVersiones: (clave: string, getToken?: TokenGetter) =>
    pedir<VersionResumen[]>(`${e(clave)}/codebook/versiones`, getToken),

  crearVersion: (
    clave: string,
    body: { etiqueta: string; clonar_de: string | null },
    getToken?: TokenGetter,
  ) => pedir<CodebookVersion>(`${e(clave)}/codebook`, getToken, { method: "POST", json: body }),

  editarVersion: (
    clave: string,
    etiqueta: string,
    body: { contenido_md: string; esquema: unknown },
    getToken?: TokenGetter,
  ) =>
    pedir<VersionEditada>(`${e(clave)}/codebook/${seg(etiqueta)}`, getToken, {
      method: "PUT",
      json: body,
    }),

  congelarVersion: (clave: string, etiqueta: string, getToken?: TokenGetter) =>
    pedir<CodebookVersion>(`${e(clave)}/codebook/${seg(etiqueta)}/congelar`, getToken, {
      method: "POST",
    }),

  fijarVigente: (clave: string, etiqueta: string, getToken?: TokenGetter) =>
    pedir<unknown>(`${e(clave)}/codebook-vigente`, getToken, { method: "PUT", json: { etiqueta } }),

  codebookVigente: async (clave: string, getToken?: TokenGetter) =>
    conEsquemaNormalizado(await pedir<CodebookVersion>(`${e(clave)}/codebook/vigente`, getToken)),

  traza: (clave: string, itemId: string, getToken?: TokenGetter) =>
    pedir<TrazaCiega>(`${e(clave)}/items/${seg(itemId)}/traza`, getToken),

  misItems: (clave: string, getToken?: TokenGetter) =>
    pedir<ItemCodificador[]>(`${e(clave)}/items`, getToken),

  cargarMuestra: (
    clave: string,
    textoCrudo: string | Blob,
    sha256Esperado: string | null,
    getToken?: TokenGetter,
  ) => {
    const qs = sha256Esperado ? `?sha256_esperado=${seg(sha256Esperado)}` : ""
    return subirTexto<ResultadoMuestra>(`${e(clave)}/muestra${qs}`, textoCrudo, getToken)
  },

  cargarEnunciados: (clave: string, textoCrudo: string | Blob, getToken?: TokenGetter) =>
    subirTexto<ResultadoCargaEnunciados>(`${e(clave)}/enunciados`, textoCrudo, getToken),

  enunciados: (clave: string, getToken?: TokenGetter) =>
    pedir<EstadoEnunciados>(`${e(clave)}/enunciados`, getToken),

  /** `contenido_mostrado_md: null` aprueba el original tal cual. */
  revisarEnunciado: (
    clave: string,
    enunciadoId: string,
    body: { contenido_mostrado_md: string | null },
    getToken?: TokenGetter,
  ) =>
    pedir<Enunciado>(`${e(clave)}/enunciados/${seg(enunciadoId)}/revision`, getToken, {
      method: "POST",
      json: body,
    }),

  anclas: (clave: string, etiqueta: string, getToken?: TokenGetter) =>
    pedir<Ancla[]>(`${e(clave)}/codebook/${seg(etiqueta)}/anclas`, getToken),

  crearAncla: (clave: string, etiqueta: string, body: AnclaNueva, getToken?: TokenGetter) =>
    pedir<AnclaGuardada>(`${e(clave)}/codebook/${seg(etiqueta)}/anclas`, getToken, {
      method: "POST",
      json: body,
    }),

  /** Solo en borrador; manda solo los campos que cambian. */
  editarAncla: (
    clave: string,
    etiqueta: string,
    itemId: string,
    cambios: Partial<AnclaNueva>,
    getToken?: TokenGetter,
  ) =>
    pedir<AnclaGuardada>(`${e(clave)}/codebook/${seg(etiqueta)}/anclas/${seg(itemId)}`, getToken, {
      method: "PUT",
      json: cambios,
    }),

  borrarAncla: (clave: string, etiqueta: string, itemId: string, getToken?: TokenGetter) =>
    pedir<unknown>(`${e(clave)}/codebook/${seg(etiqueta)}/anclas/${seg(itemId)}`, getToken, {
      method: "DELETE",
    }),

  miEtiqueta: (clave: string, itemId: string, getToken?: TokenGetter) =>
    pedir<EtiquetaGuardada>(`${e(clave)}/items/${seg(itemId)}/mi-etiqueta`, getToken),

  guardarMiEtiqueta: (
    clave: string,
    itemId: string,
    body: RespuestaFormulario,
    getToken?: TokenGetter,
  ) =>
    pedir<EtiquetaGuardada>(`${e(clave)}/items/${seg(itemId)}/mi-etiqueta`, getToken, {
      method: "PUT",
      json: body,
    }),

  cerrarMiCodificacion: (clave: string, getToken?: TokenGetter) =>
    pedir<unknown>(`${e(clave)}/mi-codificacion/cerrar`, getToken, { method: "POST" }),

  progreso: (clave: string, getToken?: TokenGetter) =>
    pedir<ProgresoCodificador[]>(`${e(clave)}/progreso`, getToken),

  entrenamiento: async (clave: string, getToken?: TokenGetter): Promise<Entrenamiento> => {
    const en = await pedir<Entrenamiento>(`${e(clave)}/entrenamiento`, getToken)
    return { ...en, codebook: en.codebook ? conEsquemaNormalizado(en.codebook) : null }
  },

  responderPractica: (
    clave: string,
    itemId: string,
    body: RespuestaFormulario,
    getToken?: TokenGetter,
  ) =>
    pedir<DevolucionPractica>(`${e(clave)}/entrenamiento/${seg(itemId)}/respuesta`, getToken, {
      method: "POST",
      json: body,
    }),

  /** Devuelve el cuerpo tal cual (CSV o JSON como texto) para descargarlo. */
  exportar: async (
    clave: string,
    contenido: ContenidoExportacion,
    formato: FormatoExportacion,
    getToken?: TokenGetter,
  ): Promise<string> => {
    const r = await fetch(`${e(clave)}/exportacion?contenido=${contenido}&formato=${formato}`, {
      headers: await authHeaders(getToken),
    })
    await throwIfNotOk(r)
    return r.text()
  },
}
