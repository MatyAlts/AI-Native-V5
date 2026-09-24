/**
 * BUG-08 (QA 2026-09-23): el pie de auditoria vivia en la raiz del router con
 * `episodeId={null}` hardcodeado, asi que el poll a
 * `/api/v1/audit/episodes/{id}/verify` nunca corria y el pie quedaba muerto
 * ("cadena: sin verificacion previa") aun con un episodio abierto.
 *
 * `activeEpisodeIdFromMatches` es la pieza pura que resuelve el episodio
 * activo a partir de los matches del router (TanStack), leyendo el `id` del
 * match de la ruta hija `/episodio/$id`. Se testea sola, sin montar un
 * RouterProvider — mismo patron que `MateriaContextLine` en
 * `materia.$id.tsx` (ver MateriaPage.test.tsx).
 */
import { describe, expect, test } from "vitest"
import { activeEpisodeIdFromMatches } from "../src/routes/__root"

describe("activeEpisodeIdFromMatches (BUG-08)", () => {
  test("con el alumno en /episodio/$id, devuelve el episodeId real del match", () => {
    const matches = [
      { routeId: "__root__", params: {} },
      { routeId: "/episodio/$id", params: { id: "ep-abc-123" } },
    ]
    expect(activeEpisodeIdFromMatches(matches)).toBe("ep-abc-123")
  })

  test("fuera de /episodio/$id (ej. en la home) no hay episodio activo", () => {
    const matches = [
      { routeId: "__root__", params: {} },
      { routeId: "/", params: {} },
    ]
    expect(activeEpisodeIdFromMatches(matches)).toBeNull()
  })
})
