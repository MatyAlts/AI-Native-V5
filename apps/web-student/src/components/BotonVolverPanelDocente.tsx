import { elegirPanelDocente } from "../utils/modoVista"

/**
 * HU-022: un docente que eligio ver como alumno vuelve a su panel desde aca.
 * Un alumno comun no lo ve.
 */
export function BotonVolverPanelDocente({ esDocente }: { esDocente: boolean }) {
  if (!esDocente) return null
  return (
    <button
      type="button"
      onClick={() => {
        elegirPanelDocente()
        window.location.assign("/teacher/")
      }}
      className="text-xs font-medium text-accent-brand border border-border-soft rounded-md px-2.5 py-1 hover:bg-surface"
    >
      Volver al panel docente
    </button>
  )
}
