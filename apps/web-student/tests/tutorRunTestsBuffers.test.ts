/**
 * comparacion-ignora-el-prompt-del-input — el runner de test cases del alumno
 * (`__tutor_run_tests`, embebido en `CodeEditor.tsx`) tiene que separar DOS
 * buffers: el de PANTALLA (prompts + prints, lo que el alumno ve) y el de
 * COMPARACION (solo lo que el codigo del alumno imprimio, sin el prompt de
 * `input()`).
 *
 * POR QUE ESTO SE TESTEA ASI Y NO EJECUTANDO EL PYTHON
 * ------------------------------------------------------
 * Igual que `pyodideBootstrapCompila.test.ts`: este Python vive como STRING
 * dentro de un template literal de `CodeEditor.tsx` y corre adentro de
 * Pyodide. Los tests del editor usan `_pyodideFake.ts`, que nunca lo ejecuta
 * (`CodeEditorOrdenEventos.test.tsx` inyecta `resultadosDeTests` directo,
 * salteando el harness entero). No hay forma de ejercitarlo de verdad en esta
 * suite — lo unico que se puede afirmar es su CONTENIDO.
 *
 * El comportamiento real del veredicto (que la comparacion use el buffer sin
 * el prompt) esta cubierto donde SI es ejecutable: `veredictoTests.test.ts`,
 * sobre `resolverVeredictosPython`.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const FUENTE = readFileSync(join(__dirname, "../src/components/CodeEditor.tsx"), "utf-8")

/** El harness de `__tutor_run_tests`, el runner de test cases del alumno. */
function bloqueDeRunTests(): string {
  const m = FUENTE.match(/runPythonAsync\(`\n(import io as _tutor_io[\s\S]*?)`\)/)
  const bloque = m?.[1]
  if (!bloque) throw new Error("no se encontro __tutor_run_tests en CodeEditor.tsx")
  return bloque
}

describe("el harness se encontro y no esta vacio", () => {
  it("el bloque extraido no es trivial", () => {
    // Guarda contra el modo de falla mas tonto: si la extraccion se rompe y
    // devuelve "", todos los `.not.toContain(...)` de abajo pasarian sin
    // haber mirado nada.
    expect(bloqueDeRunTests().length).toBeGreaterThan(1000)
    expect(bloqueDeRunTests()).toContain("def __tutor_run_tests(")
  })
})

describe("__tutor_run_tests — dos buffers, no centinelas", () => {
  it("existe un segundo StringIO para el buffer de comparacion", () => {
    const bloque = bloqueDeRunTests()
    const stringIOs = bloque.match(/_tutor_io\.StringIO\(\)/g) ?? []
    expect(stringIOs.length).toBeGreaterThanOrEqual(2)
  })

  it("el resultado de cada caso trae la clave 'comparacion'", () => {
    expect(bloqueDeRunTests()).toContain('"comparacion":')
  })

  it("el prompt de input() se sigue escribiendo SOLO al buffer de pantalla (_out)", () => {
    // No cambia: _feed sigue escribiendo el prompt directo a `_out` (que por
    // default es `buf`, el de pantalla), no al escritor dual que ve el
    // codigo del alumno.
    const bloque = bloqueDeRunTests()
    expect(bloque).toMatch(/if prompt:\s*\n\s*_out\.write\(str\(prompt\)\)/)
  })

  it("stdout ya NO se redirige directo al buffer de pantalla pelado", () => {
    // Antes: `redirect_stdout(buf)` — un solo buffer para todo. Si esto sigue
    // presente tal cual, el fix no separo nada: el print del alumno seguiria
    // yendo solo a pantalla y nunca al buffer de comparacion (o viceversa).
    expect(bloqueDeRunTests()).not.toMatch(/redirect_stdout\(buf\)/)
  })

  it("no aparece un marcador sintetico (string literal) alrededor del prompt", () => {
    // Decision de diseno explicita de esta change: separar por ESCRITURA
    // estructural (dos buffers), no por un marcador tipo "\x00PROMPT\x00"
    // insertado en el texto: si el alumno imprime esa misma secuencia, un
    // enfoque por marcador rompe la comparacion de una forma indiagnosticable.
    // Se busca el LITERAL de un marcador (comillas + \x00), no la palabra —
    // el propio comentario de diseno de arriba dice "NO CENTINELAS" y un
    // match por palabra se dispara con su propia documentacion.
    const bloque = bloqueDeRunTests()
    expect(bloque).not.toMatch(/["'][^"'\n]*\\x00[^"'\n]*["']/)
  })
})

/**
 * La rama REMOTA (Java) tambien construye `TestCaseResult`, y tiene que poner
 * `comparacion` con el stdout crudo — NO con la cadena vacia.
 *
 * POR QUE ESTE TEST EXISTE
 * ------------------------
 * `tsc` ya obliga a que el campo este (es obligatorio en la interfaz, y su
 * ausencia rompio los jobs `lint-frontend` y `build-frontend` de CI cuando se
 * escribio esta change). Lo que `tsc` NO puede decir es QUE VALOR va: `""`
 * compila igual.
 *
 * Y `""` es la trampa: hoy esta rama no llama a `resolverVeredictosPython`
 * —el veredicto lo trae el servidor en `c.status`— asi que el campo no se lee
 * y un `""` no rompe nada. El dia que alguien rutee Java por el resolvedor,
 * cada caso compararia su salida contra vacio y TODOS los ejercicios de Java
 * fallarian, sin que ningun test de hoy avise.
 *
 * En Java no hay nada que separar: el prompt del input es un
 * `System.out.print` comun (ver el comentario en `docker_runner.py`). Lo que
 * se compara ES el stdout.
 */
describe("la rama remota (Java) no deja `comparacion` en vacio", () => {
  /** El `.map` que arma los TestCaseResult desde la respuesta del servidor. */
  function bloqueRemoto(): string {
    const m = FUENTE.match(/result\.cases\.map\(\(c\) => \(\{([\s\S]*?)\}\)\),/)
    const bloque = m?.[1]
    if (!bloque) throw new Error("no se encontro el map de runTestsRemoto en CodeEditor.tsx")
    return bloque
  }

  it("el bloque extraido no es trivial", () => {
    // Misma guarda que arriba: una extraccion rota devolveria "" y los asserts
    // de abajo pasarian sin haber mirado nada.
    expect(bloqueRemoto()).toContain("passed:")
  })

  it("asigna `comparacion` desde `c.got`, igual que `actual`", () => {
    const bloque = bloqueRemoto()
    expect(bloque).toMatch(/comparacion:\s*c\.got\s*\?\?\s*""/)
  })

  it("NO asigna `comparacion` a la cadena vacia pelada", () => {
    const bloque = bloqueRemoto()
    expect(bloque).not.toMatch(/comparacion:\s*""/)
  })
})
