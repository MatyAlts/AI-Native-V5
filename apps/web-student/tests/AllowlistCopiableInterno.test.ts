import { readFileSync } from "node:fs"
import { join } from "node:path"
/**
 * El atributo `data-copiable-interno` vive en DOS archivos que tienen que
 * coincidir, y nada del compilador los ata: `EpisodePage.tsx` lo produce,
 * `CodeEditor.tsx` lo consume por selector.
 *
 * POR QUE ESTE ARCHIVO
 * --------------------
 * La primera version de este change usaba una DENYLIST: todo alimentaba el
 * portapapeles interno EXCEPTO el panel del tutor, identificado por
 * `[data-tour="tutor-chat"]`. QA renombro ese atributo en `EpisodePage.tsx` y
 * los 548 tests siguieron pasando — con la salvaguarda de ADR-026 rota. Y el
 * mismo string tenia CUATRO consumidores: el tour de onboarding tambien se
 * apagaba en silencio.
 *
 * Invertir a allowlist arreglo lo importante —el mismo rename ahora FALLA
 * CERRADO: la consigna deja de ser copiable y la feature degrada al
 * comportamiento anterior al change, en vez de volver pegable el codigo del
 * tutor— pero el rename sigue sin romper ningun test. Este archivo cierra eso.
 *
 * No es cosmetico: es la tercera vez esta semana que dos lugares que deben
 * coincidir se desincronizan sin que nada avise (el comentario de guardrails
 * que termino adentro de la tesis, las dos listas de la leyenda, y esto).
 */
import { describe, expect, it } from "vitest"

const RAIZ = join(__dirname, "..")
const EPISODE_PAGE = readFileSync(join(RAIZ, "src/pages/EpisodePage.tsx"), "utf-8")
const CODE_EDITOR = readFileSync(join(RAIZ, "src/components/CodeEditor.tsx"), "utf-8")

const ATRIBUTO = "data-copiable-interno"

describe("el productor y el consumidor del allowlist coinciden", () => {
  it("EpisodePage marca al menos una region como copiable", () => {
    // Si esto falla, nadie puede copiar nada fuera del editor y el change
    // entero quedo sin efecto — en verde, porque los tests de CodeEditor usan
    // su propio stub.
    expect(EPISODE_PAGE).toContain(ATRIBUTO)
  })

  it("CodeEditor consulta ese mismo atributo", () => {
    expect(CODE_EDITOR).toContain(`[${ATRIBUTO}]`)
  })

  it("el panel del tutor NO esta en el allowlist (ADR-026)", () => {
    // ADR-026 (deciders: Alberto Cortez, director de tesis) difirio a
    // post-defensa el canal para tomar codigo del tutor: cambia la economia de
    // la interaccion y puede inducir delegacion pasiva como variable confound.
    //
    // El allowlist ya lo protege por omision — lo que no se habilita no entra.
    // Este test hace que agregarselo sea un acto DELIBERADO que rompe algo,
    // en vez de un renglon que pasa en un code review.
    // La version anterior de este test anclaba el bloque con
    // `indexOf('data-tour="tutor-chat"')`. Si ese atributo se renombraba,
    // `indexOf` daba -1, el slice se volvia `slice(0, 399)` y **la asercion
    // pasaba vacia** — el guardian que existe PORQUE un string magico se podia
    // renombrar en silencio dependia de un string magico que se podia
    // renombrar en silencio. Lo encontro el auditor el 2026-09-30.
    //
    // Ahora se ancla en el `aria-label`, que es texto de accesibilidad visible
    // para el usuario: renombrarlo es un cambio deliberado, no un refactor. Y
    // si aun asi desaparece, el test FALLA en vez de pasar vacio.
    const marcaTutor = 'aria-label="Tutor socrático"'
    const inicio = EPISODE_PAGE.indexOf(marcaTutor)
    expect(inicio, `no encontre ${marcaTutor} — el ancla de este test se rompio`).toBeGreaterThan(
      -1,
    )
    const bloqueTutor = EPISODE_PAGE.slice(inicio, inicio + 1400)
    expect(bloqueTutor).not.toContain(ATRIBUTO)
  })
})
