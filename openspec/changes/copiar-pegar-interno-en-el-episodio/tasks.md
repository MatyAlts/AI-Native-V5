# Tareas — copiar y pegar interno

## 0. Red de seguridad

- [x] 0.1 `npx vitest run` en `apps/web-student` y anotar el baseline exacto.
      Si algo ya falla, **PARAR y reportarlo** como falla preexistente.
      → 44 archivos, 534 tests, 0 fallas (2026-09-30 16:06).
- [x] 0.2 Verificar si el panel de la consigna es copiable hoy (`user-select`,
      handlers). Si no lo es, el change no sirve para su caso principal.
      → SI es copiable: sin `user-select: none`, sin `onCopy`/`preventDefault`
      en `EnunciadoPanel`/`MarkdownRenderer`/CSS global (verificado por grep).

## 1. RED — la politica nueva, antes del codigo

- [x] 1.1 Test: texto copiado **de la consigna** se puede pegar en el editor, y
      el evento sale con `origin: "pasted_internal"`. Debe fallar hoy.
      → `CodeEditorPegadoInterno.test.tsx`.
- [x] 1.2 Test: texto copiado **del panel del tutor** NO se puede pegar
      (ADR-026). Debe fallar hoy si el editor lo permite.
      → Pasaba ya con el bloqueo total de hoy (no vino "roja" — la tabla de
      la tasks.md la condiciona con "si el editor lo permite"); verificada
      por mutacion en 5.4.
- [x] 1.3 Test: texto que **no** esta en el portapapeles interno se bloquea y
      emite `pega_intentada`, igual que hoy.
      → Idem 1.2: no requeria estar roja hoy ("igual que hoy"); mutada en 5.4.
- [x] 1.4 Test: copiar interno, despues copiar externo, despues pegar → se
      bloquea (el interno quedo viejo y la comparacion falla).

## 2. GREEN — el portapapeles interno

- [x] 2.1 Estructura `{texto, origen}` en un ref. Los dos bloqueos actuales
      (`addCommand(Ctrl+V)` y el listener DOM en CAPTURA) pasan de **cortar** a
      **validar**.
      → `lib/portapapelesInterno.ts` + `portapapelesInternoRef` en
      `CodeEditor.tsx`. `addCommand(Ctrl+V/C/X)` se ELIMINARON (ya no hace
      falta interceptar antes del evento nativo); `onPasteDom` pasó de
      bloquear siempre a comparar con `esPegadoValido`.
- [x] 2.2 Registrar el copiado en consigna y editor. **NO** en el panel del
      tutor: ahi se sigue sin registrar, asi que cualquier pegado desde el
      tutor falla la comparacion y se bloquea solo.
      → Editor: `onCopyDom`/`onCutDom` (ya no bloquean, escriben al
      clipboard real + registran `origen: "editor"`). Consigna y cualquier
      otro lugar de la pagina: listener `document`-level (`copy`/`cut`,
      registra `origen: "pagina"`), con exclusion explicita de
      `[data-tour="tutor-chat"]` (ADR-026) y del panel de Salida/pruebas del
      propio editor (`outputPanelRef`). Ver el JUICIO sobre esta decision en
      el informe de cierre — no estaba en el "Impact" del proposal.
- [x] 2.3 Resolver la normalizacion de fin de linea (pregunta abierta del
      proposal) **con un test que la demuestre**, no con una suposicion.
      → `normalizarFinDeLinea`/`esPegadoValido` en `portapapelesInterno.ts`:
      CRLF→LF normalizado de los dos lados antes de comparar. Test:
      `portapapelesInterno.test.ts` (6 casos, incluye los dos sentidos CRLF↔LF
      y un mismatch real que la normalizacion NO debe esconder).
- [x] 2.4 Drag & drop: `dropIntoEditor` esta en `false` y el comentario de
      `CodeEditor.tsx:520` lo llama "la puerta de al lado". Que siga cerrado, o
      que valide con el mismo criterio. **Decidir y dejarlo escrito.**
      → DECISION: sigue CERRADO. Escrito en el comentario junto a
      `dropIntoEditor: { enabled: false }`: validar exigiria un rastreador de
      `dragstart` sobre las mismas regiones externas que el copy (mismo
      riesgo de fuga de ADR-026 si el tutor quedara mal excluido) para un
      gesto de uso marginal. Regresion cubierta por
      `CodeEditorArrastre.test.tsx` (4 tests, sin tocar, siguen en verde).

## 3. El contrato y el labeler

- [x] 3.1 `pasted_internal` en el Literal de `EdicionCodigoPayload.origin`.
      → `packages/contracts/.../ctr/events.py`. RED/GREEN en
      `test_edicion_codigo_payload_pasted_internal.py`.
- [x] 3.2 **NO** agregarlo a `_EDICION_CODIGO_N4_ORIGINS`, y dejar el porque en
      un comentario: copiar un nombre de variable de la consigna no es
      apropiacion reflexiva.
      → Comentario en `event_labeler.py` junto al set. Verificado por
      mutacion (agregarlo tumba `test_edicion_codigo_pasted_internal_es_n2_no_n4`).
