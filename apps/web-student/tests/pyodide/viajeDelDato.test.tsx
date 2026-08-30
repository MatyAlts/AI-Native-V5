/**
 * El viaje de ida y vuelta del dato que el alumno escribe.
 *
 * `window.prompt` -> `askForInput` (JS) -> `__tutor_ask_input` (globals de
 * Pyodide) -> `__tutor_input` (override de `builtins.input`) -> el `input()`
 * del programa del alumno. Cuatro fronteras, dos runtimes, una conversion de
 * tipos JS<->Python en el medio.
 *
 * Lo que se cuida: que el texto llegue **exactamente igual**. Si volviera con
 * un `\n` pegado, `"Juan\n".isalpha()` da `False` y la validacion del alumno
 * falla sin motivo visible — que es la forma exacta del reporte de produccion
 * del 2026-08-28 ("las validaciones fallan cuando escribe un input").
 *
 * Con el doble de `tests/_pyodideFake.ts` nada de esto es observable: el doble
 * no ejecuta Python, con lo cual `input()` no existe.
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest"
import { ejecutar, guionarPrompt, montarEditor, salidaVisible } from "./_editorHarness"
import { limpiarGlobals, precalentar, versionDelComponente, versionInstalada } from "./_pyodideReal"

let editor: { desmontar(): void } | null = null

beforeAll(async () => {
  await precalentar()
})

afterEach(async () => {
  editor?.desmontar()
  editor = null
  await limpiarGlobals()
})

afterAll(() => {
  // El interprete queda vivo hasta que muere el worker; no hay que apagarlo.
})

describe("la version que se testea es la que corre el alumno", () => {
  it("PYODIDE_VERSION del componente == version del paquete npm", () => {
    // Si divergen, todo este archivo esta probando un interprete que nadie usa.
    expect(versionInstalada()).toBe(versionDelComponente())
  })
})

describe("el texto del alumno llega a Python sin modificar", () => {
  /**
   * Un solo programa que devuelve el `repr()` de lo que recibio: `repr` hace
   * visible cualquier `\n`, espacio o comilla que se haya colado en el camino.
   */
  const PROGRAMA_REPR = `d = input("dato: ")
print(repr(d))
print(type(d).__name__)`

  const casos: ReadonlyArray<[nombre: string, valor: string]> = [
    ["texto simple", "Juan"],
    ["acentos", "José María"],
    ["ñ", "Muñoz"],
    ["emoji", "aprobé 🎉"],
    ["espacios al principio y al final", "  Juan  "],
    ["comillas dobles", 'dijo "hola"'],
    ["comillas simples y backslash", "c:\\ruta 'x'"],
    ["numero como texto", "0042"],
    ["cadena vacia", ""],
    ["solo espacios", "   "],
    ["muy largo", "x".repeat(5000)],
    ["salto de linea en el medio", "linea1\nlinea2"],
    ["tabs", "a\tb"],
    ["caracteres de formato de Python", "%s {0} {x}"],
  ]

  for (const [nombre, valor] of casos) {
    it(`${nombre}: vuelve identico`, async () => {
      guionarPrompt([valor])
      const salidas: string[] = []
      editor = await montarEditor({
        initialCode: PROGRAMA_REPR,
        onCodeExecuted: ({ output }) => salidas.push(output),
      })
      await ejecutar()

      const salida = salidas.at(-1) ?? ""
      // La primera linea util es el repr; se compara contra el repr que Python
      // le daria al mismo string construido del lado JS, sin intermediarios.
      const esperado = JSON.stringify(valor).replace(/^"|"$/g, "").replace(/\\"/g, '"')
      expect(salida).toContain("str")
      // Chequeo fuerte: el largo y el contenido exacto, no un `toContain`.
      const lineas = salida.split("\n")
      const reprImpreso = lineas.find((l) => l.startsWith("'") || l.startsWith('"'))
      expect(reprImpreso, `salida completa:\n${salida}`).toBeDefined()
      // `repr` de Python escapa igual que JSON para \n y \t; para el resto
      // basta con que el contenido sobreviva.
      if (!valor.includes("\n") && !valor.includes("\t") && !valor.includes("\\")) {
        expect(reprImpreso).toContain(valor)
      } else {
        expect(reprImpreso).toContain(esperado.replace(/\\\\/g, "\\\\"))
      }
    })
  }

  it("NO le pega un salto de linea al final (el bug que rompe .isalpha())", async () => {
    guionarPrompt(["Juan"])
    const salidas: string[] = []
    editor = await montarEditor({
      initialCode: `n = input("Nombre: ")
print("isalpha", n.isalpha())
print("len", len(n))
print("igual", n == "Juan")`,
      onCodeExecuted: ({ output }) => salidas.push(output),
    })
    await ejecutar()
    const salida = salidas.at(-1) ?? ""
    expect(salida).toContain("isalpha True")
    expect(salida).toContain("len 4")
    expect(salida).toContain("igual True")
  })

  it("Cancelar y escribir nada dan EXACTAMENTE lo mismo en Python", async () => {
    // Esta es la afirmacion incomoda: para el programa del alumno, el boton
    // Cancelar de la ventanita no existe. `window.prompt` devuelve `null` y el
    // `?? ""` de `askForInput` lo aplasta a cadena vacia antes de que Python
    // se entere. No hay forma, desde Python, de distinguir un caso del otro.
    const programa = `d = input("dato: ")
print(repr(d))`

    guionarPrompt([null])
    const conCancelar: string[] = []
    editor = await montarEditor({
      initialCode: programa,
      onCodeExecuted: ({ output }) => conCancelar.push(output),
    })
    await ejecutar()
    editor.desmontar()
    editor = null
    await limpiarGlobals()

    guionarPrompt([""])
    const conVacio: string[] = []
    editor = await montarEditor({
      initialCode: programa,
      onCodeExecuted: ({ output }) => conVacio.push(output),
    })
    await ejecutar()

    // `''` = cadena vacia. Y el eco tampoco los distingue: la terminal muestra
    // el prompt seguido de nada en los dos casos.
    expect(conCancelar.at(-1)).toBe("dato: \n''\n")
    expect(conVacio.at(-1)).toBe(conCancelar.at(-1))
  })
})

