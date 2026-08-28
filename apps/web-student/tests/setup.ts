import "@testing-library/jest-dom/vitest"

/**
 * Polyfill de Web Storage para jsdom.
 *
 * Node 26 trae `localStorage` NATIVO como global, y ese global le gana al de
 * jsdom cuando vitest puebla el entorno. Pero el nativo esta inutilizable si no
 * se arranca el proceso con `--localstorage-file`, asi que `window.localStorage`
 * queda `undefined` DENTRO de vitest — aunque jsdom crudo ande perfecto.
 *
 * Sintoma: `TypeError: Cannot read properties of undefined (reading 'clear')`.
 * En la corrida del 2026-08-10 eso fueron 144 rojos falsos de 158, y el 27/08
 * daba 160 en web-teacher y 61 en packages/ui. Ninguno era del codigo.
 *
 * El CI usa Node 20, donde no pasa — o sea que la suite pasaba o fallaba segun
 * la version de Node de cada maquina, y en la de desarrollo fallaba siempre. Un
 * desarrollador que ve 160 rojos deja de correr los tests, y eso es exactamente
 * lo que hizo que 14 rojos REALES ("No QueryClient set") vivieran en `main` sin
 * que nadie los viera.
 *
 * **Los metodos se instalan en `Storage.prototype`, no en la instancia**, y eso
 * no es un detalle de estilo: `persistencia.test.tsx` simula un storage roto con
 * `vi.spyOn(Storage.prototype, "setItem")`. Un objeto plano con sus propios
 * metodos los SOMBREA, el espia no intercepta nada, y el test que verifica la
 * degradacion elegante ante `QuotaExceededError` deja de probar lo que dice.
 *
 * Se instala solo si falta, asi que en Node 20 no toca nada.
 */
function instalarStorage(nombre: "localStorage" | "sessionStorage") {
  try {
    const actual = (globalThis as Record<string, unknown>)[nombre]
    if (actual && typeof (actual as Storage).setItem === "function") return
  } catch {
    // Algunos entornos tiran al solo LEER el accessor nativo. Se sigue igual.
  }

  const Proto: { prototype: Storage } | undefined =
    typeof Storage !== "undefined" ? (Storage as unknown as { prototype: Storage }) : undefined
  const proto = (Proto?.prototype ?? {}) as Storage & Record<string, unknown>

  // Los datos viven por instancia, no en el prototipo: `localStorage` y
  // `sessionStorage` comparten prototipo y no pueden compartir contenido.
  const datos = new WeakMap<object, Map<string, string>>()
  const mapaDe = (self: object): Map<string, string> => {
    let m = datos.get(self)
    if (!m) {
      m = new Map()
      datos.set(self, m)
    }
    return m
  }

  const metodos: Record<string, (this: object, ...args: never[]) => unknown> = {
    clear(this: object) {
      mapaDe(this).clear()
    },
    getItem(this: object, k: never) {
      const m = mapaDe(this)
      return m.has(k as unknown as string) ? (m.get(k as unknown as string) as string) : null
    },
    key(this: object, i: never) {
      return Array.from(mapaDe(this).keys())[i as unknown as number] ?? null
    },
    removeItem(this: object, k: never) {
      mapaDe(this).delete(k as unknown as string)
    },
    setItem(this: object, k: never, v: never) {
      mapaDe(this).set(k as unknown as string, String(v))
    },
  }

  // Se pisan SIEMPRE, sin preguntar si ya existen. En Node 26 `Storage.prototype`
  // trae los metodos NATIVOS —o sea que existen— pero fallan sobre cualquier
  // objeto que no sea una instancia nativa, que es justo lo que estamos creando.
  // Preguntar `if (typeof proto[m] !== "function")` dejaba los nativos puestos y
  // el polyfill no servia para nada.
  //
  // Pisarlos es seguro porque a esta funcion solo se llega cuando el storage
  // global esta inutilizable: no hay un jsdom sano al que romperle nada.
  for (const [nombreMetodo, fn] of Object.entries(metodos)) {
    Object.defineProperty(proto, nombreMetodo, {
      value: fn,
      configurable: true,
      writable: true,
    })
  }
  Object.defineProperty(proto, "length", {
    get(this: object) {
      return mapaDe(this).size
    },
    configurable: true,
  })

  const storage = Object.create(proto) as Storage

  for (const destino of [globalThis, globalThis.window]) {
    if (!destino) continue
    Object.defineProperty(destino, nombre, {
      value: storage,
      configurable: true,
      writable: true,
    })
  }
}

instalarStorage("localStorage")
instalarStorage("sessionStorage")

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
