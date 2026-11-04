# apply-1-constructor-C: grupo 11 (web-teacher), tareas 11.1 a 11.10

- Rol: constructor. Fase apply, intento 1, tanda C.
- Ejecutor declarado: subagente nativo Claude Code (familia Anthropic). En paralelo corría el constructor de la tanda A (grupos 1 a 5, classifier-service) en la misma rama y el mismo árbol.
- Fecha: 04/11/2026, 12:16 a 12:48 (-03:00).
- Revisión revisada y entregada: `HEAD b32e621f992aac3f2252e03d08c1cb73c0bdcee5` (rama `feat/cibse-codificacion-ciega`) más cambios sin commitear bajo `apps/web-teacher/`. Huella de la revisión entregada: sha256 de la lista `sha256sum` de cada archivo tocado = `6f58a21afa201ad7153c9cb4b8009dbeec9039eaabf3c8ac4859ab5208ec4a9c` (lista completa en `scratchpad/constructor-C/huella.txt`, fuera del repo). Sin commits ni push; índice de git limpio.
- Alcance respetado: solo archivos bajo `apps/web-teacher/`, más este informe y su fila en `LEEME.md`. `tasks.md` no se editó.

## Fuentes leídas

- `openspec/changes/cibse-codificacion-ciega/{proposal.md, design.md, tasks.md}` y `specs/{estudio-codificacion, traza-ciega-episodio, estudio-codificacion-acceso, codebook-versionado, entrenamiento-calibracion, estudio-codificacion-exportacion}/spec.md`; `informes/LEEME.md`.
- `CLAUDE.md` del repo (secciones "Frontends React" y "Sistema de ayuda in-app"); `.claude/skills/help-system-content/SKILL.md`; `PRODUCT.md`; `DESIGN.md` (tokens y componentes, por encabezados).
- Código del web-teacher: `src/main.tsx`, `src/routes/{__root,interrater,entrenamiento-recalibracion,kappa}.tsx`, `src/views/{InterraterCodingView,interraterShared,InterraterTraining}.tsx` (los tres borrados), `src/lib/api.ts` (helpers de auth y errores, `listMyComisiones`), `src/utils/lineDiff.ts`, `src/utils/errorApi.ts`, `src/utils/helpContent.tsx`, `src/components/ViewModeToggle.tsx`, `tests/{_mocks.tsx,setup.ts,navegacionAlcanzable.test.ts,helpContent.coverage.test.ts,docenteOnboarding.test.tsx}` (encabezado), `packages/ui/src/components/ConfirmDialog.tsx` y exports de `packages/ui/src/index.ts`.
- Lecciones numeradas (L-NNN): **no existen**. Búsqueda propia `rg -l "\bL-[0-9]{3}\b" docs openspec` sin resultados (04/11/2026 12:48), coincide con lo declarado por el orquestador.

## Contaminación

- No leí el contenido de `informes/apply-1-constructor-A.md` ni el código backend del constructor A. Solo vi en `git status` que existen `models/estudio.py`, la migración y un test de esquema. El contrato HTTP lo tomé de design/specs/tasks, no de código backend.
- Incidente de scratchpad compartido: el constructor A sobrescribió mi script `scratchpad/mutar.py` con uno suyo del mismo nombre (12:25 aprox.). Un mutante mío (`RUTAS_MODO_RESTRINGIDO` sin `/entrenamiento-recalibracion`) arrancó con el script ajeno, quedó bloqueado leyendo stdin **antes de tocar ningún archivo** (su script lee el JSON antes de copiar) y lo maté (PID 4171536). Verifiqué `__root.tsx` intacto con `rg` y repetí el mutante con un script propio en `scratchpad/constructor-C/mutar_c.py`. Desde ahí todos mis mutantes usan ese script. Los backups de A (`2.1-*.bak`) y los míos no comparten nombre.
- Incidente de índice: al borrar las vistas del piloto corrí `git rm --cached`, que dejó las tres bajas preparadas en el índice. Lo revertí con `git restore --staged` sobre esas tres rutas; `git diff --cached --name-only` quedó vacío (0 líneas). No toqué el índice para nada más.
- Aviso del entorno: tras correr biome, la herramienta informó que `tasks.md` había cambiado en disco. No lo modifiqué yo (biome corrió solo sobre archivos de `apps/web-teacher/`); lo atribuyo al orquestador o al constructor A, sin verificar.

## Línea de base (antes de cambiar archivos)

EVIDENCIA
- `cd apps/web-teacher && pnpm test`, 2026-11-04T12:16:42: `Test Files 39 passed (39)`, `Tests 512 passed (512)`.
- `pnpm --filter @platform/web-teacher typecheck`, 12:16:51 a 12:16:59: `tsc --noEmit` sin errores.
- Sin fallas previas. (Lint de base no corrido antes de cambiar; ver SUPOSICIÓN.)

## Convención de la evidencia

- Esqueleto de RED: para que el RED sea por aserción y no por import faltante, antes de cada test nuevo creé el módulo con firma y sin comportamiento (funciones que no llaman a `fetch`, componentes que devuelven `<div/>`). Ningún esqueleto quedó en la entrega.
- Mutantes: `scratchpad/constructor-C/mutar_c.py ARCHIVO VIEJO NUEVO TEST`: reemplaza un patrón único, corre el test focal, revierte siempre y comprueba que el archivo vuelve byte a byte (`REVERTIDO OK`). Ningún mutante quedó aplicado.

## 11.1 `src/lib/estudioApi.ts` - HECHA

Archivos: `src/lib/estudioApi.ts` (nuevo), `src/lib/api.ts` (solo `export` en `authHeaders` y `throwIfNotOk`), `tests/estudioApi.test.ts` (nuevo, 37 tests).

