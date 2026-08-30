/**
 * Pyodide REAL (el paquete npm, no el CDN) instalado como `window.loadPyodide`.
 *
 * Por que existe, si ya hay un `tests/_pyodideFake.ts`:
 * el doble no ejecuta Python. Responde `__tutor_run_tests(...)` con un JSON
 * fijo y devuelve `undefined` para todo lo demas — con lo cual verifica el
 * cableado del componente (orden de eventos, conteos que viajan al CTR) y
 * nada de lo que pasa cuando JavaScript y Python se hablan de verdad: el
 * viaje del texto de `window.prompt` a `input()`, el eco en la terminal, el
 * watchdog, el guard de imports, el aislamiento entre casos de prueba.
 *
 * Esa costura es donde caen los alumnos, y hasta este archivo no tenia
 * un solo test.
 *
 * ## No depende de la red
 *
 * `CodeEditor` carga Pyodide de `cdn.jsdelivr.net` en produccion. Un test que
 * baje 6 MB del CDN en cada corrida es un test que falla cuando falla el CDN
 * — el repo ya tiene ese gotcha con la imagen de Java. Aca se usa el paquete
 * `pyodide` de npm, que trae `pyodide.asm.wasm` + `python_stdlib.zip` en
 * `node_modules` (14 MB) y resuelve TODO desde disco. Cero red en la corrida.
 *
 * El precio de esa decision: el `indexURL` del CDN es lo unico que NO se
 * ejercita. Se pisa a proposito con la ruta local (ver `cargar`).
 *
 * ## Version
 *
 * `PYODIDE_VERSION` en `CodeEditor.tsx` y la version del devDependency tienen
 * que coincidir. Si divergen, estos tests prueban un interprete que el alumno
 * no usa. Hay un test en `viajeDelDato.test.tsx` que compara
 * `versionInstalada()` contra `versionDelComponente()` y falla si divergen.
 */
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import path from "node:path"
import { fileURLToPath } from "node:url"

const require = createRequire(import.meta.url)
const dirActual = path.dirname(fileURLToPath(import.meta.url))

/** Ruta a `node_modules/pyodide`, que es lo que Pyodide espera como indexURL. */
export const INDEX_URL_LOCAL = path.dirname(require.resolve("pyodide/package.json"))

/** Version del paquete npm efectivamente instalado. */
export function versionInstalada(): string {
  const pkg = JSON.parse(readFileSync(path.join(INDEX_URL_LOCAL, "package.json"), "utf8")) as {
    version: string
  }
  return pkg.version
}

/** Version que `CodeEditor` pide al CDN en produccion. */
export function versionDelComponente(): string {
  const fuente = readFileSync(
    path.resolve(dirActual, "../../src/components/CodeEditor.tsx"),
    "utf8",
  )
  const m = fuente.match(/const PYODIDE_VERSION = "([^"]+)"/)
  if (!m?.[1]) throw new Error("no se encontro PYODIDE_VERSION en CodeEditor.tsx")
  return m[1]
}

/**
 * Interprete compartido por archivo de test.
 *
 * Levantar uno nuevo cuesta ~1,5 s; el bootstrap del componente (watchdog,
 * guard de imports, runner de tests) suma otro tanto. Con un interprete por
 * test la suite se vuelve inusable y nadie la corre. Se comparte uno por
 * archivo (vitest aisla los archivos entre si) y cada montaje del componente
 * vuelve a correr su bootstrap encima, que es idempotente: redefine todo.
 *
 * Consecuencia a tener presente al escribir tests: las variables que deje el
 * codigo de un alumno viven en `globals()` y sobreviven al test siguiente,
 * igual que le pasa al alumno real entre dos "Ejecutar". `limpiarGlobals()`
 * borra lo que no sea del bootstrap cuando un test necesita empezar limpio.
 */
type PyodideModule = Awaited<typeof import("pyodide")>
type Interprete = Awaited<ReturnType<PyodideModule["loadPyodide"]>>

let cache: Promise<Interprete> | null = null

async function cargar(): Promise<Interprete> {
  if (!cache) {
    const { loadPyodide } = await import("pyodide")
    // El componente pasa el indexURL del CDN; lo ignoramos a proposito.
    cache = loadPyodide({ indexURL: INDEX_URL_LOCAL })
  }
  return cache
}

/** Precalienta el interprete fuera del reloj de un test puntual. */
export async function precalentar(): Promise<void> {
  await cargar()
}

export interface PyodideReal {
  /** Deshace el parcheo de `window.loadPyodide`. NO destruye el interprete. */
  desinstalar(): void
}

/**
 * Instala el Pyodide real como `window.loadPyodide`.
 *
 * `CodeEditor` chequea `if (!window.loadPyodide)` antes de inyectar el script
 * del CDN: con esto puesto ANTES del render, salta la inyeccion y usa este.
 */
export function instalarPyodideReal(): PyodideReal {
  const anterior = window.loadPyodide
  window.loadPyodide = (async () =>
    (await cargar()) as unknown as Awaited<
      ReturnType<NonNullable<typeof window.loadPyodide>>
    >) as NonNullable<typeof window.loadPyodide>

  return {
    desinstalar() {
      if (anterior) {
        window.loadPyodide = anterior
        return
      }
      window.loadPyodide = undefined as unknown as NonNullable<typeof window.loadPyodide>
    },
  }
}

/**
 * Borra del `globals()` de Python lo que no pertenece al bootstrap.
 *
 * Todo lo que el bootstrap del componente define arranca con `_` (`_tutor*`,
 * `__tutor*`, dunders del modulo). Lo que no empieza con `_` lo dejo el codigo
 * de un alumno, y es lo que se limpia.
 */
export async function limpiarGlobals(): Promise<void> {
  const py = await cargar()
  await py.runPythonAsync(`
for _tutor_k in [k for k in list(globals()) if not k.startswith("_")]:
    del globals()[_tutor_k]
`)
}
