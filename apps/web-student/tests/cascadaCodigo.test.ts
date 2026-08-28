/**
 * ED-4 / H3 — la precedencia entre los cuatro candidatos del buffer inicial.
 *
 * El mutante que hasta hoy sobrevivia: revertir el `else` final a
 * `else if (ordenEfectivo == null)`, que hace que la siembra del arrastre
 * vuelva a PISAR la consigna del docente. Los 280 tests quedaban en verde.
 *
 * Por que el bug es peor que "el editor abre con otro texto"
 * ---------------------------------------------------------
 * El andamio del lenguaje se nota a simple vista que no es una consigna: es un
 * comentario y un `main` vacio. El codigo del ejercicio ANTERIOR, no: es Java
 * o Python plausible, escrito por el propio alumno, sobre la misma TP. Puesto
 * encima del scaffold del docente, contradice el enunciado con algo que parece
 * legitimo — y el alumno no tiene forma de saber que lo que ve no es lo que le
 * dejaron.
 *
 * Por que se assertea `origen` y no solo `codigo`
 * ----------------------------------------------
 * Es el seam que el coder abrio justo para esto. Dos candidatos con el MISMO
 * texto —el caso real: el scaffold del docente ya trabajado por el alumno en el
 * ejercicio anterior— eran indistinguibles mirando solo el string, y una
 * cascada con la precedencia invertida devolvia el mismo valor por el motivo
 * equivocado. Con `origen` la afirmacion es sobre QUIEN gano, que es lo que la
 * regla dice.
 */

import { describe, expect, it } from "vitest"
import type { CandidatosCodigo } from "../src/lib/cascadaCodigo"
import { esPlaceholder, resolverCascadaDeCodigo } from "../src/lib/cascadaCodigo"

const PLACEHOLDER = "# Escribi tu solucion aca\n"
const SNAPSHOT = "print('lo que escribi en ESTE episodio')\n"
const SCAFFOLD_TP = "# scaffold de la TP\ndef resolver():\n    pass\n"
const SCAFFOLD_EJ = "# scaffold del ejercicio\ndef resolver():\n    pass\n"
const CODIGO_PREVIO = "print('lo que deje en el ejercicio 1')\n"

/** Los cuatro candidatos presentes, con textos distinguibles. */
const TODOS: CandidatosCodigo = {
  snapshot: SNAPSHOT,
  scaffoldTp: SCAFFOLD_TP,
  scaffoldEjercicio: SCAFFOLD_EJ,
  codigoPrevio: CODIGO_PREVIO,
  placeholder: PLACEHOLDER,
}

describe("resolverCascadaDeCodigo — el orden de precedencia", () => {
  it("1. el snapshot del propio episodio gana sobre todos", () => {
    // Pisarlo es borrarle trabajo al alumno de ESTE episodio.
    expect(resolverCascadaDeCodigo(TODOS)).toEqual({
      codigo: SNAPSHOT,
      origen: "snapshot",
    })
  })

  it("2. sin snapshot manda el scaffold de la TP", () => {
    expect(resolverCascadaDeCodigo({ ...TODOS, snapshot: null })).toEqual({
      codigo: SCAFFOLD_TP,
      origen: "scaffold-tp",
    })
  })

  it("3. sin scaffold de TP manda el del ejercicio", () => {
    expect(resolverCascadaDeCodigo({ ...TODOS, snapshot: null, scaffoldTp: null })).toEqual({
      codigo: SCAFFOLD_EJ,
      origen: "scaffold-ejercicio",
    })
  })

  it("4. el arrastre entra recien cuando NO hay ningun scaffold del docente", () => {
    expect(
      resolverCascadaDeCodigo({
        ...TODOS,
        snapshot: null,
        scaffoldTp: null,
        scaffoldEjercicio: null,
      }),
    ).toEqual({ codigo: CODIGO_PREVIO, origen: "codigo-previo" })
  })

  it("5. el andamio del lenguaje es el ultimo eslabon", () => {
    expect(
      resolverCascadaDeCodigo({
        snapshot: null,
        scaffoldTp: null,
        scaffoldEjercicio: null,
        codigoPrevio: null,
        placeholder: PLACEHOLDER,
      }),
    ).toEqual({ codigo: PLACEHOLDER, origen: "placeholder" })
  })
})

