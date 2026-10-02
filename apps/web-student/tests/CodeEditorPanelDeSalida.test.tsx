/**
 * El panel de salida: que se pueda agarrar, y que se acuerde del tamaño.
 *
 * Tres defectos reales, medidos por el orquestador con una repro aislada
 * ANTES de este cambio (no se re-investigan acá, se toman como dados):
 *
 *  1. El div raiz de `CodeEditor` (`className="flex flex-col h-full
 *     relative"`) no tenia `min-h-0`: sin el, Monaco se renderizaba 15px MAS
 *     ALTO que su contenedor y se comia el manubrio del divisor vertical.
 *  2. Ni el `Panel` ni el contenedor de Monaco recortaban su contenido
 *     (`overflow: visible`, puesto por la propia libreria) — el manubrio
 *     quedaba a 2px del borde inferior de Monaco, sin margen de error.
 *  3. El manubrio es una rayita de 2px de alto x 48px de ancho sobre un panel
 *     oscuro, sin area de agarre extra: funciona, pero nadie lo encuentra.
 *
 * Este cambio cierra 1 y 2 con CSS, y le da a 3 un area de agarre mas grande
 * y un grip mas visible (ver el JSX de `CodeEditor` — eso no es testeable en
 * jsdom, ver mas abajo).
 *
 * Por que el recorte del Panel usa `style`, no una clase de Tailwind
 * ---------------------------------------------------------------------
 * `react-resizable-panels` le pone a su DIV INTERNO (el que recibe nuestra
 * `className`) un `style={{ overflow: "auto", ... }}` INLINE por default
 * (`Panel`, en el bundle de la libreria). Un inline style de la libreria le
 * gana a cualquier clase de Tailwind sin `!important` — agregar
 * `overflow-hidden` a `className` no hace NADA ahi. El prop `style` que
 * `Panel` expone se mergea DESPUES de ese default, en el mismo objeto
 * (`{ overflow: "auto", ...S }` con `S` = nuestro `style`): es la UNICA via
 * que efectivamente lo pisa. Verificado leyendo el bundle, no documentado por
 * la libreria.
 *
 * Que NO prueba este archivo
 * ---------------------------
 * El redimensionado real (arrastrar el manubrio y que el editor cambie de
 * alto) necesita layout real — `getBoundingClientRect`/`offsetHeight`/
 * `ResizeObserver`, que jsdom no calcula (siempre 0). La propia API
 * imperativa `resize()` de la libreria depende de esas medidas (divide por el
 * tamaño del grupo en pixeles), asi que ni siquiera eso es un atajo honesto
 * en jsdom — solo serviria para fingir un redimensionado con un numero
 * inventado. Lo que SI es observable sin layout: la persistencia (se lee de
 * `localStorage` al montar, se escribe cuando la libreria avisa un cambio de
 * layout) y que el manubrio exista con su rol accesible. Eso es lo unico que
 * se afirma acá.
 *
 * QA round 2 — el cableado contra el `<Group>`, no solo las funciones puras
 * --------------------------------------------------------------------------
 * Mutado por QA: sacar `defaultLayout={savedOutputPanelLayout}` O
 * `onLayoutChanged={handleOutputPanelLayoutChanged}` del `<Group>` dejaba
 * la suite entera en 630/630 verde — los tests de "persistencia" de mas abajo
 * prueban `readStoredOutputPanelLayout`/`persistOutputPanelLayout` aisladas,
 * nunca que `CodeEditor` se las pase al `Group`. El describe
 * "el layout guardado llega de verdad al <Group>" cierra la mitad de LECTURA
 * de ese hueco, leyendo el `flexGrow` inline que la libreria le pone a cada
 * `Panel` (deriva directo del estado de React, no de una medicion de layout
 * — ver el comentario en ese describe). La mitad de ESCRITURA
 * (`onLayoutChanged`) se investigo y quedo sin cerrar — ver el comentario ahi
 * mismo sobre por que, declarado explicito en vez de fingido con un test que
 * no prueba nada.
 */
import { render, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  CodeEditor,
  OUTPUT_PANEL_STORAGE_KEY,
  persistOutputPanelLayout,
  readStoredOutputPanelLayout,
} from "../src/components/CodeEditor"
import { editoresCreados, resetMonacoMock } from "./_monacoMock"

beforeEach(() => {
  resetMonacoMock()
  window.localStorage.clear()
})

describe("CodeEditor — el div raiz no deja que Monaco se coma el manubrio", () => {
  it('el div raiz lleva "min-h-0" (defecto 1: Monaco se desbordaba 15px)', () => {
    const { getByTestId } = render(<CodeEditor initialCode="x=1" language="java" />)
    expect(getByTestId("code-editor-root")).toHaveClass("min-h-0")
  })
})

