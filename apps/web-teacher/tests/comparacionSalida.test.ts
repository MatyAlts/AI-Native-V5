/**
 * JAVA-1 — comparacion de la salida, lado DOCENTE ("Probar ejercicio").
 *
 * Este test no existia, y por eso el tercer corrector pudo divergir en silencio
 * durante toda su vida. `lib/pyodideRunner.ts` tenia su propia `normalize()`
 * con el `\s` de JavaScript: 24 code points contra los 28 del alumno y del
 * servidor, y sin unificar el `\r` suelto. Fallaba 1 de los 29 casos que la
 * tabla compartida tenia entonces, y el que MAS duele no estaba — el BOM
 * (`U+FEFF`), que `\s` recorta y `str.isspace()` de Python no:
 *
 *   el docente pega el `expected_output` desde un archivo con BOM
 *     -> "Probar" da VERDE
 *     -> asigna el ejercicio
 *     -> la cohorte entera recibe WRONG_ANSWER con codigo correcto, en silencio
 *     -> y eso mueve `test_count_passed/failed`, el evento del que el labeler
 *        deriva N3 vs N4.
 *
 * La tabla NO vive aca: vive en `tests/fixtures/paridad-salida.json`, en la
 * raiz del monorepo, y la leen tambien `apps/web-student/tests/` y
 * `apps/execution-service/tests/unit/test_comparacion_salida.py`. Con tres
 * tablas copiadas, la primera correccion que toque una sola las separa.
 *
 * Se testea `evaluateCase` y no `salidaCoincide` a proposito: lo que hay que
 * demostrar no es que el corrector canonico funcione (eso ya lo cubre el lado
 * del alumno) sino que ESTE camino —el que pinta el verde del docente— pasa
 * por el.
 */

import { describe, expect, it } from "vitest"
// Import de JSON, no `readFileSync`: bajo Vitest (entorno jsdom) `import.meta.url`
// no es un `file://` y leerlo a mano tira "The URL must be of scheme file". El
// import lo resuelve Vite relativo a ESTE archivo, que es lo que queremos — si
// la tabla se mueve, el test no compila en vez de pasar sin comparar nada.
import tabla from "../../../tests/fixtures/paridad-salida.json"
import { type TestCaseLike, evaluateCase } from "../src/lib/pyodideRunner"

interface CasoParidad {
  nombre: string
  actual: string
  esperado: string
  coincide: boolean
  porque: string
}

const casos = tabla.casos as CasoParidad[]

/** Un `stdin_stdout` cuyo `expected` es el esperado de la tabla. */
function casoDocente(esperado: string): TestCaseLike {
  return {
    id: "tc-1",
    name: "caso",
    type: "stdin_stdout",
    code: "",
    expected: esperado,
    is_public: true,
    weight: 1,
  }
}

describe("evaluateCase — tabla compartida con el alumno y el execution-service", () => {
  it("la tabla se leyo y tiene casos de los dos veredictos", () => {
    // Guarda contra el modo de falla mas tonto de un test parametrizado: la
    // tabla no se encontro / quedo vacia y el `it.each` no corre nada.
    expect(casos.length).toBeGreaterThan(20)
    expect(casos.some((c) => c.coincide)).toBe(true)
    expect(casos.some((c) => !c.coincide)).toBe(true)
  })

  it.each(casos)("$nombre -> $coincide ($porque)", ({ actual, esperado, coincide }) => {
    // Esta tabla es sobre el corrector generico, no sobre el prompt de
    // input(): `comparacion` sigue a `stdout` tal cual.
    const r = evaluateCase(casoDocente(esperado), { stdout: actual, comparacion: actual, error: null })
    expect(r.status).toBe(coincide ? "pass" : "fail")
  })
})

