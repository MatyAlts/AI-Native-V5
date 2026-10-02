# Veredicto de revisión — `editor-del-alumno-tres-pedidos`

Commits revisados: `8486551`, `7b2e62f`, `2a02b6e`. Fecha: 2026-10-02.

Revisores convocados: **QA** (con mutación) y **frontend**. Más dos verificaciones
en browser real hechas por el orquestador, que están abajo con su método.

---

## EVIDENCIA

```
$ cd apps/web-student && pnpm test -- --run          (2026-10-02 13:39, orquestador)
Test Files  53 passed (53)
Tests  636 passed (636)

$ pnpm run typecheck                                  (2026-10-02 13:39)
tsc --noEmit → sin salida

$ pnpm exec biome check --write .                     (2026-10-02 14:03)
Checked 113 files. No fixes applied. 1 warning preexistente
(tests/episodioDownload.test.ts:112), no tocado por este cambio.
```

### Mutación — QA (2026-10-02 13:13 a 13:15)

Cada mutación aplicada, corrida y revertida con `git checkout --`.

| Qué se rompió | Resultado |
|---|---|
| Sacar `borradorLocal` de `resolverCascadaDeCodigo` | **ROJO** — 3 tests |
| Sacar la guarda `draft.episode_id === episodeId` | **ROJO** — 1 test, el que corresponde |
| Desalinear el `orden` de lectura vs. el de escritura | **ROJO** — 2 tests |
| `readArtefactoDraft` acepta código vacío | **ROJO** — 1 test |
| Sacar `wordBasedSuggestions` | **ROJO** — 2 tests |
| Sacar `defaultLayout` del `<Group>` | **VERDE 630/630** → cerrado en `7b2e62f` |
| Sacar `onLayoutChanged` del `<Group>` | **VERDE 630/630** → **queda abierto**, ver abajo |

El test viejo de ED-4 (`CodigoPrevioSiembra.test.tsx`) siguió en verde al mutar
la guarda nueva: el candado anti-ED-4 tiene red propia y no se apoya en la vieja.

### Mutación — orquestador (2026-10-02 14:01)

```
# try/catch removido de persistOutputPanelLayout
$ pnpm test -- --run tests/CodeEditorPanelDeSalida.test.tsx
Tests  13 passed (13)        ← el test del localStorage lleno NO discriminaba

# mismo código mutado, con el espía reescrito sobre Storage.prototype
AssertionError: expected [Function] to not throw an error but
'Error: QuotaExceededError' was thrown        ← rojo real
```

Causa: `vi.spyOn(window.localStorage, "setItem")` no intercepta — en jsdom bajo
Node 22 el `localStorage` es un Proxy, así que definirle una propiedad propia no
tapa a la del prototipo. `tests/setup.ts:23` ya documentaba la trampa y el test
la ignoró. Cerrado en `2a02b6e`.

### Verificación en browser real — orquestador

**1. El divisor del panel de salida funciona.** Repro aislado con
`react-resizable-panels@4.11.1` y el mismo encadenamiento de CSS: arrastrando
el separador, editor 524px → 304px y salida 321px → 541px.

**2. El derrame de Monaco, medido con A/B.** Sin `min-h-0` en la raíz del
`CodeEditor`, Monaco se renderiza **15px más alto que su contenedor**; con
`min-h-0`, **0px**. El manubrio mide 8px y quedaba a 2px del borde inferior de
Monaco. De ahí sale el arreglo de `CodeEditor.tsx:1831`.

**3. `fixedOverflowWidgets` NO queda anulado por el `transform` del ancestro.**
El revisor de frontend advirtió que `animate-fade-in-up` (fill-mode `both`) deja
un `transform: translateY(0)` permanente en el `<section>` de
`EpisodePage.tsx:937`, que lo volvería containing block y rompería el
`position: fixed` del widget de sugerencias. Se montaron los dos casos lado a
lado con Monaco real dentro de un panel con `overflow: hidden`: el widget
aparece en **coordenadas idénticas** con y sin transform (top 601, bottom 643),
en dos corridas independientes y con dos geometrías de panel distintas, y se
desborda 42px fuera del panel recortado — que es exactamente para lo que está la
bandera. El mecanismo CSS que describe el revisor es real; Monaco lo compensa
posicionando el widget con coordenadas medidas.

