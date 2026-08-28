/**
 * JAVA-2 / H6 — los campos `final` NO son un caso, son TRES.
 *
 * La regla ingenua —"los `final` quedan afuera del constructor"— cambia un
 * error de compilacion por otro, y el segundo es peor porque aparece sobre una
 * clase que el alumno cree bien escrita:
 *
 *   | declaracion                              | setter | constructor | si no va al ctor          |
 *   |------------------------------------------|--------|-------------|---------------------------|
 *   | `private final int x = 5;`                | NO     | NO          | compila                   |
 *   | `private static final int MAX = 20;`      | NO     | NO          | compila                   |
 *   | `private final String nombre;` (blank)    | NO     | SI          | "might not have been       |
 *   |                                           |        |             |  initialized" — NO compila |
 *
 * Las tres filas se verificaron con `javac` real (no se dedujeron del lenguaje)
 * y las tres tienen que estar acá: cubrir solo la constante estatica —el caso
 * idiomatico de Programacion 1— deja pasar la regla ingenua entera.
 *
 * Los fixtures no se inventan: se PARSEAN con `parseFields` desde el codigo
 * Java literal. Un `FieldDecl` armado a mano fijaria el test contra mi lectura
 * de los modificadores en vez de contra la del parser, y si el parser dejara de
 * reconocer `final` estos tests seguirian verdes mientras produccion genera
 * Java roto.
 */

import { describe, expect, it } from "vitest"
import {
  admiteAsignacionEnConstructor,
  admiteSetter,
  constructorSource,
  equalsSource,
  parseFields,
  registerJavaSnippets,
} from "../src/lib/javaSnippets"
import { crearMonacoFalso } from "./_monacoSnippetsFake"

/** Parsea UN campo desde su declaracion Java literal. */
function decl(linea: string) {
  const campos = parseFields(`class A {\n    ${linea}\n}`)
  const campo = campos[0]
  if (!campo) throw new Error(`parseFields no reconocio: ${linea}`)
  return campo
}

const NO_FINAL = "private String nombre;"
const FINAL_CON_INICIALIZADOR = "private final int base = 5;"
const CONSTANTE = "private static final int MAX_TURNOS = 20;"
const BLANK_FINAL = "private final String nombre;"
const BLANK_FINAL_STATIC = "private static final String VERSION;"

describe("el parser reconoce los modificadores (base de todo lo demas)", () => {
  it("distingue las cinco formas", () => {
    expect(decl(NO_FINAL)).toMatchObject({ esFinal: false, esStatic: false })
    expect(decl(FINAL_CON_INICIALIZADOR)).toMatchObject({
      esFinal: true,
      esStatic: false,
      tieneInicializador: true,
    })
    expect(decl(CONSTANTE)).toMatchObject({
      esFinal: true,
      esStatic: true,
      tieneInicializador: true,
    })
    expect(decl(BLANK_FINAL)).toMatchObject({
      esFinal: true,
      esStatic: false,
      tieneInicializador: false,
    })
    expect(decl(BLANK_FINAL_STATIC)).toMatchObject({
      esFinal: true,
      esStatic: true,
      tieneInicializador: false,
    })
  })
})

describe("admiteSetter — ningun final lleva setter", () => {
  it("un campo comun si", () => {
    expect(admiteSetter(decl(NO_FINAL))).toBe(true)
  })

  it("los cuatro finales no", () => {
    // `javac`: "cannot assign a value to final variable" (y "...to static final
    // variable" cuando ademas es `static`). El getter SI puede ir: leer una
    // constante es legitimo, y eso lo cubre el proveedor mas abajo.
    for (const linea of [FINAL_CON_INICIALIZADOR, CONSTANTE, BLANK_FINAL, BLANK_FINAL_STATIC]) {
      expect(admiteSetter(decl(linea)), linea).toBe(false)
    }
  })
})

describe("admiteAsignacionEnConstructor — los tres casos que NO son el mismo", () => {
  it("no final: siempre va", () => {
    expect(admiteAsignacionEnConstructor(decl(NO_FINAL))).toBe(true)
  })

  it("final CON inicializador: no va — ya tiene valor", () => {
    // `this.base = base` sobre un campo ya inicializado es
    // "cannot assign a value to final variable".
    expect(admiteAsignacionEnConstructor(decl(FINAL_CON_INICIALIZADOR))).toBe(false)
  })

  it("static final con inicializador (la constante idiomatica): no va", () => {
    expect(admiteAsignacionEnConstructor(decl(CONSTANTE))).toBe(false)
  })

  it("blank final DE INSTANCIA: SI va — sin eso la clase no compila", () => {
    // El caso que la regla ingenua se lleva puesto. `javac` sobre una clase con
    // `private final String nombre;` y un constructor que no lo asigna:
    // "variable nombre might not have been initialized".
    expect(admiteAsignacionEnConstructor(decl(BLANK_FINAL))).toBe(true)
  })

  it("blank final STATIC: no va — se asigna en un bloque static { }", () => {
    // La otra mitad del caso anterior: `static` cambia el veredicto. Una regla
    // que solo mirara `tieneInicializador` metaria `this.VERSION = VERSION` en
    // el constructor, que es "cannot assign a value to static final variable".
    expect(admiteAsignacionEnConstructor(decl(BLANK_FINAL_STATIC))).toBe(false)
  })
})

