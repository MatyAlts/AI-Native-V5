import "@testing-library/jest-dom/vitest"

// jsdom no implementa ResizeObserver y `react-resizable-panels` lo instancia al
// montar un `Group` — sin este stub, cualquier test que renderice el editor o
// el layout de paneles del episodio muere con "n is not a constructor".
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver
}

// Mismo motivo: `EpisodeView` instancia un IntersectionObserver al montar (mide
// el tiempo de lectura del enunciado para `lectura_enunciado`). jsdom no lo
// implementa y sin el stub el componente no se puede montar en ningun test.
// Nunca dispara: los tests que lo necesiten que emitan el evento a mano.
if (typeof globalThis.IntersectionObserver === "undefined") {
  globalThis.IntersectionObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): [] {
      return []
    }
    readonly root = null
    readonly rootMargin = ""
    readonly thresholds: readonly number[] = []
  } as unknown as typeof IntersectionObserver
}