- [x] 3.3 Verificar que agregar el valor **no** cambia el comportamiento sobre
      eventos historicos (un valor fuera del set cae al default).
      → `test_edicion_codigo_pasted_internal_es_n2_no_n4` en
      `test_event_labeler.py`.

## 4. El prompt

- [x] 4.1 v1.9.0 desde una copia limpia de v1.8.0, con el titulo bumpeado.
      → `ai-native-prompts/prompts/tutor/v1.9.0/system.md`.
- [x] 4.2 Corregir la afirmacion "copiar y pegar esta bloqueado": pasa a ser
      bloqueo **hacia afuera**; dentro del episodio se puede.
- [x] 4.3 El consejo de "llevatelo a VS Code" sigue prohibido, ahora por el
      argumento pedagogico y no por imposibilidad tecnica.
      → RED/GREEN en `test_prompt_v1_9_0_copiar_pegar_interno.py` (16 tests).
- [x] 4.4 Los **cinco** literales de version juntos, incluido el titulo del
      propio archivo. Re-firmar el hash del manifest por version.
      → título de system.md, `ai-native-prompts/prompts/tutor/v1.9.0/manifest.yaml`
      (hash propio), `ai-native-prompts/manifest.yaml` (root, `tutor: v1.9.0`),
      `tutor_service/config.py::default_prompt_version`,
      `test_config_prompt_version.py::EXPECTED_TUTOR_VERSION`,
      `test_prompt_v1_0_1_bump.py::ACTIVE_TUTOR_VERSION` (governance-service).
      Contados por `test_config_prompt_version.py`: documenta CUATRO
      ubicaciones de pin + el titulo de `system.md` = cinco. El literal de
      version se activa en este commit (igual que v1.6.0/v1.7.0/v1.8.0, ver
      precedente archivado `tutor-prompt-v1-6-0-contexto-real`); lo que
      "espera a Ana Garis" (proposal.md, Gobernanza) es el DEPLOY a
      produccion, marcado BLOQUEANTE en `ai-native-prompts/manifest.yaml`,
      no este commit. Ver JUICIO en el informe de cierre.

## 5. Verificacion

- [x] 5.1 Suite de `web-student` en verde, con el conteo antes/despues.
      → antes: 44 archivos / 534 tests. despues: 46 archivos / 548 tests
      (2026-09-30 16:34).
- [x] 5.2 `npx tsc --noEmit` limpio.
      → limpio (sin output) tras agregar `pasted_internal` tambien en
      `packages/ctr-client/src/index.ts` (duplicaba el Literal, no listado
      en el Impact del proposal — ver informe).
- [x] 5.3 Suites de tutor-service y governance-service en verde.
      → tutor-service 532/532, governance-service 30/30 (2026-09-30 16:32).
      `uv run pytest apps -q`: 2271 passed, 10 failed — los 10 son
      preexistentes en academic-service/ctr-service/evaluation-service,
      archivos que este change nunca toco (confirmado con
      `git status --porcelain`). Reportados al orquestador, NO arreglados.
- [x] 5.4 **Cada ancla verificada por mutacion.** Un test de contenido que no se
      pone rojo cuando se revierte el cambio no ancla nada.
      → Mutado y restaurado: `esPegadoValido(...)` → `true` (cae 1.2/1.3/1.4);
      exclusion `data-tour="tutor-chat"` → selector que no matchea (cae SOLO
      1.2); `_EDICION_CODIGO_N4_ORIGINS` con `pasted_internal` agregado (cae
      el test del labeler); frase falsa reinsertada en v1.9.0/system.md (cae
      el guardian del prompt); `normalizarFinDeLinea` → identidad (caen los
      3 tests de CRLF). Detalle completo en el informe de cierre.
- [x] 5.5 **NO correr builds** — prohibido por las reglas del proyecto.
      → Respetado: solo `vitest run`, `tsc --noEmit`, `pytest`.

## Fuera de alcance

- El boton "Insertar codigo del tutor" y `copied_from_tutor` (ADR-026).
- Levantar el bloqueo de pegado externo.


---

## Estado final tras los tres pases (2026-09-30 17:05)

Los conteos de arriba quedaron vencidos: son del pase del implementador, antes
de los nueve hallazgos de QA y los siete cambios posteriores. **Este bloque es
el vigente**, y se agrega acá porque `tasks.md` es lo que sobrevive al archive.

```
web-student          47 files / 554 tests            (eran 46 / 548)
tsc --noEmit         limpio
apps + packages      10 failed, 2675 passed, 100 skipped
```

**Los 10 fallos son preexistentes**, en academic/ctr/evaluation. Verificado por
QA revirtiendo `packages/contracts` al estado previo y volviendo a correrlos:
los mismos 10, con el contrato viejo. No alcanzaba con «el diff no tocó esos
archivos», porque esos servicios importan contracts.

**Lo que quedó abierto está en `review-verdict.md`**, con los cuatro casos que
hay que probar en un navegador antes de confiar en esto.
