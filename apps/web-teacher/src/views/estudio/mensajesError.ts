// Mensajes de error del estudio de codificacion, por codigo de negocio (design
// D9, D10, D14). Formas REALES del backend (classifier-service, routes/estudio*.py):
//   - 409: `detail` string con el codigo;
//   - 422 (y 400 de `pedido_invalido`): `detail: {codigo, errores?: string[]}`;
//   - 400 del esquema del codebook: `detail: {mensaje, errores: string[]}`.
// Lo que no tiene codigo conocido se muestra con `formatApiError`, que nunca
// devuelve "[object Object]". Un `detail` objeto nunca se muestra como JSON.

import { codigoDeError, statusDeError } from "../../lib/estudioApi"
import { formatApiError } from "../../utils/errorApi"

const POR_CODIGO: Record<string, string> = {
  enunciados_pendientes:
    "Faltan consignas por cargar o revisar en el estudio. La codificación queda bloqueada hasta que el investigador las complete.",
  codebook_borrador:
    "El codebook vigente todavía es un borrador. Se puede codificar cuando el investigador lo congele.",
  codificacion_cerrada: "Tu codificación está cerrada: ya no se pueden guardar cambios.",
  enunciado_revisado: "Ese enunciado ya fue revisado y no se puede reemplazar con otro texto.",
  episodio_es_ancla:
    "Uno de los episodios es ancla de entrenamiento del estudio: no puede ir en la muestra.",
  episodio_en_muestra: "Ese episodio ya está en la muestra del estudio: no puede ser ancla.",
  muestra_con_etiquetas: "Ya hay etiquetas del estudio: la muestra no se puede reemplazar.",
  version_congelada: "Esa versión está congelada: no se puede editar ni cambiar sus anclas.",
  ancla_con_respuestas: "Esa ancla ya tiene respuestas de entrenamiento: no se puede borrar.",
  sha256_distinto: "El sha256 del archivo no coincide con el esperado. No se cargó nada.",
  csv_invalido: "El archivo CSV no es válido. No se cargó nada.",
  episodios_invalidos: "Hay episodios que no se pueden usar. No se cargó nada.",
  pedido_invalido: "La respuesta no es válida para el esquema del codebook.",
  episodio_inexistente: "Ese episodio no existe en el registro de episodios.",
  episodio_no_terminado: "Ese episodio no está terminado (cerrado o abandonado).",
  sin_muestra:
    "La muestra del estudio todavía no se cargó: no hay ítems para codificar ni nada que cerrar.",
  anclas_invalidas:
    "Hay anclas que no valen contra el esquema de la versión: corregilas o borralas antes de congelar.",
}

/** `errores: string[]` del detail, si vienen. */
function erroresDe(e: unknown): string[] {
  if (!e || typeof e !== "object") return []
  const detail = (e as { detail?: unknown }).detail
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return []
  const errores = (detail as { errores?: unknown }).errores
  return Array.isArray(errores) ? errores.filter((x): x is string => typeof x === "string") : []
}

function mensajeDelDetail(e: unknown): string | null {
  if (!e || typeof e !== "object") return null
  const detail = (e as { detail?: unknown }).detail
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null
  const mensaje = (detail as { mensaje?: unknown }).mensaje
  return typeof mensaje === "string" ? mensaje : null
}

function conErrores(base: string, errores: string[]): string {
  return errores.length > 0 ? `${base} ${errores.join("; ")}` : base
}

export function mensajeDeErrorEstudio(e: unknown): string {
  const errores = erroresDe(e)
  const codigo = codigoDeError(e)
  if (codigo && POR_CODIGO[codigo]) return conErrores(POR_CODIGO[codigo], errores)
  const mensaje = mensajeDelDetail(e)
  if (mensaje) return conErrores(`${mensaje}.`, errores)
  const status = statusDeError(e)
  if (status === 403) return "No tenés acceso a este estudio con tu cuenta."
  if (status === 502 || status === 503 || status === 504) {
    return "El servicio del estudio no respondió. Probá de nuevo en unos minutos."
  }
  if (errores.length > 0) return conErrores("No se pudo completar la operación:", errores)
  return formatApiError(e)
}
