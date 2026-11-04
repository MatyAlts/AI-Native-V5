// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Mensajes de error del estudio (`src/views/estudio/mensajesError.ts`) contra las
 * formas REALES del backend (routes/estudio.py y estudio_trabajo.py):
 *   - 409 con `detail` string: el codigo (`episodio_es_ancla`, `version_congelada`...);
 *   - 422 con `detail: {codigo, errores?: string[]}`;
 *   - 400 del esquema con `detail: {mensaje, errores: string[]}`.
 * Ningun caso puede terminar en "[object Object]" ni en el JSON crudo del detail.
 */
import { describe, expect, it } from "vitest"
import { mensajeDeErrorEstudio } from "../src/views/estudio/mensajesError"

function err(status: number, detail: unknown) {
  return Object.assign(new Error(`${status}: ${JSON.stringify(detail)}`), { status, detail })
}

describe("mensajeDeErrorEstudio", () => {
  const conflictos: [string, RegExp][] = [
    ["enunciado_revisado", /ya fue revisado/],
    ["episodio_es_ancla", /es ancla de entrenamiento/],
    ["episodio_en_muestra", /ya está en la muestra/],
    ["muestra_con_etiquetas", /ya hay etiquetas/i],
    ["version_congelada", /versión está congelada/],
    ["ancla_con_respuestas", /respuestas de entrenamiento/],
  ]
  for (const [codigo, esperado] of conflictos) {
    it(`409 ${codigo}`, () => {
      expect(mensajeDeErrorEstudio(err(409, codigo))).toMatch(esperado)
    })
  }

  it("422 sha256_distinto", () => {
    expect(mensajeDeErrorEstudio(err(422, { codigo: "sha256_distinto" }))).toMatch(
      /sha256 del archivo no coincide/,
    )
  })

  it("422 con errores: lista cada error, sin JSON crudo", () => {
    const m = mensajeDeErrorEstudio(
      err(422, {
        codigo: "csv_invalido",
        errores: ["fila 3: episode_id no es UUID", "fila 7: episode_id repetido"],
      }),
    )
    expect(m).toContain("fila 3: episode_id no es UUID")
    expect(m).toContain("fila 7: episode_id repetido")
    expect(m).not.toContain("{")
  })

  it("422 episodios_invalidos y pedido_invalido tambien listan sus errores", () => {
    expect(
      mensajeDeErrorEstudio(err(422, { codigo: "episodios_invalidos", errores: ["fila 2: abierto"] })),
    ).toContain("fila 2: abierto")
    expect(
      mensajeDeErrorEstudio(err(400, { codigo: "pedido_invalido", errores: ["clave desconocida 'x'"] })),
    ).toContain("clave desconocida 'x'")
    expect(
      mensajeDeErrorEstudio(err(422, { codigo: "episodios_invalidos", errores: ["fila 2: abierto"] })),
    ).not.toContain("{")
  })

  it("422 episodio_no_terminado e inexistente (anclas)", () => {
    expect(mensajeDeErrorEstudio(err(422, { codigo: "episodio_no_terminado", motivo: "abierto" }))).toMatch(
      /no está terminado/,
    )
    expect(mensajeDeErrorEstudio(err(422, { codigo: "episodio_inexistente" }))).toMatch(/no existe/)
  })

  it("400 del esquema: mensaje y cada error del meta-esquema", () => {
    const m = mensajeDeErrorEstudio(
      err(400, {
        mensaje: "Esquema inválido",
        errores: ["esquema: falta 'regimenes'", "dimensiones[0]: clave inválida"],
      }),
    )
    expect(m).toContain("Esquema inválido")
    expect(m).toContain("esquema: falta 'regimenes'")
    expect(m).toContain("dimensiones[0]: clave inválida")
    expect(m).not.toContain("{")
  })

  it("los codigos que ya conocia siguen igual", () => {
    expect(mensajeDeErrorEstudio(err(409, "enunciados_pendientes"))).toMatch(/consignas/)
    expect(mensajeDeErrorEstudio(err(409, "codebook_borrador"))).toMatch(/borrador/)
  })

  // verify-1, F4 y F1: codigos nuevos del backend.
  it("409 sin_muestra: la muestra todavia no se cargo", () => {
    const m = mensajeDeErrorEstudio(err(409, "sin_muestra"))
    expect(m).toMatch(/muestra del estudio todavía no se cargó/)
    expect(m).not.toMatch(/Faltan 0/)
  })

  it("422 anclas_invalidas al congelar: explica y lista cada ancla con su motivo", () => {
    const m = mensajeDeErrorEstudio(
      err(422, {
        codigo: "anclas_invalidas",
        anclas: [{ item_id: "x", uso: "practica", orden: 1, motivos: ["regimen: otro"] }],
        errores: ["ancla practica 1: regimen: otro"],
      }),
    )
    expect(m).toMatch(/anclas que no valen contra el esquema/)
    expect(m).toContain("ancla practica 1: regimen: otro")
    expect(m).not.toContain("{")
  })
})
