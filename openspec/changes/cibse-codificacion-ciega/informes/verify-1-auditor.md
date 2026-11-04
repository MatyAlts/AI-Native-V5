# verify-1-auditor: auditor final, intento 1

- Change: `cibse-codificacion-ciega`. Rol: auditor (fase verify). Nivel CRITICAL, aprobado por el humano el 04/11/2026 (proposal.md, `## Aprobación`).
- Ejecutor: subagente nativo de Claude Code (familia Anthropic, la misma que todos los roles previos). Sin independencia por proveedor; la independencia de este informe es de ejecución (corridas, conteos y mutantes propios).
- Fecha: 04/11/2026, 14:54 a 15:01 (-03:00).
- Revisión auditada: árbol sobre HEAD `b32e621` (= origin/main), rama `feat/cibse-codificacion-ciega`, sin commits. Huella recalculada con `scratchpad/hash-arbol.sh` (excluye la carpeta del change):
  - 14:54:08 `HEAD=b32e621 diff_HEAD_sha256=d4e664d02f90ea5a14ccfc3187389638300fd01f9b78feaa6646ad4b2ba84216 untracked_n=59 untracked_list_sha256=62de33cf8563b29fe392225de3bb654accf985607ebd36b2d805da1c395745be arbol=50fadc6b8a034547`
  - Repetida después de cada mutante propio (14:58:13, 14:58:32, 15:00:07): `arbol=50fadc6b8a034547`. **Coincide con la del brief: la evidencia del constructor F (apply-3) y del breaker 3 es fresca.**
- Lecciones L-NNN: no existen en el repo (declarado en tasks.md por el orquestador y por los constructores A y C con búsqueda propia). Ruta leída: ninguna.
- No edité código, plan ni informes ajenos. Los dos mutantes propios se aplicaron con respaldo, se revirtieron y se cotejaron con `cmp`.

## Veredicto

**BLOQUEANTES** (2). Ninguno es un defecto de código: el código y las pruebas pasan la auditoría. Lo que impide APROBADO es el gate humano de CRITICAL y una contradicción con el texto de la aprobación humana.

| # | Bloqueante | Responsable | Cómo se levanta |
|---|---|---|---|
| B-1 | Recorrido humano con Clerk real no ejecutado. Es requisito CRITICAL para archivar (proposal, Clasificación; tasks.md, Workflow follow-up). Sin recorrido no hay rutas visitadas ni no visitadas que clasificar. | humano (Juani) con el orquestador | Recorrido con la cuenta real según la lista de tasks.md (Workflow follow-up). Lo no recorrido pasa a DEUDA. Si el árbol no cambia, el auditor reaudita solo ese punto |
| B-2 | El texto de la aprobación humana dice: "La 1 (consentimiento) queda pendiente con Alberto y bloquea dar de alta a los codificadores". En cambio, proposal.md P1 y tasks.md (líneas 25, 45 y 421) dicen "codificadores **externos**" y "solo después de responder la pregunta 1 **si alguno es externo** al equipo". El plan reduce lo que el humano bloqueó. | orquestador (artefactos) | Alinear P1 y el follow-up con el texto literal de la aprobación, o preguntarle a Juani y registrar su respuesta fechada. No inventar una tercera versión |

## EVIDENCIA (corridas propias, árbol `50fadc6b8a034547`)

