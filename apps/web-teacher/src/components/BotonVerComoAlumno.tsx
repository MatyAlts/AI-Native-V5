/**
 * HU-022: el docente pasa a la vista de alumno para probar los TPs de punta a
 * punta. La eleccion se guarda en `localStorage["modo-vista"]`, que el web-student
 * (mismo origen) lee para no rebotarlo de vuelta a /teacher/.
 */
const MODO_VISTA_KEY = "modo-vista"

export function BotonVerComoAlumno() {
  return (
    <button
      type="button"
      onClick={() => {
        try {
          window.localStorage.setItem(MODO_VISTA_KEY, "alumno")
        } catch {
          /* sin localStorage el web-student lo devolveria al panel; no hay mas que hacer */
        }
        window.location.assign("/")
      }}
      title="Entrar a la plataforma como la ve un alumno"
      className="text-xs text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-strong"
    >
      Ver como alumno
    </button>
  )
}