EVIDENCIA
- RED `pnpm test -- tests/estudioApi.test.ts`, 12:19:46: `Tests 36 failed (36)`. 35 por aserción (`expected '(sin fetch)' to be '/api/v1/interrater/estudios/...'`, `expected null not to be null`, `expected 'x' to be 'enunciado_pendiente'`, `expected -1 to be 502`); 1 (revocación) por `"undefined" is not valid JSON` al parsear un cuerpo inexistente: no cuenta como RED, se acreditó con el mutante (a) de abajo.
- GREEN mismo comando, 12:20:48: `Tests 36 passed (36)`.
- Mutantes, 12:21:03 a 12:21:08, todos muertos y revertidos:
  - (a) email de revocación en la URL (`/membresias?email=${email}`): fallan "revocar membresia" y "la revocacion manda el email en el cuerpo y no en la URL" (`not to contain 'Ejemplo'`).
  - (b) cuerpo de muestra normalizado (`texto.replace(/\r\n/g, "\n")`): falla "la muestra viaja como texto crudo" (`expected '...\n...' to be '...\r\n...'`).
  - (c) régimen del pedido en lugar del devuelto por el servidor: falla "el regimen derivado ... llega al llamador" (`expected null to be 'reflexiva'`).
- Ampliación posterior (durante 11.8): `cargarMuestra`/`cargarEnunciados` aceptan `string | Blob` para mandar el `File` con sus bytes exactos. Test nuevo "un archivo (Blob) viaja tal cual como cuerpo" nació verde (12:38:04, `37 passed`) porque en runtime el `Blob` ya pasaba; acreditado con mutante `body: String(texto)` (12:38:16): `expected '[object Blob]' to be Blob{...}`, 1 failed. Después cambié solo los tipos; `typecheck` limpio y `37 passed`.

## 11.3 `src/utils/diffLineas.ts` - HECHA

Archivos: `src/utils/diffLineas.ts` (nuevo), `tests/diffLineas.test.ts` (nuevo, 9 tests).

JUICIO (constructor C, comparación con `src/utils/lineDiff.ts`, confianza alta): ya existe un LCS por líneas sin dependencias (`lineDiff.ts`, con clamp de tamaño). Reescribirlo sería duplicar código existente; `diffLineas.ts` delega en él y agrega lo que faltaba: normalización CRLF/CR a LF y la forma que consume la traza.

EVIDENCIA
- RED `pnpm test -- tests/diffLineas.test.ts`, 12:21:30: `Tests 9 failed (9)`, todos por aserción (`expected [] to deeply equal [...]`, `expected -1 to be +0`, `expected true to be false`).
- GREEN `pnpm test -- tests/diffLineas.test.ts tests/eventDisplay.test.ts`, 12:21:41: `Test Files 2 passed`, `Tests 15 passed` (9 propios + 6 de `eventDisplay`, consumidor vecino).
- Mutante (durante 11.4, 12:31:09): invertir `add`/`remove` en el mapeo: falla "dos estados de codigo..." de `TrazaCiega` (`expected '−quitada: x = 2' to contain 'x = 1'`).

## 11.2 `accesoPanel.ts`, `main.tsx`, `routes/__root.tsx` - HECHA

Archivos: `src/utils/accesoPanel.ts` (nuevo: `resolverAcceso` y `consultarAcceso`), `src/main.tsx`, `src/routes/__root.tsx`, `tests/accesoPanel.test.ts` (nuevo, 12 tests), `tests/rootModoRestringido.test.tsx` (nuevo, 5 tests).

Decisiones de implementación (JUICIO, constructor C):
- El modo viaja en el contexto del router (`RouterContext.modoAcceso`); ausente equivale a `completo` (dev sin Clerk y tests existentes).
- `__root.tsx`: `beforeLoad` del root redirige a `/interrater` en modo restringido salvo `/interrater` y `/entrenamiento-recalibracion`; `LayoutRestringido` no monta `TourProvider`, `OnboardingDocente`, `TourAutoStart`, `ComisionSelectorRouted`, `TenantSelector` ni `ViewModeToggle`.
- `main.tsx` solo orquesta: la lógica de "dos consultas en paralelo, la falla de una no tapa a la otra" quedó en `consultarAcceso` (con `Promise.allSettled`) para poder probarla. Casos borde decididos: sin comisiones y con `mis-membresias` caído, redirige (nada acredita acceso); comisiones caídas y sin membresías, redirige.

EVIDENCIA
- RED `resolverAcceso`, 12:21:57: `Tests 6 failed | 3 passed (9)`, los 6 por aserción (`expected { modo: 'completo' } to deeply equal { modo: 'restringido' }` y similares). Los 3 nacidos verdes (casos "completo") se acreditaron con mutantes.
- GREEN 12:22:10: `Tests 9 passed (9)`.
- Mutantes `resolverAcceso` (12:22:12 a 12:22:23), todos muertos: completo solo sin membresías (2 fallas); completo solo con membresías OK (1); restringido con lista vacía (2); completo solo con membresías no vacías (mata el nacido verde "docente con comisiones y sin membresias").
- RED `consultarAcceso`, 12:27:13: `Tests 3 failed | 9 passed (12)`, por aserción (`expected { modo: 'redirigir' } ...`, `expected [] to deeply equal [ 'comisiones', 'membresias' ]`). GREEN 12:27:21: `12 passed`.
- Mutantes `consultarAcceso` (12:28:14 y 12:28:16), muertos: consultas en serie (`expected [ 'comisiones' ] to deeply equal [ 'comisiones', 'membresias' ]`); `Promise.all` en lugar de `allSettled` (3 fallas).
- RED root, 12:24:17 (tras dos ajustes de montaje del test: `comisionId` tiene que ser UUID y la vista de Progresión se cae con el mock genérico, por eso el control usa `/interrater-admin`): `Tests 3 failed | 2 passed (5)`, por aserción (`expected '/progression' to be '/interrater'`, `not to contain 'Progresión'`, `expected <h2 id="cartel-bienvenida"> to be null`). Los 2 verdes: el control en modo completo (comportamiento existente) y "Entrenamiento alcanzable" (acreditado con mutante).
- Ajuste del test durante GREEN: la aserción "sin selectores" contaba cualquier `/api/v1/universidades`, pero el pedido a `?limit=200` venía de la vista VIEJA de `/interrater` (AcademicContextSelector), no del layout. La acoté a `/api/v1/universidades/mine` (lo que pide `TenantSelector`), en el caso restringido y en el control.
- GREEN root, 12:24:49: `Tests 5 passed (5)`.
- Mutantes root (12:24:59, 12:25:03, 12:28:11), muertos: sin redirect (`expected '/progression' to be '/interrater'`); layout completo en modo restringido (2 fallas: menú y cartel de bienvenida); rutas permitidas sin Entrenamiento (`expected '/interrater' to be '/entrenamiento-recalibracion'`).
- `main.tsx`: typecheck limpio a las 12:28:31. No tiene test propio (su lógica está en `consultarAcceso`).
- Consumidores, 12:28:42: `pnpm test -- tests/docenteOnboarding.test.tsx tests/navegacionAlcanzable.test.ts tests/toursDocente.test.tsx tests/rootModoRestringido.test.tsx tests/accesoPanel.test.ts`: `Test Files 5 passed (5)`, `Tests 180 passed (180)`.

