import { describe, expect, it } from "vitest"
import {
  capitalize,
  getterName,
  getterSource,
  importInsertLine,
  parseFields,
  setterName,
  setterSource,
} from "../src/lib/javaSnippets"

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
      { type: "String", name: "nombre" },
      { type: "int", name: "cantidad" },
      { type: "double", name: "precioUnitario" },
      { type: "boolean", name: "activo" },
    ])
  })

  it("ignora campos que no son private", () => {
    const src = `public class Main {
    public int visible;
    protected int protegido;
    int packagePrivate;
    private int oculto;
}`
    expect(parseFields(src)).toEqual([{ type: "int", name: "oculto" }])
  })

  it("acepta modificadores extra y arrays y genericos", () => {
    const src = `class A {
    private static final int MAX = 10;
    private int[] numeros;
    private List<String> nombres;
}`
    expect(parseFields(src)).toEqual([
      { type: "int", name: "MAX" },
      { type: "int[]", name: "numeros" },
      { type: "List<String>", name: "nombres" },
    ])
  })

  it("no duplica si el mismo nombre aparece dos veces", () => {
    const src = "class A {\n    private int x;\n    private int x;\n}"
    expect(parseFields(src)).toEqual([{ type: "int", name: "x" }])
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
    const f = { type: "String", name: "nombre" }
    expect(getterName(f)).toBe("getNombre")
    expect(setterName(f)).toBe("setNombre")
  })

  it("usa is para booleanos (convencion JavaBeans)", () => {
    expect(getterName({ type: "boolean", name: "activo" })).toBe("isActivo")
  })

  it("no duplica el prefijo si el campo boolean ya se llama isX", () => {
    expect(getterName({ type: "boolean", name: "isActivo" })).toBe("isActivo")
  })
})

describe("cuerpo de los accesores", () => {
  it("genera un getter compilable", () => {
    expect(getterSource({ type: "double", name: "precio" })).toBe(
      "public double getPrecio() {\n    return precio;\n}",
    )
  })

  it("genera un setter compilable con this", () => {
    expect(setterSource({ type: "int", name: "cantidad" })).toBe(
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
