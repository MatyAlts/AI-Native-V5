// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Tests de los TOURS LINEALES del docente: el panoramico de primer ingreso
 * (`src/tour/docenteTour.tsx`) y los cinco tutoriales por vista (`src/tour/vistas.tsx`).
 *
 * Son datos: un array de pasos con id, ruta, ancla y copy. Se testean sin renderizar.
 *
 * Lo que blinda esta suite:
 *
 *   1. IDS UNICOS por flow. El id del paso es lo que sostiene el resume post-reload
 *      (`persistencia.leerTour` guarda `paso` y `maybeStart` lo busca con `findIndex`).
 *      Dos pasos con el mismo id hacen que el resume vuelva siempre al primero de los
 *      dos, en silencio.
 *   2. IDS DE FLOW UNICOS entre tours. El id del flow es la clave de localStorage
 *      (`ai-native:tour:<id>`). Dos flows con el mismo id comparten estado: completar
 *      uno apaga el otro.
 *   3. ANCLAS Y RUTAS COHERENTES. Un ancla que no resuelve degrada a cartel centrado
 *      en silencio (`useAnchorRect` devuelve null tras 2,5s). No falla nada: solo se
 *      pierde el senalamiento, que es justo lo que el tour venia a hacer. Por eso hay
 *      un test que va a buscar cada ancla al codigo de las vistas: es el unico modo de
 *      que un ancla escrita de memoria no pase desapercibida.
 *   4. TEXTOS SIN TILDES NI EM DASHES (regla de encoding del repo, cp1252 en Windows).
 *
 * Lo que NO se testea aca: el comportamiento del motor (navegacion, medicion del ancla,
 * resume). Eso vive en `packages/ui/src/components/Tour/*.test.tsx`. Replicarlo seria
 * fabricar una copia que se queda verde afirmando la regla vieja cuando el motor cambie.
 */
import type { TourFlow, TourStep } from "@platform/ui"
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, test } from "vitest"
import { docenteTour } from "../src/tour/docenteTour"
import {
  correccionesTour,
  ejerciciosTour,
  nivelesTour,
  tareasPracticasTour,
  unidadesTour,
} from "../src/tour/vistas"

const FLOWS: { nombre: string; flow: TourFlow }[] = [
  { nombre: "docenteTour", flow: docenteTour },
  { nombre: "unidadesTour", flow: unidadesTour },
  { nombre: "ejerciciosTour", flow: ejerciciosTour },
  { nombre: "tareasPracticasTour", flow: tareasPracticasTour },
  { nombre: "correccionesTour", flow: correccionesTour },
  { nombre: "nivelesTour", flow: nivelesTour },
]

/**
 * Los tutoriales de vista (capa 2) son todos menos el panoramico. Se disparan desde la
 * vista ya montada, asi que no navegan: por eso tienen reglas propias mas abajo.
 */
const TUTORIALES_DE_VISTA = FLOWS.filter(({ nombre }) => nombre !== "docenteTour")

/**
 * Prefijo de `data-tour` que le corresponde a cada tutorial de vista. Convencion que ya
 * seguian los cuatro originales: el ancla lleva el nombre de la vista adelante, asi que
 * dos vistas no pueden pisarse el mismo `data-tour`.
 */
const PREFIJO_DE_ANCLA: Record<string, string> = {
  unidadesTour: "unidades:",
  ejerciciosTour: "ejercicios:",
  tareasPracticasTour: "tp:",
  correccionesTour: "correcciones:",
  nivelesTour: "niveles:",
}

/**
 * Rutas que el web-teacher registra hoy (TanStack file-based, `src/routes/`).
 * Si agregaste una vista nueva y su tour, sumala aca.
 */
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
  "/student-longitudinal",
  "/cohort-adversarial",
]

/* ========================================================================== */
/* 1. Ids                                                                     */
/* ========================================================================== */

