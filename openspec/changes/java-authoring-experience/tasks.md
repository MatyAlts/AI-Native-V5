## 1. Gates previos

- [x] 1.1 Confirmar que `multi-language-research-integrity` está mergeada. Esta change es la que hace un ejercicio Java alcanzable por un alumno: sin la segmentación por lenguaje, el corpus de la tesis se mezcla desde el primer episodio sin ningún error visible.
- [x] 1.2 Cargar la skill `impeccable` antes de tocar UI y pasar sus gates (`PRODUCT.md`, `DESIGN.md`, shape brief confirmado). No se saltean. Register `product`. Shape brief confirmado: selector nativo en el grid de datos básicos, `Badge variant="default"` neutro sin color por lenguaje (D1), bloqueo en el momento de la selección, controles de ejecución deshabilitados con explicación (D2). Gate de imagen salteado: no hay superficie nueva, son cambios sobre componentes existentes de `@platform/ui`.
- [x] 1.3 Consultar con Ana Garis el diff del prompt del tutor. Son dos líneas de generalización de ejemplos — llevar el diff concreto, no la descripción.

## 2. Tipos y transporte del lenguaje

- [x] 2.1 Agregar el lenguaje a los tipos del cliente HTTP de web-student (`lib/api.ts:584-618,919-941`).
- [x] 2.2 Agregar el lenguaje a los tipos del cliente HTTP de web-teacher (`lib/api.ts:1904-1945`).
- [x] 2.4 🔴 Agregar `junit_assert` a las uniones de tipo de caso de prueba del frontend. El backend ya lo admite (`contracts/.../ejercicio.py:153`) pero **ninguna app lo conoce**: `TestCaseEjercicio` (teacher `lib/api.ts:1897`), `TestCasePublic` (student `lib/api.ts:571`) y `CodeEditor.tsx:151`. Sin esto, un ejercicio Java con casos de prueba llega al frontend con un `type` que TypeScript no admite. Detectado en el reconocimiento de esta epic; las tareas 2.1/2.2 no lo cubrían.
- [x] 2.3 Verificar que el lenguaje llega desde el endpoint que resuelve los ejercicios de una TP, sin pedirle nada extra al backend. Verificado por inspección de la cadena completa: `routes/tareas_practicas.py:589-631` → `TpEjercicioService.list_by_tp` (`selectinload`) → `TpEjercicioRead.ejercicio: EjercicioRead`, que hereda `language` de `_EjercicioBase` (`contracts/.../ejercicio.py:178`). Sobrevive el saneado para alumno (`content_visibility.py:59-69` usa `model_copy(update=...)` y no lista `language`) y el proxy del gateway (`proxy.py:249-253` devuelve el cuerpo crudo, sin reserializar). No hace falta pedir nada al backend.

## 3. UI del docente

