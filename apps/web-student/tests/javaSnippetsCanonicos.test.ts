/**
 * JAVA-2 — constructores y overrides canonicos de los snippets Java.
 *
 * Archivo aparte de `javaSnippets.test.ts` (que cubre campos y accesores)
 * porque lo que se protege aca es otra cosa: el cuerpo de estos snippets queda
 * DETERMINADO por los campos —dado el conjunto de campos, el constructor, el
 * `toString`, el `equals` y el `hashCode` se escriben siempre igual— y lo unico
 * que puede salir mal es que el codigo generado este mal.
 *
 * Y "mal" aca no significa "no compila". Significa **compila y anda mal**: un
 * array concatenado con `+` imprime `[I@1b6d3586`, un `double` comparado con
 * `==` rompe el contrato de `equals` con `NaN`. El alumno acepta el snippet, no
 * lo revisa, y arrastra el error. Un snippet que ensena mal es peor que no
 * ofrecer nada.
 *
 * Los tests marcados **LIMITACION CONOCIDA** documentan el comportamiento TAL
 * COMO ES, no como deberia ser. No son aprobacion: son el registro de que se
 * verifico y de que si alguien lo arregla, el test que cae le dice que ese caso
 * estaba declarado.
 */

import { describe, expect, it } from "vitest"
import {
  constructorSource,
  declaredConstructorParams,
  emptyConstructorSource,
  equalsSource,
  hashCodeSource,
  importsParaIgualdad,
  importsParaToString,
  parseClassBlocks,
  parseFields,
  registerJavaSnippets,
  toStringSource,
} from "../src/lib/javaSnippets"
import { crearMonacoFalso } from "./_monacoSnippetsFake"

/** Clase auxiliar tipica de Programacion 1: dos campos, tipos mixtos. */
const CLASE_PERSONA = `class Persona {
    private String nombre;
    private int edad;
}`

describe("parseClassBlocks", () => {
  it("parte el archivo por declaracion y cada bloque se queda con SUS campos", () => {
    const src = `public class Main {
    public static void main(String[] args) {
    }
}

class Persona {
    private String nombre;
}`
    const bloques = parseClassBlocks(src)
    expect(bloques.map((b) => b.name)).toEqual(["Main", "Persona"])
    // Un constructor de `Main` con los campos de `Persona` no seria ceremonia,
    // seria basura: por eso los overrides se resuelven POR BLOQUE y no sobre el
    // archivo entero como los accesores.
    expect(parseFields(bloques[1]?.source ?? "")).toEqual([{ type: "String", name: "nombre" }])
    expect(parseFields(bloques[0]?.source ?? "")).toEqual([])
  })

  it("acepta modificadores en la declaracion", () => {
    const src = "public final class A {}\nabstract class B {}\nclass C {}"
    expect(parseClassBlocks(src).map((b) => b.name)).toEqual(["A", "B", "C"])
  })

  it("el ultimo bloque llega hasta el fin del archivo", () => {
    const bloques = parseClassBlocks("class A {}\nclass B {\n    private int x;\n}")
    expect(bloques[1]?.source).toContain("private int x;")
  })

  it("sin ninguna clase devuelve vacio", () => {
    expect(parseClassBlocks("// solo un comentario")).toEqual([])
  })

  it("es estable entre llamadas (lastIndex de la regex global reseteado)", () => {
    expect(parseClassBlocks(CLASE_PERSONA)).toEqual(parseClassBlocks(CLASE_PERSONA))
  })
})

describe("declaredConstructorParams", () => {
  it("el constructor sin argumentos aparece como lista vacia", () => {
    expect(declaredConstructorParams("class P {\n    public P() {\n    }\n}", "P")).toEqual([""])
  })

  it("devuelve la lista cruda de parametros del constructor con argumentos", () => {
    const src = "class Persona {\n    public Persona(String nombre, int edad) {\n    }\n}"
    expect(declaredConstructorParams(src, "Persona")).toEqual(["String nombre, int edad"])
  })

  it("encuentra los dos si estan sobrecargados", () => {
    const src = [
      "class Persona {",
      "    public Persona() {",
      "    }",
      "    public Persona(String nombre) {",
      "    }",
      "}",
    ].join("\n")
    expect(declaredConstructorParams(src, "Persona")).toEqual(["", "String nombre"])
  })

  it("no confunde `new Persona(...)` con la declaracion del constructor", () => {
    const src = 'class Main {\n    Persona p = new Persona("Ana", 20);\n}'
    expect(declaredConstructorParams(src, "Persona")).toEqual([])
  })

  it("escapa el $ del nombre de la clase (es legal en un identificador Java)", () => {
    // Sin escaparlo, `A$B` arma una regex con "fin de input" en el medio y el
    // patron deja de matchear.
    expect(
      declaredConstructorParams("class A$B {\n    public A$B(int x) {\n    }\n}", "A$B"),
    ).toEqual(["int x"])
  })
})