describe("tours del docente — ids", () => {
  test.each(FLOWS)("$nombre no repite ids de paso", ({ flow }) => {
    const ids = flow.steps.map((s) => s.id)
    // Un id repetido rompe el resume: `maybeStart` hace findIndex y vuelve siempre al
    // primero de los dos, asi que el tour se queda trabado ahi despues de un reload.
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([])
  })

  test.each(FLOWS)("$nombre tiene ids de paso no vacios y sin espacios", ({ flow }) => {
    for (const s of flow.steps) {
      expect(s.id).toMatch(/^[a-z0-9-]+$/)
    }
  })

  test("los ids de flow son unicos entre todos los tours", () => {
    // El id del flow es la clave de localStorage `ai-native:tour:<id>`. Compartirla
    // hace que completar un tour apague otro.
    const ids = FLOWS.map(({ flow }) => flow.id)
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([])
  })

  test("los ids de flow son estables (bumpear uno re-dispara el tour para todos)", () => {
    // Candado deliberado: cambiar un id aca le vuelve a mostrar el tour a TODOS los
    // docentes. Se hace cuando el recorrido cambia de verdad, no por retocar copy.
    expect(FLOWS.map(({ flow }) => flow.id)).toEqual([
      "docente-v1",
      "docente-unidades-v1",
      "docente-ejercicios-v1",
      "docente-tareas-practicas-v1",
      "docente-correcciones-v1",
      "docente-niveles-v1",
    ])
  })

  test("ningun id de paso se repite entre flows distintos", () => {
    // No lo rompe hoy (el estado se guarda por flow) pero hace ilegible cualquier
    // rastro y es sintoma de copy-paste entre tutoriales.
    const todos = FLOWS.flatMap(({ nombre, flow }) =>
      flow.steps.map((s) => ({ nombre, id: s.id })),
    )
    const vistos = new Map<string, string>()
    const choques: { id: string; en: string[] }[] = []
    for (const { nombre, id } of todos) {
      const previo = vistos.get(id)
      if (previo !== undefined) choques.push({ id, en: [previo, nombre] })
      else vistos.set(id, nombre)
    }
    expect(choques).toEqual([])
  })
})

/* ========================================================================== */
/* 2. Forma de los pasos                                                      */
/* ========================================================================== */

describe("tours del docente — forma de los pasos", () => {
  test.each(FLOWS)("$nombre tiene al menos un paso", ({ flow }) => {
    // Un flow vacio hace que `start` guarde `paso: undefined` y el overlay no monte:
    // el boton de "ver el tour de nuevo" queda sin efecto visible.
    expect(flow.steps.length).toBeGreaterThan(0)
  })

  test.each(FLOWS)("$nombre declara titulo y cuerpo en cada paso", ({ flow }) => {
    for (const s of flow.steps) {
      expect(s.title.trim().length).toBeGreaterThan(0)
      expect(s.body).toBeTruthy()
    }
  })

  test.each(FLOWS)("$nombre solo navega a rutas registradas", ({ flow }) => {
    // `TourProvider` hace `navigate(paso.route)` al entrar al paso. Una ruta que no
    // existe tira al 404 del router en medio del tour.
    for (const s of flow.steps) {
      if (s.route !== undefined) expect(RUTAS_REGISTRADAS).toContain(s.route)
    }
  })

  test.each(FLOWS)("$nombre usa anchors con forma de data-tour, no selectores", ({ flow }) => {
    // El motor interpola el anchor dentro de `[data-tour="..."]`. Un punto o un
    // numeral adelante indica que alguien escribio un selector CSS y no va a resolver.
    for (const s of flow.steps) {
      if (s.anchor !== undefined) expect(s.anchor).toMatch(/^[a-z0-9:/-]+$/)
    }
  })

  test.each(FLOWS)("$nombre apunta sus anchors nav: a rutas registradas", ({ flow }) => {
    // El Sidebar deriva `data-tour="nav:<item.id>"` del id del NavItem, que es la ruta.
    // Un `nav:/ruta-inexistente` degrada a cartel centrado en silencio.
    for (const s of flow.steps) {
      if (s.anchor?.startsWith("nav:")) {
        expect(RUTAS_REGISTRADAS).toContain(s.anchor.slice("nav:".length))
      }
    }
  })

  test.each(FLOWS)("$nombre usa placements validos", ({ flow }) => {
    const validos = ["top", "bottom", "left", "right"]
    for (const s of flow.steps) {
      if (s.placement !== undefined) expect(validos).toContain(s.placement)
    }
  })

  test.each(FLOWS)("$nombre declara ancla en todo paso que navega a una vista", ({ flow }) => {
    // Un paso con `route` y sin `anchor` navega y despues muestra una card centrada
    // sobre una pantalla que el usuario no pidio. No es fatal, pero casi siempre es
    // un ancla que se olvidaron de poner.
    const sinAncla = flow.steps.filter((s) => s.route !== undefined && s.anchor === undefined)
    expect(sinAncla.map((s) => s.id)).toEqual([])
  })
})