- [x] 3.1 Selector de lenguaje en el formulario de ejercicios, en el grid de datos básicos junto a unidad temática y dificultad (`views/EjerciciosView.tsx:684`).
- [x] 3.2 Lenguaje visible en el listado del banco.
- [x] 3.3 Bloqueo de selección de lenguaje distinto en el modal de composición de TP (`views/TareasPracticasView.tsx`), con explicación visible.
- [x] 3.4 Liberar el bloqueo al deseleccionar todos los ejercicios. **RESUELTO corrigiendo el spec** (decisión de Juani, 2026-07-28). La tarea y su escenario asumían que el lenguaje de la TP lo fija el primer ejercicio seleccionado; en el modelo implementado `TareaPractica.language` es NOT NULL desde que la TP se crea y el backend valida `ejercicio.language != tp.language` (`tp_ejercicio_service.py:101-108`) — nunca hay un estado «sin lenguaje elegido», así que no hay bloqueo que liberar. Implementar el spec literal habría dejado seleccionar un ejercicio Java en una TP Python para comerse un 422 al confirmar, que es justo lo que la change evita. `specs/language-authoring-ui/spec.md` actualizado: el lenguaje de referencia es el que declara la TP, y los dos escenarios que asumían el estado intermedio se reemplazaron por uno que exige anunciar el motivo ANTES de que el docente choque contra un control deshabilitado (implementado: aviso sobre el listado).
- [x] 3.5 🔴 Corregir el ternario que rotula tipos de caso de prueba. Hoy es `type === "stdin_stdout" ? "stdin/stdout" : "pytest"` — con el tipo nuevo, Java se rotula como pytest. Son **cuatro** ternarios binarios en `EjerciciosView.tsx`, no dos: `:1005` y `:1077` rotulan el tipo; `:1011` y `:1085` rotulan el campo (`"entrada"` / `"assert"`). Además `:1122` filtra por `type === "pytest_assert"` para mostrar stdout, así que con `junit_assert` ese bloque deja de renderizarse.
- [x] 3.6 Advertir al crear un ejercicio Java que todavía no podrá verificarse con el panel de prueba (ver 6.2).
- [x] 3.7 🔴 El runner de Pyodide del docente despacha por tipo con un `if/else` binario (`lib/pyodideRunner.ts:230-252`): un `junit_assert` cae en la rama de `stdin_stdout` y compara stdout contra `expected`. No es un rótulo equivocado — son **resultados de test verdes o rojos que no significan nada**. Hacer que el tipo sin runtime se reporte como no ejecutable en vez de producir un veredicto falso. Es el "resultado engañoso" que 6.2 pide documentar, verificable por lectura.

## 4. UI del alumno

- [x] 4.1 Badge de lenguaje en el selector de tareas (`components/TareaSelector.tsx`), en el encabezado de cada tarjeta junto al código y título. El archivo hoy no importa `Badge` de `@platform/ui`.
- [x] 4.2 Badge en la cabecera del editor, reemplazando el `badge="Python"` fijo (`pages/EpisodePage.tsx:755`).
- [x] 4.3 Usar variante neutra del badge. No inventar colores por lenguaje: el sistema reserva el color para lo que tiene carga semántica (severidad, niveles N1–N4, apropiación).

## 5. Editor

- [x] 5.1 Ampliar el tipo de la prop de lenguaje de `CodeEditor`, hoy una unión de un solo miembro (`CodeEditor.tsx:114`).
- [x] 5.2 Pasar el lenguaje real a Monaco al crear el modelo. El paquete ya se importa completo sin tree-shaking de lenguajes, así que el tokenizer de Java ya viaja en el bundle — es un cambio de una palabra, sin costo de peso.
- [x] 5.3 Quitar el hardcode del payload del evento de edición (`pages/EpisodePage.tsx:799`) y emitir el lenguaje real.
- [x] 5.4 🔴 Deshabilitar ejecutar y probar cuando no hay entorno para el lenguaje, con explicación visible. Hoy el efecto de Pyodide sale temprano (`CodeEditor.tsx:442`), `loading` queda en `false`, el botón sigue habilitado (`:973`) y el guard de ejecución retorna sin hacer nada (`:747`): click sin ningún efecto ni mensaje.
- [x] 5.5 Corregir el rótulo accesible del botón de ejecutar, hoy fijo en Python (`CodeEditor.tsx:975`).
- [x] 5.6 Anunciar el panel de salida a tecnologías de asistencia. Hoy el bloque de error no tiene rol ni región activa, así que un alumno con lector de pantalla no se entera de un error salvo que navegue hasta ahí.
- [x] 5.7 Verificar que el camino de Python queda idéntico: carga de Pyodide, ejecución, casos de prueba, historial de corridas y marcadores de error.

## 6. Verificación manual con navegador

