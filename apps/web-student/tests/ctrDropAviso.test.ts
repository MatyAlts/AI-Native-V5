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
  it('"exhausted" avisa lo que paso, sin ocultarlo y sin inventar la causa', () => {
    const mensaje = mensajeAvisoDescartado("exhausted")
    expect(mensaje).not.toBeNull()
    // Lo que es CIERTO y le sirve al alumno: algo no se registro, y su codigo
    // no se perdio (el borrador local lo cubre, sincronico, mismo tick).
    expect(mensaje).toMatch(/no pudimos registrar/i)
    expect(mensaje).toMatch(/código está a salvo/i)
  })

  it('"exhausted" NO afirma que se vencio la sesion — no se puede saber', () => {
    // La guarda de este PR: "exhausted" tambien lo produce una caida de red o
    // un 5xx persistente, y el CTRClient no guarda que status vio en el ultimo
    // intento. Afirmar la sesion manda a reloguear a quien solo perdio el wifi.
    expect(mensajeAvisoDescartado("exhausted")).not.toMatch(/venció tu sesión/i)
  })

  it('"exhausted" NO promete que volver a entrar recupere el evento perdido', () => {
    // Al agotar reintentos, `drain()` hace `queue.shift()` ANTES de `onDrop`:
    // el evento ya no esta en la cola y ninguna reconexion lo retransmite. Lo
    // que vuelve a registrar el trabajo es la PROXIMA edicion.
    expect(mensajeAvisoDescartado("exhausted")).not.toMatch(/para que se registre/i)
  })

  it('"rejected" (409/422/403 — evento invalido, no sesion) NO muestra aviso', () => {
    // "rejected" es un rechazo de NEGOCIO (episodio cerrado, payload
    // invalido, permiso) — no tiene nada que ver con la sesion, y decirle al
    // alumno "volve a entrar" ahi seria un dato falso.
    expect(mensajeAvisoDescartado("rejected")).toBeNull()
  })
})