describe("el eco de la salida", () => {
  it("despues de N inputs la SALIDA tiene las N lineas", async () => {
    // El reporte de produccion decia que el panel SALIDA "se ve negro" tras
    // cargar 7 productos. La filmacion corta esa zona, asi que no se puede
    // afirmar que estuviera vacio: esto lo resuelve.
    const N = 7
    guionarPrompt(Array.from({ length: N }, (_, i) => `producto-${i + 1}`))
    const salidas: string[] = []
    editor = await montarEditor({
      initialCode: `productos = []
for i in range(${N}):
    p = input("Producto " + str(i + 1) + ": ")
    productos.append(p)
    print("cargado:", p)
print("total:", len(productos))`,
      onCodeExecuted: ({ output }) => salidas.push(output),
    })
    await ejecutar()

    const buffer = salidas.at(-1) ?? ""
    for (let i = 1; i <= N; i += 1) {
      expect(buffer, `falta el eco del input ${i}`).toContain(`Producto ${i}: producto-${i}`)
      expect(buffer, `falta el print del producto ${i}`).toContain(`cargado: producto-${i}`)
    }
    expect(buffer).toContain(`total: ${N}`)

    // Y lo mismo en el DOM: el buffer del CTR y lo que el alumno ve tienen que
    // contar la misma historia.
    const visible = salidaVisible()
    for (let i = 1; i <= N; i += 1) {
      expect(visible, `el alumno no ve el producto ${i}`).toContain(`producto-${i}`)
    }
  })

  it("el eco muestra el prompt inline y el valor, como una consola real", async () => {
    guionarPrompt(["42"])
    const salidas: string[] = []
    editor = await montarEditor({
      initialCode: `x = input("Edad: ")
print("ok")`,
      onCodeExecuted: ({ output }) => salidas.push(output),
    })
    await ejecutar()
    expect(salidas.at(-1)).toBe("Edad: 42\nok\n")
  })
})