| Hora (-03:00) | Comando | Resultado |
|---|---|---|
| 14:54:08 | `bash scratchpad/hash-arbol.sh` | `arbol=50fadc6b8a034547` (igual al brief) |
| 14:55:15 a 14:56:00 | `CLASSIFIER_TEST_DB_URL=...@127.0.0.1:55432/classifier_db CLASSIFIER_TEST_MIGRATION_CYCLE=1 uv run pytest apps/classifier-service -q -rs` | `4 failed, 708 passed`, sin skips. Los 4: `test_precheck_mas_gobernanza_bajo_el_router_completo`, `test_dos_revisiones_concurrentes_no_pierden_la_primera`, `test_segunda_revision_tras_commit_de_la_primera_no_pisa`, `test_conflicto_contra_reclasificacion_automatica_sugiere_reintentar`, todos `InvalidPasswordError` contra el 5432 ajeno. Sus archivos fijan `127.0.0.1:5432` (línea 40 y 56) y no tienen diff contra HEAD (`git diff --quiet`). Log: `scratchpad/auditor-classifier.log` |
| 14:56:16 | mismos tests, solo los del estudio (14 `_db` + 7 unitarios) | `474 passed`. Conteo por archivo con `--collect-only`: integración 262 (acceso 37, anclas 28, codebook 35, concurrencia 6, entrenamiento 11, enunciados 14, etiquetas 24, exportación 11, inmutabilidad 34, muestra 22, panel 10, schema 9, separación 1, traza 20); unitarios 212 (codebook 6, enunciados 35, esquema 94, export 13, orden 5, traza_ciega 17, ctr_lectura 42). Cierre: base 238 (224 + 4 + 10 errores) + 474 = 712 = 708 + 4 |
| 14:55:16 a 14:55:27 | `cd apps/web-teacher && pnpm test` | `51 passed` archivos, `687 passed` tests |
| ~14:55:40 | vitest de los 12 archivos del estudio | `174 passed`: Administración 25, Codificación 18, Entrenamiento 12, FormularioEsquema 15, TrazaCiega 14, accesoPanel 12, diffLineas 9, estudioApi 45, mensajesError 14, rootModoRestringido 5, rutasEstudio 2, sinEntrenamientoPiloto 3 |
| ~14:55:45 | `python3 scripts/check-claude-md.py -v` | `[OK] Smoke tests E2E: 63`, `[OK] ADRs numerados: 63`, `[OK] 3 claims verificados, 2 skip, sin drift` |
| idem | `rg -c '^(async )?def test_' tests/e2e/smoke/test_smoke_estudio_codificacion.py` | `6` (63 = 57 de HEAD + 6) |
| 14:58:00 | `ruff check` / `ruff format --check` (classifier + smoke nuevo); `mypy apps/classifier-service/src`; `pnpm turbo lint typecheck --filter @platform/web-teacher` | `All checks passed!` / `94 files already formatted` / `Success: no issues found in 39 source files` / `Tasks: 2 successful` |
| 14:58:32 | **Mutante propio 1**: `require_membresia` sin `membresia.rol not in roles`; acceso, exportación, codebook, muestra y panel | `5 failed, 110 passed`, todos por aserción (`assert 201 == 403`, `200 == 403`): codificador asigna membresías, exporta, gestiona codebook, carga muestra y lista membresías. Revertido, `cmp` OK |
| 15:00:07 | **Mutante propio 2**: `intento_adverso_detectado` agregado a `TIPOS_INCLUIDOS`; `tests/unit/test_traza_ciega.py` | muerto por aserción: `'overuse' not in ...`, `[1..6] == [1..5]`, conjunto exacto y decisión explícita de tipos. Revertido, `cmp` OK |
| 14:57:31 | `motivos_ancla_para_congelar` con un ancla que usa `d1` contra un esquema con `d1_nueva` | `["respuestas: dimensión desconocida 'd1'"]`, y lo mismo sin el prefijo. La edición de un ancla devolvería ese texto en `faltantes`, no un código de completitud (ver DEUDA D-6) |
| 14:59:43 | `openspec validate cibse-codificacion-ciega --strict` | `Change 'cibse-codificacion-ciega' is valid` |
| varios | `git diff HEAD --stat` y `git ls-files --others` | 17 archivos con seguimiento, todos en classifier-service, web-teacher, `CLAUDE.md` y `docs/`. Sin diff en tutor-service, ctr-service, academic-service, api-gateway, analytics-service, web-student, web-admin, `packages/`, `.github/`, `infrastructure/` ni `Makefile`. Sin seguimiento ajenos: `openspec/config.yaml` y `scripts/backfill-attestations.py`, ambos con mtime 2026-10-01 15:21 (anteriores al change); el segundo viene del commit `43c605c` de otra rama |
| varios | diff de `services/pipeline.py`, `event_labeler.py`, `routes/health.py`, `test_pipeline_reproducibility.py` | 0 líneas. `LABELER_VERSION = "1.3.0"`; golden `56f39058...1180` en su lugar y en verde dentro de la suite |
| varios | cotejo del incidente de proposal.md | `scratchpad/proposal-roto.md` (11:48) y el respaldo `respaldo-plan-cibse-1215/proposal.md` (12:15) coinciden en las líneas 1 a 53, y la aprobación es idéntica byte a byte a la línea 88 actual. Contra el respaldo de las 12:15, proposal solo cambió en Impact y KB Impact (A4-3, constructor D). `design.md`, sin cambios desde la aprobación. Specs: 62 líneas de diferencia, las de verify-2 y verify-3 del planner |
| varios | `.github/workflows/ci.yml` (job de tests) y `e2e-smoke.yml` | CI corre `apps/*/tests/unit/`, no `apps/classifier-service/tests/integration/`. **Corrección a lo declarado**: el workflow `E2E Smoke`, que corre en cada PR a main, ejecuta `scripts/migrate-all.sh`, que incluye classifier. Así que el `upgrade` de la 0007 y los 6 smoke del estudio sí corren en CI; no corren el downgrade, los triggers ni los 262 tests `_db` |

