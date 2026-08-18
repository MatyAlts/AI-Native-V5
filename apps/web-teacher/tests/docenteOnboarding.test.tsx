// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Tests del ONBOARDING POR ESTADO DEL DOCENTE (`src/onboarding/docenteOnboarding.tsx`).
 *
 * ALCANCE: el flow es DATOS y esta suite testea LOS DATOS. No replica el motor.
 *
 * El matching de rutas, el descarte persistido y la eleccion de cual cartel se ve
 * cuando aplican varios estan cubiertos en
 * `packages/ui/src/components/Tour/OnboardingProvider.test.tsx`. Copiarlos aca no los
 * verificaria: los duplicaria, y cuando el motor cambie la copia se queda verde
 * afirmando la regla vieja. Lo unico que se evalua aca es la regla del contrato sobre
 * CADA cartel: `pendiente <=> unlockWhen(estado) && !doneWhen(estado)`.
 *
 * Las pocas aserciones que SI necesitan el motor (el progreso "N de M", cual cartel gana
 * cuando hay dos pendientes) montan el `OnboardingProvider` de verdad con el flow de
 * verdad. Usar el motor no es replicarlo: si el motor cambia, estas se mueven con el en
 * vez de quedarse afirmando lo viejo.
 *
 * Lo que blinda esta suite:
 *
 *   1. EL RECORRIDO. Sin comision solo el primer cartel; con comision y sin nada armado,
 *      el de unidades junto al del TP; el de corregir NO aparece si no hay ninguna
 *      entrega esperando.
 *   2. LA UNIDAD ES OPCIONAL. Es la regla de la que cuelga el diseno de ese cartel:
 *      `unidad_id` es nullable en la TP (`ON DELETE SET NULL`) y el alumno ve igual los
 *      TPs huerfanos bajo "Sin unidad asignada". De ahi salen dos candados: el cartel de
 *      unidades NO cuenta para el progreso, y el cartel del TP NO depende de que exista
 *      una unidad.
 *   3. IDS UNICOS Y ESTABLES. El id es la clave del descarte en localStorage. Repetirlo
 *      rompe la persistencia en silencio; renombrarlo resucita un cartel ya cerrado.
 *   4. NADA SE MUESTRA SOBRE DATOS QUE NO TENEMOS. Los flags `*Cargad*` son la mitad de
 *      cada `unlockWhen`: un cartel que aparece cuando llega el fetch le afirma al
 *      docente que le falta algo que en realidad ya tiene.
 *   5. TEXTOS SIN TILDES NI EM DASHES (regla de encoding del repo, cp1252 en Windows).
 */
import {
  OnboardingProvider,
  type OnboardingFlow,
  type OnboardingHint,
  useOnboardingProgress,
} from "@platform/ui"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, test } from "vitest"
import { docenteOnboarding } from "../src/onboarding/docenteOnboarding"
import type { EstadoDocente } from "../src/onboarding/estadoDocente"

type Hint = OnboardingHint<EstadoDocente>

const hints: Hint[] = docenteOnboarding.hints

/**
 * Los ids de los carteles, en un solo lugar. Son claves de localStorage: renombrar uno
 * resucita un cartel ya descartado en todos los navegadores donde estaba cerrado.
 */
const ID_COMISION = "sin-comision"
const ID_UNIDADES = "sin-unidades"
const ID_TP = "sin-tp"
const ID_CORREGIR = "primera-entrega-sin-corregir"

/**
 * Los que cuentan para la barra de "primeros pasos N de M". El de unidades queda afuera
 * a proposito: la unidad es opcional (ver el bloque de mas abajo).
 */
const CONTABLES = [ID_COMISION, ID_TP, ID_CORREGIR]

/**
 * La regla del CONTRATO sobre un cartel suelto (`types.ts`): esta pendiente cuando sus
 * precondiciones estan dadas y todavia no se cumplio.
 *
 * No incluye ruta ni descartes a proposito: eso lo compone el motor y se testea alla.
 */
