/**
 * Aceptación HU-031 (orquestador, antes de construir; el constructor no la
 * modifica). Criterios acordados el 24/11/2026 (Juani delegó criterios y
 * aceptación).
 *
 * C05  En un ejercicio PSeInt el docente tiene "Insertar diagrama", que agrega
 *      un bloque ```diagrama a la consigna, y una vista previa de la consigna
 *      donde ve el diagrama como lo verá el alumno (y el aviso si tiene error).
 * N02  En Python no aparece "Insertar diagrama".
 *
 * Contrato: `EjercicioFormModal` se exporta desde `EjerciciosView`.
 *
 * Corrección de la aceptación (24/11): el `Modal` de `@platform/ui` se dibuja
 * en un portal sobre `document.body`, fuera del `container` del render. Se
 * busca en `document`; con `container` una prueba caía por TypeError y la del
 * aviso de error pasaba sin medir nada.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import * as vista from "../src/views/EjerciciosView"

function base(language: string, enunciado = "Escribi el algoritmo del diagrama.") {
  return {
    titulo: "Doble",
    enunciado_md: enunciado,
    inicial_codigo: null,
    unidad_tematica: "secuenciales",
    dificultad: null,
    prerequisitos: { sintacticos: [], conceptuales: [] },
    test_cases: [],
    rubrica: null,
    tutor_rules: null,
    banco_preguntas: null,
    misconceptions: [],
    respuesta_pista: [],
    heuristica_cierre: null,
    anti_patrones: [],
    created_via_ai: false,
    language,
  }
}

function Modal(props: Record<string, unknown>) {
  const M = (vista as Record<string, unknown>).EjercicioFormModal as ((p: Record<string, unknown>) => JSX.Element) | undefined
  expect(M, "falta export EjercicioFormModal en EjerciciosView").toBeTypeOf("function")
  return M!(props)
}

const comunes = { title: "Nuevo ejercicio", unidades: ["secuenciales"], onClose: vi.fn(), onSubmit: vi.fn(async () => {}) }

describe("C05 diagrama en la consigna, del lado del docente", () => {
  it("Insertar diagrama agrega un bloque ```diagrama y la vista previa lo dibuja", async () => {
    render(<Modal {...comunes} initial={base("pseint")} />)
    const boton = screen.getByRole("button", { name: /Insertar diagrama/i })
    await act(async () => {
      fireEvent.click(boton)
    })
    const enunciado = document.querySelector("#ejercicio-enunciado") as HTMLTextAreaElement
    expect(enunciado.value).toContain("```diagrama")
    expect(enunciado.value).toContain("Escribi el algoritmo del diagrama.")
    await waitFor(() => expect(document.querySelectorAll('svg[role="img"]').length).toBeGreaterThanOrEqual(1))
  })

  it("la vista previa avisa si el bloque tiene un error", async () => {
    const md = 'Consigna\n\n```diagrama\nAlgoritmo roto\n\tEscribir "hola\nFinAlgoritmo\n```\n'
    render(<Modal {...comunes} initial={base("pseint", md)} />)
    // Guarda contra la prueba vacía: el formulario tiene que estar en pantalla.
    expect(document.querySelector("#ejercicio-enunciado")).not.toBeNull()
    await waitFor(() => expect(screen.getByText(/l[ií]nea 2/i)).toBeTruthy())
    expect(document.querySelector('svg[role="img"]')).toBeNull()
  })
})

describe("N02 en Python no hay diagrama", () => {
  it("no aparece Insertar diagrama", () => {
    render(<Modal {...comunes} initial={base("python")} />)
    expect(screen.queryByRole("button", { name: /Insertar diagrama/i })).toBeNull()
  })
})