describe("constructorSource / emptyConstructorSource", () => {
  it("recibe todos los campos en el orden declarado y los asigna con this", () => {
    expect(constructorSource("Persona", parseFields(CLASE_PERSONA))).toBe(
      [
        "public Persona(String nombre, int edad) {",
        "    this.nombre = nombre;",
        "    this.edad = edad;",
        "}",
      ].join("\n"),
    )
  })

  it("el constructor vacio es el que Java deja de dar gratis al escribir otro", () => {
    expect(emptyConstructorSource("Persona")).toBe("public Persona() {\n}")
  })
})

describe("toStringSource", () => {
  it("concatena los campos con + y separa con coma a partir del segundo", () => {
    expect(toStringSource("Persona", parseFields(CLASE_PERSONA))).toBe(
      [
        "@Override",
        "public String toString() {",
        '    return "Persona{" + "nombre=" + nombre + ", edad=" + edad + "}";',
        "}",
      ].join("\n"),
    )
  })

  it("un array va por Arrays.toString, NO concatenado con +", () => {
    // Concatenar un array con `+` imprime su referencia (`[I@1b6d3586`): anda,
    // compila, y esta mal.
    const fuente = toStringSource("Caja", [{ type: "int[]", name: "numeros" }])
    expect(fuente).toContain("Arrays.toString(numeros)")
    expect(fuente).not.toContain("+ numeros +")
  })

  it("una clase sin campos igual devuelve un toString compilable", () => {
    expect(toStringSource("Main", [])).toBe(
      ["@Override", "public String toString() {", '    return "Main{}";', "}"].join("\n"),
    )
  })
})

describe("equalsSource — el tipo del campo decide la comparacion", () => {
  it("los objetos van por Objects.equals (null-safe)", () => {
    expect(equalsSource("Persona", [{ type: "String", name: "nombre" }])).toContain(
      "Objects.equals(this.nombre, otro.nombre)",
    )
  })

  it("los primitivos que no son coma flotante van por ==", () => {
    for (const tipo of ["int", "long", "char", "boolean", "byte", "short"]) {
      expect(equalsSource("A", [{ type: tipo, name: "x" }]), tipo).toContain("this.x == otro.x")
    }
  })

  it("float va por Float.compare, no por ==", () => {
    // `NaN != NaN` y `0.0 == -0.0` rompen el contrato de equals.
    const fuente = equalsSource("A", [{ type: "float", name: "peso" }])
    expect(fuente).toContain("Float.compare(this.peso, otro.peso) == 0")
    expect(fuente).not.toContain("this.peso == otro.peso")
  })

  it("double va por Double.compare, no por ==", () => {
    const fuente = equalsSource("A", [{ type: "double", name: "precio" }])
    expect(fuente).toContain("Double.compare(this.precio, otro.precio) == 0")
    expect(fuente).not.toContain("this.precio == otro.precio")
  })

  it("los arrays van por Arrays.equals, no por == (que compara referencias)", () => {
    const fuente = equalsSource("A", [{ type: "int[]", name: "nums" }])
    expect(fuente).toContain("Arrays.equals(this.nums, otro.nums)")
    expect(fuente).not.toContain("this.nums == otro.nums")
  })

  it("arma el equals canonico completo: identidad, null + clase, cast, campos", () => {
    expect(equalsSource("Persona", parseFields(CLASE_PERSONA))).toBe(
      [
        "@Override",
        "public boolean equals(Object o) {",
        "    if (this == o) return true;",
        "    if (o == null || getClass() != o.getClass()) return false;",
        "    Persona otro = (Persona) o;",
        "    return Objects.equals(this.nombre, otro.nombre) && this.edad == otro.edad;",
        "}",
      ].join("\n"),
    )
  })
})

describe("hashCodeSource", () => {
  it("usa Objects.hash con los mismos campos que equals", () => {
    expect(hashCodeSource(parseFields(CLASE_PERSONA))).toBe(
      ["@Override", "public int hashCode() {", "    return Objects.hash(nombre, edad);", "}"].join(
        "\n",
      ),
    )
  })

  it("un array va por Arrays.hashCode (el suyo propio es la identidad)", () => {
    const fuente = hashCodeSource([{ type: "int[]", name: "nums" }])
    expect(fuente).toContain("Arrays.hashCode(nums)")
    expect(fuente).not.toContain("Objects.hash(nums)")
  })
})

