/**
 * BUG-18: el form de TP mostraba "Error: 422: [object Object]" cuando el
 * backend rechazaba el alta/edicion (peso fuera de 0-1, fecha_fin < inicio).
 * FastAPI devuelve `{ detail: [{ loc, msg, type }, ...] }` para 422 de
 * validacion, y `{ detail: "..." }` para errores de negocio (409, 400, etc.).
 *
 * `formatApiError` es pura: no debe importar nada de React ni de api.ts, para
 * poder testearla sin montar el form completo.
 */
import { describe, expect, test } from "vitest"
import { formatApiError } from "../src/utils/errorApi"

describe("formatApiError", () => {
  test("detail array de FastAPI (422) produce mensaje por campo", () => {
    const err = {
      detail: [
        { loc: ["body", "peso"], msg: "el valor debe ser menor o igual a 1", type: "value_error" },
        {
          loc: ["body", "fecha_fin"],
          msg: "debe ser posterior a fecha_inicio",
          type: "value_error",
        },
      ],
    }

    const mensaje = formatApiError(err)

    expect(mensaje).toContain("peso: el valor debe ser menor o igual a 1")
    expect(mensaje).toContain("fecha_fin: debe ser posterior a fecha_inicio")
    expect(mensaje).not.toContain("[object Object]")
  })

  test("detail string se usa tal cual", () => {
    const err = { detail: "El codigo ya esta en uso para esta comision" }

    expect(formatApiError(err)).toBe("El codigo ya esta en uso para esta comision")
  })

  test("error generico sin detail cae a String(err)", () => {
    const err = new Error("network request failed")

    expect(formatApiError(err)).toBe("Error: network request failed")
  })

  test("nunca devuelve '[object Object]'", () => {
    // Un objeto sin detail y sin toString util: el fallback debe evitar
    // el "[object Object]" crudo que reporta el bug.
    const err = { foo: "bar" }

    expect(formatApiError(err)).not.toBe("[object Object]")
  })
})
