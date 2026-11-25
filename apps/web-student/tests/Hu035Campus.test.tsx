import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
/**
 * Aceptacion HU-035 (orquestador, antes de construir; el constructor no la
 * modifica). Autorizada por Jarvis en nombre de Juani (24/11). Prototipo:
 * https://claude.ai/artifact/BzTaGZcb55VdcZUbdswv6B (fila del alumno).
 *
 * El alumno navega el campus de su comision: a la izquierda solo "Mis
 * cursos"; el curso muestra la bienvenida y las unidades como tarjetas; cada
 * unidad tiene Introduccion y Trabajos practicos con su estado. El TP y el
 * episodio quedan como hoy: se llega a `/materia/$id?tareaId=...`.
 *
 * Contrato que fija esta prueba:
 *  - `estadoTp(entrega)` en `src/lib/estadoTp.ts` -> { tipo, etiqueta }:
 *      sin entrega o draft sin ejercicios completados -> pendiente "Pendiente"
 *      draft con >=1 completado, o returned           -> en_curso "En curso"
 *      submitted                                      -> esperando "Esperando correccion" (con tilde)
 *      graded                                         -> calificado "Calificado · 8" (8.5 -> "8,5"; sin nota -> "Calificado")
 *  - `unidadAbierta(fecha, hoy)` y `formatearFecha(fecha)` en
 *    `src/lib/fechaCampus.ts` (fechas "YYYY-MM-DD", sin pasar por Date).
 *  - `BarraCursos({ cursos, comisionActiva })` en `src/components/BarraCursos.tsx`:
 *    <nav aria-label="Mis cursos"> con un link "Mis cursos" a "/" y un link
 *    por curso (texto = nombre de la materia) a `/curso/<comision_id>`;
 *    el activo con aria-current="page". `mostrarBarraCursos(pathname)` es
 *    false en `/episodio/...` y true en el resto.
 *  - `CursoView({ comisionId, getToken, hoy })` en `src/views/CursoView.tsx`:
 *    titulo = nombre de la materia; bienvenida en `HtmlAislado` titulo
 *    "Bienvenida del curso" (si hay HTML); una tarjeta por unidad en orden.
 *    Abierta: link con el nombre a `/curso/<c>/unidad/<u>` y "N trabajos
 *    practicos" (singular "1 trabajo practico", con tildes). Cerrada: sin
 *    link y el texto "Abre el dd/mm/aaaa". Links "Mis notas" a
 *    `/mis-notas?comisionId=<c>` y "Mi progreso" a `/progreso?comisionId=<c>`.
 *  - `UnidadView({ comisionId, unidadId, pestana, getToken, hoy })` en
 *    `src/views/UnidadView.tsx`: pestañas (role=tab) "Introducción" y
 *    "Trabajos prácticos" con aria-selected. Introduccion en `HtmlAislado`
 *    titulo "Introducción de la unidad", o el texto "Esta unidad todavía no
 *    tiene introducción". Trabajos practicos: solo los TPs publicados de esa
 *    unidad, cada uno un link con su titulo a
 *    `/materia/<materia_id>?tareaId=<tp_id>` y su etiqueta de estado.
 *    Unidad cerrada: "Esta unidad abre el dd/mm/aaaa", sin introduccion ni
 *    links a TPs.
 *  - Rutas `src/routes/curso.$comisionId.tsx` y
 *    `src/routes/curso.$comisionId.unidad.$unidadId.tsx` (search `pestana`);
 *    la home navega a `/curso/$comisionId`; `/materia/$id` acepta `tareaId`;
 *    `/mis-notas` y `/progreso` aceptan `comisionId`.
 *
 * C01  Barra izquierda solo con "Mis cursos" y los cursos del alumno.
 * C02  El curso muestra la bienvenida en el recuadro aislado.
 * C03  Las unidades son tarjetas en orden, con su cantidad de TPs.
 * C04  La unidad tiene Introduccion y Trabajos practicos.
 * C05  Cada TP muestra su estado: Pendiente, En curso, Esperando correccion,
 *      Calificado con nota.
 * C06  El TP lleva al flujo de hoy (`/materia/$id?tareaId=`).
 * C07  Mis notas y Mi progreso se abren filtrados por el curso.
 * N01  Una unidad que todavia no abrio no se puede abrir ni muestra su
 *      introduccion ni sus TPs.
 * N02  La barra no aparece en el episodio (pantalla completa como hoy).
 * N03  Los TPs de otra unidad o en borrador no aparecen en la unidad.
 * N04  La fecha no se corre un dia por la zona horaria.
 */
