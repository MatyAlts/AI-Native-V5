/**
 * El respaldo local se lee al reabrir — hoy no se lee.
 *
 * El bug: el alumno escribe, cada segundo se guarda una copia en
 * `localStorage` (`saveArtefactoDraft`) Y se intenta emitir el snapshot al
 * servidor (`last_code_snapshot`). Al reabrir un episodio pausado, el editor
 * se siembra SOLO con el snapshot del servidor. Si ese POST fallo (red,
 * server caido, lo que sea — es fire-and-forget), el alumno ve codigo viejo
 * teniendo el suyo, mas fresco, en su propia maquina.
 *
 * El arreglo agrega un cuarto candidato a `resolverCascadaDeCodigo`
 * (`borradorLocal`) con la MAYOR precedencia, y en `EpisodePage` lo resuelve
 * con una regla deliberadamente angosta: el borrador local solo gana si fue
 * escrito en ESTE MISMO episodio (`draft.episode_id === episodeId`).
 *
 * Por que gana sobre el snapshot
 * -------------------------------
 * Dentro del mismo episodio, el borrador es por construccion al menos tan
 * fresco como el snapshot: los dos se escriben en el mismo tick del debounce
 * de `onEditDebounced`, pero el local es sincronico (no puede fallar) y el
 * del servidor es fire-and-forget (si puede). El unico caso en que difieren
 * es exactamente el bug que esto cierra.
 *
 * Por que NO se usa un borrador de OTRO episodio
 * -----------------------------------------------
 * `EpisodeStateResponse` no expone timestamp de `last_code_snapshot` (solo
 * `opened_at`/`closed_at`), asi que no hay forma de comparar frescura entre
 * dos episodios distintos — un borrador viejo dejado por un episodio
 * abandonado resucitaria codigo muerto. Y sembrar codigo de OTRO episodio es
 * exactamente la puerta por la que volveria ED-4 (arrastre de codigo de un
 * ejercicio anterior), eliminado el 2026-09-28 — ver
 * `openspec/changes/eliminar-ed4-siembra-codigo-previo/`. Por eso el chequeo
 * de `episode_id` no es un detalle de implementacion: es la frontera entre
 * este fix y ese bug.
 *
 * Esta frontera solo es observable en la rama multi-ejercicio (ADR-047): el
 * scope del borrador ahi es `entregaId`, compartido entre episodios distintos
 * del MISMO ejercicio (uno abandonado, uno reabierto). En la TP monolitica el
 * scope es el propio `episodeId`, asi que un borrador bajo esa clave solo
 * pudo haberse escrito en ese mismo episodio — no hay "otro episodio" que
 * probar ahi, y por eso el caso negativo vive en la seccion multi-ejercicio.
 */
import { render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  type ArtefactoDraft,
  MONOLITHIC_ORDEN,
  readArtefactoDraft,
  saveArtefactoDraft,
} from "../src/lib/artefactos"
import type { CandidatosCodigo } from "../src/lib/cascadaCodigo"
import { resolverCascadaDeCodigo } from "../src/lib/cascadaCodigo"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

// ---------------------------------------------------------------------------
// 1. La cascada pura: `borradorLocal` es el candidato de MAYOR precedencia.
// ---------------------------------------------------------------------------

const PLACEHOLDER = "# Escribi tu solucion aca\n"
const SNAPSHOT = "print('lo que el servidor cree que escribi')\n"
const SCAFFOLD_TP = "# scaffold de la TP\ndef resolver():\n    pass\n"
const SCAFFOLD_EJ = "# scaffold del ejercicio\ndef resolver():\n    pass\n"
const BORRADOR = "print('lo que quedo en ESTA maquina, mas fresco que el snapshot')\n"

const TODOS: CandidatosCodigo = {
  snapshot: SNAPSHOT,
  scaffoldTp: SCAFFOLD_TP,
  scaffoldEjercicio: SCAFFOLD_EJ,
  placeholder: PLACEHOLDER,
}