describe("constructorSource — la regla llega al codigo generado", () => {
  const CLASE = `class Turno {
    private String paciente;
    private final String id;
    private final int base = 5;
    private static final int MAX_TURNOS = 20;
}`

  it("lleva los asignables y solo los asignables", () => {
    const fuente = constructorSource("Turno", parseFields(CLASE))
    expect(fuente).toContain("public Turno(String paciente, String id) {")
    expect(fuente).toContain("this.paciente = paciente;")
    // El blank final de instancia TIENE que estar: sin el, "might not have
    // been initialized".
    expect(fuente).toContain("this.id = id;")
    // Y las dos constantes NO: "cannot assign a value to (static) final".
    expect(fuente).not.toContain("base")
    expect(fuente).not.toContain("MAX_TURNOS")
  })

  it("una clase de puras constantes produce un constructor SIN parametros", () => {
    // No es un caso teorico: es la clase `Config` con `MAX_TURNOS` y nada mas.
    // El proveedor no ofrece este `ctor` justamente porque saldria identico a
    // `ctorvacio` (ver el bloque del proveedor mas abajo), pero la funcion es
    // exportada y no puede devolver `public Config(int MAX_TURNOS)`.
    const fuente = constructorSource(
      "Config",
      parseFields("class Config {\n    private static final int MAX_TURNOS = 20;\n}"),
    )
    expect(fuente).toBe("public Config() {\n}")
  })
})

describe("equalsSource — el caso vacio no puede generar Java roto", () => {
  it("sin campos NO produce `return ;`", () => {
    // `fields.map(...).join(" && ")` sobre una lista vacia da `""`, y la linea
    // sale `return ;` — que no compila. La funcion es exportada y el hueco
    // estaba solo acá: `toStringSource` si manejaba su caso vacio.
    const fuente = equalsSource("Vacia", [])
    expect(fuente).not.toContain("return ;")
    expect(fuente).not.toMatch(/return\s*;/)
  })

  it("sin campos, la igualdad es por clase y las dos guardas alcanzan", () => {
    // Dos instancias de una clase sin estado son iguales si son de la misma
    // clase. El `equals` generado tiene que decir eso, no cualquier cosa que
    // compile.
    expect(equalsSource("Vacia", [])).toBe(
      [
        "@Override",
        "public boolean equals(Object o) {",
        "    if (this == o) return true;",
        "    return o != null && getClass() == o.getClass();",
        "}",
      ].join("\n"),
    )
  })

  it("no declara el cast a una variable que despues no usa", () => {
    // Un `Vacia otro = (Vacia) o;` sin campos que comparar es un warning de
    // variable no usada sobre codigo que el alumno no escribio.
    expect(equalsSource("Vacia", [])).not.toContain("(Vacia) o")
  })

  it("con campos sigue armando la comparacion completa", () => {
    // Contraste: el recorte del caso vacio no puede haberse comido el camino
    // normal.
    const fuente = equalsSource("Persona", parseFields("class P {\n    private int edad;\n}"))
    expect(fuente).toContain("Persona otro = (Persona) o;")
    expect(fuente).toContain("return this.edad == otro.edad;")
  })
})

describe("el proveedor de snippets aplica las tres reglas", () => {
  const CON_BLANK_FINAL = `class Turno {
    private final String id;
    private String paciente;
}`

  const SOLO_CONSTANTES = `class Config {
    private static final int MAX_TURNOS = 20;
}`

  function etiquetas(source: string): string[] {
    const fake = crearMonacoFalso()
    registerJavaSnippets(fake.monaco, () => {})
    return fake.sugerencias(source).map((s) => String(s.label))
  }

  it("no ofrece setter de un campo final, pero si su getter", () => {
    const labels = etiquetas(CON_BLANK_FINAL)
    expect(labels).toContain("getId")
    expect(labels).not.toContain("setId")
    // Y el campo comun conserva los dos, o el test estaria pasando porque el
    // proveedor no ofrece nada.
    expect(labels).toEqual(expect.arrayContaining(["getPaciente", "setPaciente"]))
  })

  it("con un blank final de instancia NO ofrece `ctorvacio`", () => {
    // El unico constructor legal es el que asigna el blank final. Ofrecer
    // `ctorvacio` es ofrecer una clase que no compila.
    const labels = etiquetas(CON_BLANK_FINAL)
    expect(labels).toContain("ctor")
    expect(labels).not.toContain("ctorvacio")
  })

  it("sin blank final si ofrece `ctorvacio`", () => {
    // El contraste que hace no-vacuo al anterior: un proveedor que nunca
    // ofreciera `ctorvacio` pasaria aquel test igual.
    expect(etiquetas("class Turno {\n    private String paciente;\n}")).toContain("ctorvacio")
  })

  it("una clase de puras constantes no ofrece `ctor`", () => {
    // Sin campos asignables, `constructorSource` armaria un `public Config()
    // {}` identico a `ctorvacio`: la misma sugerencia dos veces en la lista.
    const labels = etiquetas(SOLO_CONSTANTES)
    expect(labels).not.toContain("ctor")
    expect(labels).toContain("ctorvacio")
  })
})
