/**
 * H3 — la precedencia entre los tres candidatos del buffer inicial.
 *
 * El mutante que hasta hoy sobrevivia: revertir el `else` final a
 * `else if (ordenEfectivo == null)`, que hacia que una siembra (ED-4, desde
 * entonces eliminada) volviera a PISAR la consigna del docente. Los 280 tests
 * quedaban en verde.
 *
 * ED-4 se saco de acá el 2026-09-28 (ver
 * `openspec/changes/eliminar-ed4-siembra-codigo-previo/`): reinterpretaba un
 * `inicial_codigo` vacio como "el docente no se expreso" en vez de "el
 * docente eligio que arranque vacio", y contaminaba la cadena CTR con codigo
 * heredado indistinguible de lo que escribio el alumno. Los tests que
 * protegian la precedencia del arrastre contra el scaffold del docente
 * ("LA regla: el arrastre no pisa al docente") se borraron con ella: ya no
 * hay arrastre que ordenar contra nada. Lo que sobrevive de esa garantia —
 * que el scaffold del docente gana cuando hay snapshot ausente— ya esta
 * cubierto por los tests 2 y 3 de abajo, que no necesitan un cuarto
 * candidato para demostrarlo.
 *
 * Por que se assertea `origen` y no solo `codigo`
 * ----------------------------------------------
 * Es el seam que el coder abrio justo para esto. Dos candidatos con el MISMO
 * texto eran indistinguibles mirando solo el string, y una cascada con la
 * precedencia invertida devolvia el mismo valor por el motivo equivocado. Con
 * `origen` la afirmacion es sobre QUIEN gano, que es lo que la regla dice.
 */

import { describe, expect, it } from "vitest"
import type { CandidatosCodigo } from "../src/lib/cascadaCodigo"
import { esPlaceholder, resolverCascadaDeCodigo } from "../src/lib/cascadaCodigo"

const PLACEHOLDER = "# Escribi tu solucion aca\n"
const SNAPSHOT = "print('lo que escribi en ESTE episodio')\n"
const SCAFFOLD_TP = "# scaffold de la TP\ndef resolver():\n    pass\n"
const SCAFFOLD_EJ = "# scaffold del ejercicio\ndef resolver():\n    pass\n"

/** Los tres candidatos presentes, con textos distinguibles. */
const TODOS: CandidatosCodigo = {
  snapshot: SNAPSHOT,
  scaffoldTp: SCAFFOLD_TP,
  scaffoldEjercicio: SCAFFOLD_EJ,
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

  it("4. sin ningun scaffold del docente ni snapshot, gana el placeholder — no existe 'codigo del ejercicio anterior'", () => {
    // Este es el reemplazo directo del viejo "4. el arrastre entra recien
    // cuando NO hay ningun scaffold del docente": antes, sin scaffold, entraba
    // un cuarto candidato (`codigoPrevio`). Ahora, sin scaffold, no queda nada
    // que interponer entre el docente y el andamio del lenguaje.
    expect(
      resolverCascadaDeCodigo({
        snapshot: null,
        scaffoldTp: null,
        scaffoldEjercicio: null,
        placeholder: PLACEHOLDER,
      }),
    ).toEqual({ codigo: PLACEHOLDER, origen: "placeholder" })
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

describe("resolverCascadaDeCodigo — ED-4 fuera: la cascada no consulta codigoPrevio en ninguna rama", () => {
  it("un candidato `codigoPrevio` colado (dato heredado de una version vieja del tipo) no cambia el resultado", () => {
    // `CandidatosCodigo` ya no declara el campo, asi que solo se puede colar
    // via cast — exactamente lo que dejaria en memoria un build viejo del
    // frontend sirviendo contra el codigo nuevo a mitad de un deploy.
    const conCodigoPrevioColado = {
      snapshot: null,
      scaffoldTp: null,
      scaffoldEjercicio: null,
      placeholder: PLACEHOLDER,
      codigoPrevio: "print('lo que deje en el ejercicio 1')\n",
    } as unknown as CandidatosCodigo
    expect(resolverCascadaDeCodigo(conCodigoPrevioColado)).toEqual({
      codigo: PLACEHOLDER,
      origen: "placeholder",
    })
  })
})

describe("esPlaceholder — la licencia para re-sembrar el buffer", () => {
  it("es true solo cuando gano el andamio", () => {
    // `EpisodePage` lo usa para saber si todavia puede reemplazar el buffer
    // cuando se resuelve el lenguaje del ejercicio. Si devolviera `true` sobre
    // codigo real, ese reemplazo BORRA trabajo del alumno.
    expect(esPlaceholder({ codigo: PLACEHOLDER, origen: "placeholder" })).toBe(true)
    for (const origen of ["snapshot", "scaffold-tp", "scaffold-ejercicio"] as const) {
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
