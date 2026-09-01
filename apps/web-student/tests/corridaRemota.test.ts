/**
 * El timeout de una corrida remota tiene que decirle algo al alumno.
 *
 * EL REPORTE (alumna de Prog 2, 2026-09-01)
 * ------------------------------------------
 * "No puede avanzar en un intento, se queda como un bucle infinito."
 *
 * LO QUE PASABA
 * -------------
 * `timed_out` existía en el tipo `ExecutionResult`, el backend lo medía y lo
 * mandaba en cada respuesta, y **no lo leía nadie**. `git grep timed_out` sobre
 * los tres frontends devolvía una sola línea: la declaración del campo.
 *
 * Con lo cual, en Java (que corre en el servidor), un bucle infinito del alumno
 * terminaba así:
 *
 *   1. el contenedor se mata a los 10 s de wall-time;
 *   2. el payload de modo libre manda `outcome: "completed"` SIEMPRE, así que
 *      no entra por la rama de `infrastructure_failure`;
 *   3. `stderr` viene vacío —lo matamos nosotros, no hubo excepción Java— así
 *      que `parseJavaError` no encuentra nada;
 *   4. el alumno ve su salida parcial y NINGÚN mensaje.
 *
 * Desde su lado el programa "anduvo". Entonces vuelve a apretar Ejecutar. Y
 * otra vez. El bucle infinito que ella reporta es el de los intentos.
 *
 * LO QUE MÁS DUELE
 * ----------------
 * La plataforma ya sabía decirlo, en los otros dos caminos:
 *   - Python: el watchdog levanta "La ejecución superó los 5 segundos… Revisá
 *     si tenés un bucle infinito".
 *   - Java modo "Probar": `_ERROR_MESSAGE[TIME_LIMIT_EXCEEDED]` dice "posible
 *     bucle infinito".
 *
 * El único mudo era "Ejecutar" en un lenguaje remoto — justo el botón que se
 * aprieta mientras se escribe el programa.
 */
import { describe, expect, it } from "vitest"
import { MENSAJE_TIMEOUT, PISTA_ENTRADA_VACIA, mensajeDeCorrida } from "../src/lib/corridaRemota"

describe("mensajeDeCorrida", () => {
  it("un timeout SIN error de Java produce mensaje", () => {
    // El corazón del fix, y el caso exacto del reporte: el contenedor lo
    // matamos nosotros, así que no hay excepción Java que parsear.
    //
    // Verificado por reversión: sin leer `timed_out`, esto devuelve null, no se
    // llama a `setError`, y el alumno se queda mirando una salida parcial sin
    // saber que su programa fue interrumpido.
    expect(mensajeDeCorrida({ timed_out: true, errorJava: null })).toBe(MENSAJE_TIMEOUT)
  })

  it("una corrida normal no dice nada", () => {
    // El mensaje no puede aparecer donde no corresponde: un cartel de "bucle
    // infinito" sobre un programa que anduvo bien enseña lo contrario de lo que
    // queremos.
    expect(mensajeDeCorrida({ timed_out: false, errorJava: null })).toBeNull()
  })

  it("sin el campo tampoco dice nada", () => {
    // Un backend viejo, o un rollback a mitad de deploy, no manda `timed_out`.
    // Ausente NO es `true`.
    expect(mensajeDeCorrida({})).toBeNull()
  })

  it("el error de Java gana sobre el timeout", () => {
    // Una excepción con línea y causa es información concreta; el timeout es
    // una hipótesis sobre por qué tardó. Entre las dos, la concreta.
    expect(
      mensajeDeCorrida({ timed_out: true, errorJava: "NullPointerException en la linea 12" }),
    ).toBe("NullPointerException en la linea 12")
  })

  it("un error de Java sin timeout se propaga tal cual", () => {
    expect(mensajeDeCorrida({ timed_out: false, errorJava: "cannot find symbol" })).toBe(
      "cannot find symbol",
    )
  })
})

describe("el mensaje sirve para actuar", () => {
  it("nombra el bucle, que es la causa mas probable", () => {
    expect(MENSAJE_TIMEOUT.toLowerCase()).toContain("bucle")
  })

  it("la pista de la ENTRADA nombra la causa que nadie sospecha", () => {
    // En Java el stdin viaja entero y por adelantado: no hay `input()`
    // interactivo, porque un contenedor efímero no tiene canal de vuelta.
    //
    // El bucle infinito más común de quien recién arranca es el que valida la
    // entrada sin consumirla:
    //
    //     while (!sc.hasNextInt()) { System.out.println("Ingresá un número"); }
    //
    // Con la caja "Entrada" vacía, `hasNextInt()` devuelve false para siempre y
    // el bucle gira sin leer nada. Sin esta pista el alumno busca el error en la
    // condición del while —que está bien— en vez de en la entrada, que falta.
    expect(PISTA_ENTRADA_VACIA).toContain("Entrada")
    expect(PISTA_ENTRADA_VACIA).toContain("Scanner")
  })

  it("con la entrada VACIA, el mensaje trae la pista", () => {
    const m = mensajeDeCorrida({ timed_out: true, stdinVacio: true })

    expect(m).toContain("bucle")
    expect(m).toContain("Entrada")
  })

  it("con la entrada LLENA, NO la trae — una pista falsa cuesta mas que ninguna", () => {
    // El alumno con datos en la caja se iria a revisar su entrada, que está
    // bien, mientras el bucle de verdad sigue en otro lado. Es el mismo defecto
    // que el "Abrí cada ejercicio una vez antes de entregar" del PR #86: una
    // instrucción precisa, dicha con seguridad, sobre algo que nadie verificó.
    const m = mensajeDeCorrida({ timed_out: true, stdinVacio: false })

    expect(m).toContain("bucle")
    expect(m).not.toContain("Entrada")
    expect(m).not.toContain("Scanner")
  })

  it("si no se sabe si la entrada estaba vacia, tampoco adivina", () => {
    // `undefined` es "no lo sé". Ante la duda, el mensaje que siempre es cierto.
    const m = mensajeDeCorrida({ timed_out: true })

    expect(m).toBe(MENSAJE_TIMEOUT)
    expect(m).not.toContain("Entrada")
  })

  it("no culpa al alumno de algo que no hizo", () => {
    // Un timeout NO es un fallo de infraestructura y no debe leerse como tal, ni
    // al revés. El mensaje describe lo que pasó y qué mirar, sin acusar.
    const t = MENSAJE_TIMEOUT.toLowerCase()
    expect(t).not.toContain("error tuyo")
    expect(t).not.toContain("fallaste")
  })
})

describe("regresion: la corrida cortada NO es exitosa", () => {
  it("hay mensaje, entonces no hubo exito", () => {
    // La propiedad que fija el tercer defecto del mismo reporte.
    //
    // El editor calculaba el éxito como `!javaErr`. Con un timeout, `javaErr`
    // es null, así que la corrida entraba al historial con el tilde verde Y
    // viajaba al CTR como `codigo_ejecutado` sin error: el registro afirmaba
    // que el alumno ejecutó su programa con éxito justo cuando su programa no
    // terminó.
    //
    // Ahora el éxito se deriva de `mensajeDeCorrida(...) === null`, así que las
    // dos cosas no pueden volver a separarse.
    const conTimeout = mensajeDeCorrida({ timed_out: true, errorJava: null })
    expect(conTimeout === null).toBe(false)

    const normal = mensajeDeCorrida({ timed_out: false, errorJava: null })
    expect(normal === null).toBe(true)
  })
})