describe("resolverCascadaDeCodigo — borradorLocal, el candidato nuevo", () => {
  it("gana incluso sobre el snapshot del servidor", () => {
    // El caso que cierra el bug: snapshot viejo (lo que el servidor alcanzo a
    // guardar) compitiendo contra el borrador local (lo que el alumno
    // realmente escribio). Gana el local.
    expect(resolverCascadaDeCodigo({ ...TODOS, borradorLocal: BORRADOR })).toEqual({
      codigo: BORRADOR,
      origen: "borrador-local",
    })
  })

  it('vacio ("") cae al snapshot — no es "el alumno no escribio nada"', () => {
    expect(resolverCascadaDeCodigo({ ...TODOS, borradorLocal: "" })).toEqual({
      codigo: SNAPSHOT,
      origen: "snapshot",
    })
  })

  it("null cae al snapshot, y el resto de la cascada (2, 3, 4) sigue intacto", () => {
    expect(resolverCascadaDeCodigo({ ...TODOS, borradorLocal: null })).toEqual({
      codigo: SNAPSHOT,
      origen: "snapshot",
    })
    expect(resolverCascadaDeCodigo({ ...TODOS, borradorLocal: null, snapshot: null })).toEqual({
      codigo: SCAFFOLD_TP,
      origen: "scaffold-tp",
    })
    expect(
      resolverCascadaDeCodigo({
        ...TODOS,
        borradorLocal: null,
        snapshot: null,
        scaffoldTp: null,
      }),
    ).toEqual({ codigo: SCAFFOLD_EJ, origen: "scaffold-ejercicio" })
  })

  it("ausente (candidato no pasado) se comporta igual que null", () => {
    // `EpisodePage` siempre lo pasa, pero la funcion sigue siendo pura sobre
    // candidatos parciales — mismo contrato que el resto de los campos.
    expect(resolverCascadaDeCodigo(TODOS)).toEqual({ codigo: SNAPSHOT, origen: "snapshot" })
  })
})

// ---------------------------------------------------------------------------
// 2. `readArtefactoDraft` — lectura puntual de UN borrador, por clave exacta.
// ---------------------------------------------------------------------------

function rawKey(scopeId: string, orden: number): string {
  return `entrega_artefacto_${scopeId}_${orden}`
}

const DRAFT_BASE: ArtefactoDraft = {
  orden: 3,
  ejercicio_id: "ej-x",
  episode_id: "ep-x",
  codigo: "x = 1\n",
  language: "python",
}