/* ========================================================================== */
/* 3. El panoramico                                                           */
/* ========================================================================== */

describe("docenteTour — el panoramico", () => {
  test("recorre las secciones en el orden del trabajo real", () => {
    // Candado sobre el recorrido entero. Sumar o sacar un paso aca cambia lo que ve
    // TODO docente que entra por primera vez: que sea una decision explicita y no el
    // efecto colateral de tocar el archivo.
    expect(docenteTour.steps.map((s) => s.id)).toEqual([
      "bienvenida",
      "comisiones",
      "unidades",
      "ejercicios",
      "tps",
      "correcciones",
      "niveles",
    ])
  })

  test("el paso de Unidades navega a /unidades y senala su item del sidebar", () => {
    const paso = docenteTour.steps.find((s) => s.id === "unidades")
    expect(paso).toBeDefined()
    expect(paso?.route).toBe("/unidades")
    expect(paso?.anchor).toBe("nav:/unidades")
  })

  test("Unidades va antes que Ejercicios y que TPs: el contenedor antes que el contenido", () => {
    // El orden del panoramico es el argumento pedagogico del recorrido, no el del
    // sidebar: primero el tema, despues las piezas que viven adentro. El candado de la
    // lista completa ya lo fija, pero esto deja escrito POR QUE, para que reordenar sea
    // una decision y no un accidente de edicion.
    const pos = (id: string) => docenteTour.steps.findIndex((s) => s.id === id)
    expect(pos("unidades")).toBeGreaterThan(-1)
    expect(pos("unidades")).toBeLessThan(pos("ejercicios"))
    expect(pos("unidades")).toBeLessThan(pos("tps"))
  })

  test("solo el primer paso va sin ancla (es la card de bienvenida)", () => {
    // El resto senala algo. Un paso sin ancla en el medio del panoramico es una card
    // centrada sobre una pantalla que el docente no pidio.
    const sinAncla = docenteTour.steps.filter((s) => s.anchor === undefined).map((s) => s.id)
    expect(sinAncla).toEqual(["bienvenida"])
  })

  test("el panoramico es el UNICO flow que navega", () => {
    // Los tutoriales de vista se disparan desde la vista ya montada: navegar seria
    // redundante, y peor, los sacaria de la pantalla que estan explicando.
    const queNavegan = TUTORIALES_DE_VISTA.filter(({ flow }) =>
      flow.steps.some((s) => s.route !== undefined),
    ).map(({ nombre }) => nombre)
    expect(queNavegan).toEqual([])
  })
})

/* ========================================================================== */
/* 4. Anclas de los tutoriales de vista                                       */
/* ========================================================================== */