function pendiente(hint: Hint, estado: EstadoDocente): boolean {
  return hint.unlockWhen(estado) && !hint.doneWhen(estado)
}

/** Los ids de los carteles pendientes en un estado, en el orden del flow. */
function pendientes(estado: EstadoDocente): string[] {
  return hints.filter((h) => pendiente(h, estado)).map((h) => h.id)
}

function porId(id: string): Hint {
  const h = hints.find((x) => x.id === id)
  if (!h) throw new Error(`El flow del docente no declara el hint "${id}"`)
  return h
}

function indiceDe(id: string): number {
  return hints.findIndex((h) => h.id === id)
}

/** Nada cargado todavia. Es lo que devuelve el hook antes de que resuelva ningun fetch. */
const NADA_CARGADO: EstadoDocente = {
  comisionesCargadas: false,
  tieneComision: false,
  comisionActivaId: null,
  tpsCargados: false,
  tieneTp: false,
  unidadesCargadas: false,
  tieneUnidad: false,
  entregasCargadas: false,
  hayEntregaPendiente: false,
  hayEntregaCorregida: false,
}

function estado(parcial: Partial<EstadoDocente> = {}): EstadoDocente {
  return { ...NADA_CARGADO, ...parcial }
}

const COMISION = "11111111-1111-1111-1111-111111111111"

/** Sabemos que no tiene ninguna comision asignada. */
const SIN_COMISION = estado({ comisionesCargadas: true })

/** Tiene comision y esta parado en ella. Ya sabemos que no hay unidades ni TPs. */
const SIN_UNIDADES_NI_TP = estado({
  comisionesCargadas: true,
  tieneComision: true,
  comisionActivaId: COMISION,
  unidadesCargadas: true,
  tpsCargados: true,
})

/** Creo una unidad. Todavia no hay ningun TP. */
const SIN_TP = estado({ ...SIN_UNIDADES_NI_TP, tieneUnidad: true })

/**
 * El caso que sostiene el diseno del cartel de unidades: publico su TP sin crear
 * ninguna unidad. Es un estado LEGITIMO, no un a medio hacer: `unidad_id` es nullable
 * y el alumno ve el TP igual, bajo "Sin unidad asignada".
 */
const SIN_UNIDADES_CON_TP = estado({ ...SIN_UNIDADES_NI_TP, tieneTp: true })

/** Publico un TP (y creo su unidad). Todavia no entrego nadie. */
const CON_TP_SIN_ENTREGAS = estado({ ...SIN_TP, tieneTp: true, entregasCargadas: true })

/** Llego la primera entrega y espera correccion. */
const CON_ENTREGA_PENDIENTE = estado({ ...CON_TP_SIN_ENTREGAS, hayEntregaPendiente: true })

/** Ya corrigio. Nada del onboarding puede quedar vivo. */
const TERMINAL = estado({ ...CON_ENTREGA_PENDIENTE, hayEntregaCorregida: true })

/**
 * Hizo todo lo que se le puede pedir a un docente, sin usar unidades nunca. El progreso
 * tiene que dar COMPLETO igual: si no, el docente que no las usa no llega jamas.
 */
const TERMINAL_SIN_UNIDADES = estado({ ...TERMINAL, tieneUnidad: false })

