// Identidad del alumno + constantes compartidas. Vive APARTE de main.tsx para
// romper el import circular main.tsx -> routeTree.gen -> (__root / TenantSelector)
// -> main.tsx, que causaba "Cannot access 'routeTree' before initialization" al
// re-evaluar el entry via HMR.
import { v5 as uuidv5 } from "uuid"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string
// Dev sin Clerk: si no hay publishable key, hardcodeamos un alumno del seed
// (alumno01) y la identidad la inyecta el proxy de Vite. El UUID coincide con
// el default x-user-id del proxy y tiene inscripcion real en el tenant fallback.
export const DEV_NO_CLERK = !CLERK_PUBLISHABLE_KEY
export const DEV_STUDENT_UUID = "e19354fb-c05a-4535-a0bf-a7d3ea09692d"

export const SELECTED_TENANT_STORAGE_KEY = "selectedTenantId"

// Namespace UUID fijo del piloto AI-Native N4. NO cambiar: regenera todos
// los student_pseudonym y rompe la continuidad de la cadena CTR por usuario.
// Generado UNA vez con `uuidgen` el 2026-05-29.
const CLERK_PSEUDONYM_NAMESPACE = "8f9d2c4a-7b1e-5d3f-9a8c-1e2b3c4d5e6f"

// Storage key del pseudonym derivado del Clerk user.id. Se preserva entre
// sessions y entre versiones del algoritmo (ver clerkIdToUuid abajo).
const CLERK_PSEUDONYM_STORAGE_KEY = "clerkDerivedUserId"
const LEGACY_PSEUDONYM_VERSION_KEY = "clerkDerivedUserIdVersion"
const PSEUDONYM_ALGO_VERSION = "v5-2026-05-29"

/**
 * UUID determinista desde Clerk user.id → student_pseudonym valido para el CTR.
 *
 * v5-2026-05-29 (este): UUID v5 (SHA-1 namespaced, RFC 4122). Sin colision
 * computacional dentro del piloto. Reemplazo del hash truncado v1 que daba
 * 8 chars de entropia (~10^-5 prob colision en 1000 alumnos).
 *
 * BACKWARDS-COMPAT: si el localStorage tiene un pseudonym pre-fix (legacy),
 * lo conservamos en memoria pero generamos el v5 para futuras escrituras.
 * Esto NO migra eventos viejos del CTR — son inmutables por design.
 */
export function clerkIdToUuid(clerkId: string): string {
  return uuidv5(clerkId, CLERK_PSEUDONYM_NAMESPACE)
}

// Variable global: el UUID del alumno logueado. Se setea desde el root layout.
let _currentUserUuid: string | null = localStorage.getItem(CLERK_PSEUDONYM_STORAGE_KEY)

// Getter para el fetch patch de main.tsx (lee el UUID vigente por request).
export function getCurrentUserUuid(): string | null {
  return _currentUserUuid
}

export function setClerkUserId(clerkId: string) {
  // Identidad determinista: el pseudonym SIEMPRE se deriva del Clerk user.id
  // logueado actual (UUID v5 namespaced). NO se confia en lo que ya este en
  // localStorage — ese valor puede ser de OTRO alumno que uso este browser, o
  // un pseudonym legacy pre-v5 que ya no matchea ninguna inscripcion. En ese
  // caso el header `x-user-id` salia con el UUID equivocado y
  // academic.assert_comision_access devolvia 403 al abrir un episodio; la vieja
  // rama "preservar legacy" ademas dejaba ese UUID pegado (escribia un version
  // tag != PSEUDONYM_ALGO_VERSION), asi que el 403 solo se curaba limpiando
  // localStorage a mano.
  //
  // Verificado 2026-06-04 contra la DB de prod: el 100% de las inscripciones y
  // de los episodios del CTR usan pseudonym v5 (namespace fijado 2026-05-29).
  // No existe ninguna cadena CTR legacy que preservar, asi que derivar siempre
  // es seguro y NO rompe el append-only.
  const uuid = clerkIdToUuid(clerkId)
  _currentUserUuid = uuid
  localStorage.setItem(CLERK_PSEUDONYM_STORAGE_KEY, uuid)
  localStorage.setItem(LEGACY_PSEUDONYM_VERSION_KEY, PSEUDONYM_ALGO_VERSION)
}

export function clearClerkUserId() {
  _currentUserUuid = null
  localStorage.removeItem(CLERK_PSEUDONYM_STORAGE_KEY)
  localStorage.removeItem(LEGACY_PSEUDONYM_VERSION_KEY)
}

// Dev sin Clerk: fija el UUID del alumno hardcodeado SIN pasar por
// clerkIdToUuid (queremos exactamente el student_pseudonym del seed).
export function setDevStudentId() {
  _currentUserUuid = DEV_STUDENT_UUID
}
