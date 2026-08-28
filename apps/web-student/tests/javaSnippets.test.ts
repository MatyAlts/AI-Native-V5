import { describe, expect, it } from "vitest"
import {
  type FieldDecl,
  capitalize,
  getterName,
  getterSource,
  importInsertLine,
  parseFields,
  setterName,
  setterSource,
} from "../src/lib/javaSnippets"

/**
 * Campo comun de Programacion 1: ni `final`, ni `static`, ni inicializado en la
 * declaracion. Los tres modificadores son parte de `FieldDecl` desde H6 —
 * `admiteSetter` y `admiteAsignacionEnConstructor` los miran para no generar
 * Java que no compila sobre una constante. Los casos que SI llevan
 * modificadores se escriben con el literal completo, para que se vean.
 */
function campo(type: string, name: string): FieldDecl {
  return { type, name, esFinal: false, esStatic: false, tieneInicializador: false }
}

// Clase tipica de Programacion 1: campos privados con tipos mixtos.
const CLASE_PRODUCTO = `public class Main {
    private String nombre;
    private int cantidad;
    private double precioUnitario;
    private boolean activo;

    public static void main(String[] args) {
    }
}`

describe("parseFields", () => {
  it("extrae tipo y nombre de cada campo privado", () => {
    expect(parseFields(CLASE_PRODUCTO)).toEqual([
      campo("String", "nombre"),
      campo("int", "cantidad"),
      campo("double", "precioUnitario"),
      campo("boolean", "activo"),
    ])
  })

  it("ignora campos que no son private", () => {
    const src = `public class Main {
    public int visible;
    protected int protegido;
    int packagePrivate;
    private int oculto;
}`
    expect(parseFields(src)).toEqual([campo("int", "oculto")])
  })

  it("acepta modificadores extra y arrays y genericos", () => {
    const src = `class A {
    private static final int MAX = 10;
    private int[] numeros;
    private List<String> nombres;
}`
    expect(parseFields(src)).toEqual([
      // Los modificadores se CAPTURAN, no se descartan: `MAX` es la constante
      // idiomatica de Programacion 1 y `admiteSetter` /
      // `admiteAsignacionEnConstructor` la reconocen por estos tres flags.
      { type: "int", name: "MAX", esFinal: true, esStatic: true, tieneInicializador: true },
      campo("int[]", "numeros"),
      campo("List<String>", "nombres"),
    ])
  })

  it("no duplica si el mismo nombre aparece dos veces", () => {
    const src = "class A {\n    private int x;\n    private int x;\n}"
    expect(parseFields(src)).toEqual([campo("int", "x")])
  })

  it("es estable entre llamadas (lastIndex de la regex global reseteado)", () => {
    // Sin resetear `lastIndex` la segunda llamada arrancaria donde quedo la
    // primera y devolveria menos campos — bug clasico de regex /g compartida.
    expect(parseFields(CLASE_PRODUCTO)).toEqual(parseFields(CLASE_PRODUCTO))
  })

  it("devuelve vacio si no hay campos", () => {
    expect(parseFields("public class Main {}")).toEqual([])
  })
})

describe("nombres de accesores", () => {
  it("capitaliza la primera letra", () => {
    expect(capitalize("precioUnitario")).toBe("PrecioUnitario")
    expect(capitalize("")).toBe("")
  })

  it("usa get/set para tipos no booleanos", () => {
    const f = campo("String", "nombre")
    expect(getterName(f)).toBe("getNombre")
    expect(setterName(f)).toBe("setNombre")
  })

  it("usa is para booleanos (convencion JavaBeans)", () => {
    expect(getterName(campo("boolean", "activo"))).toBe("isActivo")
  })

  it("no duplica el prefijo si el campo boolean ya se llama isX", () => {
    expect(getterName(campo("boolean", "isActivo"))).toBe("isActivo")
  })
})

describe("cuerpo de los accesores", () => {
  it("genera un getter compilable", () => {
    expect(getterSource(campo("double", "precio"))).toBe(
      "public double getPrecio() {\n    return precio;\n}",
    )
  })

  it("genera un setter compilable con this", () => {
    expect(setterSource(campo("int", "cantidad"))).toBe(
      "public void setCantidad(int cantidad) {\n    this.cantidad = cantidad;\n}",
    )
  })
})

describe("importInsertLine", () => {
  it("inserta arriba de todo si no hay imports ni package", () => {
    expect(importInsertLine(["public class Main {", "}"])).toBe(1)
  })

  it("inserta despues del ultimo import existente", () => {
    const lines = ["import java.util.List;", "import java.util.Map;", "", "public class Main {"]
    expect(importInsertLine(lines)).toBe(3)
  })

  it("respeta la linea package cuando no hay imports", () => {
    expect(importInsertLine(["package ar.utn;", "", "public class Main {"])).toBe(2)
  })
})