const ESTADOS: { nombre: string; estado: EstadoDocente }[] = [
  { nombre: "nada cargado", estado: NADA_CARGADO },
  { nombre: "sin comision", estado: SIN_COMISION },
  { nombre: "sin unidades ni TP", estado: SIN_UNIDADES_NI_TP },
  { nombre: "sin TP", estado: SIN_TP },
  { nombre: "con TP y sin unidades", estado: SIN_UNIDADES_CON_TP },
  { nombre: "con TP y sin entregas", estado: CON_TP_SIN_ENTREGAS },
  { nombre: "con entrega pendiente", estado: CON_ENTREGA_PENDIENTE },
  { nombre: "terminal", estado: TERMINAL },
  { nombre: "terminal sin unidades", estado: TERMINAL_SIN_UNIDADES },
  // Adversarios: caches desfasadas entre las consultas de `estadoDocente.ts`.
  {
    nombre: "comision recien elegida, nada mas cargado",
    estado: estado({ comisionesCargadas: true, tieneComision: true, comisionActivaId: COMISION }),
  },
  {
    nombre: "entregas cargadas antes que las comisiones",
    estado: estado({ entregasCargadas: true, hayEntregaPendiente: true }),
  },
  {
    nombre: "corregidas sin pendientes (cola vaciada)",
    estado: estado({ ...CON_TP_SIN_ENTREGAS, hayEntregaCorregida: true }),
  },
  {
    nombre: "unidades cargadas antes que las comisiones",
    estado: estado({ unidadesCargadas: true }),
  },
]

/** Rutas que el web-teacher registra hoy (TanStack file-based, `src/routes/`). */
const RUTAS_REGISTRADAS = [
  "/",
  "/ejercicios",
  "/templates",
  "/kappa",
  "/progression",
  "/tareas-practicas",
  "/materiales",
  "/unidades",
  "/export",
  "/correcciones",
  "/episode-n-level",
  "/episode-timeline",
  "/student-longitudinal",
  "/cohort-adversarial",
  "/cohort-quartiles",
  "/entrenamiento-recalibracion",
  "/instrumentos-cohorte",
  "/interrater",
  "/interrater-admin",
  "/uso-ia",
]

/* ========================================================================== */
/* 0. El motor de verdad, para las pocas cosas que lo necesitan               */
/* ========================================================================== */

function Progreso() {
  const p = useOnboardingProgress()
  return <span data-testid="progreso">{`${p.hechos}/${p.total}/${p.completo ? "si" : "no"}`}</span>
}

/**
 * Monta el `OnboardingProvider` REAL con el flow REAL del docente. Se usa solo donde la
 * pregunta es del motor (progreso, cual gana entre varios pendientes); todo lo demas se
 * evalua sobre los predicados declarados, sin renderizar.
 */
function montar(e: EstadoDocente, route = "/", children: ReactNode = <Progreso />) {
  return render(
    <OnboardingProvider
      flow={docenteOnboarding as OnboardingFlow<EstadoDocente>}
      estado={e}
      route={route}
    >
      {children}
    </OnboardingProvider>,
  )
}

/** El id del cartel que el motor esta mostrando, o null. Se identifica por su titulo. */
function idVisible(): string | null {
  for (const h of hints) {
    if (screen.queryByText(h.title) !== null) return h.id
  }
  return null
}

