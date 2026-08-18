// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import type { TourStatus } from "./types"

/**
 * Persistencia del onboarding en localStorage. Deliberadamente por-navegador y no
 * por-usuario: el backend todavia no guarda estado de onboarding. Consecuencia asumida
 * y declarada (ver el bloque final de `types.ts`) — el mismo docente en otra maquina
 * vuelve a ver el panoramico. Cuando exista el campo en el perfil, reemplazar ESTE
 * modulo es todo el cambio necesario: ni los providers ni los flows lo saben.
 *
 * Todas las funciones son tolerantes a fallo. Modo privado de Safari, storage lleno,
 * cookies bloqueadas o JSON de una version anterior del formato degradan en silencio:
 * el onboarding arranca igual y simplemente no recuerda. Nunca tiran.
 */

const PREFIJO_TOUR = "ai-native:tour:"
const PREFIJO_ONBOARDING = "ai-native:onboarding:"

/* ========================================================================== */
/* 1. Tour lineal: estado + paso en curso                                     */
/* ========================================================================== */

export interface EstadoTour {
  estado: TourStatus
  /** Id del paso en curso. Sostiene el resume post-reload. */
  paso?: string
}

/**
 * Construye un estado "pendiente" a partir de un paso que puede no existir.
 *
 * Existe por `exactOptionalPropertyTypes`: con esa opcion, `{ paso: undefined }` NO es
 * lo mismo que `{}`, y no es asignable a `paso?: string`. La distincion es correcta y
 * no se tapa con un cast — "no hay paso" es ausencia de la clave, no la clave con
 * valor `undefined`. Ademas es lo que queremos serializar: `JSON.stringify` tira las
 * claves `undefined`, asi que el objeto que guardamos y el que leemos coinciden.
 */
export function estadoPendiente(paso: string | undefined): EstadoTour {
  return paso === undefined ? { estado: "pendiente" } : { estado: "pendiente", paso }
}

function esStatus(v: unknown): v is TourStatus {
  return v === "pendiente" || v === "completado" || v === "salteado"
}

/**
 * Lee el estado del tour de un flow. Cualquier cosa que no reconozcamos vuelve como
 * "pendiente": ante un formato viejo preferimos volver a mostrar el tour antes que
 * dejar al usuario sin el.
 */
export function leerTour(flowId: string): EstadoTour {
  try {
    const raw = window.localStorage.getItem(PREFIJO_TOUR + flowId)
    if (!raw) return { estado: "pendiente" }
    const v: unknown = JSON.parse(raw)
    if (typeof v !== "object" || v === null) return { estado: "pendiente" }
    const { estado, paso } = v as { estado?: unknown; paso?: unknown }
    if (!esStatus(estado)) return { estado: "pendiente" }
    return typeof paso === "string" ? { estado, paso } : { estado }
  } catch {
    return { estado: "pendiente" }
  }
}

export function guardarTour(flowId: string, valor: EstadoTour): void {
  try {
    window.localStorage.setItem(PREFIJO_TOUR + flowId, JSON.stringify(valor))
  } catch {
    /* ver el bloque de arriba: degradar en silencio */
  }
}

/* ========================================================================== */
/* 2. Onboarding por estado: descartes                                        */
/* ========================================================================== */

/**
 * Ids de los carteles que el usuario ya cerro, por flow.
 *
 * Es el UNICO dato nuevo que persistimos del onboarding: todo lo demas (si un paso
 * aplica, si ya se cumplio) sale del estado real de la app. Por eso perder este set
 * degrada bien — reaparecen carteles pendientes, nunca carteles ya cumplidos.
 */
export function leerDescartes(flowId: string): ReadonlySet<string> {
  try {
    const raw = window.localStorage.getItem(PREFIJO_ONBOARDING + flowId)
    if (!raw) return new Set()
    const v: unknown = JSON.parse(raw)
    if (!Array.isArray(v)) return new Set()
    return new Set(v.filter((x): x is string => typeof x === "string"))
  } catch {
    return new Set()
  }
}

export function guardarDescartes(flowId: string, ids: ReadonlySet<string>): void {
  try {
    window.localStorage.setItem(PREFIJO_ONBOARDING + flowId, JSON.stringify([...ids]))
  } catch {
    /* ver el bloque de arriba: degradar en silencio */
  }
}
