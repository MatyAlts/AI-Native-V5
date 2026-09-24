// BUG-18: traduce errores de API a un mensaje legible. Antes el catch del
// form de TP hacia `setFormError(String(e))`, y con un 422 de FastAPI
// (`{ detail: [{ loc, msg, type }, ...] }`) eso rendereaba literalmente
// "422: [object Object]" porque el array de objetos se stringifica asi por
// defecto. Funcion pura: no toca React ni fetch, solo el shape del error.

interface FastApiValidationError {
  loc?: unknown
  msg?: unknown
}

function esValidationError(item: unknown): item is FastApiValidationError {
  return typeof item === "object" && item !== null
}

function mensajePorCampo(item: FastApiValidationError): string {
  const loc = Array.isArray(item.loc) ? item.loc : []
  const campo = loc.length > 0 ? String(loc[loc.length - 1]) : "valor"
  const msg = typeof item.msg === "string" ? item.msg : "es invalido"
  return `${campo}: ${msg}`
}

/**
 * `err` es lo que llega al `catch` de un submit: puede ser el body JSON ya
 * parseado (`{ detail: ... }`, shape de FastAPI), un `Error` de red, o
 * cualquier otra cosa. Nunca devuelve el literal "[object Object]".
 */
export function formatApiError(err: unknown): string {
  const detail = err && typeof err === "object" ? (err as { detail?: unknown }).detail : undefined

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => (esValidationError(item) ? mensajePorCampo(item) : String(item)))
      .join("; ")
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail
  }

  const texto = String(err)
  return texto === "[object Object]" ? "Ocurrio un error inesperado" : texto
}
