/**
 * Toda ruta del panel tiene que ser ALCANZABLE desde el menu.
 *
 * El 2026-08-28 se descubrio que `/activeia` —la pantalla donde el docente
 * conecta su cuenta de Active-IA y sincroniza rubricas, o sea la que habilita
 * el boton "Corregir con IA"— existia completa, ruteada y con su formulario,
 * pero **no figuraba en ninguno de los 16 items del sidebar**. Solo se llegaba
 * escribiendo la URL a mano.
 *
 * Nadie la habia usado nunca. No porque estuviera rota: porque no tenia
 * puerta. Eso explica que la doc dijera que jamas se sincronizo una rubrica
 * con Active-IA — se leia como "falta la cuenta" y era ademas "no se podia
 * entrar".
 *
 * Lo que hace a este bug interesante es que la suite tenia ~300 tests del
 * panel y ninguno lo veia. Todos prueban que una vista FUNCIONA; ninguno
 * preguntaba si se puede LLEGAR. Un menu es de las pocas cosas que se
 * verifican mirando, y por eso lo encontro un humano usando la app.
 *
 * Este test cierra esa clase entera: si mañana alguien agrega una ruta y se
 * olvida del item, se entera acá y no tres meses despues.
 */
import { readdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import { NAV_GROUPS } from "../src/routes/__root"

const RUTAS_DIR = join(dirname(fileURLToPath(import.meta.url)), "../src/routes")

/**
 * Rutas que NO van al menu, cada una con su motivo.
 *
 * La lista es explicita a proposito: agregar algo acá obliga a escribir por
 * que, y eso es justo lo que no paso con `/activeia`. Un `.filter()` generico
 * la habria tragado en silencio.
 */
const FUERA_DEL_MENU: Record<string, string> = {
  __root: "es el layout, no una pantalla",
  index: "es la home; entra por 'Mis comisiones'",
  "episode-timeline": "detalle de UN episodio: se llega desde Progresion, no del menu",
  kappa: "detalle de una corrida de inter-jueces: se llega desde Codificacion",
  "interrater-admin": "vista de administracion: se llega desde Codificacion",
  templates: "detalle de plantillas: se llega desde Trabajos Practicos",
}

function rutasEnDisco(): string[] {
  return readdirSync(RUTAS_DIR)
    .filter((f) => f.endsWith(".tsx"))
    .map((f) => f.replace(/\.tsx$/, ""))
}

function idsDelMenu(): string[] {
  return NAV_GROUPS.flatMap((g) => g.items.map((i) => i.id))
}

describe("toda ruta del panel es alcanzable desde el menu", () => {
  it("no hay ninguna pantalla sin puerta", () => {
    const enMenu = new Set(idsDelMenu().map((id) => id.replace(/^\//, "")))
    const huerfanas = rutasEnDisco().filter(
      (r) => !enMenu.has(r) && !(r in FUERA_DEL_MENU),
    )
    expect(huerfanas, `rutas sin item en el sidebar (agregalas al menu, o a FUERA_DEL_MENU con el motivo): ${huerfanas.join(", ")}`).toEqual([])
  })

  it("/activeia esta en el menu — es la regresion que origino este archivo", () => {
    expect(idsDelMenu()).toContain("/activeia")
  })

  it("no hay items del menu apuntando a rutas que no existen", () => {
    // La otra mitad: un item cuyo destino se borro es un link roto, y el
    // sintoma (pantalla en blanco) es mas confuso que no tener el item.
    const enDisco = new Set(rutasEnDisco())
    const rotos = idsDelMenu()
      .map((id) => id.replace(/^\//, ""))
      .filter((r) => r !== "" && !enDisco.has(r))
    expect(rotos, `items del menu sin ruta: ${rotos.join(", ")}`).toEqual([])
  })

  it("la lista de excepciones no tiene entradas muertas", () => {
    // Una excepcion que ya no corresponde a ninguna ruta es documentacion
    // vencida: dice que algo esta fuera del menu a proposito cuando ese algo
    // ya no existe.
    const enDisco = new Set(rutasEnDisco())
    const muertas = Object.keys(FUERA_DEL_MENU).filter((r) => !enDisco.has(r))
    expect(muertas, `excepciones que ya no existen: ${muertas.join(", ")}`).toEqual([])
  })
})