---

## JUICIO

**(QA, confianza alta)** Los tests nuevos discriminan en 5 de las 6 mutaciones
pedidas. Ninguno cae en las formas de aserción vacía ya catalogadas en este repo.

**(QA, confianza media)** El candado `episode_id === episodeId` —lo único que
separa este cambio de ED-4— tiene exactamente **un** test que lo prueba. Es una
red angosta pero real. No se evaluó cuán fácil sería que ese test desaparezca en
un refactor futuro sin que nadie note qué protegía.

**(frontend, confianza alta)** El manubrio hacía `focus-visible:outline-none`
sin ningún `ring` de reemplazo, quedando como el control que **peor** indicaba el
foco de los tres patrones que conviven en el mismo archivo
(`CodeEditor.tsx:1921` y `:1955` usan `ring-2 ring-accent-brand/40`; los
divisores de `EpisodePage.tsx:1473,1481` conservan el outline nativo). Cerrado
en `7b2e62f`.

**(orquestador, confianza alta)** Roles no convocados en este cambio:
- **DBA** — el diff no toca migración, esquema ni consulta.
- **backend** — no toca ningún endpoint ni servicio.
- **DevOps** — deploy y configuración intactos.
- **arquitecto** — el cambio no mueve ninguna frontera: agrega un candidato a una
  función pura que ya existía.
- **analista funcional** — corresponde a `archive`, no a esta fase.

Leí el diff completo antes de elegir.

---

## SUPUESTO

**(orquestador, no verificado)** No se logró llevar el editor a la geometría
extrema donde el widget de sugerencias tendría que pasarse del borde inferior de
la `<section>` entera — o sea, el caso "el alumno arrastra el divisor hasta el
fondo y el popup no entra". Queda sin verificar, y el comentario de producción en
`CodeEditor.tsx` lo dice como supuesto, no como cubierto.

**(implementador, declarado)** No se corrió línea base de la suite completa antes
de tocar `EpisodePage.tsx` y `CodeEditor.tsx`, sólo una acotada. Se compensó
corriendo la completa después (630/630, luego 636/636). Es evidencia fuerte, no
el protocolo literal.

**(implementador, declarado)** El ajuste visual del manubrio (tamaño, color,
hover) no tiene test — imposible en jsdom. Sigue el lenguaje visual de los
divisores laterales, pero que "ahora se agarra mejor" no está verificado.

---

## Hallazgos que quedan ABIERTOS

Escritos acá a propósito: cerrar sobre un hallazgo abierto es legítimo, que el
hallazgo se vuelva invisible no.

1. **`onLayoutChanged` no tiene test que caiga si se borra.** La dirección de
   lectura quedó cubierta en `7b2e62f`; la de escritura no. La única vía honesta
   que se encontró (resize por teclado) falla en jsdom con
   `Error: Previous layout not found for panel index 0`, antes de llegar al
   cálculo. Si alguien borra esa línea, el tamaño del panel deja de guardarse y
   la suite sigue verde.

2. **Los separadores no tienen nombre accesible.** El nuevo lo recibió
   (`aria-label="Redimensionar el panel de salida"`); los dos laterales de
   `EpisodePage.tsx:1473,1481` siguen sin él. Deuda preexistente a nivel de
   patrón, deliberadamente fuera de este PR.

3. **No se revisó si el patrón ED-2 original tiene el mismo hueco de cableado**
   que se encontró acá — es decir, si la persistencia de los tres paneles
   horizontales de `EpisodePage` también pasa en verde al borrarle los props.
   La sospecha es que sí. No se verificó.