## Cobertura declarada contra escenarios de spec

- Las specs tienen 6 capacidades, 53 requisitos y 158 escenarios (`rg '^#### Scenario'`). Los escenarios de F1, F4, F5, N1, N2 y O1 **existen** (codebook-versionado:74-95, estudio-codificacion:217, 225-238, estudio-codificacion-acceso:61, traza-ciega-episodio:134, entrenamiento-calibracion:16-23). El breaker 3 dice que "siguen sin escenarios", pero eso quedó viejo: el planner validó a las 14:48:59, mientras el breaker trabajaba (de 14:48 a 14:53).
- Revisé por muestreo, contra los nombres de test y el código, los escenarios de seguridad y de datos: acceso por membresía, rol, atadura y revocación; ciego (lista blanca, tope, versión, IDOR por `item_id` y `episode_id`); inmutabilidad, incluido TRUNCATE; régimen según la regla; exportación; separación del piloto. Todos tienen test, y los críticos tienen mutante muerto, propio o registrado.
- **Escenario sin test directo**: estudio-codificacion "Agregado del piloto". Por construcción, `analytics.py::interrater_aggregate` lee solo `InterraterRating` filtrado por materia y protocolo (líneas 521-538), y `test_estudio_separacion_db.py` prueba con mutantes que el estudio no toca `interrater_ratings`. Lo clasifico como DEUDA de test, no como hueco de comportamiento.
- Los escenarios de UI que dependen de Clerk (codificador externo entra en modo restringido, otra cuenta con el mismo email) están probados en jsdom y en integración. En navegador con Clerk no se probaron: es B-1.

## Caminos independientes y conclusiones copiadas

- Independientes por ejecución:
  - los breakers 1 a 3 (tests temporales propios, 37, 453 y 383; fuzz; 380 rondas de concurrencia; 113 episodios reales);
  - el plan-reviewer, que reejecutó las líneas de base;
  - este informe (suite completa, conteo por archivo y 2 mutantes).
- Todos los roles son de la misma familia de proveedor: no hay independencia por proveedor, y cada informe lo declara.
- Copiado o reusado sin reejecutar, y declarado así: el planner tomó E2-8 del reviewer; los breakers 1 y 3 reusaron la suite del constructor; el planner de specs reusó el RED/GREEN registrado; el constructor C tomó la fila 12 del informe B sin verificarla. Ninguno de esos reusos sostiene una conclusión crítica que yo no haya verificado: la suite la volví a correr y las etiquetas reservadas están cubiertas por `test_estudio_acceso_db.py`.
- Diferencia no material: apply-3 registra `475 passed` para "estudio + ctr + traza" a las 14:42:51. Mi conjunto de 21 archivos da 474. La suite completa coincide (708), así que lo atribuyo a otro conjunto de archivos.

## Código crítico y reescrituras

