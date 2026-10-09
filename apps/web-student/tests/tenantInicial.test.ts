/**
 * QA 08/10 #16: el tenant por defecto ya no es el primero que devuelve el
 * backend (orden por UUID = arbitrario). Orden de decision: ultima eleccion
 * persistida (si sigue siendo valida) -> orden alfabetico por nombre.
 */
import { describe, expect, it } from "vitest"
import { elegirTenantInicial } from "../src/lib/tenantInicial"

const UM = { tenant_id: "t-um", nombre: "Universidad de Mendoza" }
const UTN = { tenant_id: "t-utn", nombre: "Universidad Tecnologica Nacional" }
const UBA = { tenant_id: "t-uba", nombre: "Universidad de Buenos Aires" }

describe("elegirTenantInicial", () => {
  it("respeta la ultima eleccion persistida si sigue en la lista", () => {
    expect(elegirTenantInicial([UM, UTN], "t-utn")).toBe("t-utn")
  })

  it("sin persistido, elige por nombre alfabetico y no por posicion", () => {
    expect(elegirTenantInicial([UTN, UM, UBA], "")).toBe("t-uba")
    expect(elegirTenantInicial([UM, UTN], null)).toBe("t-um")
  })

  it("un persistido que ya no esta en la lista se descarta", () => {
    expect(elegirTenantInicial([UTN, UM], "t-viejo")).toBe("t-um")
  })

  it("lista vacia -> cadena vacia (nada que elegir)", () => {
    expect(elegirTenantInicial([], "t-utn")).toBe("")
  })

  it("no muta la lista recibida", () => {
    const lista = [UTN, UM]
    elegirTenantInicial(lista, "")
    expect(lista[0]).toBe(UTN)
  })
})