## 11.4 `src/views/estudio/TrazaCiega.tsx` - HECHA

Archivos: `src/views/estudio/TrazaCiega.tsx` (nuevo), `tests/TrazaCiega.test.tsx` (nuevo, 14 tests).

Comportamiento: consigna de TP y de ejercicio arriba (regiones rotuladas, `MarkdownRenderer`, solo TP si `ejercicio_md` es null); elementos por tipo con localizador global `#n`, localizador por tipo (`turno k`, `código k`, `ejecución k`, `prueba k`, `nota k`, `lectura k`) y tiempo relativo `+mm:ss` / `+h:mm:ss`; diff de líneas entre estados de código; salida de error rotulada; fin cerrado distinto de fin abandonado. Segunda barrera: omite tipos desconocidos y lee solo campos conocidos por nombre (nunca recorre ni serializa `datos`). Errores: 409 `evidencia_alterada`, `traza_version_distinta`, `enunciado_pendiente`, 502/504 y cualquier otro con mensaje propio, sin reenviar el cuerpo del servidor.

EVIDENCIA
- RED `pnpm test -- tests/TrazaCiega.test.tsx`, 12:29:35: `Tests 13 failed (13)`, por aserción de Testing Library (`Unable to find role="region" and name "Consigna del trabajo práctico"`, `Unable to find an element by: [data-testid="traza-elemento-7"]`, etc.).
- GREEN 12:30:38: `Tests 13 passed (13)`.
- Mutantes (12:30:50 a 12:31:12): muertos 6 de 8: sin filtro de tipos (`expected <li> to be null`); mensaje del alumno con todos los valores de `datos` (3 fallas); pegado con `contenido_preview` (`aparecio "texto_pegado_prohibido"`); 502 con el cuerpo del error (`not to contain 'detalle_interno'`); diff invertido; sin localizador de turno en la respuesta del tutor.
- Sobrevivientes:
  - `default: return <pre>{JSON.stringify(d)}</pre>` en el `switch`: **mutante equivalente**. La rama es inalcanzable porque el filtro de tipos conocidos corre antes; el filtro sí tiene su mutante muerto.
  - Mensaje genérico con `String(e)`: **hueco real**. Agregué el test "otro error (500): mensaje generico, sin el cuerpo del error" y lo acredité con ese mismo mutante (12:31:27): `not to contain 'secreto_500'`, 1 failed. Revertido; GREEN 12:31:30: `Tests 14 passed (14)`.

## 11.5 `src/views/estudio/FormularioEsquema.tsx` - HECHA

Archivos: `src/views/estudio/FormularioEsquema.tsx` (nuevo), `src/views/estudio/mensajesError.ts` (nuevo, mensajes por código compartidos por las vistas), `tests/FormularioEsquema.test.tsx` (nuevo, 15 tests, con dos esquemas distintos construidos en el test: uno con regla y otro sin regla).

Comportamiento: con regla, el panel manda `regimen: null` (lo deriva el servidor) y solo deja marcar regímenes exentos; muestra lo que volvió como "Régimen según la regla: X", o "Marcado como (exento). Con estas dimensiones, según la regla correspondería: Y" (R3-1). Sin regla, deja elegir cualquier régimen. `regimen_propuesto` exige nota (sin contar espacios) antes de mandar nada. Frontera y confianza solo si el esquema las define. Lista "Falta para cerrar" con los motivos del 422 de cierre. 409/422 visibles.

EVIDENCIA
- RED `pnpm test -- tests/FormularioEsquema.test.tsx`, 12:32:29: `Tests 15 failed (15)`, por aserción (`Unable to find an accessible element with the role "group" and name "Dimension Alfa"`, `expected false to be true`, etc.).
- GREEN 12:33:25: `Tests 15 passed (15)`.
- Mutantes (12:33:36 a 12:33:47), todos muertos: régimen por defecto del esquema en el pedido (`expected 'rojo' to be null`, 2 fallas); nota sin `trim` (1); ignorar la regla (`conRegla = false`, 7); mostrar el régimen del pedido en vez del devuelto (2); omitir dimensiones sin valor del cuerpo (1).

## 11.7 `CodificacionEstudioView.tsx` y `routes/interrater.tsx` - HECHA

Archivos: `src/views/estudio/CodificacionEstudioView.tsx` (nuevo), `src/views/estudio/SeccionEstudio.tsx` (nuevo, marco compartido por las dos secciones: carga de membresías, error dentro de la sección, aviso con enlace a `/interrater-admin` sin pedir datos del estudio, selector si hay varias membresías), `src/routes/interrater.tsx`, `tests/CodificacionEstudioView.test.tsx` (nuevo, 12 tests), `tests/rutasEstudio.test.tsx` (nuevo, 2 tests con el router real).

EVIDENCIA
- RED `pnpm test -- tests/CodificacionEstudioView.test.tsx`, 12:34:46: `Tests 12 failed (12)`, por aserción (`Unable to find role="list" and name "Ítems en tu orden"`, `Unable to find role="alert"`, etc.).
- Primera corrida de GREEN 12:35:58: `3 failed | 9 passed`. Dos fallas eran del helper del test (`{...extra, [clave]: base}` hacía que la base pisara el override); corregido el orden del spread, 12:36:14: `1 failed | 11 passed`. La restante (investigador ve la administración) dependía de 11.8 y pasó en 12:41:22 (`27 passed`, junto con 11.8).
- RED ruta `pnpm test -- tests/rutasEstudio.test.tsx`, 12:36:35: `Tests 2 failed (2)` (`Unable to find an element with the text: /se usa para un estudio de codificación/`). GREEN de `/interrater` tras cambiar la ruta, 12:36:48: `1 failed | 1 passed` (la otra es de 11.6).
- Mutantes (12:37:05 a 12:37:30), todos muertos (cada uno suma una falla además de la del investigador, que en ese momento seguía roja): enlace al piloto visible a miembros; sin membresía igual pide ítems (`expected [ {…}, {…} ] to deeply equal []`); sin ordenar por posición (4); cerrar sin respetar "Cancelar"; formulario con codebook en borrador; formulario habilitado con codificación cerrada.

