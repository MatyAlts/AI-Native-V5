/**
 * `__tutor_run_tests` con Python de verdad — el camino de "Probar".
 *
 * Este es el bloque que el doble de `tests/_pyodideFake.ts` reemplaza entero:
 * el fake devuelve el JSON de resultados que se le configuro y nunca corre el
 * codigo. Todo lo que se afirma aca (el aislamiento entre casos, el EOFError,
 * que el guard de imports tambien aplique adentro, que el unicode sobreviva al
 * viaje por el JSON de ida y de vuelta) era indemostrable hasta ahora.
 *
 * Casi todo esto AGUANTO. Se deja escrito igual: un test que pasa marca donde
 * no hace falta volver a mirar, y estos cubren la mitad del editor que decide
 * si un alumno aprueba o no un ejercicio.
 */
import { screen } from "@testing-library/react"
import { afterEach, beforeAll, describe, expect, it } from "vitest"
import type { TestCasePublic } from "../../src/lib/api"
import { montarEditor, probar } from "./_editorHarness"
import { limpiarGlobals, precalentar } from "./_pyodideReal"

let editor: { desmontar(): void } | null = null

beforeAll(async () => {
  await precalentar()
})

afterEach(async () => {
  editor?.desmontar()
  editor = null
  await limpiarGlobals()
})

const caso = (
  id: string,
  name: string,
  code: string,
  expected: string | null,
  type: TestCasePublic["type"] = "stdin_stdout",
): TestCasePublic => ({ id, name, code, expected, type, is_public: true })

/** Texto del panel de Pruebas, que es lo que el alumno lee. */
const panel = (): string => document.body.textContent ?? ""

describe("el runner de tests corre Python de verdad", () => {
  it("el unicode del stdin sobrevive el viaje y la comparacion", async () => {
    // El stdin del caso viaja JS -> JSON -> Python -> `_feed` -> `input()`, y
    // la salida vuelve por el mismo camino para compararse en JS
    // (`resolverVeredictosPython`). Siete fronteras para un emoji.
    const resultados: Array<{ passed: number; failed: number }> = []
    editor = await montarEditor({
      initialCode: "print(input())",
      testCases: [
        caso("c1", "acentos", "José María", "José María"),
        caso("c2", "ñ", "Muñoz", "Muñoz"),
        caso("c3", "emoji", "aprobé 🎉", "aprobé 🎉"),
      ],
      onTestsRun: (r) => resultados.push(r),
    })
    await probar()
    expect(resultados.at(-1)).toMatchObject({ total: 3, passed: 3, failed: 0 })
  })

  it("cada caso corre en un namespace fresco: no hay fuga entre casos", async () => {
    // `ns = {"__name__": "__main__", "input": _feed}` se arma nuevo por caso.
    // Si se compartiera, el segundo caso veria el contador del primero — y un
    // alumno podria aprobar el caso 2 gracias a lo que dejo el caso 1.
    editor = await montarEditor({
      initialCode: `try:
    contador
except NameError:
    contador = 0
contador += 1
print("vuelta", contador)`,
      testCases: [caso("c1", "primero", "", "vuelta 1"), caso("c2", "segundo", "", "vuelta 1")],
    })
    await probar()
    // Los dos casos esperan "vuelta 1". Si el namespace se compartiera, el
    // segundo imprimiria "vuelta 2" y fallaria.
    expect(screen.getByText(/Pasan las 2 pruebas/)).toBeTruthy()
    expect(panel()).not.toContain("vuelta 2")
  })

  it("pedir mas datos de los que el caso provee da un EOFError explicado", async () => {
    // Sin esto el `next()` agotado tiraria un StopIteration crudo dentro de un
    // generador y el alumno leeria un mensaje que no dice nada.
    editor = await montarEditor({
      initialCode: `a = input()
b = input()
print(a, b)`,
      testCases: [caso("c1", "un solo dato", "hola", "hola")],
    })
    await probar()
    expect(panel()).toContain("El programa pidio mas datos (input) de los que este test provee")
  })

  it("el bucle de revalidacion NO se cuelga en Probar (a diferencia de Ejecutar)", async () => {
    // El mismo `while True` que en `cancelarInput.test.tsx` deja al alumno
    // atrapado para siempre: aca termina en milisegundos. La diferencia es que
    // el runner NO usa `window.prompt` sino `_feed`, que se agota y levanta
    // EOFError — y que `_feed` no llama a `_tutor_reset_deadline()`, asi que el
    // watchdog tampoco queda desarmado.
    //
    // O sea: el bug del bucle infinito vive SOLO en el camino interactivo. Este
    // test es el que lo acota.
    const t0 = Date.now()
    editor = await montarEditor({
      initialCode: `while True:
    d = input("n: ")
    try:
        n = int(d)
        break
    except ValueError:
        print("no es un numero")
print(n)`,
      testCases: [caso("c1", "texto invalido", "abc", "1")],
    })
    await probar()
    expect(Date.now() - t0).toBeLessThan(30_000)
    expect(panel()).toContain("El programa pidio mas datos")
  })

  it("el guard de imports tambien vale adentro de los casos", async () => {
    // El guard vive en `sys.meta_path`, que es global al interprete: vale para
    // el `exec` del runner igual que para la corrida interactiva. Si alguna vez
    // el runner pasara a un sub-interprete, esto avisa.
    editor = await montarEditor({
      initialCode: `import js
print(js.document.cookie)`,
      testCases: [caso("c1", "acceso al navegador", "", "x")],
    })
    await probar()
    expect(panel()).toContain("El acceso al navegador esta bloqueado en este editor")
  })

  it("pytest_assert corre el snippet contra el codigo del alumno", async () => {
    editor = await montarEditor({
      initialCode: `def saludo(n):
    return "Hola " + n`,
      testCases: [
        caso("c1", "saluda", "assert saludo('Muñoz') == 'Hola Muñoz'", null, "pytest_assert"),
        caso("c2", "falla", "assert saludo('a') == 'chau'", null, "pytest_assert"),
      ],
    })
    await probar()
    expect(panel()).toContain("Pasan 1 de 2")
    expect(panel()).toContain("La comprobacion no se cumplio")
  })

  it("un error del alumno se reporta por caso, no tumba la corrida entera", async () => {
    editor = await montarEditor({
      initialCode: `n = int(input())
print(n * 2)`,
      testCases: [caso("c1", "numero", "21", "42"), caso("c2", "texto", "abc", "42")],
    })
    await probar()
    expect(panel()).toContain("Pasan 1 de 2")
    // El caso que revienta muestra el tipo de excepcion real de Python.
    expect(panel()).toContain("ValueError")
  })
})