- **Ninguno de los servicios ni de las constantes protegidas tiene diff**: tutor-service, ctr-service, academic-service, hashes de `classifier_config` y `LABELER_VERSION`.
- Cambios en código existente, todos dentro del alcance aprobado:
  - `main.py` registra dos routers;
  - `models/__init__.py` agrega un import y `__all__`; no hay `import *` del módulo en el repo;
  - `api.ts` solo agrega dos `export`;
  - `main.tsx` y `__root.tsx` agregan el modo restringido (D13);
  - se borran las tres vistas del piloto (D13, BREAKING aprobado);
  - `conftest.py` de integración toma la URL por variable, con el mismo default.
- Documentación: `docs/servicios/classifier-service.md` solo agrega líneas, ninguna borrada. En `CLAUDE.md` hay 4 reescrituras, todas declaradas en KB Impact (helpContent, conteo smoke, ADRs, rutas) más el append de dos invariantes.
- `diffLineas.ts` delega en el `lineDiff.ts` existente en vez de duplicarlo.
- No encontré reescritura innecesaria de algo existente.

## Clasificación de los puntos pedidos

| Punto | Clasificación | Justificación |
|---|---|---|
| Tests `_db` y migración 0007 fuera de CI | DEUDA (D-1) | Hoy pasan los 262 `_db` en esta revisión (corrida propia). El `upgrade` de la 0007 y el smoke del estudio sí corren en CI (e2e-smoke); faltan downgrade, triggers e integración. Propuesta concreta en apply-1-constructor-B.md §(c). Destino: change de CI propio, antes del próximo cambio a las tablas del estudio |
| Mutante del smoke sobre `intento_adverso` | DEUDA (D-2) | El seed no tiene el evento. La aserción la cubre `test_traza_ciega.py`, con mutante muerto (constructor B y mutante propio 2). Destino: el change que agregue eventos adversos al seed de CI |
| Exposición preexistente de POST `/interrater/ratings` y del agregado κ | DEUDA (D-3), fuera de alcance | Observada por lectura (planner, plan-reviewer), no reproducida. Es previa al change. El change no la amplía en capacidad, pero sí suma cuentas reales con motivo para entrar: conviene resolverla antes del alta de codificadores, junto con P1 |
| `docs/servicios/classifier-service.md` ya desactualizado | DEUDA (D-4) preexistente | Verificado: `LABELER_VERSION = "1.2.0"` en las líneas 17 y 165, y 4 apariciones de `1.2.0` en HEAD. El change no lo empeoró (solo agrega). Destino: el primer change que toque ese documento fuera del estudio |
| Sospechas S2 y S3 del breaker | DEUDA (D-5) | S2 está reproducida como comportamiento (19 lecturas al CTR siguen después del 502), sin efecto sobre datos ni sobre la spec: desperdicio. S3 no está reproducida (celdas que empiezan con LF o con espacios antes de `=`; exportación solo del investigador): queda como suposición abierta |
| `faltantes` en la edición de anclas (verify-3-planner-specs) | DEUDA (D-6), reproducida a nivel de función | Con un ancla que no valida contra el esquema, `faltantes` trae un error de validez sin prefijo, no un código de completitud. El comentario de `estudio_trabajo.py:1036-1037` ("El ancla guardada vale contra este esquema") es falso en ese caso. Congelar igual da 422: no hay daño a la referencia. La edición no tiene UI. Responsable: constructor, en el change que agregue la edición de anclas al panel |
| Recorrido humano con Clerk real | **BLOQUEANTE (B-1)** | Requisito CRITICAL antes de archivar; no ejecutado |
| Firma classifier -> ctr con la configuración real | DEUDA (D-7), verificación posterior al deploy | La lectura contra el ctr-service real local sin firma está verificada (smoke y 113 episodios). Con `REQUIRE_GATEWAY_SIGNATURE` y el secreto de producción, no. Una falla ahí da 502, no fuga. Va en el paso 2 a 4 del Migration Plan, antes de cargar la muestra real |
| P1, consentimiento | Abierta. No bloquea el archivo; bloquea el alta (decisión humana) | No es defecto. Ver B-2 sobre su alcance escrito |

## JUICIO

