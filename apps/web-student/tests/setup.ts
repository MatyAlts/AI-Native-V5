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