describe("readArtefactoDraft — lectura puntual de un borrador", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("clave ausente -> null", () => {
    expect(readArtefactoDraft("scope-cualquiera", 1)).toBeNull()
  })

  it("lo que guarda saveArtefactoDraft se lee de vuelta tal cual", () => {
    saveArtefactoDraft("scope-x", DRAFT_BASE)
    const leido = readArtefactoDraft("scope-x", DRAFT_BASE.orden)
    expect(leido?.codigo).toBe(DRAFT_BASE.codigo)
    expect(leido?.episode_id).toBe(DRAFT_BASE.episode_id)
  })

  it("entrada corrupta (JSON invalido) -> null, no tira", () => {
    window.localStorage.setItem(rawKey("scope-x", 3), "{esto no es json valido")
    expect(readArtefactoDraft("scope-x", 3)).toBeNull()
  })

  // Las dos siguientes importan por lo que NO hacen: `readArtefactoDraft` no
  // filtra por `episode_id` (esa es responsabilidad del llamador, el `===`
  // de `EpisodePage.tsx` — el candado anti-ED-4, ver docstring arriba). Si
  // alguien cambiara esta funcion para "normalizar" un `episode_id` faltante
  // a, por ejemplo, el string vacio o el propio episodeId esperado, el
  // candado de `EpisodePage` dejaria de poder distinguir "borrador de otro
  // episodio" de "borrador de este episodio" — y nadie se enteraria sin este
  // test, porque la suite de integracion de mas abajo siempre pasa un
  // `episode_id` explicito.
  it("episode_id AUSENTE en el JSON guardado -> se lee igual, episode_id queda undefined (no lo inventa)", () => {
    window.localStorage.setItem(
      rawKey("scope-x", 3),
      JSON.stringify({ orden: 3, ejercicio_id: "ej-x", codigo: "x = 1\n", language: "python" }),
    )
    const leido = readArtefactoDraft("scope-x", 3)
    expect(leido?.codigo).toBe("x = 1\n")
    expect(leido?.episode_id).toBeUndefined()
  })

  it("episode_id: null en el JSON guardado -> se lee igual, episode_id queda null (no lo descarta)", () => {
    window.localStorage.setItem(
      rawKey("scope-x", 3),
      JSON.stringify({ ...DRAFT_BASE, episode_id: null }),
    )
    const leido = readArtefactoDraft("scope-x", 3)
    expect(leido?.codigo).toBe(DRAFT_BASE.codigo)
    expect(leido?.episode_id).toBeNull()
  })

  it("codigo vacio o solo espacios -> null — no es un borrador util", () => {
    window.localStorage.setItem(
      rawKey("scope-x", 3),
      JSON.stringify({ ...DRAFT_BASE, codigo: "   " }),
    )
    expect(readArtefactoDraft("scope-x", 3)).toBeNull()
  })

  it("no mezcla scopes ni ordenes distintos — es la clave EXACTA, no un prefijo", () => {
    saveArtefactoDraft("scope-x", DRAFT_BASE)
    expect(readArtefactoDraft("scope-x", DRAFT_BASE.orden + 1)).toBeNull()
    expect(readArtefactoDraft("scope-y", DRAFT_BASE.orden)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 3. Integracion: `EpisodeView` resuelve el borrador local SOLO si es de
//    este mismo episodio. Las dos ramas de escritura (monolitica /
//    multi-ejercicio) usan scopes distintos, asi que cada una se prueba con
//    su propia clave — y de paso queda probado que la lectura usa la MISMA
//    clave que la escritura en cada rama (si no coincidiera, el candidato
//    nunca se encontraria y estos tests fallarian igual que el caso "ausente").
// ---------------------------------------------------------------------------

const TAREA_BASE = {
  codigo: "TP1",
  titulo: "Primera TP",
  enunciado: "Enunciado",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.00",
  estado: "published",
  version: 1,
  inicial_codigo: null,
  language: "python",
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
})

afterEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
})

describe("EpisodeView — TP monolitica (scope = episodeId)", () => {
  const EPISODIO_ID = "ep-monolitico-borrador"
  const TAREA_ID = "tp-monolitica-borrador"
  const CODIGO_VIEJO_SERVIDOR = "print('version vieja, la que SI llego al servidor')\n"
  const CODIGO_LOCAL_FRESCO = "print('version fresca, la que quedo solo en esta maquina')\n"

  function montar() {
    setupFetchMock({
      "/resume": () => ({ ok: true }),
      [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => ({ id: TAREA_ID, ...TAREA_BASE }),
      [`/api/v1/episodes/${EPISODIO_ID}`]: () => ({
        episode_id: EPISODIO_ID,
        tarea_practica_id: TAREA_ID,
        comision_id: "com-1",
        estado: "open",
        opened_at: "2026-08-27T10:00:00Z",
        closed_at: null,
        last_code_snapshot: CODIGO_VIEJO_SERVIDOR,
        messages: [],
        notes: [],
        ejercicio_id: null,
        ejercicio_orden: null,
      }),
    })
    return render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)
  }

  it("el borrador local de ESTE episodio gana sobre el snapshot viejo del servidor", async () => {
    saveArtefactoDraft(EPISODIO_ID, {
      orden: MONOLITHIC_ORDEN,
      ejercicio_id: null,
      episode_id: EPISODIO_ID,
      codigo: CODIGO_LOCAL_FRESCO,
      language: "python",
    })

    montar()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).toBe(CODIGO_LOCAL_FRESCO)
  })

  it("sin borrador local, sigue cayendo al snapshot del servidor (sin regresion)", async () => {
    montar()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).toBe(CODIGO_VIEJO_SERVIDOR)
  })

  it("localStorage.getItem tira para la clave del borrador (modo privado / cuota): el editor abre igual, cae al snapshot", async () => {
    // Acotado a la clave EXACTA del borrador, no un throw global: un mock
    // global de `getItem` rompe OTRAS lecturas sin relacion (ej. el
    // `useState` de `skippedReflection` en `EpisodePage`, que lee localStorage
    // sin try/catch) y el test fallaria por una razon distinta a la que
    // afirma. Lo que este test prueba es puntual: que el try/catch DENTRO de
    // `readArtefactoDraft` (no en el llamador) es lo que mantiene la
    // hidratacion del episodio funcionando cuando ESA lectura puntual falla.
    //
    // Gotcha de este repo (nuevo, no documentado antes): `vi.spyOn(window.
    // localStorage, "getItem")` NO INTERCEPTA en este entorno (Node 22 +
    // vitest/jsdom) — probado a mano: el mock nunca se invoca y la llamada
    // real sigue pasando. `tests/setup.ts` ya avisa de esto para `setItem`
    // ("los metodos se instalan en `Storage.prototype`, no en la instancia")
    // pero el test de `CodeEditorPanelDeSalida.test.tsx` que simula
    // `setItem` roto sigue espiando la INSTANCIA de todos modos — queda
    // reportado aparte, no se toca acá. La via que SI intercepta es
    // `Storage.prototype`.
    const draftKey = rawKey(EPISODIO_ID, MONOLITHIC_ORDEN)
    const original = Storage.prototype.getItem
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
      this: Storage,
      k: string,
    ) {
      if (k === draftKey) throw new Error("SecurityError: almacenamiento no disponible")
      return original.call(this, k)
    })

    montar()

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).toBe(CODIGO_VIEJO_SERVIDOR)

    spy.mockRestore()
  })
})