- [x] 6.1 Recorrer el flujo completo logueado. **Verificado con stack real (10 servicios + 2 frontends + Postgres/Redis) el 2026-07-28**:
  - ✅ Crear ejercicio Java (`language=java`, casos `stdin_stdout` + `junit_assert` aceptados por el backend).
  - ✅ Componer TP Java y publicar. El backend RECHAZA la mezcla con 422 y el mensaje correcto al intentar sumar un ejercicio Python.
  - ✅ Selector de lenguaje en el grid de datos básicos, preseleccionado en Python; el aviso de "todavia no se pueden verificar" aparece al elegir Java.
  - ✅ Columna Lenguaje en el banco, badge neutro (la dificultad conserva su color: D1 en vivo).
  - ✅ Badge de lenguaje en el selector de tareas del alumno — dos TPs, una Python y una Java, distinguibles sin abrirlas.
  - ✅ Rótulo `tutor/v1.3.0` en el pie de auditoría de AMBOS frontends, con `labeler: 1.2.0` intacto.
  - ✅ El endpoint TP→ejercicios devuelve `language` al alumno y sobrevive el saneado (2.3 confirmada en vivo, no solo por inspección).
  - ✅ **Episodio Java abierto y verificado en navegador**: badge `Java` en la cabecera, Monaco resaltando sintaxis Java, botón Ejecutar deshabilitado con el motivo al lado, panel de salida explicando que el tutor sí está disponible, y el tutor socrático operativo. Cero errores de consola.
  - ✅ **Python sin regresión** (5.7): botón Ejecutar habilitado, Pyodide carga, panel invita a ejecutar. Cero errores.
  - 📌 El 403 inicial NO era de la change: el `TenantSelector` del browser guardaba `selectedTenantId` de otra universidad, y el seed dejó todos los datos bajo un tenant (`aaaaaaaa-…`) que **ni figura en la tabla `universidades`**. El listado igual mostraba las TPs porque filtra por comisión; el tutor-service sí compara tenant y devolvía «Tarea práctica de otro tenant». Se destraba alineando `selectedTenantId`.
  - 📌 Segundo bloqueo del entorno: `GET /episodes/{id}` daba 404 tras un POST 201 porque **faltaban los 8 ctr-workers** drenando el stream Redis a Postgres (gotcha ya documentado en CLAUDE.md). Con los workers arriba, el episodio se materializa.
- [x] 6.2 Confirmar el comportamiento del panel de prueba del docente con un ejercicio Java. Corre sobre un runner de Pyodide propio, separado del editor del alumno — sin ejecución server-side no puede verificar autoría. Documentar qué muestra hoy y confirmar que no produce resultados engañosos.
- [ ] 6.3 Verificar con lector de pantalla los estados nuevos.

## 7. Prompt del tutor v1.3.0

- [x] 7.1 Crear `ai-native-prompts/prompts/tutor/v1.3.0/system.md` generalizando las dos menciones a Python (líneas 47 y 133 de v1.2.0). Nada más: el método queda idéntico.
- [x] 7.2 Crear `v1.3.0/manifest.yaml` con el hash del contenido declarado. Es lo que faltó en v1.2.0 y lo que permitió que se editara in-place sin que el cargador lo detectara.
- [x] 7.3 Actualizar el manifiesto global y el config efectivo del tutor **en el mismo commit**. El servicio no lee el manifiesto en runtime; si divergen, las interfaces informan una versión y la trazabilidad registra otra.
- [x] 7.4 Test golden del contenido de v1.3.0. Hoy no existe ninguno para v1.2.0.
- [x] 7.5 Actualizar el test que verifica la alineación entre manifiesto y config. Se edita in-place, no se crea uno nuevo por versión. **Eran DOS, no uno**: `tutor-service/tests/unit/test_config_prompt_version.py` y `governance-service/tests/unit/test_prompt_v1_0_1_bump.py`. El segundo se llamaba `test_manifest_global_activa_v101_para_tutor_default` mientras asserteaba `v1.2.0` — el nombre venía mintiendo dos bumps seguidos. Ambos pasan ahora a una constante única por archivo (`EXPECTED_TUTOR_VERSION` / `ACTIVE_TUTOR_VERSION`) y el nombre del test ya no lleva la versión.
- [x] 7.6 Actualizar los rótulos de versión visibles en la UI.

## 8. Contexto y generadores

