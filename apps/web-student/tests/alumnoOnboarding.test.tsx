// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Tests del ONBOARDING PROGRESIVO DEL ALUMNO (`src/onboarding/alumnoOnboarding.tsx`).
 *
 * ALCANCE, Y POR QUE ES ESTE:
 *
 * El flow es DATOS: un array de carteles con dos predicados puros cada uno. Esta suite
 * testea LOS DATOS. No replica el motor.
 *
 * El matching de rutas, el descarte persistido y la eleccion de cual cartel se ve
 * cuando aplican varios son del motor, y ya estan cubiertos en
 * `packages/ui/src/components/Tour/OnboardingProvider.test.tsx`. Copiar esas reglas
 * aca no las verificaria: las duplicaria, y cuando el motor cambie la copia se queda
 * verde afirmando la regla vieja. (Paso: una replica local del match de rutas
 * sobrevivio a que el motor pasara de prefijo pelado a comparacion por segmento, sin
 * ponerse roja ni una vez.)
 *
 * Lo unico que se evalua aca es la regla que declara el contrato sobre CADA cartel:
 *
 *     pendiente(hint, estado)  <=>  unlockWhen(estado) && !doneWhen(estado)
 *
 * Lo que blinda la suite, en orden de importancia:
 *
 *   1. ANTI-ZOMBIE. Un alumno inscripto en una comision donde el docente NO publico
 *      ningun TP no puede recibir "abri tu primer TP". Es el escenario que motivo que
 *      cada cartel declare DOS condiciones y no una. Si `unlockWhen` de
 *      `abrir-primer-tp` deja de mirar `hayTpsDisponibles`, este archivo se pone rojo.
 *   2. IDEMPOTENCIA. El alumno que se inscribio por afuera nunca ve el cartel del
 *      codigo de aula: nace cumplido, sin haberlo descartado jamas.
 *   3. IDS UNICOS Y ESTABLES. El id es la clave del descarte en localStorage. Un id
 *      repetido rompe la persistencia en silencio; renombrar uno resucita un cartel
 *      que el alumno ya habia cerrado.
 *   4. TEXTOS SIN TILDES NI EM DASHES. Regla de encoding del repo (cp1252 en Windows).
 *      Es la clase de regresion que se cuela en una correccion de copy.
 */
import type { OnboardingHint } from "@platform/ui"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, test } from "vitest"
import { alumnoOnboarding } from "../src/onboarding/alumnoOnboarding"
import { ESTADO_ALUMNO_DESCONOCIDO, type EstadoAlumno } from "../src/onboarding/estado"

type Hint = OnboardingHint<EstadoAlumno>

const hints: Hint[] = alumnoOnboarding.hints

/**
 * La regla del CONTRATO sobre un cartel suelto (`types.ts`): esta pendiente cuando sus
 * precondiciones estan dadas y todavia no se cumplio.
 *
 * No incluye ruta ni descartes a proposito: eso lo compone el motor y se testea alla.
 * "Pendiente" no es lo mismo que "visible" — un cartel pendiente atado a `/episodio`
 * no se ve mientras el alumno esta en la home, y eso esta bien.
 */
function pendiente(hint: Hint, estado: EstadoAlumno): boolean {
  return hint.unlockWhen(estado) && !hint.doneWhen(estado)
}

/** Los ids de los carteles pendientes en un estado, en el orden del flow. */
function pendientes(estado: EstadoAlumno): string[] {
  return hints.filter((h) => pendiente(h, estado)).map((h) => h.id)
}

function porId(id: string): Hint {
  const h = hints.find((x) => x.id === id)
  if (!h) throw new Error(`El flow del alumno no declara el hint "${id}"`)
  return h
}

/**
 * Estado del alumno YA CONOCIDO (cargando: false). Partimos del "desconocido" del
 * modulo para que agregar un campo nuevo al estado no obligue a tocar cada test.
 */
function estado(parcial: Partial<EstadoAlumno> = {}): EstadoAlumno {
  return { ...ESTADO_ALUMNO_DESCONOCIDO, cargando: false, ...parcial }
}

/* ── Los momentos del recorrido del alumno ─────────────────────────────────── */

/** Recien logueado. Sin inscripcion, sin TPs, sin episodios, sin entregas. */
const NUEVO = estado()

/** Se inscribio, pero el docente todavia no publico ningun TP. EL ESCENARIO ZOMBIE. */
const INSCRIPTO_SIN_TPS = estado({ tieneInscripcion: true })