describe("CodeEditor — el Panel del editor recorta su contenido (defecto 2)", () => {
  it('el div interno del Panel "editor-code" tiene overflow:hidden inline', () => {
    const { container } = render(<CodeEditor initialCode="x=1" language="java" />)
    const panelExterno = container.querySelector('[data-testid="editor-code"]')
    const panelInterno = panelExterno?.firstElementChild as HTMLElement | null
    expect(panelInterno).not.toBeNull()
    // Inline, no clase: ver el docstring del archivo sobre por que una clase
    // de Tailwind no alcanza acá.
    expect(panelInterno?.style.overflow).toBe("hidden")
  })

  it("Monaco se crea con fixedOverflowWidgets: true, para que el overflow-hidden de arriba no le recorte el widget de sugerencias", async () => {
    // El widget de autocompletado de Monaco (y el de parametros, y el de
    // busqueda) por default se posiciona `absolute` DENTRO del propio
    // contenedor del editor. Si ese contenedor ahora vive dentro de un
    // ancestro con `overflow: hidden` (el fix de arriba) y el widget necesita
    // abrirse mas abajo de lo que el panel mide, quedaria recortado — la
    // sugerencia se veria cortada a la mitad o directamente invisible.
    // `fixedOverflowWidgets: true` es la opcion que Monaco expone para este
    // caso exacto: monta esos widgets con `position: fixed` en un nodo
    // separado que ignora cualquier `overflow: hidden` ancestro.
    render(<CodeEditor initialCode="x=1" language="java" />)
    await waitFor(() => expect(editoresCreados.length).toBeGreaterThanOrEqual(1))
    expect(editoresCreados[0]?.__opciones.fixedOverflowWidgets).toBe(true)
  })
})

describe("CodeEditor — el manubrio del panel de salida es accesible", () => {
  it('existe con role="separator" y es alcanzable por teclado (tabIndex 0)', () => {
    const { container } = render(<CodeEditor initialCode="x=1" language="java" />)
    const manubrio = container.querySelector('[role="separator"]')
    expect(manubrio).not.toBeNull()
    expect(manubrio).toHaveAttribute("tabIndex", "0")
  })

  // QA round 2 (frontend): el manubrio llevaba `focus-visible:outline-none`
  // SIN ningun `focus-visible:ring-*` que lo reemplace — quedaba solo el
  // cambio de color del grip de 4px. El archivo ya tiene el patron correcto
  // en otros dos botones (`focus-visible:ring-2
  // focus-visible:ring-accent-brand/40`, ver `CodeEditor.tsx:1921,1955`): el
  // manubrio nuevo tiene que alinearse con ESE anillo, no ser el unico
  // control del archivo sin indicador de foco real.
  it('lleva el mismo anillo de foco que el resto del archivo ("focus-visible:ring-2 focus-visible:ring-accent-brand/40")', () => {
    const { container } = render(<CodeEditor initialCode="x=1" language="java" />)
    const manubrio = container.querySelector('[role="separator"]')
    expect(manubrio).toHaveClass("focus-visible:ring-2")
    expect(manubrio).toHaveClass("focus-visible:ring-accent-brand/40")
  })

  // Ningun separador del archivo (ni este ni los dos laterales preexistentes
  // de `EpisodePage.tsx`) tenia nombre accesible. Este test cierra el nuevo
  // nada mas — los dos laterales quedan como deuda preexistente declarada en
  // `tasks.md`, no se tocan en este cambio.
  it('tiene nombre accesible ("Redimensionar el panel de salida")', () => {
    const { container } = render(<CodeEditor initialCode="x=1" language="java" />)
    const manubrio = container.querySelector('[role="separator"]')
    expect(manubrio).toHaveAttribute("aria-label", "Redimensionar el panel de salida")
  })
})

