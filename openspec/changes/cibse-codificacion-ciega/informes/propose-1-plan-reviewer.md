# Informe propose-1-plan-reviewer

- Change: `cibse-codificacion-ciega`
- Rol: plan-reviewer (propose, intento 1)
- Ejecutor: subagente nativo de Claude Code (role plan-reviewer), familia Anthropic, misma familia que el planner. No se declara independencia de proveedor.
- Revisión revisada: `origin/main @ b32e621f992a`, rama `feat/cibse-codificacion-ciega`, artefactos sin commitear. sha256 (12 primeros) de lo revisado: proposal `b26cc450b4af`, design `8a4cdd1f2902`, tasks `6acf69824370`, specs: codebook-versionado `5b91a69cf698`, entrenamiento-calibracion `e24d1852b6ec`, estudio-codificacion-acceso `983ce6e50c4d`, estudio-codificacion-exportacion `b4345b55a56f`, estudio-codificacion `b86ab9bfd703`, traza-ciega-episodio `046c61fa2ed8`. Si cambian, este informe deja de cubrirlos.
- Fecha: 2026-11-04
- No se editó ningún artefacto del plan ni código.

## Veredicto

**APTO CON CORRECCIONES** (equivale a CORRECCIONES): 1 BLOQUEANTE, 8 MAYOR, 11 MENOR. La construcción no se habilita hasta que el planner corrija, se revise la corrección y el humano complete `## Aprobación` (hoy vacía).

**Clasificación: CRITICAL** (coincido con el planner, contra el HIGH del orquestador). Fundamento en J-1.

## EVIDENCIA (chequeos ejecutados)