describe("evaluateCase — los cinco code points que el \\s de JS no cubre", () => {
  // Estan en la tabla compartida (U+001F y U+0085 explicitos), pero se afirman
  // tambien aca uno por uno: es el set exacto que separaba a este corrector de
  // los otros dos, y un dia que alguien vuelva a `\s` tiene que verse en el
  // nombre del test que falla, no en un caso parametrizado anonimo.
  const soloPython = [
    ["U+001C separador de archivo", "\u001c"],
    ["U+001D separador de grupo", "\u001d"],
    ["U+001E separador de registro", "\u001e"],
    ["U+001F separador de unidad", "\u001f"],
    ["U+0085 NEL", "\u0085"],
  ] as const

  it.each(soloPython)("%s se recorta al final (isspace() de Python SI lo es)", (_n, ch) => {
    const salida = `Hola${ch}`
    const r = evaluateCase(casoDocente("Hola"), { stdout: salida, comparacion: salida, error: null })
    expect(r.status).toBe("pass")
  })

  it("U+FEFF (BOM) NO se recorta: `\\s` de JS lo recortaba y Python no", () => {
    // El caso estrella. Con la `normalize()` vieja esto daba "pass" y el
    // docente asignaba un ejercicio que reprobaba a la cohorte entera.
    const r = evaluateCase(casoDocente("\ufeffHola"), { stdout: "Hola", comparacion: "Hola", error: null })
    expect(r.status).toBe("fail")
  })

  it("el `\\r` suelto (Mac clasico) se unifica a `\\n`", () => {
    // La `normalize()` vieja solo reemplazaba `\r\n`, asi que este daba "fail".
    const r = evaluateCase(casoDocente("Hola\nmundo"), {
      stdout: "Hola\rmundo",
      comparacion: "Hola\rmundo",
      error: null,
    })
    expect(r.status).toBe("pass")
  })
})

describe("evaluateCase — el buffer de comparacion ignora el prompt de input() (comparacion-ignora-el-prompt-del-input)", () => {
  // Mismo contrato que `resolverVeredictosPython` del lado alumno
  // (apps/web-student/src/lib/veredictoTests.ts): `stdout` es la PANTALLA
  // (prompts + prints, lo que se muestra en "Obtenido"), `comparacion` es lo
  // unico que se coteja contra `expected`.
  it("usa `comparacion`, no `stdout`, para decidir el veredicto", () => {
    // Si esto comparara contra `stdout`, el docente veria ROJO al probar la
    // propia pista del ejercicio con el mensaje puesto — exactamente el
    // incidente del 2026-09-10 referenciado arriba en este archivo.
    const r = evaluateCase(casoDocente("Hola Marcos!"), {
      stdout: "Ingrese su nombre: Hola Marcos!",
      comparacion: "Hola Marcos!",
      error: null,
    })
    expect(r.status).toBe("pass")
  })

  it("un print de mas en `comparacion` sigue fallando aunque `stdout` coincida con el expected", () => {
    // Triangula el caso de arriba: descarta una implementacion que comparara
    // contra `stdout` (que aca coincide por casualidad) o que ignorara
    // `comparacion` por completo.
    const r = evaluateCase(casoDocente("Hola Marcos!"), {
      stdout: "Hola Marcos!",
      comparacion: "Hola Marcos!\nDebug: ejecutando",
      error: null,
    })
    expect(r.status).toBe("fail")
  })

  it("`got` sigue siendo el stdout de PANTALLA, con el prompt, aunque el veredicto use `comparacion`", () => {
    // El docente tiene que seguir viendo el prompt en el panel de resultado
    // ("Obtenido"): separar los buffers para el veredicto no le saca
    // contexto a la pantalla.
    const r = evaluateCase(casoDocente("Hola Marcos!"), {
      stdout: "Ingrese su nombre: Hola Marcos!",
      comparacion: "Hola Marcos!",
      error: null,
    })
    expect(r.got).toBe("Ingrese su nombre: Hola Marcos!")
  })
})

describe("evaluateCase — lo que NO cambia", () => {
  it("un error de ejecucion sigue ganandole a la comparacion", () => {
    const r = evaluateCase(casoDocente("Hola"), {
      stdout: "Hola",
      comparacion: "Hola",
      error: "ZeroDivisionError",
    })
    expect(r.status).toBe("error")
  })

  it("un `pytest_assert` sin excepcion pasa sin comparar salida", () => {
    const tc: TestCaseLike = { ...casoDocente(null as unknown as string), type: "pytest_assert" }
    const r = evaluateCase(tc, { stdout: "cualquier cosa", comparacion: "cualquier cosa", error: null })
    expect(r.status).toBe("pass")
  })

  it("`expected` nulo equivale a esperar que no imprima nada", () => {
    const tc: TestCaseLike = { ...casoDocente(""), expected: null }
    expect(evaluateCase(tc, { stdout: "", comparacion: "", error: null }).status).toBe("pass")
    expect(evaluateCase(tc, { stdout: "Hola", comparacion: "Hola", error: null }).status).toBe("fail")
  })
})
