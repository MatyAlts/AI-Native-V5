/**
 * Mensaje visible cuando el CTRClient descarta un evento (dead-letter).
 *
 * El modulo que prueba este archivo (`src/lib/ctrDropAviso.ts`) es deliberado
 * en lo que NO hace: `DropReason` ("rejected" | "exhausted", ver
 * `@platform/ctr-client`) no alcanza para distinguir "se vencio la sesion" de
 * "el evento era invalido". Ver el docstring de `ctrDropAviso.ts` para el
 * detalle de por que se elige mostrar el aviso solo ante "exhausted".
 */
import { describe, expect, it } from "vitest"
import { mensajeAvisoDescartado } from "../src/lib/ctrDropAviso"

describe("mensajeAvisoDescartado", () => {
  it('"exhausted" devuelve el aviso de sesion vencida — no asusta, no miente', () => {
    const mensaje = mensajeAvisoDescartado("exhausted")
    expect(mensaje).not.toBeNull()
    // No le decimos que perdio el codigo (el borrador local lo cubre) ni le
    // ocultamos que algo no se registro.
    expect(mensaje).toMatch(/sesión/i)
    expect(mensaje).toMatch(/código está a salvo/i)
    expect(mensaje).toMatch(/volvé a entrar/i)
  })

  it('"rejected" (409/422/403 — evento invalido, no sesion) NO muestra aviso', () => {
    // "rejected" es un rechazo de NEGOCIO (episodio cerrado, payload
    // invalido, permiso) — no tiene nada que ver con la sesion, y decirle al
    // alumno "volve a entrar" ahi seria un dato falso.
    expect(mensajeAvisoDescartado("rejected")).toBeNull()
  })
})