describe("imports que exigen los overrides", () => {
  it("equals/hashCode siempre necesitan Objects", () => {
    expect(importsParaIgualdad([{ type: "int", name: "x" }])).toEqual(["import java.util.Objects;"])
  })

  it("con un campo array suman Arrays", () => {
    expect(
      importsParaIgualdad([
        { type: "int", name: "x" },
        { type: "String[]", name: "tags" },
      ]),
    ).toEqual(["import java.util.Objects;", "import java.util.Arrays;"])
  })

  it("toString solo necesita Arrays, y solo si hay algun array", () => {
    expect(importsParaToString([{ type: "String", name: "n" }])).toEqual([])
    expect(importsParaToString([{ type: "double[]", name: "notas" }])).toEqual([
      "import java.util.Arrays;",
    ])
  })
})

// ── El proveedor de completions ─────────────────────────────────────────────

/** Sugerencias que el proveedor de Java devuelve para este fuente. */
function sugerenciasPara(source: string) {
  const fake = crearMonacoFalso()
  registerJavaSnippets(fake.monaco, () => {})
  return fake.sugerencias(source)
}

/** Etiquetas de las sugerencias, para afirmar presencia/ausencia. */
function etiquetas(source: string): string[] {
  return sugerenciasPara(source).map((s) => String(s.label))
}

const CLASE_CON_ARRAY = `class Alumno {
    private String nombre;
    private int[] notas;
}`

describe("registerJavaSnippets — que se ofrece y que no", () => {
  it("una clase sin campos NO ofrece ctor / tostring / equals / hashCode", () => {
    // `Main` nunca tiene estado: un `ctorvacio` o un `toString` ahi es ruido en
    // la lista, no ayuda.
    const labels = etiquetas(
      "public class Main {\n    public static void main(String[] a) {\n    }\n}",
    )
    for (const l of ["ctor", "ctorvacio", "tostring", "equals", "hashCode"]) {
      expect(labels, `no deberia ofrecer "${l}"`).not.toContain(l)
    }
    // Pero la ceremonia estatica sigue estando.
    expect(labels).toContain("sout")
    expect(labels).toContain("psvm")
  })

  it("una clase con campos ofrece los cuatro", () => {
    const labels = etiquetas(CLASE_PERSONA)
    expect(labels).toEqual(
      expect.arrayContaining(["ctor", "ctorvacio", "tostring", "equals", "hashCode"]),
    )
  })

  it("TODAS las sugerencias llevan el command de trazabilidad", () => {
    // Mismo invariante que del lado Python: sin `command`, lo que inserta el
    // editor entra a la cadena CTR como `student_typed`.
    for (const s of sugerenciasPara(CLASE_CON_ARRAY)) {
      expect(s.command, `la sugerencia "${String(s.label)}" no lleva command`).toBeDefined()
      expect(s.command?.id).toBe("aiNative.javaSnippetAccepted")
    }
  })

  it("los overrides se resuelven POR CLASE, no sobre el archivo entero", () => {
    // El archivo real de Programacion 1: la clase `Main` con el `main`, y al
    // lado la clase auxiliar con los campos. Si el proveedor mirara el archivo
    // entero (como SI hacen los accesores), `Main` recibiria los campos de
    // `Persona` y ofreceria `public Main(String nombre, int edad)` — un
    // constructor que asigna campos que su clase no tiene: no compila.
    const src = `public class Main {
    public static void main(String[] args) {
    }
}

class Persona {
    private String nombre;
    private int edad;
}`
    const ctores = sugerenciasPara(src)
      .filter((s) => s.label === "ctor")
      .map((s) => String(s.insertText))

    expect(ctores).toHaveLength(1)
    expect(ctores[0]).toContain("public Persona(String nombre, int edad)")
    expect(ctores.join("\n")).not.toContain("public Main(")
  })

  it("un override ya escrito no se vuelve a ofrecer", () => {
    const src = `class Persona {
    private String nombre;

    @Override
    public String toString() {
        return nombre;
    }
}`
    expect(etiquetas(src)).not.toContain("tostring")
  })

  it("el constructor vacio ya escrito no se vuelve a ofrecer, el completo si", () => {
    const src = "class Persona {\n    private String nombre;\n    public Persona() {\n    }\n}"
    const labels = etiquetas(src)
    expect(labels).not.toContain("ctorvacio")
    expect(labels).toContain("ctor")
  })
})