describe("resolverCascadaDeCodigo — LA regla: el arrastre no pisa al docente", () => {
  it("el scaffold de la TP le gana al codigo del ejercicio anterior", () => {
    const r = resolverCascadaDeCodigo({
      snapshot: null,
      scaffoldTp: SCAFFOLD_TP,
      scaffoldEjercicio: null,
      codigoPrevio: CODIGO_PREVIO,
      placeholder: PLACEHOLDER,
    })
    expect(r.origen).toBe("scaffold-tp")
    expect(r.codigo).not.toBe(CODIGO_PREVIO)
  })

  it("el scaffold del EJERCICIO tambien le gana al arrastre", () => {
    // Esta es la mitad que caia con `else if (ordenEfectivo == null)`: la
    // siembra ED-4 solo aplica a ejercicios (orden no nulo), asi que la rama
    // revertida la ponia justo cuando el scaffold del ejercicio existe.
    const r = resolverCascadaDeCodigo({
      snapshot: null,
      scaffoldTp: null,
      scaffoldEjercicio: SCAFFOLD_EJ,
      codigoPrevio: CODIGO_PREVIO,
      placeholder: PLACEHOLDER,
    })
    expect(r.origen).toBe("scaffold-ejercicio")
    expect(r.codigo).not.toBe(CODIGO_PREVIO)
  })

  it("con el MISMO texto en los dos, `origen` sigue diciendo quien gano", () => {
    // El caso que hacia indistinguibles a los candidatos antes de que existiera
    // `origen`: el alumno abrio el ejercicio anterior con el scaffold del
    // docente y lo dejo sin tocar, asi que el arrastre guardado ES el scaffold.
    // Mirando solo `codigo`, la cascada correcta y la invertida devuelven lo
    // mismo. `origen` es lo unico que las separa.
    const mismoTexto = SCAFFOLD_TP
    const r = resolverCascadaDeCodigo({
      snapshot: null,
      scaffoldTp: mismoTexto,
      scaffoldEjercicio: null,
      codigoPrevio: mismoTexto,
      placeholder: PLACEHOLDER,
    })
    expect(r.codigo).toBe(mismoTexto)
    expect(r.origen).toBe("scaffold-tp")
  })
})

describe("resolverCascadaDeCodigo — truthiness, no `!= null`", () => {
  it('un scaffold "" es "el docente no dejo scaffold", no "dejo un archivo vacio"', () => {
    // Semantica heredada de la cascada imperativa: `inicial_codigo` llega como
    // `""` desde el backend cuando el campo esta vacio, y abrir el editor en
    // blanco por eso seria peor que el andamio.
    const r = resolverCascadaDeCodigo({
      snapshot: null,
      scaffoldTp: "",
      scaffoldEjercicio: "",
      codigoPrevio: null,
      placeholder: PLACEHOLDER,
    })
    expect(r).toEqual({ codigo: PLACEHOLDER, origen: "placeholder" })
  })

  it("un snapshot vacio no cuenta como trabajo del alumno", () => {
    const r = resolverCascadaDeCodigo({ ...TODOS, snapshot: "" })
    expect(r.origen).toBe("scaffold-tp")
  })

  it("los candidatos ausentes (undefined) se saltean igual que los null", () => {
    // `EpisodePage` pasa `undefined` cuando la TP todavia no hidrato.
    const r = resolverCascadaDeCodigo({ placeholder: PLACEHOLDER })
    expect(r).toEqual({ codigo: PLACEHOLDER, origen: "placeholder" })
  })
})

describe("esPlaceholder — la licencia para re-sembrar el buffer", () => {
  it("es true solo cuando gano el andamio", () => {
    // `EpisodePage` lo usa para saber si todavia puede reemplazar el buffer
    // cuando se resuelve el lenguaje del ejercicio. Si devolviera `true` sobre
    // codigo real, ese reemplazo BORRA trabajo del alumno.
    expect(esPlaceholder({ codigo: PLACEHOLDER, origen: "placeholder" })).toBe(true)
    for (const origen of [
      "snapshot",
      "scaffold-tp",
      "scaffold-ejercicio",
      "codigo-previo",
    ] as const) {
      expect(esPlaceholder({ codigo: "cualquier cosa", origen }), origen).toBe(false)
    }
  })

  it("mira el origen y no el texto", () => {
    // El caso que rompe una implementacion por comparacion de strings: el
    // alumno escribio EXACTAMENTE el andamio (o lo restauro y lo dejo asi) y
    // eso quedo como snapshot. Es codigo del alumno, no andamio: re-sembrarlo
    // seria pisar su decision.
    expect(esPlaceholder({ codigo: PLACEHOLDER, origen: "snapshot" })).toBe(false)
  })

  it("compone con la cascada: el ultimo eslabon habilita el re-seed", () => {
    const sinNada = resolverCascadaDeCodigo({ placeholder: PLACEHOLDER })
    expect(esPlaceholder(sinNada)).toBe(true)
    expect(esPlaceholder(resolverCascadaDeCodigo(TODOS))).toBe(false)
  })
})
