import { useViewMode } from "../hooks/useViewMode"

export function ViewModeToggle() {
  const [mode, setMode] = useViewMode()

  return (
    <div
      className="flex items-center rounded-full bg-border p-0.5 text-xs"
      role="radiogroup"
      aria-label="Modo de visualizacion"
    >
      <button
        type="button"
        role="radio"
        aria-checked={mode === "docente"}
        onClick={() => setMode("docente")}
        className={`px-3 py-1 rounded-full transition-colors ${
          mode === "docente"
            ? "bg-white text-ink font-medium shadow-sm"
            : "text-muted hover:text-ink"
        }`}
      >
        Docente
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={mode === "investigador"}
        onClick={() => setMode("investigador")}
        className={`px-3 py-1 rounded-full transition-colors ${
          mode === "investigador"
            ? "bg-white text-ink font-medium shadow-sm"
            : "text-muted hover:text-ink"
        }`}
      >
        Investigador
      </button>
    </div>
  )
}