describe("registerJavaSnippets — los imports faltantes salen en UN SOLO edit", () => {
  it("equals sobre una clase con array pide Objects y Arrays en un unico edit", () => {
    // Dos edits en el mismo rango se pisan entre si al aplicarse: si `Objects` y
    // `Arrays` salieran por separado, uno de los dos imports no llega y el
    // archivo queda sin compilar.
    const equals = sugerenciasPara(CLASE_CON_ARRAY).find((s) => s.label === "equals")
    expect(equals?.additionalTextEdits).toHaveLength(1)
    expect(equals?.additionalTextEdits?.[0]?.text).toBe(
      "import java.util.Objects;\nimport java.util.Arrays;\n",
    )
  })

  it("no ofrece un edit para un import que ya esta en el archivo", () => {
    const src = `import java.util.Objects;

class Persona {
    private String nombre;
}`
    const equals = sugerenciasPara(src).find((s) => s.label === "equals")
    // `Objects` ya esta y no hay arrays: no falta nada.
    expect(equals?.additionalTextEdits).toBeUndefined()
  })

  it("el edit del import va despues del ultimo import existente", () => {
    const src = `import java.util.Scanner;

class Persona {
    private String nombre;
}`
    const equals = sugerenciasPara(src).find((s) => s.label === "equals")
    const rango = equals?.additionalTextEdits?.[0]?.range
    expect(equals?.additionalTextEdits?.[0]?.text).toBe("import java.util.Objects;\n")
    expect(rango?.startLineNumber).toBe(2)
    expect(rango?.startColumn).toBe(1)
  })

  it("toString sobre una clase SIN arrays no pide ningun import", () => {
    const tostring = sugerenciasPara(CLASE_PERSONA).find((s) => s.label === "tostring")
    expect(tostring?.additionalTextEdits).toBeUndefined()
  })
})

// ── Limitaciones conocidas ──────────────────────────────────────────────────
//
// Las declaro el que escribio el codigo. Estos tests las FIJAN tal como son.
// NO son aprobacion: si alguien las arregla, el test que caiga le dice que el
// caso estaba declarado y que hay que actualizar el registro, no que rompio
// algo.

describe("LIMITACION CONOCIDA — un constructor parcial suprime el completo", () => {
  it("con un constructor de 1 de los 2 campos, `ctor` no se ofrece", () => {
    // `declaredConstructorParams` devuelve la lista CRUDA de parametros y el
    // proveedor solo pregunta si alguna es no vacia — no compara contra los
    // campos de la clase. Consecuencia: el alumno que arranco el constructor a
    // mano se queda sin el completo, que es justo cuando mas le serviria.
    const src = `class Persona {
    private String nombre;
    private int edad;

    public Persona(String nombre) {
        this.nombre = nombre;
    }
}`
    expect(declaredConstructorParams(src, "Persona")).toEqual(["String nombre"])
    expect(etiquetas(src)).not.toContain("ctor")
    // El vacio si se sigue ofreciendo: ese chequeo es exacto.
    expect(etiquetas(src)).toContain("ctorvacio")
  })
})

describe("LIMITACION CONOCIDA — un `.equals(` que es LLAMADA suprime el snippet", () => {
  it("usar equals en el cuerpo de un metodo cuenta como tenerlo declarado", () => {
    // `hasMethod` es `\bequals\s*\(` sobre el fuente del bloque: no distingue
    // declaracion de invocacion. Falso negativo — el snippet desaparece aunque
    // la clase no tenga el override.
    const src = `class Persona {
    private String nombre;

    public boolean mismoNombre(Persona otra) {
        return this.nombre.equals(otra.nombre);
    }
}`
    expect(etiquetas(src)).not.toContain("equals")
    // `hashCode` no aparece en el fuente, asi que ese si se ofrece — y queda
    // ofrecido SOLO, que es la parte fea: un hashCode sin su equals.
    expect(etiquetas(src)).toContain("hashCode")
  })
})

describe("LIMITACION CONOCIDA — la clase anidada no se corta por llaves balanceadas", () => {
  it("una clase anidada queda como bloque hermano y le roba el resto a la externa", () => {
    // `parseClassBlocks` corta por DECLARACION, no por llaves: la interna
    // arranca su bloque ahi y la externa pierde todo lo que venia despues.
    const src = `class Externa {
    private int a;

    class Interna {
        private int b;
    }

    private int c;
}`
    const bloques = parseClassBlocks(src)
    expect(bloques.map((b) => b.name)).toEqual(["Externa", "Interna"])
    // `c` esta declarado en `Externa` pero cae del lado de `Interna`.
    expect(parseFields(bloques[0]?.source ?? "")).toEqual([{ type: "int", name: "a" }])
    expect(parseFields(bloques[1]?.source ?? "")).toEqual([
      { type: "int", name: "b" },
      { type: "int", name: "c" },
    ])
    // Consecuencia observable: el `ctor` de `Externa` sale sin `c`.
    expect(constructorSource("Externa", parseFields(bloques[0]?.source ?? ""))).toBe(
      "public Externa(int a) {\n    this.a = a;\n}",
    )
  })
})