## 11.8 `AdministracionEstudioView.tsx` - HECHA

Archivos: `src/views/estudio/AdministracionEstudioView.tsx` (nuevo), `tests/AdministracionEstudioView.test.tsx` (nuevo, 17 tests).

Comportamiento: solo para `rol === "investigador"` (si no, `null` y ningún pedido). Secciones: Progreso (solo cantidades por alias), Membresías (asignar email y rol; revocar por email en el cuerpo, con confirmación), Codebook (versiones con estado, vigente y sha de las congeladas; crear versión vacía o clonando; cargar `.md` y esquema `.json` al borrador con errores 400 visibles y JSON inválido rechazado en el panel; congelar con confirmación; fijar vigente), Anclas de la versión vigente (con "enunciado pendiente"; alta y baja en borrador), Muestra (el `File` crudo como cuerpo + `sha256_esperado` opcional), Enunciados (CSV crudo, cobertura con faltantes e ítems afectados, filas ignoradas, aviso de bloqueo, revisión por enunciado con alertas y texto original: "Aprobar tal cual" manda `null`, "Guardar versión editada" manda el texto), Exportación (contenido y formato, descarga por `Blob`).

EVIDENCIA
- RED `pnpm test -- tests/AdministracionEstudioView.test.tsx`, 12:39:21: `Tests 14 failed | 1 passed (15)`, por aserción (`Unable to find role="heading" and name "Administración del estudio"`). El nacido verde ("a un codificador no le renderiza nada") se acreditó con mutante.
- GREEN 12:41:12: `1 failed | 26 passed (27)` (con la vista de codificación): la consulta `/Prof\. Perez/` encontraba el texto en el `<pre>` del original y en el `<textarea>`; acoté la consulta al `<pre>`. 12:41:22: `Tests 27 passed (27)`.
- Mutantes (12:41:33 a 12:41:50): muertos 5 de 6: renderizar para cualquier rol; muestra decodificada a texto (la salida muestra que la decodificación **perdió el BOM**: `expected 'estrato,origen,...' to be File{...}`); aprobar mandando el original en vez de `null`; alertas sin detalle; enunciados decodificados a texto.
- Sobreviviente: congelar sin `if (!ok) return`. Hueco real (no había caso "Cancelar"). Test nuevo "congelar cancelado no manda nada", acreditado con ese mutante (12:42:07): `expected true to be false`, 1 failed. El mismo hueco existía en revocar: mutante sobreviviente (12:42:10, `16 passed`); test nuevo "revocar cancelado no manda el DELETE", acreditado (12:42:25): 1 failed. GREEN final 12:42:29: `Tests 17 passed (17)`.

## 11.6 `EntrenamientoEstudioView.tsx` y `routes/entrenamiento-recalibracion.tsx` - HECHA

Archivos: `src/views/estudio/EntrenamientoEstudioView.tsx` (nuevo), `src/routes/entrenamiento-recalibracion.tsx`, `tests/EntrenamientoEstudioView.test.tsx` (nuevo, 10 tests).

Comportamiento: codebook vigente con `MarkdownRenderer`, marca "Borrador" o sha256 si está congelado; estados vacíos (sin codebook; sin ejemplos ni práctica); ejemplos con traza ciega, régimen y dimensiones esperadas y explicación; práctica a ciegas con devolución recién después de responder (régimen derivado contra esperado, "coincide" / "no coincide"); aviso y enlace al piloto para docentes sin membresía (vía `SeccionEstudio`); texto explícito "no es obligatorio" y ningún umbral.

EVIDENCIA
- RED `pnpm test -- tests/EntrenamientoEstudioView.test.tsx`, 12:43:12: `Tests 9 failed (9)`, por aserción.
- GREEN 12:43:57: `Tests 9 passed (9)`. Ruta: `pnpm test -- tests/rutasEstudio.test.tsx`, 12:44:05: `Tests 2 passed (2)`.
- Mutantes (12:44:15 a 12:45:15): el primero (devolución inventada antes de responder) rompió el render y no mide nada: descartado y reemplazado por "Esperado" visible antes de responder, muerto (12:45:04). Marca de borrador ausente: muerto. Comparación contra `regimen_propuesto`: **sobrevivió** porque el único caso era "no coincide"; test nuevo "coincide cuando el regimen de la regla es el esperado, aunque haya propuesto otro" (GREEN 12:44:47, `10 passed`) y el mutante lo mata (12:45:01). Dimensiones esperadas sin valor: un primer intento con patrón cortado dio error de compilación ("no tests") y no cuenta; repetido con el patrón completo, muerto (12:45:15, 2 fallas).

## 11.9 Retiro del piloto - HECHA

Archivos: borrados `src/views/InterraterTraining.tsx`, `src/views/InterraterCodingView.tsx`, `src/views/interraterShared.tsx` (copia en `scratchpad/constructor-C/borrados/`, fuera del repo); `src/utils/helpContent.tsx` (`interraterCoding` reescrita sin reglas de clasificación, `estudioEntrenamiento` nueva, sin tildes, con el patrón del skill y las clases que ya usa el archivo); `tests/sinEntrenamientoPiloto.test.ts` (nuevo, 3 tests); `tests/helpContent.coverage.test.ts` (ahora recorre subcarpetas de `views/`); `tests/navegacionAlcanzable.test.ts` (motivos de `kappa` e `interrater-admin` corregidos y test nuevo de la puerta de `/interrater-admin`).