- [x] 8.1 Rotular el bloque de código inicial con el lenguaje del ejercicio (`services/tutor_core.py:1931`). Es el único fence hardcodeado del builder: el código que el alumno escribe en vivo ya usa uno genérico.
- [x] 8.2 Variante Java de `ejercicio_generator`, con progresión de dificultad propia (básica: tipos primitivos, entrada/salida; intermedia: métodos, arreglos, métodos de `String`; avanzada: clases, excepciones, colecciones) y el tipo de caso de prueba de Java.
- [x] 8.3 Variante Java de `tp_generator`. Está tan atado a Python como el anterior: su tabla de construcciones por dificultad es sintaxis Python literal bajo una regla marcada "ESTRICTO".
- [x] 8.4 Resolver la variante de prompt según el lenguaje solicitado. Hoy ambos generadores usan una versión fija de config, sin selección dinámica.
- [ ] 8.5 🟡 PARCIAL — Verificar que una TP generada en Java pasa la validación de un solo lenguaje y se puede publicar.
  - ✅ La **cadena de resolución** funciona contra el stack real: `POST /ejercicios/generate` con `language=java` resolvió la variante sin error (un fallo de resolución da 502 «No se pudo resolver el prompt activo», que no ocurrió) y el log muestra `output_tokens=18/32768` — o sea la detección de truncamiento mide contra el techo nuevo, no contra el 8192 viejo.
  - ✅ Que una TP **Java** pasa la validación de un solo lenguaje y se publica está verificado en vivo y cubierto por smoke (`test_smoke_java_language.py` y `test_smoke_java_authoring.py`).
  - ❌ Falta validar el **contenido generado** (que el ejercicio use construcciones Java del nivel pedido y casos `junit_assert`). Con `LLM_PROVIDER=mock` el provider devuelve texto plano y el JSON nunca parsea. Requiere una corrida con un proveedor real.
- [x] 8.6 🔴 PREREQUISITO de 8.3 — `tareas_practicas.py:398` tenía `max_tokens=8192` hardcodeado, el mismo techo que trunco el wizard de ejercicios el 27/07. La variante Java del `tp_generator` engorda prompt y salida, así que iba a romper igual. Replicado el patrón del PR #54: setting propia `tp_generator_max_tokens` (default 32768, mismo tope `le=65536` del contrato del ai-gateway) + deteccion de truncamiento por `output_tokens >= max_tokens` para cortar al primer intento en vez de quemar 3 llamadas al LLM en un fallo determinista.

## 9. Cierre

- [x] 9.1 Smoke test del flujo de autoría Java, de creación a publicación. `tests/e2e/smoke/test_smoke_java_authoring.py` (5 tests, 8 casos): el alumno recibe `language` y `junit_assert` sin normalizar, la TP declara su lenguaje, y las 4 variantes de prompt son resolubles en governance. Complementa el `test_smoke_java_language.py` de la epic anterior, que cubre la autoría del docente.
- [x] 9.2 `pnpm test` de las apps tocadas y `make test-fast` en verde. `make test-fast`: **1479 passed, 4 skipped**. `pnpm test`: web-student 56/56, packages/ui 51/51. web-teacher tiene 14 fallos **preexistentes** (`No QueryClient set` en HomeView/CorreccionesView), verificados contra el árbol limpio.
- [x] 9.3 Verificar que el hash de configuración del clasificador y la versión del etiquetador no cambiaron. `LABELER_VERSION` sigue en `1.2.0` en los dos lugares (`event_labeler.py:76` y `AuditFooter.tsx`). `git diff` sobre `apps/classifier-service/` y `packages/contracts/.../ctr/` está **vacío**. Los 159 tests del classifier pasan, incluidos los 13 de reproducibilidad bit-a-bit.
- [x] 9.4 Actualizar `CLAUDE.md` si cambió el conteo de smoke tests. 45 → 50 `def test_` (85 casos con parametrizados). Documentado además `SMOKE_SKIP_ATTESTATION_CHECK=1`, que hace falta en local porque el `integrity-attestation-service` vive en la infra institucional.