Autor: auditor verify-1. Comparé el plan aprobado (proposal, design, 6 specs), el árbol `50fadc6b8a034547` y los 22 informes originales con mis corridas.

- **El código cumple el plan aprobado** (confianza alta). Cada tarea de código tiene RED por aserción antes de producción (con stubs declarados y RED inválidos descartados), GREEN y mutantes sobre las aserciones de seguridad y de datos. Los nacidos verdes se acreditaron con mutantes. Las tres rondas del gate verify cerraron en LIMPIO sobre esta misma huella.
- **Decisiones del orquestador contrastadas**:
  - B-1/N-2 (régimen siempre el de la regla) está en D9, en las specs y en 3.2, con mutantes. La corrección de su instrucción previa está registrada (tasks.md:30) y la confirmó el humano (P6).
  - M-2 (evidencia de conducta) está en D4 y en la lista blanca, y P5 la confirmó el humano.
  - O1 (congelar exige anclas completas) está implementada, especificada y atacada (breaker 3). Es una decisión del orquestador dentro del alcance aprobado: no amplía servicios ni datos, endurece un control.
- **Desvío de la tanda C en paralelo**: está declarado y su riesgo se materializó dos veces. Un script de mutantes fue pisado, sin daño, porque el mutante no llegó a tocar archivos; y el contrato quedó asumido. Quedó contenido por la reconciliación con TDD y por las corridas posteriores del breaker sobre el front.
- **Incidente de proposal.md**: la aprobación sobrevivió intacta (cotejo propio). Las secciones reconstruidas (P1 a P12 y KB Impact) no las pude cotejar contra la versión previa al incidente, porque no hay copia (ver SUPOSICIÓN). El cotejo del orquestador es su palabra, no evidencia mía.
- **Muestra movida**: el breaker 1 encontró el esquema v0 en `~/Documentos/MTAC/...`. `design.md` (Context) y tasks.md:17 siguen con `~/Descargas`: DEUDA documental (D-8).
- **B-2**: la aprobación es la autoridad. Que el plan diga "externos" donde el humano no lo dijo es justo el conflicto de redacción que el workflow manda resolver explícitamente.
- **B-1**: el workflow global exige el recorrido antes de archivar, y la publicación exige un change archivado antes de pushear. Si el recorrido se planea "en producción", el ciclo no cierra. Hace falta decidir dónde se hace: un deploy de la rama con la instancia real de Clerk, sin pasar por `main`, o lo que el humano elija.

## SUPOSICIÓN (no verificado por mí)

- Que las secciones reconstruidas de proposal.md (P1 a P12, KB Impact) coinciden con las previas al incidente: no hay copia anterior a las 11:48 con esas secciones. El sha `37a59893694b` que registra propose-4-plan-reviewer no es reproducible.
- No ejecuté: `make test-smoke` (reusé el del breaker 3, 14:51:03, `100 passed, 2 skipped`, misma huella), analytics, `create_all`, `check-rls`, el ciclo de migración en base limpia (cubierto por `test_estudio_schema_db` dentro de mi corrida, sin skips), CI de GitHub, la firma real del gateway, Clerk ni producción.
- No mapeé uno por uno los 158 escenarios: el mapeo es por muestreo, dirigido a seguridad y datos.
- Que el email de Clerk es verificado: lo decide el recorrido (B-1).

## DEUDA