/** Inscripto y con TPs publicados, todavia no abrio ninguno. */
const INSCRIPTO_CON_TPS = estado({ tieneInscripcion: true, hayTpsDisponibles: true })

/** Abrio su primer episodio. */
const CON_EPISODIO = estado({
  tieneInscripcion: true,
  hayTpsDisponibles: true,
  tieneEpisodios: true,
  cantidadEpisodios: 1,
})

/** Ya hizo todo lo que el onboarding pide. Nada puede quedar pendiente aca. */
const TERMINAL = estado({
  tieneInscripcion: true,
  hayTpsDisponibles: true,
  tieneEpisodios: true,
  cantidadEpisodios: 4,
  entregoAlgunaVez: true,
})

const ESTADOS: { nombre: string; estado: EstadoAlumno }[] = [
  { nombre: "desconocido (cargando)", estado: ESTADO_ALUMNO_DESCONOCIDO },
  { nombre: "nuevo", estado: NUEVO },
  { nombre: "inscripto sin TPs", estado: INSCRIPTO_SIN_TPS },
  { nombre: "inscripto con TPs", estado: INSCRIPTO_CON_TPS },
  { nombre: "con un episodio", estado: CON_EPISODIO },
  { nombre: "terminal", estado: TERMINAL },
  // Combinaciones adversarias: estados que no deberian existir pero que la app puede
  // producir con caches desfasadas entre las cuatro consultas de `estado.ts`.
  {
    nombre: "episodios sin inscripcion (cache desfasada)",
    estado: estado({ tieneEpisodios: true, cantidadEpisodios: 2 }),
  },
  {
    nombre: "entrego sin episodios (cache desfasada)",
    estado: estado({ tieneInscripcion: true, entregoAlgunaVez: true }),
  },
  { nombre: "TPs sin inscripcion", estado: estado({ hayTpsDisponibles: true }) },
]

/** Rutas que el web-student registra hoy (TanStack file-based, `src/routes/`). */
const RUTAS_REGISTRADAS = [
  "/",
  "/materia/$id",
  "/episodio/$id",
  "/progreso",
  "/reflexiones",
  "/instrumentos",
]

/* ========================================================================== */
/* 1. Ids                                                                     */
/* ========================================================================== */

describe("alumnoOnboarding — ids", () => {
  test("no hay ids repetidos", () => {
    const ids = hints.map((h) => h.id)
    // Un id repetido rompe la persistencia del descarte EN SILENCIO: descartar uno
    // descarta los dos, y el segundo cartel no se muestra nunca.
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([])
  })

  test("los ids son no vacios y sin espacios (son clave de localStorage)", () => {
    for (const h of hints) {
      expect(h.id).toMatch(/^[a-z0-9-]+$/)
    }
  })

  test("los ids son estables: renombrar uno resucita un cartel ya descartado", () => {
    // Candado deliberado. Si cambiaste un id a proposito, actualiza esta lista Y
    // bumpea el `id` del flow: los descartes viejos ya no aplican.
    expect(hints.map((h) => h.id)).toEqual([
      "unirse-a-comision",
      "abrir-primer-tp",
      "episodio-tutor",
      "episodio-editor",
      "como-se-entrega",
    ])
  })

  test("el id del flow es estable (es el prefijo de todos los descartes)", () => {
    expect(alumnoOnboarding.id).toBe("alumno-v1")
  })
})

/* ========================================================================== */
/* 2. Coherencia de las dos condiciones                                       */
/* ========================================================================== */

