import { useCallback, useSyncExternalStore } from "react"

export type ViewMode = "docente" | "investigador"

const LS_KEY = "analytics-view-mode"

function getSnapshot(): ViewMode {
  return (localStorage.getItem(LS_KEY) as ViewMode) ?? "docente"
}

function getServerSnapshot(): ViewMode {
  return "docente"
}

function subscribe(callback: () => void): () => void {
  const handler = (e: Event) => {
    if (e instanceof StorageEvent && e.key !== LS_KEY) return
    callback()
  }
  window.addEventListener("storage", handler)
  window.addEventListener("viewmode-change", callback)
  return () => {
    window.removeEventListener("storage", handler)
    window.removeEventListener("viewmode-change", callback)
  }
}

export function useViewMode(): [ViewMode, (mode: ViewMode) => void] {
  const mode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  const setMode = useCallback((m: ViewMode) => {
    localStorage.setItem(LS_KEY, m)
    window.dispatchEvent(new Event("viewmode-change"))
  }, [])

  return [mode, setMode]
}