| # | Comando / lectura | Momento | Resultado |
|---|---|---|---|
| E1 | `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T11:07:48-03:00 | `Change 'cibse-codificacion-ciega' is valid` (formato, no contenido) |
| E2 | `sha256sum muestra_150.csv`; encabezado; `wc -l`; duplicados y regex UUID sobre la columna 4; `file` | 04/11 ~11:05 | `6a6cc0c77e32...86052137`; `estrato,origen,tp,episode_id`; 151 líneas (150 filas); 0 duplicados; 0 valores no-UUID; ASCII con LF |
| E3 | UUID completos de `apps/web-teacher/src/views/InterraterTraining.tsx` (7) buscados con `rg -F` en la muestra | 04/11 | 0 coincidencias (por UUID completo, no solo prefijo) |
| E4 | `sha256sum codebook_v0_borrador.md` y lectura completa (§1 a §10) | 04/11 | `8c20baf7...65501b`, 163 líneas; coincide con design |
| E5 | `uv run pytest apps/analytics-service -q -k interrater` (el chequeo de consumidor que pide la tarea 2.1) | 04/11 ~11:08 | `182 deselected` : **selecciona 0 tests** |
| E6 | `uv run pytest apps/analytics-service/tests/unit/test_cohort_slopes_batch.py packages/platform-ops/tests/test_real_datasources.py packages/platform-ops/tests/test_ghost_episodes_exclusion.py -q` | 04/11 ~11:08 | `25 passed` (línea de base; estos tests hacen `ClsBase.metadata.create_all` sobre SQLite) |
| E7 | `rg -l 'metadata.create_all' ...` + `rg -l classifier_service.models` | 04/11 | create_all de `classifier_service.models.Base` en SQLite: `apps/analytics-service/tests/unit/test_cohort_slopes_batch.py:68`, `packages/platform-ops/tests/test_real_datasources.py:67`, `packages/platform-ops/tests/test_ghost_episodes_exclusion.py:56` (y `test_language_segmentation.py` con el mismo patrón JSONB->sqlite) |
| E8 | Lectura `packages/contracts/.../ctr/events.py` | b32e621 | 21 tipos con `Literal`. `TestsEjecutadosPayload.tests_hidden` es `int` (conteo). `CodigoEjecutadoPayload` tiene `passed/failed/total/failed_test_names`. `EpisodioAbandonadoPayload` tiene `reason`. `PegaIntentadaPayload.contenido_preview` |
| E9 | Lectura `apps/execution-service/.../ctr_emitter.py:108-140` | b32e621 | `tests_ejecutados` server-side emite `tests_hidden` = cantidad de casos ocultos corridos y un campo extra `execution_engine` fuera del contrato. No emite nombres ni contenido de casos |
| E10 | `rg failed_test_names` fuera de contracts | b32e621 | Solo en seeds (`seed-demo-data.py`, `seed-3-comisiones.py`, `seed-smoke.py`); ningún emisor real |
| E11 | Lectura `apps/ctr-service/.../auth/dependencies.py:21-49,60-200`, `config.py` | b32e621 | La identidad se toma de headers `X-User-Id/X-Tenant-Id/X-User-Email/X-User-Roles` (los tres primeros + email obligatorios). `classifier_worker` en `READ_ROLES` y `CTR_OVERSIGHT_ROLES` (salta A0.6). Firma opcional `require_gateway_signature` (default False) verificada sobre user_id, tenant, roles. **Una cuenta de servicio nueva no requiere registro en ctr-service**: basta mandar los headers con el rol |
| E12 | Lectura `packages/observability/.../gateway_trust.py:48-90` | b32e621 | `sign_headers`/`verify_gateway_signature` firman `user_id, tenant_id, roles, ts`. **El email no está firmado** |
| E13 | Lectura `apps/api-gateway/.../middleware/jwt_auth.py:146-175`, `services/jwt_validator.py:285-305` | b32e621 | El gateway purga y reinyecta `x-user-email` desde el claim `email` del token; no hay chequeo de `email_verified`. `user_id = uuid5(sub)` |
| E14 | Lectura `apps/classifier-service/.../routes/interrater.py:30-38,92-96,150-153,200-203` y `analytics.py:505-511` | b32e621 | `CODER_ROLES = ("docente","docente_admin","superadmin")` en `/sample`, `/ratings`, `/my-progress`; el router lleva `require_gateway_auth`. `interrater_aggregate` solo depende de `get_tenant_id`/`get_user_id`, sin rol |
| E15 | Lectura `apps/web-teacher/src/routes/__root.tsx:139-145,225-299` y `src/tour/docenteTour.ts` | b32e621 | El layout raíz monta `TourAutoStart` (`maybeStart(docenteTour)`), `OnboardingDocente`, `ComisionSelectorRouted`, `TenantSelector`. El tour navega a `/`, `/unidades`, `/ejercicios`, `/tareas-practicas`, `/correcciones`, `/episode-n-level` |
| E16 | Lectura `apps/web-teacher/src/main.tsx:76-130` | b32e621 | Si `listMine()` falla, `setEsDocente(false)` y redirige a `/` |
| E17 | Lectura `apps/classifier-service/.../services/regimen_llm.py:398-448` | b32e621 | El juez ve: transcript alumno/tutor, anotaciones, último snapshot y conteos de ejecuciones/prompts. No ve stdout/stderr, snapshots intermedios, copias ni pegados |
| E18 | Lectura `apps/ctr-service/.../schemas/*.py:42-80`, `models/event.py:50`, `partition_worker.py` | b32e621 | `EpisodeOut.estado` toma `open`, `paused`, `closed`; el episodio se lee completo, incluidos eventos posteriores al cierre |
| E19 | `rg` en `apps/classifier-service/tests/test_auth.py` | b32e621 | El test de procedencia cubre `/api/v1/interrater/sample` por URL fija; no enumera routers, así que un router nuevo sin `require_gateway_auth` no lo rompería |
| E20 | Revisión de alembic | b32e621 | Última revisión `20260906_0006`; `down_revision` de la tarea 2.1 es correcto. `apply_tenant_rls` se usa igual en 0006 |
| E21 | Lectura `apps/web-teacher/tests/docenteOnboarding.test.tsx:180-200`, `navegacionAlcanzable.test.ts:42-43` | b32e621 | Ambos listan `/entrenamiento-recalibracion`, `/interrater`, `/interrater-admin` como rutas registradas |
| E22 | `rg -i 'la trampa|sobreuso manda|si ves que sobreusa'` en `apps/web-teacher/src` | b32e621 | Aparecen en `InterraterTraining.tsx:73,77,453` (el test RED de 11.9 puede fallar por aserción antes de borrar) |

No ejecuté suites completas, typecheck, build, migraciones ni nada contra Postgres, Clerk, staging o producción. No hay código nuevo: nada de lo que sigue afirma comportamiento runtime del change.

## Hallazgos

### BLOQUEANTE

**B-1. La regla de coherencia régimen/dimensiones contradice el codebook v0.**
- Fuente: codebook v0 §7 última línea ("El régimen tiene que ser coherente con las dimensiones según la sección 4. Si el codificador cree que la regla da un resultado injusto ... lo codifica igual según la regla y lo explica en las notas") y §4 (regla ordenada: reflexiva si D1 y (D2 o D3) y D4 no oráculo/transferencia; pasiva si D4=transferencia con cita y sin citas en D1-D3; superficial el resto; evidencia insuficiente si no hay material). Contra design D9 ("La coherencia dimensiones<->régimen ... no se fuerza en código ... su incumplimiento se documenta en notas"), tarea 3.2 y spec estudio-codificacion "Cierre de la codificación" (sin escenario de coherencia).
- Observación: el plan lee la §7 al revés. Para el codebook la incoherencia es un error de codificación; las notas son para disentir de la regla, no para reemplazarla. El informe del planner declara haber leído solo §2, §7, §8 y §9 (no la §4). Además el meta-esquema de D9 no tiene forma de expresar la regla, así que agregarla después cambia el formato del esquema congelado.
- Impacto: la referencia humana puede quedar con etiquetas incoherentes sin que nadie lo vea; el κ contra C0/C1 se mide sobre régimen y la definición del régimen queda sin control. Criterio incumplido: el formulario y la completitud tienen que reflejar el codebook vigente.
- Disposición sugerida (planner, con decisión humana): elegir y escribir una de dos. (a) Regla declarativa en el meta-esquema (por ejemplo `reglas_regimen`: lista ordenada de condiciones sobre valores y citas de dimensiones, más un régimen por defecto), evaluada en el servidor al guardar como advertencia visible y al cerrar como 422 o como bandera `incoherente` persistida y exportada; sin texto del codebook en el código. (b) Decisión humana explícita y fechada de no validar, con la coherencia calculada fuera del sistema sobre la exportación. Agregar escenario en spec (régimen incoherente con dimensiones) y caso por regla en 3.2. Verificable: test unitario con esquema construido en el test donde D1 presente, D2 presente, D4 interlocutor y régimen `superficial` produce el resultado elegido.

### MAYOR

**M-1. La evidencia de un ítem no está fijada: la traza se lee en vivo del CTR.**
- Fuente: design D4/D6 (se persiste solo `episode_id`), E18 (el CTR devuelve el episodio completo con eventos posteriores), contrato `episodio_reabierto` (E8).
- Observación: si un docente reabre un episodio de la muestra (o se agrega cualquier tipo incluido), la traza cambia entre el codificador A y el B y los localizadores `n` se corren, invalidando citas ya guardadas. Lo mismo si en un change futuro se amplía la lista blanca.
- Impacto: la "muestra fija" no garantiza evidencia fija; se rompe la integridad de la referencia (CRITICAL, integridad de auditoría).
- Disposición: al cargar la muestra (y al crear un ancla) persistir por ítem `seq` máximo, `events_count` y `last_chain_hash`; servir solo eventos con `seq <=` ese tope; si el CTR ya no coincide en el prefijo, responder con un estado explícito y registrarlo. Versionar la lista blanca (`traza_version`) y guardarla en cada etiqueta y en la exportación. Escenario nuevo en traza-ciega-episodio: "evento agregado después de la carga no aparece". Test en 6.3 con cliente CTR falso que devuelve un evento extra.

**M-2. La lista blanca omite conductas del alumno que el codebook nombra como evidencia.**
- Fuente: codebook §4 (marcadores de pasiva: "intentos de copiar", "abandono tras baja implicación") y §3 D2 ("relee la consigna"); design D4 (omite `copia_intentada`, `pega_intentada`, `lectura_enunciado`, `edicion_codigo.origin`; `episodio_cerrado` y `episodio_abandonado` quedan como el mismo marcador "fin" sin campos).
- Observación: no son decisiones de la máquina sino capturas de conducta; el codificador no puede distinguir abandono de cierre. Hay un trade-off real (evidencia del codebook contra paridad con lo que ve el juez, E17, y contra la marca `origin` que alimenta el override N4), y no está planteado como pregunta.
- Impacto: humanos y codebook trabajan con evidencia distinta de la que el codebook describe; cambiarlo después de empezar a codificar mueve los localizadores (ver M-1).
- Disposición: agregar pregunta abierta para el investigador con default explícito, al menos: distinguir "fin: cerrado" de "fin: abandonado"; incluir o no intentos de copia/pegado (sin `contenido_preview` si se decide privacidad). Documentar en design la diferencia de evidencia humano/juez para la sección de método del paper. Decidir antes de la tarea 6.1.

**M-3. El modo restringido del web-teacher ignora tour, onboarding y selector de comisión.**
- Fuente: design D13 y tarea 11.2 (solo menú y redirección) contra E15.
- Observación: un codificador externo entra al layout raíz, que arranca automáticamente el tour docente (navega a `/unidades`, `/ejercicios`, etc., que en modo restringido redirigen a `/interrater`), muestra carteles de onboarding docente y monta `ComisionSelectorRouted` y `TenantSelector`. El brief de la tarea no lo cubre ni lo prueba.
- Impacto: experiencia rota o bucle tour/redirección para el usuario objetivo del change; llamadas innecesarias a APIs docentes.
- Disposición: en modo restringido no montar `TourAutoStart`, `OnboardingDocente` con flow docente, ni selectores de comisión/tenant. Test en 11.2: render del root en modo restringido sin tour activo, sin carteles y sin fetch a comisiones. Agregar `docenteOnboarding.test.tsx` a los consumidores.

**M-4. La puerta de entrada pasa a depender de classifier-service para todos los docentes.**
- Fuente: design D13 (main.tsx consulta `mis-membresias`), Migration Plan paso 3 ("mostraría error en las dos secciones"), E16.
- Observación: si la consulta de membresías se encadena al chequeo de acceso y su error se trata como el de `listMine()`, una caída o redeploy de classifier-service deja afuera a docentes con comisiones, no solo a las dos secciones. La afirmación del paso 3 no está respaldada por ningún requisito ni test.
- Impacto: disponibilidad del panel docente entero atada a un servicio no crítico para ellos.
- Disposición: requisito y escenario explícitos: "docente con comisiones entra aunque `mis-membresias` falle; el error solo afecta a las dos secciones". Agregar a `resolverAcceso` el caso de error de membresías (y el de error de comisiones con membresía válida) en `tests/accesoPanel.test.ts`.

**M-5. El chequeo de consumidores de `classifier_service.models` es vacío y omite los que sí se rompen.**
- Fuente: tarea 2.1 (`pytest apps/analytics-service -q -k interrater`), tarea 8.3 ("si existen"), E5, E6, E7.
- Observación: `-k interrater` selecciona 0 tests (EVIDENCIA E5): el chequeo pasa siempre. Los consumidores reales de las tablas nuevas son los tests que hacen `ClsBase.metadata.create_all` sobre SQLite (E7); un índice parcial, `server_default` de Postgres, tipo `ARRAY` o `CheckConstraint` específico en `models/estudio.py` puede romperlos. Para pedagogía existe `apps/analytics-service/tests/unit/test_pedagogia_distribucion.py`.
- Impacto: regresión de consumidores no detectada (HIGH/CRITICAL exige regresiones de consumidores).
- Disposición: reemplazar el comando de 2.1 por los archivos concretos de E6/E7 más `apps/analytics-service -q` completo, y nombrar `test_pedagogia_distribucion.py` en 8.3. Línea de base ya medida: 25 passed (E6).

**M-6. Concurrencia entre guardado, cierre, vigente y muestra sin bloqueo definido.**
- Fuente: design D6 (lock `FOR UPDATE` solo en carga de muestra y anclas), D8 (409 al cambiar vigente con etiquetas), D10 (cierre valida completitud y fija `cerrada_at`).
- Observación (razonada, no ejecutada): (a) un `PUT mi-etiqueta` de otra pestaña puede commitear entre la validación de completitud y el `cerrada_at`, dejando cerrada una codificación incompleta, o guardar después del cierre si no relee `cerrada_at` bajo lock; (b) un `PUT` puede leer la vigente v1 mientras el investigador cambia a v2 al no haber etiquetas todavía, quedando una etiqueta con v1 y vigente v2; (c) un `PUT` concurrente con un reemplazo de muestra.
- Impacto: datos de la referencia inconsistentes con las reglas declaradas.
- Disposición: `SELECT ... FOR UPDATE` de la membresía en `PUT` y `cerrar`; lock compartido (o el mismo `FOR UPDATE`) de la fila del estudio en `PUT`, cambio de vigente y carga de muestra. Escenarios en spec y tests de concurrencia al estilo de `tests/integration/test_submit_review_concurrency_db.py`.

**M-7. Identidad por email sin firma y `user_id_visto` sin uso.**
- Fuente: design D3, E11, E12, E13, E19.
- Observación: la membresía se resuelve por `X-User-Email`, que el gateway reinyecta pero la firma HMAC no cubre; `user_id` (uuid5 del `sub` de Clerk) sí está firmado y es estable. El plan guarda `user_id_visto` pero no lo usa. Además el plan no dice que el router nuevo lleve `require_gateway_auth` (el test de E19 no lo detectaría). Hoy el flag está apagado, así que el riesgo es el mismo que el resto del servicio; pero el change convierte el email en la llave de acceso a episodios completos.
- Impacto: si otra cuenta llega con el mismo email (email no verificado, o puerto interno expuesto), hereda la membresía y sus etiquetas.
- Disposición: fijar la membresía al `user_id` en el primer uso y rechazar (403 + log) un `user_id` distinto para la misma membresía; escenario y mutante en 4.1. Exigir `dependencies=[Depends(require_gateway_auth)]` en el router nuevo y un test con el flag encendido. Mantener el recorrido humano sobre email verificado.

**M-8. La inmutabilidad del codebook congelado tiene un hueco en INSERT de anclas y el sha no cubre anclas.**
- Fuente: design D2 (triggers `BEFORE UPDATE OR DELETE`), D8 (sha sobre `contenido_md` + esquema), spec codebook-versionado "Congelamiento e inmutabilidad" ("ni por la API ni por la base").
- Observación: un `INSERT` directo de un ancla en una versión congelada no lo rechaza la base; y el sha256 de la versión no cambia si cambian sus anclas, que son parte del entrenamiento de esa versión.
- Impacto: incumple el requisito "ni por la base" y la trazabilidad del entrenamiento.
- Disposición: trigger `BEFORE INSERT OR UPDATE OR DELETE` en `estudio_ancla` contra versión congelada; decidir si el sha incluye anclas canonicalizadas o declarar un `anclas_sha256` aparte al congelar. Caso en `test_estudio_inmutabilidad_db.py` con INSERT y mutante.

### MENOR

- **m-1. Unidad de cita.** Codebook §3 y §8 citan "turno del chat" o "ejecución 4"; el plan da un localizador global `n` que mezcla ediciones (muchas por episodio) con mensajes y ejecuciones. Disposición: localizador por tipo además del global (turno k, ejecución k, prueba k, código k) o ajustar el codebook; decidirlo con el investigador.
- **m-2. Marca de tiempo absoluta.** Spec traza "su marca de tiempo" devuelve `ts` absoluto: fecha y hora pueden delatar comisión/turno o cercanía a la entrega a un codificador docente. Disposición: devolver segundos desde el inicio, no `ts`.
- **m-3. Formato de `respuestas` no especificado.** No se define cómo se guarda cada dimensión (valor + cita), ni si la cita es texto libre o lista de localizadores; la exportación "aplana cada campo". Disposición: fijarlo en design D9/D10 y en el spec de guardado.
- **m-4. Estado del episodio.** "no está abierto" es ambiguo con `paused` (E18); las anclas no validan estado. Disposición: exigir `estado == "closed"` (o la lista que decida el investigador) para muestra y anclas, con escenario.
- **m-5. Colisión de ruta.** `GET /estudios/mis-membresias` y `/estudios/{clave}`: una clave `mis-membresias` choca. Disposición: validar `clave` con patrón y lista reservada.
- **m-6. Re-alta tras revocación.** No se especifica si reactivar un email revocado crea membresía nueva (semilla, alias y etiquetas nuevas) o reabre la vieja. Disposición: escenario explícito.
- **m-7. Reproducibilidad del orden.** `random.Random(semilla).shuffle` no tiene garantía entre versiones de Python. Disposición: persistir la posición de cada ítem por membresía al fijarse la muestra, o declarar la versión.
- **m-8. Logs con PII.** El log de membresías lleva "autor" y la membresía es un email. Disposición: loguear `membresia_id`/alias y user_id del autor, nunca emails.
- **m-9. Tests de la lista blanca con modelos del contrato.** La tarea 6.1 usa modelos de `platform_contracts`; el CTR devuelve dicts con campos fuera del contrato (`execution_engine`, E9). Disposición: casos con dicts crudos con claves extra y aserción del conjunto exacto de claves por tipo, no solo la lista de claves prohibidas.
- **m-10. Esquema v0 sin tarea propia y límites de evidencia.** No hay tarea para preparar y validar contra el meta-esquema el JSON del v0 antes de congelar, ni para documentar que la mayoría de las corridas solo traen conteos (`tests_ejecutados`, sin salida), aunque el codebook §2 promete "lo que imprimió y el error". Disposición: tarea en Workflow follow-up y nota en el runbook.
- **m-11. Impacto en KB incompleto.** `CLAUDE.md` del repo lista las keys de `helpContent` y las rutas del web-teacher; agregar `estudioEntrenamiento` las deja desactualizadas. Disposición: sumar esas líneas al Knowledge Base Impact (REWRITE).

## Puntos verificados sin defecto

- `tests_hidden` (pregunta del brief): es un conteo de casos ocultos corridos (E8, E9), no revela entradas ni salidas esperadas. `failed_test_names` no tiene emisor real (E10). No es fuga de casos ocultos; el riesgo residual es nulo en contenido.
- Cuenta de servicio hacia el CTR: creable sin tocar ctr-service por lectura de código (E11); pendiente solo la verificación real con `REQUIRE_GATEWAY_SIGNATURE` de producción, ya prevista en Workflow follow-up.
- Ruteo: `/api/v1/interrater/estudios/*` cae en `/api/v1/interrater` del ROUTE_MAP por `startswith` (lectura de `proxy.py:64,123-128`).
- Formulario contra §7 del codebook: D1-D3 presente/ausente con cita, D4 interlocutor/oráculo/transferencia con cita, régimen con evidencia insuficiente, notas obligatorias en frontera o insuficiente, confianza opcional: el meta-esquema de D9 puede expresarlo todo. Falta solo la regla de coherencia (B-1).
- Exclusión ancla/muestra: cubierta en ambos sentidos y bajo el mismo lock (spec entrenamiento-calibracion). Muestra real y anclas del piloto: 0 coincidencias (E3).
- Muestra recargada con otro hash: 422 con `sha256_esperado`, reemplazo solo sin etiquetas (409). Hash real coincide con el brief (E2).
- Codebook congelado editado por API: 409; por base: triggers (salvo M-8).
- Codificador no asignado: 403 sin revelar existencia; revocado: 403 con etiquetas conservadas.
- Migración: `down_revision` correcto (E20), aditiva y reversible con borrado de tablas; el plan limita el downgrade a "sin datos".
- Exportación: restringida a investigador, sin emails ni contenido, CSV con prefijo anti-fórmula, log sin valores.
- Consumidores del piloto: tablas separadas preservan `interrater_ratings`, κ y scripts; `navegacionAlcanzable` y `docenteOnboarding` siguen listando rutas existentes.
- Tareas: todas las de código tienen test nombrado y RED identificable; 11.9 puede fallar por aserción antes de borrar (E22). Para 2.1/2.2 el RED por aserción depende de mutante (ya marcado [MUTANTE]).

## Observación del planner sobre DEUDA (no promovida)

EVIDENCIA de código (E14, E13), no runtime: con Clerk todo usuario recibe `estudiante,docente`; `POST /api/v1/interrater/ratings`, `GET /sample` y `GET /my-progress` exigen solo uno de `docente,docente_admin,superadmin`, así que por lectura cualquier cuenta logueada pasa el control de rol. `GET /api/v1/analytics/interrater/aggregate` no tiene control de rol. No lo reproduje contra un gateway real. Coincido con registrarlo como DEUDA fuera de alcance. Matiz: el change da cuentas de Clerk a personas externas con motivo para entrar, lo que no agrega una capacidad nueva (cualquiera puede registrarse si el alta de Clerk es abierta, SUPOSICIÓN) pero sí agrega usuarios reales con esa capacidad; conviene mencionarlo en la pregunta 1 del proposal.

## JUICIO

Autor: plan-reviewer. Comparación: artefactos del change contra código en `b32e621`, codebook v0 completo y muestra real.

- **J-1. Clasificación CRITICAL** (confianza alta). El change crea un camino de autorización nuevo por el que personas sin comisión (posiblemente externas) leen chats, código y salidas de alumnos a través de una cuenta de servicio que salta el gate A0.6 (E11). Eso es un límite de datos sensibles y de seguridad; el workflow lo fija como CRITICAL independientemente del tamaño. Se suma integridad de auditoría: la referencia del paper depende del cegamiento, la inmutabilidad y el aislamiento. HIGH subestimaría el requisito de mutante por aserción de seguridad y el recorrido humano real con Clerk, que acá son necesarios.
- **J-2.** La arquitectura es sólida: cegamiento server-side por lista blanca que falla cerrada, test de cobertura de tipos, identificador opaco, tablas separadas, codebook como dato. Los defectos son de completitud y de alineación con el codebook, no de dirección (confianza alta).
- **J-3.** B-1 y M-2 son decisiones del investigador más que técnicas; el planner tiene que presentarlas como preguntas con default, no resolverlas solo (confianza media-alta).
- **J-4.** M-1 y M-6 son escenarios razonados; no hay código para probarlos. Se proponen como escenarios de spec y tests, no como fallas demostradas (confianza media en la probabilidad, alta en el impacto si ocurren).

## SUPOSICIÓN

- Que en producción `REQUIRE_GATEWAY_SIGNATURE` está apagado en ctr-service y classifier-service (inferido de que `classify_ep.py` lee sin firmar); no verificado contra EasyPanel.
- Que el claim `email` de Clerk es un email verificado; no verificado.
- Que la reapertura de episodios (M-1) puede ocurrir sobre episodios del S2 2026; no consulté producción.
- Que el alta en Clerk es abierta; no verificado.
- Que una consulta de 150 episodios completos con concurrencia 8 entra en el timeout de 120 s del gateway; no medido (tamaño real de snapshots desconocido).
- No ejecuté suites completas ni Postgres; las afirmaciones sobre SQLite create_all (M-5) son de riesgo, no de falla observada: hoy pasan (E6) porque el modelo nuevo no existe.

## Fuentes leídas

- Artefactos: `proposal.md`, `design.md`, `tasks.md`, los 6 `specs/*/spec.md`, `informes/LEEME.md`; `openspec status --change ... --json`.
- `/home/juanisarmiento/Proyectos/AI-Native/codigo/CLAUDE.md` (cargado en contexto).
- Codebook v0 completo; muestra (hash, encabezado, columna `episode_id`).
- `packages/contracts/src/platform_contracts/ctr/events.py`; `packages/observability/src/platform_observability/gateway_trust.py`.
- ctr-service: `auth/dependencies.py`, `config.py`, `schemas` (EventOut/EpisodeOut), `models/event.py:50`.
- classifier-service: `auth/__init__.py`, `auth/gateway_auth.py`, `config.py:95-125`, `routes/classify_ep.py:85-100`, `routes/interrater.py` (fragmentos), `reclassify_all.py:75-85`, `services/regimen_llm.py:395-448`, `main.py`, lista de `alembic/versions`, `tests/test_auth.py` (encabezado).
- execution-service: `services/ctr_emitter.py:100-140`. tutor-service/web-student: búsquedas de `tests_hidden`/`failed_test_names`.
- api-gateway: `routes/proxy.py:55-128`, `middleware/jwt_auth.py:100-175`, `services/jwt_validator.py` (búsquedas), `config.py:95-125`.
- analytics-service: `routes/analytics.py:500-530`; tests con `create_all`.
- web-teacher: `main.tsx:60-140`, `routes/__root.tsx` (imports, 139-145, 225-299), `routes/{interrater,entrenamiento-recalibracion}.tsx`, `tour/docenteTour.ts` (rutas), `utils/helpContent.tsx:788-835`, `tests/{navegacionAlcanzable,docenteOnboarding}.test.ts*` (fragmentos), `tests/_mocks.tsx` (setupFetchMock), `vite.config.ts:59`.

## Contaminación por informes ajenos

Leí `informes/propose-1-planner.md` **después** de formar mi lectura y redactar la lista de hallazgos. Lo usé solo para confirmar que el planner no leyó la §4 del codebook (refuerza B-1) y para no repetir evidencia ya registrada. Ningún hallazgo proviene de ese informe. Comparto familia de modelo con el planner: no hay independencia de proveedor. No consulté Engram ni otros informes.