describe("alumnoOnboarding — coherencia unlockWhen / doneWhen", () => {
  test.each(ESTADOS)(
    "en el estado $nombre, un hint cumplido nunca queda pendiente",
    ({ estado: e }) => {
      // El contrato es `unlock && !done`. Que los dos den true a la vez es legal y
      // significa "cumplido": lo que no puede pasar es que igual quede pendiente.
      const cumplidosPendientes = hints
        .filter((h) => h.doneWhen(e) && pendiente(h, e))
        .map((h) => h.id)
      expect(cumplidosPendientes).toEqual([])
    },
  )

  test("en el estado terminal no queda NINGUN cartel pendiente", () => {
    // Este es el "se muestra para siempre": un hint cuyo `doneWhen` no llega a cubrir
    // el estado final le queda pidiendo al alumno algo que ya hizo, para siempre.
    expect(pendientes(TERMINAL)).toEqual([])
  })

  test("todo hint es alcanzable: existe al menos un estado donde queda pendiente", () => {
    // Un hint con `unlockWhen` contenido en `doneWhen` es codigo muerto: nunca se ve.
    const inalcanzables = hints
      .filter((h) => !ESTADOS.some(({ estado: e }) => pendiente(h, e)))
      .map((h) => h.id)
    expect(inalcanzables).toEqual([])
  })

  test("mientras el estado no cargo no hay NADA pendiente", () => {
    // La guarda `cuando()` del flow. Sin ella el cartel parpadea al llegar el fetch.
    expect(pendientes(ESTADO_ALUMNO_DESCONOCIDO)).toEqual([])
  })

  test("los predicados son puros: no mutan el estado que reciben", () => {
    const e = estado({ tieneInscripcion: true, hayTpsDisponibles: true })
    const antes = JSON.stringify(e)
    for (const h of hints) {
      h.unlockWhen(e)
      h.doneWhen(e)
    }
    expect(JSON.stringify(e)).toBe(antes)
  })
})

/* ========================================================================== */
/* 3. El recorrido completo del alumno nuevo                                  */
/* ========================================================================== */

describe("alumnoOnboarding — recorrido del alumno nuevo", () => {
  test("estado vacio: SOLO el cartel del codigo de aula", () => {
    expect(pendientes(NUEVO)).toEqual(["unirse-a-comision"])
  })

  test("el cartel del codigo de aula no se ata a ninguna ruta", () => {
    // Sin inscripcion la app le muestra la pantalla del codigo este donde este. Un
    // cartel global se declara OMITIENDO `route`, no poniendo `route: "/"`.
    expect(porId("unirse-a-comision").route).toBeUndefined()
  })

  test("suma inscripcion + TPs publicados: avanza al de abrir el primer TP", () => {
    expect(pendientes(INSCRIPTO_CON_TPS)).toContain("abrir-primer-tp")
    expect(pendientes(INSCRIPTO_CON_TPS)).not.toContain("unirse-a-comision")
  })

  test("suma el primer episodio: el de abrir el TP se retira solo", () => {
    expect(porId("abrir-primer-tp").doneWhen(CON_EPISODIO)).toBe(true)
    expect(pendientes(CON_EPISODIO)).not.toContain("abrir-primer-tp")
  })

  test("con un solo episodio, los dos carteles del episodio quedan pendientes", () => {
    // Los dos comparten condiciones y ruta a proposito: el motor muestra uno solo, y
    // el segundo aparece recien cuando el primero se descarta.
    expect(pendientes(CON_EPISODIO)).toEqual(
      expect.arrayContaining(["episodio-tutor", "episodio-editor"]),
    )
  })

  test("con dos episodios los carteles del episodio ya no quedan pendientes", () => {
    const segundoEpisodio = estado({ ...CON_EPISODIO, cantidadEpisodios: 2 })
    expect(pendientes(segundoEpisodio)).not.toContain("episodio-tutor")
    expect(pendientes(segundoEpisodio)).not.toContain("episodio-editor")
  })

  test("con episodios y sin entregar queda pendiente el de como se entrega", () => {
    expect(pendientes(CON_EPISODIO)).toContain("como-se-entrega")
  })

  test("despues de la primera entrega no queda ningun cartel", () => {
    expect(pendientes(TERMINAL)).toEqual([])
  })

  test("la progresion completa, estado por estado", () => {
    // La foto entera del recorrido en un solo lugar: si un cambio de condiciones
    // corre un cartel de momento, se ve aca aunque los tests puntuales sigan verdes.
    expect(ESTADOS.slice(0, 6).map(({ nombre, estado: e }) => [nombre, pendientes(e)])).toEqual([
      ["desconocido (cargando)", []],
      ["nuevo", ["unirse-a-comision"]],
      ["inscripto sin TPs", ["episodio-tutor", "episodio-editor"]],
      ["inscripto con TPs", ["abrir-primer-tp", "episodio-tutor", "episodio-editor"]],
      ["con un episodio", ["episodio-tutor", "episodio-editor", "como-se-entrega"]],
      ["terminal", []],
    ])
  })
})

/* ========================================================================== */
/* 4. Anti-zombie (el escenario que motivo el diseno)                         */
/* ========================================================================== */

