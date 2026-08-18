/**
 * La card de sugerencia. Lo que fijan estos tests es que MUESTRE y no decida.
 */
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, test, vi } from "vitest"
import { ResumenCorreccionIA } from "../src/components/ResumenCorreccionIA"
import type { CorreccionIA } from "../src/lib/api"

function correccion(orden: number, nota: number | null, over: Partial<CorreccionIA> = {}) {
  return {
    id: `c${orden}`,
    entrega_id: "e1",
    tp_ejercicio_id: `ej-${orden}`,
    orden,
    estado: nota === null ? "error" : "done",
    rubrica_id: "r1",
    nota_100: nota,
    desglose: [],
    tests_snapshot: {},
    artefacto_sha256: "s",
    error_code: null,
    error_detail: null,
    es_infraestructura: false,
    external_correccion_id: null,
    tiene_pdf: false,
    created_at: "2026-08-18T10:00:00Z",
    finished_at: "2026-08-18T10:02:00Z",
    ...over,
  } as CorreccionIA
}

const DOS = [
  { ejercicioId: "ej-1", orden: 1, titulo: "Ejercicio 1", peso: 0.5 },
  { ejercicioId: "ej-2", orden: 2, titulo: "Ejercicio 2", peso: 0.5 },
]

describe("ResumenCorreccionIA", () => {
  test("sin correcciones no renderiza nada", () => {
    const { container } = render(
      <ResumenCorreccionIA ejercicios={DOS} correcciones={[]} onUsarComoBase={() => {}} />,
    )
    expect(container.firstChild).toBeNull()
  })

  test("muestra el calculo, no solo el resultado", () => {
    render(
      <ResumenCorreccionIA
        ejercicios={DOS}
        correcciones={[correccion(1, 80), correccion(2, 60)]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.getByTestId("resumen-calculo")).toBeInTheDocument()
    expect(screen.getByTestId("resumen-propuesta")).toHaveTextContent("7")
  })

  test("si falta una correccion NO promedia y nombra la que falta", () => {
    render(
      <ResumenCorreccionIA
        ejercicios={DOS}
        correcciones={[correccion(1, 90)]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.getByTestId("resumen-sin-promedio")).toBeInTheDocument()
    expect(screen.getByText(/Ejercicio 2/)).toBeInTheDocument()
    expect(screen.queryByTestId("resumen-usar-como-base")).not.toBeInTheDocument()
  })

  test("'Usar como base' entrega la nota /10 y no guarda nada", () => {
    const onUsar = vi.fn()
    render(
      <ResumenCorreccionIA
        ejercicios={DOS}
        correcciones={[correccion(1, 80), correccion(2, 60)]}
        onUsarComoBase={onUsar}
      />,
    )
    fireEvent.click(screen.getByTestId("resumen-usar-como-base"))
    expect(onUsar).toHaveBeenCalledWith(7)
    // El texto tiene que decir que no guarda: es la propiedad del epic.
    expect(screen.getByText(/No guarda nada/i)).toBeInTheDocument()
  })

  test("avisa cuando los criterios no suman el total", () => {
    // El caso real del 2026-08-17.
    render(
      <ResumenCorreccionIA
        ejercicios={[{ ejercicioId: "ej-1", orden: 1, titulo: "E1", peso: 1 }]}
        correcciones={[
          correccion(1, 61, {
            desglose: [
              { nombre: "C1", puntaje: 48 },
              { nombre: "C2", puntaje: 39 },
            ],
          }),
        ]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.getByTestId("resumen-no-cierra-1")).toBeInTheDocument()
  })

  test("no avisa cuando cierran", () => {
    render(
      <ResumenCorreccionIA
        ejercicios={[{ ejercicioId: "ej-1", orden: 1, titulo: "E1", peso: 1 }]}
        correcciones={[
          correccion(1, 87, {
            desglose: [
              { nombre: "C1", puntaje: 50 },
              { nombre: "C2", puntaje: 37 },
            ],
          }),
        ]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.queryByTestId("resumen-no-cierra-1")).not.toBeInTheDocument()
  })

  test("los criterios se muestran tal cual, sin cruzarlos con la rubrica local", () => {
    render(
      <ResumenCorreccionIA
        ejercicios={[{ ejercicioId: "ej-1", orden: 1, titulo: "E1", peso: 1 }]}
        correcciones={[
          correccion(1, 87, { desglose: [{ nombre: "Excepcion propia", puntaje: 2 }] }),
        ]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.getByTestId("resumen-desgloses")).toBeInTheDocument()
    expect(screen.getByText("Excepcion propia")).toBeInTheDocument()
  })

  test("lleva los modos de fallo medidos del motor", () => {
    render(
      <ResumenCorreccionIA
        ejercicios={[{ ejercicioId: "ej-1", orden: 1, titulo: "E1", peso: 1 }]}
        correcciones={[correccion(1, 87)]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.getByText(/Cuenta presencia, no vinculo/i)).toBeInTheDocument()
    expect(screen.getByText(/Elogia lo hardcodeado/i)).toBeInTheDocument()
  })
})

describe("la nota la decide el docente", () => {
  test("'Usar como base' propone, pero el docente puede guardar otra cosa", () => {
    // El escenario completo, sin la vista: la card ENTREGA un numero, y quien
    // lo recibe es libre de ignorarlo. Es la propiedad del epic — la
    // plataforma nunca escribe la nota.
    let campoNota = ""
    render(
      <ResumenCorreccionIA
        ejercicios={DOS}
        correcciones={[correccion(1, 90), correccion(2, 70)]}
        onUsarComoBase={(n) => {
          campoNota = String(n)
        }}
      />,
    )

    fireEvent.click(screen.getByTestId("resumen-usar-como-base"))
    expect(campoNota).toBe("8") // (90 + 70) / 2 = 80/100 -> 8/10

    // El docente lo corrige a mano y eso es lo que vale.
    campoNota = "6.5"
    expect(campoNota).not.toBe("8")

    // Y la card sigue mostrando SU sugerencia, sin adoptar la del docente:
    // son dos numeros distintos y la pantalla no los confunde.
    expect(screen.getByTestId("resumen-propuesta")).toHaveTextContent("8")
  })

  test("la card no expone ninguna forma de guardar", () => {
    const { container } = render(
      <ResumenCorreccionIA
        ejercicios={DOS}
        correcciones={[correccion(1, 90), correccion(2, 70)]}
        onUsarComoBase={() => {}}
      />,
    )
    const botones = Array.from(container.querySelectorAll("button")).map((b) => b.textContent ?? "")
    expect(botones.some((t) => /guardar|calificar|aplicar/i.test(t))).toBe(false)
  })
})

describe("el guardrail dice lo que NO cubre", () => {
  test("un desglose ilegible se marca como indeterminado, no como que cierra", () => {
    render(
      <ResumenCorreccionIA
        ejercicios={[{ ejercicioId: "ej-1", orden: 1, titulo: "E1", peso: 1 }]}
        correcciones={[correccion(1, 87, { desglose: [{ comentario: "bien" }] })]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.getByTestId("resumen-indeterminado-1")).toBeInTheDocument()
  })

  test("la pantalla advierte que un desglose que cierra no prueba nada", () => {
    // Sin esto el docente lee "no hay aviso" como "el numero cierra", y en el
    // caso medido el numero cerraba y estaba mal igual.
    render(
      <ResumenCorreccionIA
        ejercicios={[{ ejercicioId: "ej-1", orden: 1, titulo: "E1", peso: 1 }]}
        correcciones={[correccion(1, 87)]}
        onUsarComoBase={() => {}}
      />,
    )
    expect(screen.getByText(/no prueba que la nota sea correcta/i)).toBeInTheDocument()
  })
})