EVIDENCIA
- RED centinela `pnpm test -- tests/sinEntrenamientoPiloto.test.ts`, 12:45:59: `Tests 2 failed | 1 passed (3)`, por aserción: 10 hallazgos, todos en `views/InterraterTraining.tsx` ("la trampa", "sobreuso manda", "si ves que sobreusa" y los 7 `episode_id`), y `la ayuda menciona "delegacion pasiva"`.
- RED cobertura de ayuda (recursiva) `pnpm test -- tests/helpContent.coverage.test.ts`, 12:46:08: `1 failed | 1 passed`, falta `"key": "estudioEntrenamiento"` (referenciada en `views/estudio/EntrenamientoEstudioView.tsx`; el test de un solo nivel no la veía).
- GREEN tras borrar y reescribir, `pnpm test -- tests/sinEntrenamientoPiloto.test.ts tests/helpContent.coverage.test.ts`, 12:46:29: `Tests 5 passed (5)`.
- `navegacionAlcanzable` 12:46:55: `Tests 5 passed (5)`. El motivo viejo de `kappa` ("se llega desde Codificacion") era falso: `rg` sobre `src/` no encuentra ningún enlace a `/kappa` (tampoco desde las vistas viejas). Motivo nuevo: se abre por URL.
- Mutantes (12:46:57 a 12:47:02), todos muertos: enlace del aviso a otra ruta (la puerta de `/interrater-admin`: `expected 0 to be greater than 0`); "Delegacion pasiva" de vuelta en la ayuda; "la trampa" en un comentario de otro archivo de `src/` (el centinela recorre todo `src/`).
- Mutante sobre la versión recursiva de la cobertura de ayuda: no corrido; su RED (12:46:08) ya muestra que detecta la key faltante en una subcarpeta.

## 11.10 Lint, tipos y build - HECHA

EVIDENCIA
- `pnpm turbo lint typecheck --filter @platform/web-teacher`, 12:47:11: lint falló con 9 errores de **formato** de biome, todos en archivos que toqué (`estudioApi.ts`, `main.tsx`, `helpContent.tsx` y los 6 de `views/estudio/`). Corregidos con `pnpm exec biome check --write` solo sobre esos archivos (`Fixed 9 files`).
- Reejecución 12:47:22: `Tasks: 2 successful, 2 total`; biome `Checked 88 files ... No fixes applied`; `tsc --noEmit` limpio.
- `pnpm --filter @platform/web-teacher build`, 12:47:37 a 12:47:50: `✓ built in 5.29s`. Aviso de chunk mayor a 500 kB (`index-*.js 543.98 kB`). `routeTree.gen.ts` sin cambios (sha256 `c5e380e3...dcd` antes y después); `dist/` y `*.tsbuildinfo` ignorados por git.
- Suite completa sobre la revisión entregada (después del formato), `cd apps/web-teacher && pnpm test`, 12:48:00 a 12:48:10: `Test Files 50 passed (50)`, `Tests 649 passed (649)`. Delta contra la base: +11 archivos y +137 tests = estudioApi 37 + diffLineas 9 + accesoPanel 12 + rootModoRestringido 5 + TrazaCiega 14 + FormularioEsquema 15 + CodificacionEstudioView 12 + rutasEstudio 2 + AdministracionEstudioView 17 + EntrenamientoEstudioView 10 + sinEntrenamientoPiloto 3 (= 136) + 1 nuevo en navegacionAlcanzable.
- Em dashes: `rg "—"` sobre archivos nuevos y líneas agregadas, sin resultados.

## Contrato HTTP asumido (para reconciliar con los constructores de backend)

Lo tomé de design D3 a D14 y de tasks; donde el plan no fija la forma, la elegí yo. **Nada de esto está verificado contra backend** (no existía al construir). Rutas relativas a `/api/v1/interrater/estudios`:

| Función | Método y ruta | Cuerpo / respuesta asumidos |
|---|---|---|
| `misMembresias` | GET `/mis-membresias` | `[{clave, titulo, rol, cerrada}]` |
| `crearEstudio` | POST `` | `{clave, titulo}` |
| `asignarMembresia` | POST `/{clave}/membresias` | `{email, rol}` |
| `revocarMembresia` | DELETE `/{clave}/membresias` | `{email}` en el cuerpo (no en la URL) |
| `listarVersiones` | GET `/{clave}/codebook` | `[{etiqueta, estado, contenido_sha256, congelada_at, vigente}]` |
| `crearVersion` | POST `/{clave}/codebook` | `{etiqueta, clonar_de}` |
| `editarVersion` | PUT `/{clave}/codebook/{etiqueta}` | `{contenido_md, esquema}`; 400 con `detail` lista FastAPI |
| `congelarVersion` | POST `/{clave}/codebook/{etiqueta}/congelar` | |
| `fijarVigente` | POST `/{clave}/codebook/{etiqueta}/vigente` | |
| `codebookVigente` | GET `/{clave}/codebook/vigente` | `{etiqueta, estado, contenido_md, esquema, contenido_sha256}`; sin vigente: 404 con `detail` `sin_codebook` |
| `traza` | GET `/{clave}/items/{item_id}/traza` | `{traza_version, enunciado: {tp_md, ejercicio_md}, elementos: [{n, tipo, t_seg, k, datos}]}`; `tipo` en `inicio, lectura, mensaje_alumno, respuesta_tutor, codigo, ejecucion, prueba, nota, copia, pegado, fin_cerrado, fin_abandonado`; `datos` con los campos de la lista blanca de D4 |
| `misItems` | GET `/{clave}/items` | `[{item_id, posicion, estado: sin_empezar/parcial/completa}]` |
| `cargarMuestra` | POST `/{clave}/muestra[?sha256_esperado=]` | cuerpo crudo `text/csv`; `{items, sha256}` |
| `cargarEnunciados` | POST `/{clave}/enunciados` | cuerpo crudo `text/csv`; `{cobertura, ignoradas: [{tipo, id}]}` |
| `enunciados` | GET `/{clave}/enunciados` | `{cobertura: {requeridos, cargados, revisados, faltantes: [{tipo, id, items_afectados}]}, enunciados: [{id, tipo, fuente_id, contenido_original_md, contenido_mostrado_md, alertas, revisado}]}` |
| `revisarEnunciado` | POST `/{clave}/enunciados/{id}/revision` | `{contenido_mostrado_md: string \| null}` (`null` = aprobar tal cual) |
| `anclas` / `crearAncla` / `borrarAncla` | GET, POST `/{clave}/codebook/{etiqueta}/anclas`; DELETE `.../anclas/{item_id}` | ancla `{item_id, episode_id, uso, orden, respuesta_esperada, explicacion_md, consensuado_por, enunciados_listos}` |
| `miEtiqueta` / `guardarMiEtiqueta` | GET / PUT `/{clave}/items/{item_id}/mi-etiqueta` | pedido `{respuestas, regimen, regimen_propuesto, es_frontera, confianza, notas}`; respuesta igual más `regimen_regla` y `updated_at`; ítem nunca guardado: 404 |
| `cerrarMiCodificacion` | POST `/{clave}/mi-codificacion/cerrar` | 422 con `detail: {codigo: "incompleta", faltantes: [{item_id, posicion, motivos}]}` |
| `progreso` | GET `/{clave}/progreso` | `[{alias, completos, parciales, con_regimen_propuesto, cerrada, revocada}]` |
| `entrenamiento` | GET `/{clave}/entrenamiento` | `{codebook \| null, ejemplos: [{item_id, orden, respuesta_esperada, explicacion_md}], practicas: [{item_id, orden}]}` |
| `responderPractica` | POST `/{clave}/entrenamiento/{item_id}/respuesta` | `{regimen, regimen_regla, regimen_propuesto, esperada, explicacion_md}` |
| `exportar` | GET `/{clave}/exportacion?contenido=&formato=` | texto CSV o JSON |

