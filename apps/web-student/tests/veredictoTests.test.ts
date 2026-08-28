/**
 * JAVA-1 / H2 — quien decide si un caso de Python paso, y que conteo sale de ahi.
 *
 * Por que este archivo importa mas que un unitario cualquiera
 * ----------------------------------------------------------
 * El runner Pyodide (`__tutor_run_tests`, embebido en `CodeEditor`) devuelve
 * `passed: False` FIJO para TODO caso `stdin_stdout` que corrio sin excepcion —
 * es un placeholder deliberado, con el comentario "Este False es un placeholder
 * que el lado JS pisa" al lado. O sea: el veredicto real de todos los casos de
 * Python lo pone `resolverVeredictosPython`, y de ahi sale el conteo que
 * `onTestsRun` manda al CTR como `tests_ejecutados` — el evento del que el
 * labeler v1.2.0 deriva N3 vs N4.
 *
 * El mutante que hasta hoy sobrevivia: reemplazar el `.map()` por la identidad.
 * Con eso TODO caso de Python reporta fallado, el alumno ve rojo aunque su
 * programa este bien, y los episodios del piloto quedan mal nivelados en los
 * datos de la tesis. Nada explota. Los 280 tests seguian en verde.
 *
 * De donde salen los fixtures
 * ---------------------------
 * De grepear el runner, no de inventar. `__tutor_run_tests` arma el dict con
 * estas ocho claves (`id, name, type, passed, expected, actual, stdin, error`)
 * y estos invariantes, que son los que hacen que el test no sea vacuo:
 *
 *   - `stdin_stdout` que corrio OK  → `passed: false`, `error: null`
 *   - `pytest_assert` que corrio OK → `passed: true`,  `error: null`
 *   - cualquiera que murio          → `passed: false`, `error: <string>` y
 *                                     `actual` con lo que alcanzo a imprimir
 *
 * Si los fixtures arrancaran con `passed: true` en los `stdin_stdout`, la
 * identidad pasaria los tests: seria el octavo test vacuo del epic.
 */

import { describe, expect, it } from "vitest"
import type { TestCaseResult } from "../src/lib/veredictoTests"
import { contarTests, resolverVeredictosPython } from "../src/lib/veredictoTests"

/** Un `stdin_stdout` tal como sale del runner: `passed` SIEMPRE false. */
function delRunner(over: Partial<TestCaseResult> = {}): TestCaseResult {
  return {
    id: "tc-1",
    name: "Caso 1",
    type: "stdin_stdout",
    passed: false, // el placeholder del runner
    expected: "hola",
    actual: "hola\n",
    stdin: "",
    error: null,
    ...over,
  }
}

describe("resolverVeredictosPython — el veredicto de los stdin_stdout", () => {
  it("un caso que coincide pasa a passed:true", () => {
    // Sin el `.map()` esto queda en `false` y el alumno ve rojo con el
    // programa bien. `actual` trae el "\n" que `print` siempre agrega y
    // `expected` no lo trae: es el caso normal del banco, no un borde.
    const [r] = resolverVeredictosPython([delRunner()])
    expect(r?.passed).toBe(true)
  })

  it("un caso que NO coincide queda en passed:false", () => {
    const [r] = resolverVeredictosPython([delRunner({ actual: "chau\n" })])
    expect(r?.passed).toBe(false)
  })

  it("aplica la MISMA normalizacion que el corrector de Java", () => {
    // No es una comparacion literal: `salidaCoincide` recorta EOL, blancos al
    // final de cada linea y el salto final. Es el gemelo de `outputs_match`
    // del execution-service — si acá se comparara con `===` pelado, el mismo
    // programa aprobaria en Java y fallaria en Python.
    const [r] = resolverVeredictosPython([
      delRunner({ actual: "hola  \r\nchau\r\n\r\n", expected: "hola\nchau" }),
    ])
    expect(r?.passed).toBe(true)
  })

  it("no perdona una diferencia real de contenido", () => {
    // La otra mitad: si `salidaCoincide` se aflojara a "case-insensitive" o a
    // "ignorar espacios internos", corregiria mal.
    expect(resolverVeredictosPython([delRunner({ actual: "HOLA\n" })])[0]?.passed).toBe(false)
    expect(resolverVeredictosPython([delRunner({ actual: "h o l a\n" })])[0]?.passed).toBe(false)
  })

  it("expected null se compara contra la salida vacia", () => {
    // El runner propaga `case.get("expected")`, que es `None` cuando el caso
    // no declara salida esperada.
    expect(resolverVeredictosPython([delRunner({ expected: null, actual: "" })])[0]?.passed).toBe(
      true,
    )
    expect(
      resolverVeredictosPython([delRunner({ expected: null, actual: "algo\n" })])[0]?.passed,
    ).toBe(false)
  })
})