import {
  Outlet,
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { BarraCursos, mostrarBarraCursos } from "../src/components/BarraCursos"
import { estadoTp } from "../src/lib/estadoTp"
import { formatearFecha, unidadAbierta } from "../src/lib/fechaCampus"
import { CursoView } from "../src/views/CursoView"
import { UnidadView } from "../src/views/UnidadView"
import { setupFetchMock } from "./_mocks"

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..")
const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const COM2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const MAT = "99999999-9999-9999-9999-999999999999"
const U1 = "11111111-1111-1111-1111-111111111111"
const U2 = "22222222-2222-2222-2222-222222222222"
const U3 = "33333333-3333-3333-3333-333333333333"
const HOY = "2027-03-10"

const curso = (comision_id: string, nombre: string, materia_id = MAT) => ({
  materia_id,
  codigo: "PROG1",
  nombre,
  comision_id,
  comision_codigo: "C1",
  comision_nombre: "Comision 1",
  horario_resumen: null,
  periodo_id: "p1",
  periodo_codigo: "2027-1",
  inscripcion_id: `i-${comision_id}`,
  fecha_inscripcion: "2027-03-01",
})

const unidad = (
  id: string,
  nombre: string,
  orden: number,
  extra: Record<string, unknown> = {},
) => ({
  id,
  comision_id: COM,
  nombre,
  descripcion: `Resumen de ${nombre}`,
  orden,
  introduccion_html: null,
  fecha_apertura: null,
  ...extra,
})

const tp = (id: string, titulo: string, unidad_id: string | null, estado = "published") => ({
  id,
  comision_id: COM,
  codigo: id.slice(0, 4),
  titulo,
  enunciado: "x",
  fecha_inicio: null,
  fecha_fin: null,
  estado,
  unidad_id,
})

const entrega = (
  tarea_practica_id: string,
  estado: string,
  extra: Record<string, unknown> = {},
) => ({
  id: `e-${tarea_practica_id}`,
  tarea_practica_id,
  comision_id: COM,
  estado,
  ejercicio_estados: [],
  nota_final: null,
  ...extra,
})

const UNIDADES = [
  unidad(U2, "Unidad 2 · Secuenciales", 1, {
    introduccion_html: "<h2>De que se trata</h2>",
    fecha_apertura: "2027-03-09",
  }),
  unidad(U1, "Unidad 1 · Bienvenida", 0),
  unidad(U3, "Unidad 3 · Condicionales", 2, { fecha_apertura: "2027-03-16" }),
]

const TPS = [
  tp("t1aaaaaa", "TP 2 · Primeros programas", U2),
  tp("t2aaaaaa", "TP 2b · Conversion de unidades", U2),
  tp("t3aaaaaa", "TP 2c · Precio con descuento", U2),
  tp("t4aaaaaa", "TP 2d · Secuenciales en Python", U2),
  tp("t5aaaaaa", "TP 2e · Borrador del docente", U2, "draft"),
  tp("t6aaaaaa", "TP 3 · Condicionales", U3),
]

const ENTREGAS = [
  entrega("t1aaaaaa", "graded", { nota_final: 8 }),
  entrega("t2aaaaaa", "submitted"),
  entrega("t3aaaaaa", "draft", { ejercicio_estados: [{ ejercicio_id: "e1", completado: true }] }),
]

function datos() {
  setupFetchMock({
    [`/api/v1/comisiones/${COM}/bienvenida`]: () => ({ html: "<h1>Bienvenidos a Prog 1</h1>" }),
    "/api/v1/materias/mias": () => ({
      data: [
        curso(COM, "Programación 1"),
        curso(COM2, "Programación 4", "88888888-8888-8888-8888-888888888888"),
      ],
    }),
    "/api/v1/unidades": () => ({ data: UNIDADES, meta: { cursor_next: null } }),
    "/api/v1/tareas-practicas": () => ({ data: TPS, meta: { cursor_next: null } }),
    "/api/v1/entregas": () => ({ data: ENTREGAS, meta: { cursor_next: null } }),
  })
}

function conRouter(node: ReactNode) {
  const root = createRootRoute({ component: () => <Outlet /> })
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => <>{node}</> })
  const router = createRouter({
    routeTree: root.addChildren([index]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>,
  )
}

const getToken = async () => "t"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

// ── Reglas puras ───────────────────────────────────────────────────────

describe("HU-035 · estado de cada TP (C05)", () => {
  it("sin entrega o borrador sin avances: Pendiente", () => {
    expect(estadoTp(null)).toEqual({ tipo: "pendiente", etiqueta: "Pendiente" })
    expect(estadoTp({ estado: "draft", ejercicio_estados: [], nota_final: null })).toEqual({
      tipo: "pendiente",
      etiqueta: "Pendiente",
    })
    expect(
      estadoTp({
        estado: "draft",
        ejercicio_estados: [{ completado: false }] as never,
        nota_final: null,
      }).tipo,
    ).toBe("pendiente")
  })

  it("borrador con un ejercicio completado o devuelto: En curso", () => {
    expect(
      estadoTp({
        estado: "draft",
        ejercicio_estados: [{ completado: true }] as never,
        nota_final: null,
      }),
    ).toEqual({ tipo: "en_curso", etiqueta: "En curso" })
    expect(estadoTp({ estado: "returned", ejercicio_estados: [], nota_final: null }).tipo).toBe(
      "en_curso",
    )
  })

  it("entregado: Esperando corrección", () => {
    expect(estadoTp({ estado: "submitted", ejercicio_estados: [], nota_final: null })).toEqual({
      tipo: "esperando",
      etiqueta: "Esperando corrección",
    })
  })

  it("calificado, con la nota en formato argentino", () => {
    expect(estadoTp({ estado: "graded", ejercicio_estados: [], nota_final: 8 })).toEqual({
      tipo: "calificado",
      etiqueta: "Calificado · 8",
    })
    expect(estadoTp({ estado: "graded", ejercicio_estados: [], nota_final: 8.5 }).etiqueta).toBe(
      "Calificado · 8,5",
    )
    expect(estadoTp({ estado: "graded", ejercicio_estados: [], nota_final: null }).etiqueta).toBe(
      "Calificado",
    )
  })
})

describe("HU-035 · fechas de apertura (N01, N04)", () => {
  it("abre el mismo dia de la fecha, no antes", () => {
    expect(unidadAbierta(null, HOY)).toBe(true)
    expect(unidadAbierta("2027-03-10", HOY)).toBe(true)
    expect(unidadAbierta("2027-03-09", HOY)).toBe(true)
    expect(unidadAbierta("2027-03-11", HOY)).toBe(false)
  })

  it("N04: formatea sin correr el dia", () => {
    expect(formatearFecha("2027-03-09")).toBe("09/03/2027")
    expect(formatearFecha("2027-01-01")).toBe("01/01/2027")
  })
})

// ── Barra izquierda ────────────────────────────────────────────────────

describe("HU-035 · barra Mis cursos (C01, N02)", () => {
  it("C01: solo Mis cursos y los cursos del alumno", async () => {
    conRouter(
      <BarraCursos
        cursos={[curso(COM, "Programación 1"), curso(COM2, "Programación 4")] as never}
        comisionActiva={COM}
      />,
    )
    const nav = await screen.findByRole("navigation", { name: "Mis cursos" })
    const links = within(nav).getAllByRole("link")
    expect(links.map((l) => l.textContent?.trim())).toEqual([
      "Mis cursos",
      "Programación 1",
      "Programación 4",
    ])
    expect(links[0]?.getAttribute("href")).toBe("/")
    expect(links[1]?.getAttribute("href")).toBe(`/curso/${COM}`)
    expect(links[2]?.getAttribute("href")).toBe(`/curso/${COM2}`)
    expect(links[1]?.getAttribute("aria-current")).toBe("page")
    expect(links[2]?.getAttribute("aria-current")).toBeNull()
  })

  it("N02: no aparece en el episodio", () => {
    expect(mostrarBarraCursos("/episodio/abc")).toBe(false)
    expect(mostrarBarraCursos("/")).toBe(true)
    expect(mostrarBarraCursos(`/curso/${COM}`)).toBe(true)
    expect(mostrarBarraCursos("/mis-notas")).toBe(true)
  })

  it("C01: el layout raiz monta la barra con esa regla", () => {
    // Desde la regresion del 25/11 (Hu035bSalidaEpisodio) la barra se monta en
    // `components/CampusShell.tsx`, que usa el layout raiz.
    const raiz = readFileSync(join(RAIZ, "src/routes/__root.tsx"), "utf-8")
    const shell = readFileSync(join(RAIZ, "src/components/CampusShell.tsx"), "utf-8")
    expect(raiz).toContain("CampusShell")
    expect(shell).toContain("BarraCursos")
    expect(shell).toContain("mostrarBarraCursos")
  })
})

// ── Curso ──────────────────────────────────────────────────────────────

describe("HU-035 · pagina del curso (C02, C03, C07, N01)", () => {
  it("C02: titulo y bienvenida en el recuadro aislado", async () => {
    datos()
    conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    expect(await screen.findByRole("heading", { name: "Programación 1" })).toBeTruthy()
    await waitFor(() => {
      const iframe = document.querySelector('iframe[title="Bienvenida del curso"]')
      expect(iframe?.getAttribute("srcdoc") ?? "").toContain("<h1>Bienvenidos a Prog 1</h1>")
      expect(iframe?.getAttribute("sandbox") ?? "").not.toContain("allow-same-origin")
    })
  })

  it("C03: tarjetas en orden con links y cantidad de TPs", async () => {
    datos()
    conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    const u1 = await screen.findByRole("link", { name: /Unidad 1 · Bienvenida/ })
    const u2 = screen.getByRole("link", { name: /Unidad 2 · Secuenciales/ })
    expect(u1.getAttribute("href")).toBe(`/curso/${COM}/unidad/${U1}`)
    expect(u2.getAttribute("href")).toBe(`/curso/${COM}/unidad/${U2}`)
    // Orden: U1 antes que U2 antes que U3 en el documento.
    const texto = document.body.textContent ?? ""
    expect(texto.indexOf("Unidad 1 · Bienvenida")).toBeLessThan(
      texto.indexOf("Unidad 2 · Secuenciales"),
    )
    expect(texto.indexOf("Unidad 2 · Secuenciales")).toBeLessThan(
      texto.indexOf("Unidad 3 · Condicionales"),
    )
    // 4 publicados en U2 (el borrador no cuenta).
    expect(screen.getByText("4 trabajos prácticos")).toBeTruthy()
  })

  it("N01: la unidad que no abrio no tiene link y dice cuando abre", async () => {
    datos()
    conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    expect(await screen.findByText("Abre el 16/03/2027")).toBeTruthy()
    expect(screen.queryByRole("link", { name: /Unidad 3 · Condicionales/ })).toBeNull()
    expect(screen.getByText("Unidad 3 · Condicionales")).toBeTruthy()
  })

  it("C07: Mis notas y Mi progreso filtrados por el curso", async () => {
    datos()
    conRouter(<CursoView comisionId={COM} getToken={getToken} hoy={HOY} />)
    const notas = await screen.findByRole("link", { name: "Mis notas" })
    const progreso = screen.getByRole("link", { name: "Mi progreso" })
    expect(notas.getAttribute("href")).toBe(`/mis-notas?comisionId=${COM}`)
    expect(progreso.getAttribute("href")).toBe(`/progreso?comisionId=${COM}`)
  })
})

// ── Unidad ─────────────────────────────────────────────────────────────

describe("HU-035 · pagina de la unidad (C04, C05, C06, N01, N03)", () => {
  it("C04: pestañas e introduccion en el recuadro aislado", async () => {
    datos()
    conRouter(
      <UnidadView
        comisionId={COM}
        unidadId={U2}
        pestana="introduccion"
        getToken={getToken}
        hoy={HOY}
      />,
    )
    const intro = await screen.findByRole("tab", { name: "Introducción" })
    const tps = screen.getByRole("tab", { name: /Trabajos prácticos/ })
    expect(intro.getAttribute("aria-selected")).toBe("true")
    expect(tps.getAttribute("aria-selected")).toBe("false")
    await waitFor(() => {
      const iframe = document.querySelector('iframe[title="Introducción de la unidad"]')
      expect(iframe?.getAttribute("srcdoc") ?? "").toContain("<h2>De que se trata</h2>")
    })
  })

  it("C04: unidad sin introduccion lo dice", async () => {
    datos()
    conRouter(
      <UnidadView
        comisionId={COM}
        unidadId={U1}
        pestana="introduccion"
        getToken={getToken}
        hoy={HOY}
      />,
    )
    expect(await screen.findByText("Esta unidad todavía no tiene introducción")).toBeTruthy()
    expect(document.querySelector('iframe[title="Introducción de la unidad"]')).toBeNull()
  })

  it("C05/C06/N03: TPs de la unidad con estado y link al flujo de hoy", async () => {
    datos()
    conRouter(
      <UnidadView comisionId={COM} unidadId={U2} pestana="tps" getToken={getToken} hoy={HOY} />,
    )
    const fila = async (titulo: string) => {
      const link = await screen.findByRole("link", { name: new RegExp(titulo) })
      return link
    }
    const t1 = await fila("TP 2 · Primeros programas")
    expect(t1.getAttribute("href")).toBe(`/materia/${MAT}?tareaId=t1aaaaaa`)
    expect(within(t1).getByText("Calificado · 8")).toBeTruthy()
    expect(within(await fila("TP 2b")).getByText("Esperando corrección")).toBeTruthy()
    expect(within(await fila("TP 2c")).getByText("En curso")).toBeTruthy()
    expect(within(await fila("TP 2d")).getByText("Pendiente")).toBeTruthy()
    // N03: ni el borrador ni el TP de otra unidad.
    expect(screen.queryByText(/Borrador del docente/)).toBeNull()
    expect(screen.queryByText(/TP 3 · Condicionales/)).toBeNull()
  })

  it("N01: unidad que no abrio no muestra introduccion ni TPs", async () => {
    datos()
    conRouter(
      <UnidadView comisionId={COM} unidadId={U3} pestana="tps" getToken={getToken} hoy={HOY} />,
    )
    expect(await screen.findByText("Esta unidad abre el 16/03/2027")).toBeTruthy()
    expect(screen.queryByRole("link", { name: /TP 3/ })).toBeNull()
    expect(document.querySelector("iframe")).toBeNull()
  })
})

// ── Cableado de rutas ──────────────────────────────────────────────────

describe("HU-035 · rutas (C06, C07)", () => {
  const leer = (p: string) => readFileSync(join(RAIZ, p), "utf-8")

  it("existen las rutas del curso y de la unidad", () => {
    expect(leer("src/routes/curso.$comisionId.tsx")).toContain(
      'createFileRoute("/curso/$comisionId")',
    )
    const unidadRuta = leer("src/routes/curso.$comisionId.unidad.$unidadId.tsx")
    expect(unidadRuta).toContain('createFileRoute("/curso/$comisionId/unidad/$unidadId")')
    expect(unidadRuta).toContain("pestana")
  })

  it("la home entra al curso por comision", () => {
    expect(leer("src/routes/index.tsx")).toContain('"/curso/$comisionId"')
  })

  it("materia acepta tareaId; mis-notas y progreso aceptan comisionId", () => {
    expect(leer("src/routes/materia.$id.tsx")).toMatch(/tareaId:\s*z\./)
    expect(leer("src/routes/mis-notas.tsx")).toMatch(/comisionId:\s*z\./)
    expect(leer("src/routes/progreso.tsx")).toMatch(/comisionId:\s*z\./)
  })
})