Códigos de error que el panel interpreta (`detail` string o `{codigo}`): `evidencia_alterada`, `traza_version_distinta`, `enunciado_pendiente`, `enunciados_pendientes` (los cuatro del plan) y tres que elegí yo: `sin_codebook`, `codebook_borrador`, `codificacion_cerrada`. Sin código conocido, el panel muestra `formatApiError` (o un genérico en la traza).

## JUICIO

- Autor: constructor C. Comparación: implementación entregada contra tasks 11.1 a 11.10, design D4, D9, D13, D14 y las specs de acceso, traza, codificación, codebook y entrenamiento. Confianza: alta en que las diez tareas cumplen su verificación declarada; media en la integración con el backend, por el contrato asumido.
- El panel nunca calcula el régimen ni lee campos fuera de la lista blanca, y no muestra hora absoluta, ids ni JSON crudo al codificador. El codificador ve los ítems por posición; el `item_id` solo viaja en las rutas.
- Muestra y enunciados se suben como `File` (bytes exactos). El mutante que decodifica a texto demostró la pérdida del BOM; con texto decodificado, un CSV con BOM daría 422 por hash.
- Respuesta esperada de las anclas: se carga como JSON en un textarea (pantalla solo del investigador). Es funcional pero pobre; un editor con `FormularioEsquema` sería mejor. Va como DEUDA candidata.

## SUPOSICIÓN (no verificado)

- Contrato HTTP de la tabla anterior: sin backend al construir. Si el constructor de los grupos 4 a 10 elige otras formas, hay que ajustar `estudioApi.ts` y sus tests (o el backend). Lo más sensible: forma de `elementos` de la traza, `GET /codebook/vigente` como ruta literal (choca con `/{etiqueta}` si alguien crea una versión llamada `vigente`), DELETE de membresía con cuerpo y la forma del 422 de cierre.
- `main.tsx` (componente `InnerApp`) no tiene test que monte la app con Clerk; su lógica está en `consultarAcceso` (probada). Que en producción el usuario con membresía y sin comisiones entre en modo restringido depende además del comportamiento real del gateway y de Clerk: queda para el recorrido humano.
- La vista restringida usa `window.location.pathname` para el item activo del sidebar, igual que el layout completo; no verifiqué el resaltado bajo el basepath `/teacher` en navegador.
- Lint de base no corrido antes de cambiar archivos; los 9 errores de formato estaban todos en archivos que toqué, así que los atribuyo a mis cambios.
- Aviso de chunk mayor a 500 kB en el build (`index-*.js`): no comparé con la base ni inspeccioné qué módulos entran en ese chunk; lo supongo previo porque las rutas del estudio se cargan en chunks propios (`interrater-*.js` aparece aparte), pero no está verificado.
- No pasé por los gates de la skill `impeccable` (shape brief confirmado con el humano): como subagente no puedo pedir esa confirmación. Seguí `PRODUCT.md`, `DESIGN.md` y los patrones existentes (`PageContainer`, `HelpButton`, `useConfirm`, `MarkdownRenderer`). El microcopy queda para el recorrido (design, Open Questions).
- No ejecuté nada en navegador real; todo lo de UI está verificado en jsdom.

## Chequeos no ejecutados

- Suite Python y tests de integración: fuera de mi alcance (tanda A y siguientes).
- Recorrido en navegador y con Clerk real: fuera de la fase.
- `make test-smoke`: corresponde a 13.1.

## DEUDA candidata (para el orquestador; no bloquea 11.x)

- `src/lib/api.ts` conserva `getInterraterSample`, `saveInterraterRating` y `getInterraterProgress`, que quedaron sin consumidores en el web-teacher (los endpoints del piloto siguen vivos en el backend). No los borré para no ampliar el alcance. Destino sugerido: el primer change que toque `api.ts` en esa zona.
- Editor de respuesta esperada de anclas con el formulario del esquema en vez de JSON (ver JUICIO). Destino: el change que use las anclas en producción, antes de cargar el v0.
- `/kappa` no tiene puerta en ninguna pantalla (motivo corregido en `navegacionAlcanzable`, pero sigue accesible solo por URL). Preexistente.

## Archivos tocados (todos bajo `apps/web-teacher/`)

- Nuevos: `src/lib/estudioApi.ts`, `src/utils/accesoPanel.ts`, `src/utils/diffLineas.ts`, `src/views/estudio/{TrazaCiega,FormularioEsquema,CodificacionEstudioView,AdministracionEstudioView,EntrenamientoEstudioView,SeccionEstudio}.tsx`, `src/views/estudio/mensajesError.ts`; tests `tests/{estudioApi,diffLineas,accesoPanel,sinEntrenamientoPiloto}.test.ts`, `tests/{rootModoRestringido,TrazaCiega,FormularioEsquema,CodificacionEstudioView,rutasEstudio,AdministracionEstudioView,EntrenamientoEstudioView}.test.tsx`.
- Modificados: `src/lib/api.ts` (dos `export`), `src/main.tsx`, `src/routes/__root.tsx`, `src/routes/interrater.tsx`, `src/routes/entrenamiento-recalibracion.tsx`, `src/utils/helpContent.tsx`, `tests/helpContent.coverage.test.ts`, `tests/navegacionAlcanzable.test.ts`.
- Borrados: `src/views/InterraterTraining.tsx`, `src/views/InterraterCodingView.tsx`, `src/views/interraterShared.tsx`.