- D-1. Tests `_db`, triggers y downgrade de la 0007 fuera de CI. Destino: change de CI, con la propuesta de apply-1-constructor-B.md §(c).
- D-2. El smoke no discrimina `intento_adverso_detectado`. Destino: change que siembre eventos adversos en el seed de CI.
- D-3. Exposición preexistente de `POST /api/v1/interrater/ratings` y de `/api/v1/analytics/interrater/aggregate` a cualquier cuenta de Clerk. Destino: change propio, antes del alta de codificadores.
- D-4. `docs/servicios/classifier-service.md` desactualizado desde antes (LABELER_VERSION, bug de idempotencia, "6 archivos unit"). Destino: el primer change que lo toque.
- D-5. S2 (lecturas al CTR sin cancelar tras un 502) y S3 (prefijo CSV para LF o espacios; sin reproducir). Destino: change que toque la carga de muestra o la exportación.
- D-6. `faltantes` de la edición de anclas mezcla motivos de validez, y el comentario de `estudio_trabajo.py:1036-1037` es falso en ese caso. Destino: change que agregue la edición de anclas al panel (deuda de UI del constructor C).
- D-7. Firma classifier -> ctr con la configuración real. Destino: verificación posterior al deploy, antes de cargar la muestra.
- D-8. Rutas `~/Descargas` en design.md (Context) y en tasks.md:17, y líneas viejas del "Estado de orquestación" (29, 32 y 33 hablan de pasos ya cumplidos). Destino: orquestador, al cerrar.
- D-9. Escenario "Agregado del piloto" sin test directo. Destino: change de CI o el próximo que toque `interrater_aggregate`.
- Del constructor C, ya registradas: editor de respuesta esperada de anclas, edición y vista de versiones no vigentes en el panel, funciones del piloto sin consumidor en `api.ts`, `/kappa` sin puerta.
- Ajena al change, observada por los constructores E y los breakers: contenedores `eclipse-temurin` que quedan al 100 % de CPU tras `test_smoke_java_execution`. Destino: dueño de ADR-060.

## LECCIONES

- Cuando el humano aprueba con texto propio, cada restricción se propaga literal a proposal y a follow-up. Parafrasear ("externos") cambia la decisión (B-2).
- Un requisito "antes de archivar" que depende de producción choca con "push solo con el change archivado". El plan tiene que decir dónde se cumple sin romper el orden (B-1).
- Las tandas en paralelo necesitan scratchpad separado por constructor desde el despacho: el pisado de `mutar.py` fue inocuo por suerte.
- Las actualizaciones de specs del planner tienen que terminar antes de despachar al breaker. Si no, el breaker informa huecos que ya no existen (verify-3).

## Derivación e intentos

- B-1: humano y orquestador. B-2: orquestador (artefactos) y, si hace falta, el humano.
- Ningún bloqueante devuelve trabajo al constructor. Si el recorrido reproduce un defecto, abre una ronda nueva. El gate verify ya usó sus 3 intentos, así que el orquestador tiene que pedir dirección humana antes de un cuarto, sin lanzarlo solo.
- Si B-1 y B-2 se levantan sin cambiar el árbol (`arbol=50fadc6b8a034547`), el auditor reaudita solo esos dos puntos y lo que el recorrido deje como DEUDA.

## Fuentes leídas

- Artefactos: `proposal.md`, `design.md`, `tasks.md` (completo), las 6 `specs/*/spec.md` (requisitos y escenarios; texto completo de los citados), `informes/LEEME.md`.
- Informes originales completos: propose-1 a 5 del planner, propose-1 a 4 del plan-reviewer, apply-1 de los constructores A a E, apply-2 y apply-3 del constructor F, verify-1 a 3 del breaker, verify-2 y verify-3 del planner de specs.
- Código: `routes/estudio.py` (`require_membresia`), `routes/estudio_trabajo.py:1030-1042`, `services/estudio_esquema.py:468-478`, `services/traza_ciega.py:1-30`, diff de `main.py`, `models/__init__.py` y `api.ts`, `analytics.py::interrater_aggregate`, `.github/workflows/{ci.yml,e2e-smoke.yml}`, `scripts/migrate-all.sh`, `tests/e2e/smoke/test_smoke_estudio_codificacion.py` (nombres).
- `scratchpad/`: `proposal-roto.md`, `respaldo-plan-cibse-1215/`, `hash-arbol.sh`.
- Memoria: los artefactos del change y el listado de `openspec/changes/archive/` (13 changes archivados, ninguno de inter-jueces ni de codificación). Engram no se consultó.

## Contaminación por informes ajenos

Leí todos los informes antes de mis corridas, por mandato del rol, así que mis prioridades de ataque están orientadas por ellos. Los conteos, la huella, el cotejo del proposal, la lectura de CI y los dos mutantes son propios. La clasificación de S2 como comportamiento reproducido viene del breaker 2, y no la reproduje. Misma familia de proveedor que todos los autores.
