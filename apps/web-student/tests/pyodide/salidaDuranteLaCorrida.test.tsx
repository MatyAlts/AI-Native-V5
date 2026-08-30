/**
 * Lo que el alumno VE mientras su programa le pide datos.
 *
 * Todo esto vive en la costura entre los tres buffers que el editor mantiene
 * en paralelo durante una corrida interactiva:
 *
 * 1. el buffer interno de Pyodide (`setStdout({ batched })` acumula hasta el
 *    proximo `\n` antes de llamar al handler),
 * 2. `outputBufferRef`, el espejo sincrono que alimenta el mensaje de la
 *    ventanita,
 * 3. el state `output` de React, que es lo unico que se pinta en pantalla.
 *
 * Con `tests/_pyodideFake.ts` los tres coinciden siempre, porque no hay
 * Python que los desincronice. Con Pyodide real no coinciden, y las
 * diferencias son visibles para el alumno.
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest"
import { ejecutar, guionarPrompt, montarEditor, salidaVisible } from "./_editorHarness"
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

describe("el panel SALIDA durante la corrida", () => {
  it("BUG: esta VACIO todo el tiempo que el programa pide datos", async () => {
    // El reporte de produccion (video del 2026-08-28) decia que el panel
    // SALIDA "se ve negro" despues de cargar 7 productos, pero la filmacion
    // corta esa zona de la pantalla y no se podia afirmar. Esto lo resuelve:
    // el panel esta vacio en las 7 ventanitas, una por una.
    //
    // Por que: `setOutput` es un state update de React, y `window.prompt`
    // bloquea el event loop del navegador de forma sincrona. React no llega a
    // repintar entre dos inputs. El editor ya sabe de este bloqueo —para eso
    // existe `outputBufferRef`, que alimenta el texto de la ventanita— pero el
    // PANEL sigue leyendo el state, asi que no se entera de nada hasta que el
    // programa termina.
    //
    // Consecuencia practica: el alumno con un `while True` (el caso de
    // `cancelarInput.test.tsx`) ve una terminal negra PARA SIEMPRE, porque el
    // programa no termina nunca.
    const vistas: string[] = []
    let i = 0
    guionarPrompt([], () => {
      vistas.push(salidaVisible())
      i += 1
      return i >= 7 ? "fin" : `producto-${i}`
    })

    editor = await montarEditor({
      initialCode: `productos = []
while True:
    p = input("Producto: ")
    if p == "fin":
        break
    productos.append(p)
    print("cargado", p)
print("total", len(productos))`,
    })
    await ejecutar()

    expect(vistas).toHaveLength(7)
    // Ni una sola de las 7 ventanitas se abrio con algo escrito en el panel.
    for (const [n, v] of vistas.entries()) {
      expect(v, `en el input ${n + 1} el panel mostraba: ${JSON.stringify(v)}`).toBe("")
    }

    // Y recien al terminar aparece todo junto — lo que confirma que la salida
    // NO se estaba perdiendo: se estaba reteniendo.
    const final = salidaVisible()
    for (let n = 1; n <= 6; n += 1) {
      expect(final).toContain(`cargado producto-${n}`)
    }
    expect(final).toContain("total 6")
  })

  it("la ventanita SI muestra lo impreso (por eso existe outputBufferRef)", async () => {
    // La contracara: el mecanismo que si funciona. Sin prompt inline, el
    // mensaje de la ventanita se arma con lo que el programa ya imprimio.
    const guion = guionarPrompt(["z"])
    editor = await montarEditor({
      initialCode: `print("Cargue el nombre del producto")
x = input()
print("ok", x)`,
    })
    await ejecutar()
    expect(guion.mensajes[0]).toContain("Cargue el nombre del producto")
  })

  it("BUG: sin prompt inline, la ventanita arrastra TODA la salida acumulada", async () => {
    // `guia = inline || outputBufferRef.current.trim()` toma el buffer ENTERO,
    // no la ultima linea. Con un programa que imprime un menu y despues pide
    // un dato con `input()` pelado, la ventanita se vuelve un muro de texto
    // que crece en cada vuelta. A la septima vuelta, el alumno lee su propio
    // historial completo cada vez que tiene que cargar un producto.
    const guion = guionarPrompt(["1", "2", "3"])
    editor = await montarEditor({
      initialCode: `for i in range(3):
    print("=== Menu ===")
    print("1) Cargar producto")
    print("2) Salir")
    input()`,
    })
    await ejecutar()

    const primera = guion.mensajes[0] ?? ""
    const tercera = guion.mensajes[2] ?? ""
    // La primera ya trae el menu entero (3 lineas).
    expect(primera).toContain("=== Menu ===")
    // Y la tercera trae TRES menus: el mensaje crece sin techo.
    expect((tercera.match(/=== Menu ===/g) ?? []).length).toBe(3)
    expect(tercera.length).toBeGreaterThan(primera.length * 2)
  })
})

describe("el orden de la salida", () => {
  it("BUG: con print(end='') antes de input(), la respuesta aparece ANTES de la pregunta", async () => {
    // `print("Ingrese el nombre: ", end="")` no lleva `\n`, asi que se queda en
    // el buffer interno de Pyodide sin llamar al handler `batched`. El eco del
    // input, en cambio, se escribe directo en `outputBufferRef`. Resultado: el
    // valor tipeado se cuela ADELANTE del texto que lo pedia.
    //
    // El editor ya arreglo esta clase de problema para `input("texto")` —el
    // comentario de `askForInput` lo explica— pero interceptar `builtins.input`
    // no cubre el `print(..., end="")` que hace exactamente lo mismo, y que es
    // como se ensena a formatear la pregunta en la misma linea.
    const guion = guionarPrompt(["Juan"])
    const salidas: string[] = []
    editor = await montarEditor({
      initialCode: `print("Ingrese el nombre: ", end="")
n = input()
print("hola", n)`,
      onCodeExecuted: ({ output }) => salidas.push(output),
    })
    await ejecutar()

    const salida = salidas.at(-1) ?? ""
    // Lo que el alumno lee es esto:
    expect(salida).toBe("Juan\nIngrese el nombre: hola Juan\n")
    // Dicho como propiedad: la respuesta aparece antes que la pregunta.
    expect(salida.indexOf("Juan")).toBeLessThan(salida.indexOf("Ingrese el nombre"))

    // Y encima la ventanita no puede decirle QUE le esta pidiendo: el texto
    // seguia atascado en el buffer de Pyodide cuando se armo el mensaje.
    expect(guion.mensajes[0]).toBe("El programa pide un dato de entrada (input):")
  })

  it("con print() normal (con salto) el orden se respeta", async () => {
    // El mismo programa con `print()` en vez de `print(end="")` sale bien: el
    // `\n` fuerza el flush del `batched` antes de que llegue el eco. O sea que
    // el bug de arriba es del flush, no del eco.
    guionarPrompt(["Juan"])
    const salidas: string[] = []
    editor = await montarEditor({
      initialCode: `print("Ingrese el nombre:")
n = input()
print("hola", n)`,
      onCodeExecuted: ({ output }) => salidas.push(output),
    })
    await ejecutar()
    expect(salidas.at(-1)).toBe("Ingrese el nombre:\nJuan\nhola Juan\n")
  })

  it("stdout y stderr conservan el orden entre si", async () => {
    // Son dos handlers `batched` distintos escribiendo al mismo buffer; que no
    // se pisen ni se reordenen no es gratis.
    guionarPrompt([])
    const salidas: string[] = []
    editor = await montarEditor({
      initialCode: `import sys
print("uno")
print("dos", file=sys.stderr)
print("tres")`,
      onCodeExecuted: ({ output }) => salidas.push(output),
    })
    await ejecutar()
    expect(salidas.at(-1)).toBe("uno\ndos\ntres\n")
  })

  it("print(end='') consecutivos se concatenan sin saltos espurios", async () => {
    // El handler `batched` agrega `\n` a cada lote. Si Pyodide lotease por
    // llamada a print en vez de por linea, esto daria "a\nb\nc\n".
    guionarPrompt([])
    const salidas: string[] = []
    editor = await montarEditor({
      initialCode: `print("a", end="")
print("b", end="")
print("c")`,
      onCodeExecuted: ({ output }) => salidas.push(output),
    })
    await ejecutar()
    expect(salidas.at(-1)).toBe("abc\n")
  })
})
