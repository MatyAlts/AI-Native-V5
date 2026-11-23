/**
 * HU-022: interruptor docente/alumno.
 *
 * Una cuenta con comisiones asignadas como docente rebota sola a /teacher/. Para
 * que pueda probar el lado del alumno de punta a punta, elige la vista y la
 * eleccion queda en `localStorage["modo-vista"]`. El web-student (`/`) y el
 * web-teacher (`/teacher/`) se sirven desde el mismo origen, asi que comparten
 * esa clave: el boton "Ver como alumno" del panel docente la escribe y este
 * modulo la lee.
 *
 * Valores: "alumno" | "docente". Ausente equivale a "docente" (comportamiento de
 * siempre). Si localStorage no esta disponible, tambien.
 */
export const MODO_VISTA_KEY = "modo-vista"

function guardar(valor: "alumno" | "docente"): void {
  try {
    window.localStorage.setItem(MODO_VISTA_KEY, valor)
  } catch {
    /* sin localStorage: queda el comportamiento de siempre */
  }
}

export function elegirVistaAlumno(): void {
  guardar("alumno")
}

export function elegirPanelDocente(): void {
  guardar("docente")
}

/** Un docente va a su panel salvo que haya elegido ver como alumno. */
export function debeIrAlPanelDocente(esDocente: boolean): boolean {
  if (!esDocente) return false
  try {
    return window.localStorage.getItem(MODO_VISTA_KEY) !== "alumno"
  } catch {
    return true
  }
}