/** Todas las anclas `data-tour="..."` que el codigo del web-teacher declara hoy. */
function anclasDeclaradasEnElCodigo(): Set<string> {
  // `process.cwd()` es la raiz de la app: vitest corre desde `apps/web-teacher`.
  // `import.meta.url` no sirve aca — en el entorno jsdom no es una URL `file:`.
  const raiz = join(process.cwd(), "src")
  const encontradas = new Set<string>()
  const patron = /data-tour=\{?["'`]([^"'`]+)["'`]/g

  const recorrer = (dir: string): void => {
    for (const entrada of readdirSync(dir, { withFileTypes: true })) {
      const ruta = join(dir, entrada.name)
      if (entrada.isDirectory()) {
        recorrer(ruta)
        continue
      }
      if (!/\.tsx?$/.test(entrada.name)) continue
      const texto = readFileSync(ruta, "utf8")
      for (const m of texto.matchAll(patron)) {
        const valor = m[1]
        if (valor !== undefined) encontradas.add(valor)
      }
    }
  }

  recorrer(raiz)
  return encontradas
}

describe("tutoriales de vista — anclas", () => {
  test.each(TUTORIALES_DE_VISTA)("$nombre usa el prefijo de ancla de su vista", ({
    nombre,
    flow,
  }) => {
    const prefijo = PREFIJO_DE_ANCLA[nombre] ?? "(sin prefijo declarado)"
    const ajenas = flow.steps
      .filter((s) => s.anchor !== undefined && !s.anchor.startsWith(prefijo))
      .map((s) => ({ paso: s.id, anchor: s.anchor }))
    expect(ajenas).toEqual([])
  })

  test("ningun ancla se declara desde dos tutoriales distintos", () => {
    // Dos tutoriales apuntando al mismo `data-tour` es sintoma de copy-paste y hace que
    // mover el elemento rompa dos recorridos sin que se note.
    const vistos = new Map<string, string>()
    const choques: { anchor: string; en: string[] }[] = []
    for (const { nombre, flow } of TUTORIALES_DE_VISTA) {
      for (const s of flow.steps) {
        if (s.anchor === undefined) continue
        const previo = vistos.get(s.anchor)
        if (previo !== undefined) choques.push({ anchor: s.anchor, en: [previo, nombre] })
        else vistos.set(s.anchor, nombre)
      }
    }
    expect(choques).toEqual([])
  })

  test("toda ancla declarada existe como data-tour en el codigo del web-teacher", () => {
    // El fallo que este test evita NO rompe nada visible: `useAnchorRect` no encuentra
    // el elemento, espera 2,5s y degrada a card centrada. El tour sigue andando y no
    // senala nada. Se descubre mirandolo, o nunca.
    // El ancla `nav:<ruta>` la deriva el Sidebar del id del NavItem, asi que no aparece
    // literal en el codigo: esas ya las cubre el test de rutas registradas.
    const declaradas = anclasDeclaradasEnElCodigo()
    const huerfanas = FLOWS.flatMap(({ nombre, flow }) =>
      flow.steps
        .filter((s) => s.anchor !== undefined && !s.anchor.startsWith("nav:"))
        .filter((s) => !declaradas.has(s.anchor as string))
        .map((s) => ({ tour: nombre, paso: s.id, anchor: s.anchor })),
    )
    expect(huerfanas).toEqual([])
  })
})

/* ========================================================================== */
/* 5. Encoding de los textos                                                  */
/* ========================================================================== */

function textoVisible(s: TourStep): string {
  return [s.title, renderToStaticMarkup(<>{s.body}</>)].join(" ")
}

const TILDES = /[À-ÿĀ-ſ]/g
const PUNTUACION_PROHIBIDA = /[–—‘’“”…]/g

describe("tours del docente — encoding de los textos", () => {
  test.each(FLOWS)("$nombre no tiene tildes ni enies en el copy", ({ flow }) => {
    // Regla de encoding del repo: la consola cp1252 de Windows rompe con no-ASCII y
    // ya tumbo gates de CI (ver CLAUDE.md, "Scripts con stdout en Windows").
    const encontrados = flow.steps.flatMap((s) =>
      (textoVisible(s).match(TILDES) ?? []).map((c) => ({ paso: s.id, caracter: c })),
    )
    expect(encontrados).toEqual([])
  })

  test.each(FLOWS)("$nombre no tiene em dashes ni comillas curvas", ({ flow }) => {
    const encontrados = flow.steps.flatMap((s) =>
      (textoVisible(s).match(PUNTUACION_PROHIBIDA) ?? []).map((c) => ({ paso: s.id, caracter: c })),
    )
    expect(encontrados).toEqual([])
  })

  test.each(FLOWS)("$nombre tiene todo su texto visible en ASCII imprimible", ({ flow }) => {
    // Red de seguridad: cubre espacios duros, guiones raros y cualquier cosa que entre
    // por copy-paste desde un doc.
    const sospechosos = new Set<string>()
    for (const s of flow.steps) {
      for (const c of textoVisible(s)) {
        const code = c.codePointAt(0) ?? 0
        if (code > 126 || (code < 32 && c !== "\n")) sospechosos.add(c)
      }
    }
    expect([...sospechosos]).toEqual([])
  })
})