describe("CodeEditor — el layout guardado llega de verdad al <Group> (QA round 2, mutacion)", () => {
  // QA mutó el componente sacando `defaultLayout={savedOutputPanelLayout}` del
  // `<Group>` y la suite entera siguió en 630/630 verde: los 10 tests de este
  // archivo prueban `readStoredOutputPanelLayout`/`persistOutputPanelLayout`
  // como funciones puras aisladas, nunca que el `CodeEditor` se las pase al
  // `Group`. Este test cierra ESE hueco especifico: lee contra el DOM, no
  // contra la funcion pura.
  //
  // Como se sabe que el layout guardado es observable sin layout real:
  // `react-resizable-panels` computa, por cada `Panel`, un `flexGrow` IGUAL al
  // numero del layout (via `getPanelStyles`, ver el bundle de la libreria) y
  // lo pone en el `style` INLINE del div con `data-testid={id}` — no depende
  // de `getBoundingClientRect`/`ResizeObserver` (que jsdom no calcula), es un
  // valor puesto directo desde el estado de React. Por eso difiere del default
  // (62/38, los `defaultSize` de cada `Panel`) de forma observable en jsdom.
  it("un layout guardado en localStorage (30/70) se aplica a los paneles, no el default (62/38)", () => {
    const layoutGuardado = { "editor-code": 30, "editor-output": 70 }
    window.localStorage.setItem(OUTPUT_PANEL_STORAGE_KEY, JSON.stringify(layoutGuardado))

    const { container } = render(<CodeEditor initialCode="x=1" language="java" />)

    const panelEditor = container.querySelector('[data-testid="editor-code"]') as HTMLElement | null
    const panelSalida = container.querySelector(
      '[data-testid="editor-output"]',
    ) as HTMLElement | null
    expect(panelEditor).not.toBeNull()
    expect(panelSalida).not.toBeNull()

    // El default declarado en el JSX es `defaultSize={62}` / `defaultSize={38}`
    // — si el `defaultLayout` guardado no llegara al `Group`, estos dos
    // valores serian 62/38 en vez de 30/70.
    expect(panelEditor?.style.flexGrow).toBe("30")
    expect(panelSalida?.style.flexGrow).toBe("70")
  })

  // Por que NO hay un test equivalente para `onLayoutChanged` (la escritura)
  // ------------------------------------------------------------------------
  // Se investigo honestamente una via: disparar un `keyDown` de flecha sobre
  // el separador, porque el calculo de `adjustLayoutByDelta` para el trigger
  // "keyboard" opera en espacio de PORCENTAJES (no pixeles) — en principio no
  // deberia necesitar layout real. Probado a mano: jsdom tira
  // `Error: Previous layout not found for panel index 0` ANTES de llegar a
  // ese calculo — el registro interno de paneles de la libreria depende de
  // una medicion previa (via `ResizeObserver`, que jsdom no dispara) que
  // nunca llega a completarse. Mismo techo que documenta el resto de este
  // archivo sobre `resize()`, solo que alcanza tambien al camino de teclado.
  // Confirmado quitando la via "keyboard": no queda ninguna forma de
  // disparar `onLayoutChanged` sin simular layout real.
  //
  // Lo que SI queda cubierto: la lectura (test de arriba, que cae si se
  // borra `defaultLayout`) y que `persistOutputPanelLayout` en si misma
  // escribe bien bajo la clave (suite de persistencia, mas abajo). El hueco
  // real que queda sin cerrar: si alguien borra el `onLayoutChanged={...}`
  // del `<Group>`, NINGUN test de este archivo lo detecta. Reportado como tal
  // en el cierre, no escondido.
})

describe("persistencia del tamaño del panel de salida — patron ED-2 replicado", () => {
  it("la clave es la declarada en la tarea", () => {
    expect(OUTPUT_PANEL_STORAGE_KEY).toBe("web-student.editor.outputPanel.v1")
  })

  it("sin nada guardado, la lectura devuelve undefined (no inventa un layout)", () => {
    expect(readStoredOutputPanelLayout()).toBeUndefined()
  })

  it("lee lo que fue guardado bajo la clave", () => {
    const layout = { "editor-code": 70, "editor-output": 30 }
    window.localStorage.setItem(OUTPUT_PANEL_STORAGE_KEY, JSON.stringify(layout))
    expect(readStoredOutputPanelLayout()).toEqual(layout)
  })

  it("JSON corrupto -> undefined, no tira", () => {
    window.localStorage.setItem(OUTPUT_PANEL_STORAGE_KEY, "{esto no es json valido")
    expect(readStoredOutputPanelLayout()).toBeUndefined()
  })

  it("escribe el layout bajo la clave declarada", () => {
    const layout = { "editor-code": 55, "editor-output": 45 }
    persistOutputPanelLayout(layout)
    expect(JSON.parse(window.localStorage.getItem(OUTPUT_PANEL_STORAGE_KEY) ?? "")).toEqual(layout)
  })

  it("si localStorage.setItem tira (cuota llena / modo privado), no rompe al alumno", () => {
    const spy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError")
    })
    expect(() => persistOutputPanelLayout({ "editor-code": 60 })).not.toThrow()
    spy.mockRestore()
  })
})