## Reconciliación (contrato del front contra el backend real), 04/11/2026 13:27 a 13:35

Pedido del orquestador: ajustar `estudioApi.ts`, las vistas y sus tests a las diferencias de `informes/apply-1-constructor-B.md` (líneas 111 a 129), tomando el backend como fuente de verdad, con TDD, sin tocar `apps/classifier-service`.

Fuentes leídas en esta ronda: `apply-1-constructor-B.md` líneas 60 a 135 (decisiones de interpretación, meta-esquema y tabla de diferencias); código real de `apps/classifier-service/src/classifier_service/routes/estudio.py` (schemas `EstudioOut`, `MembresiaOut`, `RevocacionOut`, `MiMembresiaOut`, `VersionIn/Edicion/Out`, `VigenteIn`; handlers de revocar, editar versión, vigente, `GET /membresias`, `GET /codebook/versiones[/{etiqueta}]`), `routes/estudio_trabajo.py` (items, enunciados, `etiqueta_out`, cierre, progreso, anclas, entrenamiento, responder, `_conflicto` y los `detail={"codigo": ...}`), `services/estudio_esquema.py::faltantes_cierre` y `services/estudio_enunciados.py::cobertura`. Contaminación: la tabla de B orientó qué mirar; cada diferencia la verifiqué contra el código antes de escribir el test, y encontré dos más que la tabla no lista (filas 13 y 14).

Revisión entregada: `HEAD b32e621` + árbol sin commitear; huella de `apps/web-teacher/` (lista `sha256sum` de cada archivo tocado, hasheada) = `90b3c1d36018056e11c8414e1cbe1ca8e53b897e53b9eed0487fc4d2c215d122` (lista en `scratchpad/constructor-C/huella-reconciliacion.txt`). Índice de git vacío. No se tocó `apps/classifier-service` (los cambios que muestra `git status` ahí son de los otros constructores).

### Evidencia por diferencia

| # | Diferencia (verificada en el código) | Test RED (comando, hora, salida) | Cambio | GREEN | Mutante |
|---|---|---|---|---|---|
| 1 | Revocar: `DELETE /{clave}/membresias/{membresia_id}` sin cuerpo; ids desde `GET /{clave}/membresias` | `pnpm test -- tests/estudioApi.test.ts` 13:27:44: `expected '.../membresias' to be '.../membresias/mem-1'`; listar membresías: `expected '(sin fetch)'`. Vista: `pnpm test -- tests/AdministracionEstudioView.test.tsx` 13:30:42: `Unable to find [data-testid="membresia-m-2"]` (3 tests) | `estudioApi.listarMembresias`, `revocarMembresia(clave, membresiaId)`; la administración lista email, rol, alias y estado, y ofrece "Revocar <alias>" solo en no revocadas, con confirmación | 13:28:09 `45 passed`; 13:31:13 `20 passed` | cuerpo en DELETE (13:28:41, `expected '{"membresiaId":"mem-1"}' to be undefined`); botón en revocadas (13:31:32); revocar por email (13:31:36); sin `if (!ok)` (13:31:42): todos muertos |
| 2 | Versiones en `GET /{clave}/codebook/versiones` | 13:27:44: `expected '.../codebook' to be '.../codebook/versiones'` | ruta | 13:28:09 | cubierto por la ruta exacta del test |
| 3 | `PUT /{clave}/codebook-vigente` con `{etiqueta}` | 13:27:44: ruta distinta; cuerpo: `"undefined" is not valid JSON` (excepción, no cuenta como RED) | método, ruta y cuerpo | 13:28:09 | `{version: etiqueta}` (13:28:27): `expected { version: 'v1' } to deeply equal { etiqueta: 'v1' }` |
| 4 | 400 del esquema: `detail: {mensaje, errores: [str]}` | `pnpm test -- tests/mensajesError.test.ts` 13:29:18: `expected 'Error: 400: {"mensaje":"Esquema invál…' not to contain '{'` | `mensajesError.ts` muestra `mensaje` y cada error, nunca el JSON | 13:29:35 / 13:30:11 (`12 passed`) | ver fila 10 |
| 5 | `mi-etiqueta` nunca guardada: 200 con etiqueta vacía (404 = ítem inexistente) | `pnpm test -- tests/CodificacionEstudioView.test.tsx` 13:32:11: `Unable to find an element with the text: /Ítem inexistente/` | el 404 ya no se trata como ítem vacío: es error y no se ofrece formulario | 13:32:52 `15 passed` | volver a tratar 404 como vacío (13:33:09): muerto. El caso "200 vacío" nació verde (el formulario ya tolera `notas: null`); mutante `notas ?? "x"` (13:33:18): `expected 'x' to be ''` |
| 6 | `notas: string \| null`; `disiente_de_regla` extra | `pnpm test -- tests/EntrenamientoEstudioView.test.tsx` 13:33:32: con `respuesta_esperada.notas: null` el ejemplo se rompe (`Unable to find [data-testid="ejemplo-an-e"]`) | tipos `notas: string \| null` y `disiente_de_regla?`; `(esperada.notas ?? "").trim()` | 13:33:45 `12 passed` | `(notas as string).trim()` (13:34:04): muerto |
| 7 | 422 de cierre con `faltan` y motivos como CÓDIGOS (`regimen`, `dimension:<clave>`, `cita:<clave>`, `notas`, `confianza`, `sin_etiqueta`) | 13:32:11: `expected 'Faltan 2 ítems…' to contain 'Ítem 2: régimen, valor de Dimension A…'` | `describirMotivo` traduce cada código con el nombre de la dimensión del esquema, en el aviso del cierre y en la lista "Falta para cerrar" del formulario | 13:32:52 | `dimension:` sin traducir (13:33:05): muerto |
| 8 | Enunciados: `cobertura.sin_revisar`; `sha256_original/mostrado` | 13:30:42: `Unable to find … /Sin revisar tp tp-1 · 12 ítems afectados/` | tipos; la cobertura lista también los cargados sin revisar (bloquean igual) | 13:31:13 | lista vacía en lugar de `sin_revisar` (13:31:46): muerto |
| 9 | Devolución de práctica trae `coincide` | 13:33:32: con régimen derivado y esperado ambos `null`, el front decía "coincide": `expected '… sin régi…' to match /no coincide/` | la vista usa `devolucion.coincide` del servidor | 13:33:45 | volver a comparar en el front (13:34:01): muerto |
| 10 | Códigos de error nuevos (409 string: `enunciado_revisado`, `episodio_es_ancla`, `episodio_en_muestra`, `muestra_con_etiquetas`, `version_congelada`, `ancla_con_respuestas`; 422 `{codigo, errores?}`: `sha256_distinto`, `csv_invalido`, `episodios_invalidos`, `pedido_invalido`, `episodio_inexistente`, `episodio_no_terminado`) | 13:29:08: 7 failed. Tres nacieron verdes por coincidencia (el código crudo contenía "ancla", "muestra", "congelada") y uno porque el JSON crudo contenía el texto; endurecí las aserciones a la frase real y "sin `{`". 13:29:18: `11 failed \| 1 passed` | `mensajesError.ts`: mensaje por código + lista de `errores`; nunca el detail como JSON | 13:29:35 (con un ajuste de mayúscula en mi propia regex de `muestra_con_etiquetas`); `12 passed` | cubierto por las aserciones de frase y "sin `{`" |
| 11 | `PUT /{clave}/codebook/{etiqueta}/anclas/{item_id}` | 13:27:44: `expected '(sin fetch)'`; cuerpo: excepción `JSON.parse` | `estudioApi.editarAncla` (solo campos cambiados) | 13:28:09 | `{orden: 0, ...cambios}` (13:28:29): muerto |
| 12 | Choque `/codebook/vigente` contra `/{etiqueta}` | sin cambio: B indica que `vigente` y `versiones` son etiquetas reservadas (422 al crearlas). No lo verifiqué en el código | ninguno | n/a | n/a |
| 13 | **No listada por B**: el meta-esquema real deja opcionales `regimenes_exentos`, `dimensiones_opcionales_si_regimen`, `notas_obligatorias_si_regimen`, `marca_frontera`, `notas_obligatorias_si_frontera`, `confianza`, `reglas_regimen` y `regimen_por_defecto`, y el backend guarda el esquema tal como se cargó. El formulario leía esas claves sin default (`esquema.reglas_regimen.length`, `esquema.confianza !== null`): con un esquema mínimo, la vista de codificación se rompía | 13:27:44: `normalizarEsquema` `expected {…(2)} to deeply equal {…(10)}`; `codebookVigente` `expected undefined to deeply equal []` | `normalizarEsquema` completa los defaults del backend; `codebookVigente` y `entrenamiento` devuelven el esquema normalizado. Agregué `notas_obligatorias_si_frontera` al tipo | 13:28:09 | conservar exentos/confianza propios (13:28:32, 13:28:35); `null` sigue `null` (13:28:51; el primer intento murió por excepción y lo rehice). Caso integrado "esquema mínimo se renderiza" (nació verde porque la API ya normalizaba): sin normalizar en `codebookVigente` (13:33:13) `Unable to find role="group"`: muerto |
| 14 | **No listada por B**: motivos del cierre como códigos | ver fila 7 | | | |