describe("EpisodeView — TP multi-ejercicio (scope = entregaId, ADR-047)", () => {
  const ENTREGA_ID = "entrega-con-borrador"
  const TAREA_ID = "tp-multiejercicio-borrador"
  const EJERCICIO_ORDEN = 2
  const CODIGO_VIEJO_SERVIDOR = "print('snapshot viejo del servidor')\n"
  const CODIGO_LOCAL_FRESCO = "print('borrador local, escrito en ESTE episodio')\n"
  const CODIGO_DE_OTRO_EPISODIO = "print('residuo de un episodio ABANDONADO del mismo ejercicio')\n"

  function montar(episodeId: string) {
    setupFetchMock({
      "/resume": () => ({ ok: true }),
      [`/api/v1/tareas-practicas/${TAREA_ID}/ejercicios`]: () => [
        {
          id: "tpe-2",
          tarea_practica_id: TAREA_ID,
          ejercicio_id: "ej-2",
          orden: EJERCICIO_ORDEN,
          peso_en_tp: "1.00",
          ejercicio: {
            id: "ej-2",
            titulo: "E2",
            enunciado: "Enunciado del ejercicio 2",
            language: "python",
            inicial_codigo: null,
            test_cases: [],
          },
        },
      ],
      [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => ({ id: TAREA_ID, ...TAREA_BASE }),
      [`/api/v1/episodes/${episodeId}`]: () => ({
        episode_id: episodeId,
        tarea_practica_id: TAREA_ID,
        comision_id: "com-1",
        estado: "open",
        opened_at: "2026-08-27T10:00:00Z",
        closed_at: null,
        last_code_snapshot: CODIGO_VIEJO_SERVIDOR,
        messages: [],
        notes: [],
        ejercicio_id: "ej-2",
        ejercicio_orden: EJERCICIO_ORDEN,
      }),
    })
    return render(
      <EpisodeView
        episodeId={episodeId}
        onExit={() => {}}
        ejercicioContext={{
          entregaId: ENTREGA_ID,
          ejercicioId: "ej-2",
          ejercicioOrden: EJERCICIO_ORDEN,
        }}
      />,
    )
  }

  it("mismo episodio: el borrador local gana sobre el snapshot", async () => {
    const EPISODIO_ID = "ep-nuevo-mismo-episodio"
    saveArtefactoDraft(ENTREGA_ID, {
      orden: EJERCICIO_ORDEN,
      ejercicio_id: "ej-2",
      episode_id: EPISODIO_ID,
      codigo: CODIGO_LOCAL_FRESCO,
      language: "python",
    })

    montar(EPISODIO_ID)

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).toBe(CODIGO_LOCAL_FRESCO)
  })

  it("OTRO episodio: el borrador residual NO se usa — gana el snapshot, no el residuo", async () => {
    // Esto es lo que separa este fix de ED-4: un borrador que quedo de un
    // episodio ABANDONADO del mismo ejercicio (mismo entregaId+orden, otro
    // episode_id) no tiene forma de compararse en frescura contra el snapshot
    // del episodio nuevo. Si esto sembrara el residuo, seria ED-4 de nuevo.
    const EPISODIO_VIEJO = "ep-abandonado-anterior"
    const EPISODIO_NUEVO = "ep-reapertura-del-ejercicio"
    saveArtefactoDraft(ENTREGA_ID, {
      orden: EJERCICIO_ORDEN,
      ejercicio_id: "ej-2",
      episode_id: EPISODIO_VIEJO,
      codigo: CODIGO_DE_OTRO_EPISODIO,
      language: "python",
    })

    montar(EPISODIO_NUEVO)

    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    await waitFor(() => expect(editoresCreados[0]?.__opciones.value).not.toBe(""))
    expect(editoresCreados[0]?.__opciones.value).toBe(CODIGO_VIEJO_SERVIDOR)
    expect(editoresCreados[0]?.__opciones.value).not.toBe(CODIGO_DE_OTRO_EPISODIO)
  })
})