describe("resolverVeredictosPython — lo que NO se re-evalua", () => {
  it("un pytest_assert conserva el veredicto del runner", () => {
    // Ese `true` lo puso el `assert` de Python, no una comparacion de salida.
    // Pisarlo con `salidaCoincide` seria inventar un veredicto: `expected` de
    // un `pytest_assert` no describe la salida del programa.
    const entrada = delRunner({ type: "pytest_assert", passed: true, actual: "", expected: null })
    expect(resolverVeredictosPython([entrada])[0]?.passed).toBe(true)
  })

  it("un pytest_assert fallado tampoco se re-evalua a passed", () => {
    // El caso peligroso del recorte: sin el filtro por `type`, un assert
    // fallado con salida vacia y `expected: null` coincidiria y pasaria a
    // `true`. Un test rojo que se pone verde solo es peor que uno que se
    // pone rojo.
    const entrada = delRunner({
      type: "pytest_assert",
      passed: false,
      actual: "",
      expected: null,
      error: "La comprobacion no se cumplio: se esperaba 3",
    })
    expect(resolverVeredictosPython([entrada])[0]?.passed).toBe(false)
  })

  it("un caso que murio con excepcion sigue fallado aunque la salida parcial coincida", () => {
    // `actual` es lo que alcanzo a imprimir antes de morir. Compararlo contra
    // `expected` daria un veredicto derivado de una salida truncada.
    const entrada = delRunner({
      actual: "hola\n",
      expected: "hola",
      error: "ZeroDivisionError: division by zero",
    })
    expect(resolverVeredictosPython([entrada])[0]?.passed).toBe(false)
  })

  it("un timeout sigue fallado", () => {
    const entrada = delRunner({
      actual: "hola\n",
      error: "La ejecucion supero el limite de tiempo (posible bucle infinito).",
    })
    expect(resolverVeredictosPython([entrada])[0]?.passed).toBe(false)
  })
})

describe("resolverVeredictosPython — es pura", () => {
  it("no muta la entrada ni la lista original", () => {
    const original = delRunner()
    const copia = { ...original }
    const salida = resolverVeredictosPython([original])
    expect(original).toEqual(copia)
    expect(salida[0]).not.toBe(original)
  })

  it("conserva el orden y el resto de los campos", () => {
    const entrada = [
      delRunner({ id: "a", name: "A" }),
      delRunner({ id: "b", name: "B", actual: "no\n" }),
      delRunner({ id: "c", name: "C", type: "pytest_assert", passed: true }),
    ]
    const salida = resolverVeredictosPython(entrada)
    expect(salida.map((r) => r.id)).toEqual(["a", "b", "c"])
    expect(salida.map((r) => r.passed)).toEqual([true, false, true])
    expect(salida[1]?.actual).toBe("no\n")
    expect(salida[1]?.stdin).toBe("")
  })

  it("la lista vacia devuelve la lista vacia", () => {
    expect(resolverVeredictosPython([])).toEqual([])
  })
})

describe("contarTests — los numeros que viajan al CTR", () => {
  it("cuenta sobre los resultados YA veredictados", () => {
    // El orden de la composicion es la propiedad: contar ANTES del veredicto
    // daria `passed: 0` en toda corrida de Python, que es exactamente lo que
    // pasaba con el `.map()` neutralizado.
    const crudos = [delRunner({ id: "a" }), delRunner({ id: "b", actual: "mal\n" })]
    expect(contarTests(crudos)).toMatchObject({ total: 2, passed: 0, failed: 2 })
    expect(contarTests(resolverVeredictosPython(crudos))).toMatchObject({
      total: 2,
      passed: 1,
      failed: 1,
    })
  })

  it("total = passed + failed, que es el invariante que el server exige", () => {
    // `TutorCore.emit_tests_ejecutados` rechaza con 422 "Conteos
    // inconsistentes" si esto no cierra.
    const conteo = contarTests([
      delRunner({ id: "a", passed: true }),
      delRunner({ id: "b", passed: false }),
      delRunner({ id: "c", passed: false }),
    ])
    expect(conteo.passed + conteo.failed).toBe(conteo.total)
    expect(conteo).toMatchObject({ total: 3, passed: 1, failed: 2 })
  })

  it("failedNames nombra solo los que fallaron, con el name del caso", () => {
    const conteo = contarTests([
      delRunner({ id: "a", name: "Suma", passed: true }),
      delRunner({ id: "b", name: "Resta", passed: false }),
    ])
    expect(conteo.failedNames).toEqual(["Resta"])
  })

  it("cae al id, y despues a 'test', cuando el caso no tiene name", () => {
    // El runner propaga `case.get("name")`, que es `None` en los casos del
    // banco que no lo declaran.
    const conteo = contarTests([
      delRunner({ id: "tc-7", name: null, passed: false }),
      delRunner({ id: null, name: null, passed: false }),
    ])
    expect(conteo.failedNames).toEqual(["tc-7", "test"])
  })

  it("sin casos, todo en cero", () => {
    expect(contarTests([])).toEqual({ total: 0, passed: 0, failed: 0, failedNames: [] })
  })
})