Todos los mutantes quedaron revertidos (`REVERTIDO OK`). Sin esqueletos en la entrega.

### Corridas finales (sobre la revisión reconciliada, después de biome)

- `pnpm exec biome check --write src/lib/estudioApi.ts src/views/estudio/` (13:34): `Fixed 2 files` (solo formato).
- `pnpm turbo lint typecheck --filter @platform/web-teacher`, 13:34:17: `Tasks: 2 successful, 2 total`.
- `pnpm --filter @platform/web-teacher build`, 13:34:25 a 13:34:40: `✓ built in 6.19s`.
- `cd apps/web-teacher && pnpm test`, 13:34:40 a 13:34:54: `Test Files 51 passed (51)`, `Tests 677 passed (677)`. Delta contra la entrega anterior (50/649): +1 archivo (`mensajesError.test.ts`, 12) y +28 tests (estudioApi +8, mensajesError +12, Administración +3, Codificación +3, Entrenamiento +2).

### Lo que exigiría tocar el backend (NO cambiado; para el orquestador)

JUICIO del constructor C, por lectura del código, sin reproducir contra Postgres. Confianza media.

- **Ninguna diferencia es insegura.** La revocación por id y el listado con email solo para investigador o administrador son coherentes con D3.
- **Cierre con muestra vacía**: `cerrar` responde 422 `incompleta` con `faltan: 0, faltantes: []` cuando no hay ítems (`if faltantes or not item_ids`). El panel muestra "Faltan 0 ítems para poder cerrar". Sugerencia: un código propio (`muestra_vacia`) o el 409 que corresponda. Severidad MENOR; hoy no es alcanzable desde la UI porque sin muestra la lista está vacía, pero el botón de cierre se muestra igual.
- **Detalles de 409/404 como texto libre**: en `routes/estudio.py`, "Versión congelada", "Hay etiquetas del estudio: la versión vigente no se cambia", "Versión inexistente" y "Estudio inexistente" son frases y no códigos, a diferencia de `estudio_trabajo.py`. El panel las muestra tal cual (legibles), pero no puede distinguirlas por código. Sugerencia: unificar con `_conflicto`. MENOR.
- `faltan` es redundante con `len(faltantes)`. El front usa la lista; sin acción.

### DEUDA candidata nueva

- Edición de anclas en la UI: la API ya tiene `editarAncla`, pero la administración solo ofrece alta y baja. Destino: el change que cargue las anclas del v0 (junto con el editor de respuesta esperada ya anotado).
- Ver una versión no vigente con sus anclas (`GET /codebook/versiones/{etiqueta}`): sin función en el front. Destino: el mismo.

### SUPOSICIÓN

- Las formas de respuesta se verificaron por lectura del código del router, no con una llamada real; no hay test de integración front-back.
- La fila 12 (etiquetas reservadas) la tomé del informe B sin verificarla en el código.