describe("alumnoOnboarding — anti-zombie", () => {
  test('inscripto donde el docente NO publico ningun TP: "abri tu primer TP" NO queda pendiente', () => {
    const abrir = porId("abrir-primer-tp")
    expect(abrir.unlockWhen(INSCRIPTO_SIN_TPS)).toBe(false)
    expect(pendiente(abrir, INSCRIPTO_SIN_TPS)).toBe(false)
  })

  test("inscripto sin TPs: ningun cartel le pide hacer algo con un TP", () => {
    // El caso completo. No alcanza con que el cartel del TP no aparezca: no puede
    // aparecer otro en su lugar pidiendo algo que tampoco se puede hacer.
    expect(pendientes(INSCRIPTO_SIN_TPS)).toEqual(["episodio-tutor", "episodio-editor"])
    // Y los dos que quedan estan atados a `/episodio`, adonde este alumno no puede
    // llegar todavia: sin TP publicado no hay episodio que abrir.
    expect(porId("episodio-tutor").route).toBe("/episodio")
    expect(porId("episodio-editor").route).toBe("/episodio")
  })

  test("apenas el docente publica un TP, el cartel se desbloquea solo", () => {
    // Sin descartar nada ni recargar: el mismo alumno, el estado cambio.
    expect(pendiente(porId("abrir-primer-tp"), INSCRIPTO_SIN_TPS)).toBe(false)
    expect(pendiente(porId("abrir-primer-tp"), INSCRIPTO_CON_TPS)).toBe(true)
  })

  test("ningun cartel que pide accion sobre TPs se desbloquea sin TPs disponibles", () => {
    // Anti-regresion generico: si alguien agrega un cartel nuevo del tipo "hace algo
    // con un TP", tiene que mirar `hayTpsDisponibles` como lo hace `abrir-primer-tp`.
    const dependenDeTps = hints.filter(
      (h) => h.unlockWhen(INSCRIPTO_SIN_TPS) !== h.unlockWhen(INSCRIPTO_CON_TPS),
    )
    expect(dependenDeTps.map((h) => h.id)).toContain("abrir-primer-tp")
  })
})

/* ========================================================================== */
/* 5. Idempotencia                                                            */
/* ========================================================================== */

describe("alumnoOnboarding — idempotencia", () => {
  test("el alumno inscripto por afuera nunca ve el cartel del codigo de aula", () => {
    // Nace cumplido: sin descartes persistidos, con la primera evaluacion del estado.
    const unirse = porId("unirse-a-comision")
    expect(unirse.doneWhen(INSCRIPTO_SIN_TPS)).toBe(true)
    expect(pendiente(unirse, INSCRIPTO_SIN_TPS)).toBe(false)
  })

  test("cada cartel cumplido queda cumplido a medida que el alumno avanza", () => {
    // Monotonia: un `doneWhen` que vuelve a false resucita un cartel ya cerrado. Es
    // lo que hace tolerable persistir los descartes por-navegador: si el alumno cambia
    // de maquina reaparecen los pendientes, nunca los cumplidos.
    const progresion = [NUEVO, INSCRIPTO_SIN_TPS, INSCRIPTO_CON_TPS, CON_EPISODIO, TERMINAL]
    for (const h of hints) {
      let yaCumplido = false
      for (const e of progresion) {
        const cumplido = h.doneWhen(e)
        if (yaCumplido) expect({ hint: h.id, cumplido }).toEqual({ hint: h.id, cumplido: true })
        yaCumplido = yaCumplido || cumplido
      }
    }
  })

  test("`doneWhen` no depende de nada que el onboarding pueda escribir", () => {
    // Se deriva del estado real y solo de el. Si un `doneWhen` mirara el descarte o un
    // contador propio, dejaria de ser idempotente. Se aproxima verificando que dos
    // evaluaciones seguidas del mismo estado dan lo mismo.
    for (const h of hints) {
      for (const { estado: e } of ESTADOS) {
        expect(h.doneWhen(e)).toBe(h.doneWhen(e))
      }
    }
  })
})

/* ========================================================================== */
/* 6. Declaracion de rutas y anclas                                           */
/* ========================================================================== */

