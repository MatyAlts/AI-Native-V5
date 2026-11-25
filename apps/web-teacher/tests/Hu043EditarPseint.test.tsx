/**
 * Aceptacion HU-043 (orquestador, antes de construir; el constructor no la
 * modifica). Hallazgo de la prueba en produccion del 25/11: en el Banco de
 * ejercicios, "Editar" (lapiz -> "Editar de todos modos") de un ejercicio
 * PSeInt ("Par o impar") mostraba "Lenguaje: Python". Si el docente guardaba,
 * el ejercicio pasaba a Python y se rompia para los alumnos.
 *
 * Causa al escribir esta prueba: `toCreate(ej)` en `EjerciciosView.tsx` arma el
 * borrador del formulario sin copiar `language`, y el selector cae en
 * `DEFAULT_LANGUAGE` (python).
 *
 * C01  Editar un ejercicio `pseint` muestra PSeInt seleccionado en el selector
 *      "Lenguaje" y, al guardar sin tocar nada, el PATCH a
 *      `/api/v1/ejercicios/<id>` lleva `language: "pseint"`.
 * N01  Un ejercicio `python` sigue mostrando y guardando `python` (el arreglo
 *      no fuerza pseint).
 *
 * Contrato: se recorre la vista entera (`EjerciciosView`) como el docente: el
 * boton con title "Editar" de la fila, "Editar de todos modos", el selector
 * `#ejercicio-language` y el boton "Guardar". El request se lee del `fetch`
 * mockeado (metodo PATCH, cuerpo JSON).
 *
 * Por que se prueban los dos lenguajes en la misma vista: una implementacion
 * que fije `language: "pseint"` (o que tome el lenguaje del primer ejercicio de
 * la lista) pasa C01 y cae en N01; una que no copie el lenguaje pasa N01 (por
 * el default) y cae en C01.
 */
import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { EjerciciosView } from "../src/views/EjerciciosView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const COM = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const MAT = "99999999-9999-9999-9999-999999999999"
const ID_PSEINT = "11111111-1111-1111-1111-111111111111"
const ID_PYTHON = "22222222-2222-2222-2222-222222222222"

function ejercicio(id: string, titulo: string, language: "pseint" | "python") {
  return {
    id,
    tenant_id: "t",
    titulo,
    enunciado_md: `Consigna de ${titulo}.`,
    inicial_codigo: null,
    materia_id: MAT,
    unidad_tematica: "condicionales",
    dificultad: null,
    language,
    prerequisitos: { sintacticos: [], conceptuales: [] },
    test_cases: [],
    rubrica: null,
    tutor_rules: null,
    banco_preguntas: null,
    misconceptions: [],
    respuesta_pista: [],
    heuristica_cierre: null,
    anti_patrones: [],
    created_by: "u",
    created_via_ai: false,
    created_at: "2026-11-20T10:00:00Z",
    deleted_at: null,
  }
}

function montar() {
  setupFetchMock({
    "/api/v1/comisiones/mis": () => ({
      data: [{ id: COM, materia_id: MAT, materia_nombre: "Programacion 1" }],
      meta: { cursor_next: null },
    }),
    "/api/v1/ejercicios": () => ({
      // El PSeInt va primero en la lista a proposito (ver docstring, N01).
      data: [
        ejercicio(ID_PSEINT, "Par o impar", "pseint"),
        ejercicio(ID_PYTHON, "Suma de dos numeros", "python"),
      ],
      meta: { cursor_next: null },
    }),
  })
  renderWithRouter(<EjerciciosView comisionId={COM} getToken={async () => "tok"} />)
}

async function abrirEditor(titulo: string) {
  const celda = await screen.findByRole("button", { name: titulo }, { timeout: 4000 })
  const fila = celda.closest("tr") as HTMLTableRowElement
  expect(fila, `no hay fila para ${titulo}`).not.toBeNull()
  const lapiz = fila.querySelector('button[title="Editar"]') as HTMLButtonElement
  expect(lapiz, `la fila de ${titulo} no tiene boton Editar`).not.toBeNull()
  fireEvent.click(lapiz)
  fireEvent.click(await screen.findByRole("button", { name: "Editar de todos modos" }))
  await waitFor(() => expect(document.querySelector("#ejercicio-language")).not.toBeNull())
  // El formulario abierto tiene que ser el de ESTE ejercicio.
  const tituloInput = document.querySelector("#ejercicio-titulo") as HTMLInputElement
  expect(tituloInput.value).toBe(titulo)
  return document.querySelector("#ejercicio-language") as HTMLSelectElement
}

function patches(): { url: string; body: Record<string, unknown> }[] {
  const llamadas = vi.mocked(fetch).mock.calls as [string | URL | Request, RequestInit?][]
  return llamadas
    .filter(([, init]) => (init?.method ?? "GET").toUpperCase() === "PATCH")
    .map(([input, init]) => ({
      url: typeof input === "string" ? input : input.toString(),
      body: JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>,
    }))
}

async function guardarYLeerPatch(id: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }))
  })
  await waitFor(() => expect(patches().length).toBe(1))
  const [p] = patches()
  expect(p.url).toBe(`/api/v1/ejercicios/${id}`)
  return p.body
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("HU-043 · editar un ejercicio conserva su lenguaje", () => {
  it("C01: un ejercicio PSeInt se abre con PSeInt y se guarda como pseint", async () => {
    montar()
    const selector = await abrirEditor("Par o impar")
    expect(selector.value).toBe("pseint")
    expect(selector.selectedOptions[0]?.textContent).toBe("PSeInt")

    const body = await guardarYLeerPatch(ID_PSEINT)
    expect(body.language).toBe("pseint")
  })

  it("N01: un ejercicio Python sigue abriendose y guardandose como python", async () => {
    montar()
    const selector = await abrirEditor("Suma de dos numeros")
    expect(selector.value).toBe("python")
    expect(selector.selectedOptions[0]?.textContent).toBe("Python")

    const body = await guardarYLeerPatch(ID_PYTHON)
    expect(body.language).toBe("python")
  })
})