function cerrarCartelVisible(id: string): void {
  fireEvent.click(screen.getByRole("button", { name: porId(id).ctaLabel ?? "Entendido" }))
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

/* ========================================================================== */
/* 1. Ids                                                                     */
/* ========================================================================== */

describe("docenteOnboarding — ids", () => {
  test("no hay ids repetidos", () => {
    const ids = hints.map((h) => h.id)
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([])
  })

  test("los ids son no vacios y sin espacios (son clave de localStorage)", () => {
    for (const h of hints) {
      expect(h.id).toMatch(/^[a-z0-9-]+$/)
    }
  })

  test("los ids son estables y estan en orden: renombrar o reordenar cambia lo que se ve", () => {
    // Candado deliberado, y tambien candado de ORDEN. Los carteles se muestran de a uno:
    // gana el primero de la lista que califique, asi que el orden es diseno y no formato
    // de archivo. En particular el de unidades va ANTES que el del TP.
    // Si cambiaste un id a proposito, actualiza esta lista Y bumpea el `id` del flow:
    // los descartes viejos ya no aplican.
    expect(hints.map((h) => h.id)).toEqual([ID_COMISION, ID_UNIDADES, ID_TP, ID_CORREGIR])
  })

  test("el de unidades va antes que el del TP", () => {
    // Los dos pueden estar pendientes a la vez (la unidad NO es precondicion del TP), y
    // se muestra uno solo: el orden es lo unico que decide cual.
    expect(indiceDe(ID_UNIDADES)).toBeLessThan(indiceDe(ID_TP))
  })

  test("el id del flow es estable (es el prefijo de todos los descartes)", () => {
    // Renombrado de `docente` a `docente-v1` al sumar el cartel de unidades: el catalogo
    // cambio, asi que los descartes guardados bajo el id viejo ya no describen este flow.
    expect(docenteOnboarding.id).toBe("docente-v1")
  })
})

/* ========================================================================== */
/* 2. La unidad es OPCIONAL                                                   */
/* ========================================================================== */

describe("docenteOnboarding — la unidad es opcional", () => {
  test("el cartel de unidades NO cuenta para el progreso", () => {
    // `hechos` se deriva de `doneWhen`, no del descarte. Si este cartel contara, el
    // docente que no usa unidades cerraria el cartel y su progreso no llegaria NUNCA a
    // completo: el denominador tendria un paso que el eligio, con razon, no dar.
    expect(porId(ID_UNIDADES).countsTowardProgress).toBe(false)
  })

  test("los otros tres carteles SI cuentan para el progreso", () => {
    for (const id of CONTABLES) {
      expect({ id, cuenta: porId(id).countsTowardProgress !== false }).toEqual({
        id,
        cuenta: true,
      })
    }
  })

  test("el denominador del progreso es 3, no la cantidad de carteles", () => {
    // Lo mide el motor de verdad: 4 carteles declarados, 3 en el denominador.
    expect(hints.length).toBe(4)
    montar(NADA_CARGADO)
    expect(screen.getByTestId("progreso")).toHaveTextContent("0/3/no")
  })

  test("un docente que NUNCA uso unidades llega igual a progreso completo", () => {
    // El test que le da dientes a `countsTowardProgress: false`. Sin el, la asercion del
    // flag se cae sola apenas alguien lo "corrige".
    expect(porId(ID_UNIDADES).doneWhen(TERMINAL_SIN_UNIDADES)).toBe(false)
    montar(TERMINAL_SIN_UNIDADES)
    expect(screen.getByTestId("progreso")).toHaveTextContent("3/3/si")
  })

  test("el cartel de unidades sigue pendiente en el terminal sin unidades", () => {
    // Consecuencia asumida: el docente que no las usa lo ve una vez y lo cierra. Lo que
    // NO puede pasar es que eso le trabe el progreso, que es el test de arriba.
    expect(pendientes(TERMINAL_SIN_UNIDADES)).toEqual([ID_UNIDADES])
  })

  test("el cartel del TP NO depende de que exista una unidad", () => {
    // El zombie que podriamos fabricar nosotros: encadenar "primero la unidad, despues
    // el TP" cuando el dominio dice que la unidad es opcional (`unidad_id` nullable con
    // `ON DELETE SET NULL`, y el alumno ve los TPs huerfanos bajo "Sin unidad
    // asignada"). Si alguien encadena las precondiciones, este test se pone rojo.
    expect(porId(ID_TP).unlockWhen(SIN_UNIDADES_NI_TP)).toBe(true)
    expect(pendiente(porId(ID_TP), SIN_UNIDADES_NI_TP)).toBe(true)
  })

  test("con comision, sin unidades y sin TPs quedan pendientes los DOS carteles", () => {
    expect(pendientes(SIN_UNIDADES_NI_TP)).toEqual([ID_UNIDADES, ID_TP])
  })

  test("publicar un TP sin unidad retira el cartel del TP igual", () => {
    // Un TP huerfano es un TP: el paso esta hecho.
    expect(porId(ID_TP).doneWhen(SIN_UNIDADES_CON_TP)).toBe(true)
    expect(pendientes(SIN_UNIDADES_CON_TP)).toEqual([ID_UNIDADES])
  })

  test("el cartel de unidades NO aparece antes de saber si hay unidades", () => {
    const sinCargar = estado({ ...SIN_UNIDADES_NI_TP, unidadesCargadas: false })
    expect(porId(ID_UNIDADES).unlockWhen(sinCargar)).toBe(false)
  })

  test("el de unidades tampoco se dispara sin comision", () => {
    expect(porId(ID_UNIDADES).unlockWhen(SIN_COMISION)).toBe(false)
    expect(pendientes(estado({ unidadesCargadas: true }))).toEqual([])
  })

  test("con los dos pendientes, el motor muestra el de unidades", () => {
    // Se muestra uno solo a la vez y gana el primero de la lista. Que sea el de unidades
    // es una decision de orden, y esta es la unica forma de verificarla de punta a punta.
    montar(SIN_UNIDADES_NI_TP)
    expect(idVisible()).toBe(ID_UNIDADES)
  })

  test("descartado el de unidades, aparece el del TP: no quedan encadenados", () => {
    // La version end-to-end de la regla. Cerrar el cartel de unidades no bloquea nada,
    // porque el del TP nunca dependio de la unidad.
    montar(SIN_UNIDADES_NI_TP)
    expect(idVisible()).toBe(ID_UNIDADES)
    cerrarCartelVisible(ID_UNIDADES)
    expect(idVisible()).toBe(ID_TP)
  })
})

/* ========================================================================== */
/* 3. Coherencia de las dos condiciones                                       */
/* ========================================================================== */

describe("docenteOnboarding — coherencia unlockWhen / doneWhen", () => {
  test.each(ESTADOS)("en el estado $nombre, un hint cumplido nunca queda pendiente", ({
    estado: e,
  }) => {
    // El contrato es `unlock && !done`. Que los dos den true a la vez es legal y
    // significa "cumplido": lo que no puede pasar es que igual quede pendiente.
    const cumplidosPendientes = hints
      .filter((h) => h.doneWhen(e) && pendiente(h, e))
      .map((h) => h.id)
    expect(cumplidosPendientes).toEqual([])
  })

  test("en el estado terminal no queda NINGUN cartel pendiente", () => {
    // El "se muestra para siempre": un `doneWhen` que no llega a cubrir el estado
    // final le queda pidiendo al docente algo que ya hizo.
    expect(pendientes(TERMINAL)).toEqual([])
  })

  test("todo hint es alcanzable: existe al menos un estado donde queda pendiente", () => {
    // Un hint con `unlockWhen` contenido en `doneWhen` es codigo muerto: nunca se ve.
    const inalcanzables = hints
      .filter((h) => !ESTADOS.some(({ estado: e }) => pendiente(h, e)))
      .map((h) => h.id)
    expect(inalcanzables).toEqual([])
  })

  test("con nada cargado no hay NADA pendiente", () => {
    // La mitad `*Cargad*` de cada unlockWhen. Sin ella el cartel parpadea al llegar el
    // fetch y le afirma al docente algo que no sabemos.
    expect(pendientes(NADA_CARGADO)).toEqual([])
  })

  test("el unico solape de carteles pendientes es unidades + TP", () => {
    // El invariante viejo era "nunca hay dos pendientes a la vez", y lo rompio el cartel
    // de unidades A PROPOSITO: la unidad es opcional, asi que no puede ser precondicion
    // del TP y los dos conviven. Lo que reemplaza al invariante es esto: el solape es el
    // que alguien decidio, y es UNO solo. Cualquier otro par simultaneo es una cadena
    // que se construyo sin querer, o dos carteles peleando por la misma pantalla.
    const solapes = ESTADOS.map(({ nombre, estado: e }) => ({ nombre, carteles: pendientes(e) }))
      .filter((x) => x.carteles.length > 1)
      .map((x) => [x.nombre, x.carteles])
    expect(solapes).toEqual([["sin unidades ni TP", [ID_UNIDADES, ID_TP]]])
  })

  test("los predicados son puros: no mutan el estado que reciben", () => {
    const e = estado({ ...CON_ENTREGA_PENDIENTE })
    const antes = JSON.stringify(e)
    for (const h of hints) {
      h.unlockWhen(e)
      h.doneWhen(e)
    }
    expect(JSON.stringify(e)).toBe(antes)
  })
})

/* ========================================================================== */
/* 4. El recorrido del docente nuevo                                          */
/* ========================================================================== */

describe("docenteOnboarding — recorrido del docente nuevo", () => {
  test("sin comision: SOLO el cartel de comision", () => {
    expect(pendientes(SIN_COMISION)).toEqual([ID_COMISION])
  })

  test("el cartel de sin comision no se ata a ninguna ruta", () => {
    // Sin comision no hay nada que hacer en ninguna vista. Un cartel global se declara
    // OMITIENDO `route`, no poniendo `route: "/"`.
    expect(porId(ID_COMISION).route).toBeUndefined()
  })

  test("con comision y sin nada armado: unidades primero, TP despues", () => {
    expect(pendientes(SIN_UNIDADES_NI_TP)).toEqual([ID_UNIDADES, ID_TP])
    expect(porId(ID_COMISION).doneWhen(SIN_UNIDADES_NI_TP)).toBe(true)
  })

  test("con unidad creada y sin TP: SOLO el del TP", () => {
    expect(pendientes(SIN_TP)).toEqual([ID_TP])
  })

  test("con TP publicado el cartel del TP se retira solo", () => {
    expect(porId(ID_TP).doneWhen(CON_TP_SIN_ENTREGAS)).toBe(true)
    expect(pendientes(CON_TP_SIN_ENTREGAS)).toEqual([])
  })

  test("llega la primera entrega: queda pendiente el de corregir", () => {
    expect(pendientes(CON_ENTREGA_PENDIENTE)).toEqual([ID_CORREGIR])
  })

  test("despues de corregir no queda ningun cartel", () => {
    expect(pendientes(TERMINAL)).toEqual([])
  })

  test("la progresion completa, estado por estado", () => {
    // La foto entera del recorrido en un solo lugar: si un cambio de condiciones corre
    // un cartel de momento, se ve aca aunque los tests puntuales sigan verdes.
    expect(ESTADOS.slice(0, 9).map(({ nombre, estado: e }) => [nombre, pendientes(e)])).toEqual([
      ["nada cargado", []],
      ["sin comision", [ID_COMISION]],
      ["sin unidades ni TP", [ID_UNIDADES, ID_TP]],
      ["sin TP", [ID_TP]],
      ["con TP y sin unidades", [ID_UNIDADES]],
      ["con TP y sin entregas", []],
      ["con entrega pendiente", [ID_CORREGIR]],
      ["terminal", []],
      ["terminal sin unidades", [ID_UNIDADES]],
    ])
  })

  test("GAP conocido: con comision asignada pero ninguna elegida no queda nada pendiente", () => {
    // `tpsCargados` y `unidadesCargadas` salen de queries deshabilitadas mientras
    // `comisionActivaId` es null, asi que esos carteles no se desbloquean hasta que el
    // docente elige una comision en el selector. Caracterizacion, no aprobacion: si el
    // docente nuevo aterriza sin comision preseleccionada, el onboarding se queda mudo.
    const sinElegir = estado({ comisionesCargadas: true, tieneComision: true })
    expect(pendientes(sinElegir)).toEqual([])
  })
})

/* ========================================================================== */
/* 5. Anti-zombie                                                             */
/* ========================================================================== */

describe("docenteOnboarding — anti-zombie", () => {
  test("el cartel de corregir NO queda pendiente si no hay ninguna entrega esperando", () => {
    // Es el equivalente docente del zombie del alumno: pedirle que corrija cuando la
    // cola esta vacia. `hayEntregaPendiente` es la mitad que no se puede sacar.
    const corregir = porId(ID_CORREGIR)
    expect(corregir.unlockWhen(CON_TP_SIN_ENTREGAS)).toBe(false)
    expect(pendiente(corregir, CON_TP_SIN_ENTREGAS)).toBe(false)
  })

  test("el cartel de corregir tampoco queda pendiente con las entregas sin cargar", () => {
    const entregasSinCargar = estado({ ...CON_ENTREGA_PENDIENTE, entregasCargadas: false })
    expect(pendiente(porId(ID_CORREGIR), entregasSinCargar)).toBe(false)
  })

  test("el cartel del TP NO queda pendiente si todavia no sabemos si hay TPs", () => {
    const tpsSinCargar = estado({
      comisionesCargadas: true,
      tieneComision: true,
      comisionActivaId: COMISION,
      unidadesCargadas: true,
    })
    expect(porId(ID_TP).unlockWhen(tpsSinCargar)).toBe(false)
  })

  test("apenas llega la entrega, el cartel se desbloquea solo", () => {
    expect(pendiente(porId(ID_CORREGIR), CON_TP_SIN_ENTREGAS)).toBe(false)
    expect(pendiente(porId(ID_CORREGIR), CON_ENTREGA_PENDIENTE)).toBe(true)
  })

  test("ningun cartel se muestra cuando no llego NINGUN dato", () => {
    // Barrido: los datos "de contenido" puestos en su peor combinacion, pero con todos
    // los flags `*Cargad*` apagados. Nadie puede hablar.
    const nadaSabido = estado({
      tieneComision: true,
      comisionActivaId: COMISION,
      tieneUnidad: false,
      tieneTp: false,
      hayEntregaPendiente: true,
    })
    expect(pendientes(nadaSabido)).toEqual([])
  })
})

/* ========================================================================== */
/* 6. Idempotencia                                                            */
/* ========================================================================== */

describe("docenteOnboarding — idempotencia", () => {
  test("el docente que ya tenia comision nunca ve el cartel de sin comision", () => {
    const conComision = estado({ comisionesCargadas: true, tieneComision: true })
    expect(pendiente(porId(ID_COMISION), conComision)).toBe(false)
  })

  test("el docente que creo su TP por afuera nunca ve el cartel del TP", () => {
    // Nace cumplido, sin haberlo descartado jamas.
    expect(pendiente(porId(ID_TP), CON_TP_SIN_ENTREGAS)).toBe(false)
  })

  test("el docente que ya tenia unidades nunca ve el cartel de unidades", () => {
    expect(pendiente(porId(ID_UNIDADES), SIN_TP)).toBe(false)
  })

  test("dentro de una misma comision, lo cumplido queda cumplido", () => {
    // Monotonia. Un `doneWhen` que vuelve a false resucita un cartel ya cerrado. Es lo
    // que hace tolerable persistir los descartes por-navegador: al perderlos reaparecen
    // los pendientes, nunca los cumplidos.
    // Se verifica sobre UNA comision: cambiar de comision activa SI puede volver a
    // false `hayEntregaCorregida`, y eso es semantica por-comision, no un bug.
    const progresion = [
      SIN_COMISION,
      SIN_UNIDADES_NI_TP,
      SIN_TP,
      CON_TP_SIN_ENTREGAS,
      CON_ENTREGA_PENDIENTE,
      TERMINAL,
    ]
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
    // Se deriva del estado real y solo de el. Se aproxima verificando que dos
    // evaluaciones seguidas del mismo estado dan lo mismo.
    for (const h of hints) {
      for (const { estado: e } of ESTADOS) {
        expect(h.doneWhen(e)).toBe(h.doneWhen(e))
      }
    }
  })

  test("descartar un cartel no lo cuenta como hecho", () => {
    // El progreso sale del estado real. Cerrar el cartel del TP no publica ningun TP.
    montar(SIN_TP)
    expect(screen.getByTestId("progreso")).toHaveTextContent("1/3/no")
    cerrarCartelVisible(ID_TP)
    expect(screen.getByTestId("progreso")).toHaveTextContent("1/3/no")
  })
})

/* ========================================================================== */
/* 7. Declaracion de rutas y anclas                                           */
/* ========================================================================== */

describe("docenteOnboarding — declaracion de rutas y anclas", () => {
  test("las rutas declaradas arrancan con /", () => {
    for (const h of hints) {
      if (h.route !== undefined) expect(h.route.startsWith("/")).toBe(true)
    }
  })

  test("ninguna ruta declarada termina en / (salvo la raiz)", () => {
    // El motor compara por segmento: `ruta === route || ruta.startsWith(route + "/")`.
    // Un `route: "/correcciones/"` no matchea NADA y deja el cartel muerto en silencio.
    for (const h of hints) {
      if (h.route !== undefined && h.route !== "/") {
        expect(h.route.endsWith("/")).toBe(false)
      }
    }
  })

  test("toda ruta declarada corresponde a una ruta real del web-teacher", () => {
    for (const h of hints) {
      if (h.route !== undefined) expect(RUTAS_REGISTRADAS).toContain(h.route)
    }
  })

  test("los anchors son valores de data-tour, no selectores CSS", () => {
    // El motor interpola el anchor dentro de `[data-tour="..."]`. Un punto o un
    // numeral adelante indica que alguien escribio un selector y no va a resolver.
    for (const h of hints) {
      if (h.anchor !== undefined) expect(h.anchor).toMatch(/^[a-z0-9:/-]+$/)
    }
  })

  test("los anchors nav: apuntan a rutas que el sidebar realmente registra", () => {
    // El Sidebar deriva `data-tour="nav:<item.id>"` del id del NavItem, que es la ruta.
    // Un anchor `nav:/foo` con una ruta que no existe degrada a cartel centrado en
    // silencio: se pierde el senalamiento sin que nada falle.
    for (const h of hints) {
      if (h.anchor?.startsWith("nav:")) {
        expect(RUTAS_REGISTRADAS).toContain(h.anchor.slice("nav:".length))
      }
    }
  })

  test("el cartel de unidades senala el item de Unidades del sidebar", () => {
    // Es el unico senalamiento que tiene: no navega, le muestra al docente adonde ir.
    expect(porId(ID_UNIDADES).anchor).toBe("nav:/unidades")
  })

  test("todo cartel tiene titulo y cuerpo", () => {
    for (const h of hints) {
      expect(h.title.trim().length).toBeGreaterThan(0)
      expect(h.body).toBeTruthy()
    }
  })

  test("ningun titulo se repite entre carteles", () => {
    // No es cosmetico: `idVisible()` de esta suite, y cualquier lectura humana del
    // cartel, se apoyan en el titulo para saber cual es.
    const titulos = hints.map((h) => h.title)
    expect(titulos.filter((t, i) => titulos.indexOf(t) !== i)).toEqual([])
  })
})

/* ========================================================================== */
/* 8. Encoding de los textos                                                  */
/* ========================================================================== */

/** Todo lo que el docente LEE de un cartel: titulo, cuerpo renderizado y CTA. */
function textoVisible(h: Hint): string {
  return [h.title, h.ctaLabel ?? "", renderToStaticMarkup(<>{h.body}</>)].join(" ")
}

const TILDES = /[À-ÿĀ-ſ]/g
const PUNTUACION_PROHIBIDA = /[–—‘’“”…]/g

describe("docenteOnboarding — encoding de los textos", () => {
  test.each(hints.map((h) => ({ id: h.id, hint: h })))(
    "el cartel $id no tiene tildes ni enies",
    ({ hint }) => {
      // Regla de encoding del repo: la consola cp1252 de Windows rompe con no-ASCII
      // y ya tumbo gates de CI (ver CLAUDE.md, "Scripts con stdout en Windows").
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