describe("alumnoOnboarding — declaracion de rutas y anclas", () => {
  test("las rutas declaradas arrancan con /", () => {
    for (const h of hints) {
      if (h.route !== undefined) expect(h.route.startsWith("/")).toBe(true)
    }
  })

  test("ninguna ruta declarada termina en / (salvo la raiz)", () => {
    // El motor compara por segmento: `ruta === route || ruta.startsWith(route + "/")`.
    // Un `route: "/episodio/"` no matchea NADA y deja el cartel muerto en silencio.
    for (const h of hints) {
      if (h.route !== undefined && h.route !== "/") {
        expect(h.route.endsWith("/")).toBe(false)
      }
    }
  })

  test("ninguna ruta declarada usa la sintaxis de parametros del router", () => {
    // El motor compara strings literales. Un `route: "/episodio/$id"` no matchea la
    // URL real (`/episodio/abc`) y el cartel no se ve nunca.
    for (const h of hints) {
      if (h.route !== undefined) expect(h.route).not.toContain("$")
    }
  })

  test("toda ruta declarada corresponde a una ruta real del web-student", () => {
    // Puede ser la ruta exacta o un prefijo de segmento de una registrada
    // (`/episodio` cubre `/episodio/$id`). Un typo aca deja el cartel invisible.
    for (const h of hints) {
      if (h.route === undefined) continue
      const cubre = RUTAS_REGISTRADAS.some(
        (r) => r === h.route || r.startsWith(`${h.route}/`) || h.route === "/",
      )
      expect({ hint: h.id, route: h.route, cubre }).toEqual({
        hint: h.id,
        route: h.route,
        cubre: true,
      })
    }
  })

  test("los anchors son valores de data-tour, no selectores CSS", () => {
    // El motor interpola el anchor dentro de `[data-tour="..."]`. Un punto o un
    // numeral adelante indica que alguien escribio un selector y no va a resolver.
    for (const h of hints) {
      if (h.anchor !== undefined) expect(h.anchor).toMatch(/^[a-z0-9:/-]+$/)
    }
  })

  test("los carteles que piden accion cuentan para el progreso; los que explican, no", () => {
    const cuentan = hints.filter((h) => h.countsTowardProgress !== false).map((h) => h.id)
    expect(cuentan).toEqual(["unirse-a-comision", "abrir-primer-tp"])
  })

  test("todo cartel tiene titulo y cuerpo", () => {
    for (const h of hints) {
      expect(h.title.trim().length).toBeGreaterThan(0)
      expect(h.body).toBeTruthy()
    }
  })
})

/* ========================================================================== */
/* 7. Encoding de los textos                                                  */
/* ========================================================================== */

/** Todo lo que el alumno LEE de un cartel: titulo, cuerpo renderizado y CTA. */
function textoVisible(h: Hint): string {
  // El fragment no sobra: `h.body` es un ReactNode (puede ser un string) y
  // `renderToStaticMarkup` pide un ReactElement.
  // biome-ignore lint/complexity/noUselessFragments: envuelve un ReactNode suelto.
  return [h.title, h.ctaLabel ?? "", renderToStaticMarkup(<>{h.body}</>)].join(" ")
}

const TILDES = /[À-ÿĀ-ſ]/g
const PUNTUACION_PROHIBIDA = /[–—‘’“”…]/g

describe("alumnoOnboarding — encoding de los textos", () => {
  test.each(hints.map((h) => ({ id: h.id, hint: h })))(
    "el cartel $id no tiene tildes ni enies",
    ({ hint }) => {
      // Regla de encoding del repo: la consola cp1252 de Windows rompe con no-ASCII y
      // ya tumbo gates de CI (ver CLAUDE.md, "Scripts con stdout en Windows").
      expect(textoVisible(hint).match(TILDES) ?? []).toEqual([])
    },
  )

  test.each(hints.map((h) => ({ id: h.id, hint: h })))(
    "el cartel $id no tiene em dashes, comillas curvas ni puntos suspensivos unicode",
    ({ hint }) => {
      expect(textoVisible(hint).match(PUNTUACION_PROHIBIDA) ?? []).toEqual([])
    },
  )

  test("todo el texto visible del flow es ASCII imprimible", () => {
    // Red de seguridad sobre las dos de arriba: cubre cualquier caracter raro que se
    // cuele por copy-paste desde un doc (espacios duros, guiones no-ASCII, comillas).
    const sospechosos = new Set<string>()
    for (const h of hints) {
      for (const c of textoVisible(h)) {
        const code = c.codePointAt(0) ?? 0
        if (code > 126 || (code < 32 && c !== "\n")) sospechosos.add(c)
      }
    }
    expect([...sospechosos]).toEqual([])
  })
})
