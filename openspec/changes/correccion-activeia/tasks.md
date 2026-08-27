## 0. Gates previos (no son código, corren en paralelo)

> **0.1 a 0.4 respondidos el 2026-08-18** leyendo el cliente que ya opera contra la API
> en vivo: `~/Proyectos/Skill-Moodle/codigo/mcp/moodle/active_ia.py` y su
> `references/active-ia.md` (verificado contra producción el 2026-08-17). No hizo falta
> preguntarle a nadie. **0.5 sigue abierto y es el que bloquea el despliegue con datos
> reales.**

- [x] 0.1 ¿Puede modelar un TP con ejercicios hijos? **NO hoy**: el modelo es
  `materia → unidad → rubrica_id`, sin nivel de ejercicio. Pero **no hace falta que lo
  agreguen para el modelo de datos**: una entrega apunta a UNA `rubrica_id` suelta, así
  que N ejercicios son N rúbricas y N entregas. Lo que SÍ hace falta son los endpoints de
  escritura (`PUT /trabajos-practicos/by-ref/{ref}`), que hoy no existen — y
  `GET /rubricas/{id}` da **403 con rol tutor**, así que tampoco se puede leer una rúbrica
  para comparar el hash. Eso es lo que mantiene apagados `activeia_sync_rubricas_enabled`
  y el simulador `activeia_mock_escritura`
- [x] 0.2 `POST /entregas/` es **multipart**: `archivo` (zip), `alumno_nombre`,
  `comision_id`, `rubrica_id`; opcionales `moodle_url` y `modo_consolidacion`
  (`"solo_codigo"` si la API lo exige con un 422). **Ningún id de Moodle es obligatorio**:
  `moodle_url` es opcional y `comision_id` es de Active-IA, no de Moodle
- [x] 0.3 El 409 keyea por **`(comision_id, rubrica_id, alumno_nombre normalizado)`**.
  El `rubrica_id` en el match NO es opcional: sin él alcanzaba el nombre y se retomaba la
  entrega de OTRO TP del mismo alumno — el tutor le adjuntaba la devolución de otra unidad
- [x] 0.4 `GET /correcciones/entregas/{id}`: **200 = corregida** (trae nota y
  `correccion_id`), **404 = todavía no**. El PDF sale aparte de
  `GET /documentos/correcciones/{correccion_id}/pdf`. Ojo: **`GET /entregas/{id}` está
  roto del lado del server** (500), por eso el poll va por `/correcciones/`
- [x] 0.5 Confirmar si AI-Native y Active-IA son la misma personería frente al consentimiento del piloto — **2026-08-27: SON LA MISMA.** El tratamiento es interno, el consentimiento vigente alcanza, no es cesión a un tercero. Comunicado en la respuesta §2.1 y volcado al ADR-061
- [x] 0.6 Entregar `docs/research/activeia-cambios-pedidos.md` al equipo de Active-IA — entregado; contestaron el 20/08 y de nuevo el 24/08 con §3.1-3.4 construidos. Respuesta nuestra en `docs/research/activeia-respuesta-2026-08-27.md`
- [x] 0.7 Marcar `depende_de_ejecucion` en las rúbricas (§3.1 del pedido de ellos) — 34 criterios de los 7 ejercicios del piloto, 14 en `true`. Herramienta en dos fases en `scripts/marcar-depende-de-ejecucion.py`
- [x] 0.8 Migrar el cliente al endpoint `POST /correcciones/ejercicios/{ref}/corregir` — se fueron el zip, el 409 y el poll. Cierra el «comision_id mal cableado»
- [ ] 0.9 Confirmar con Active-IA el nombre del campo de la nota en la respuesta: hoy leemos `nota_100` y caemos a `nota`/`nota_final`/`calificacion`. Esa cascada funciona hasta el día que devuelve el campo equivocado
- [ ] 0.10 Definir con Active-IA `salida_obtenida` vs `obtenido` en el detalle por caso: nuestro documento decía uno y el código manda el otro (ver §4.1 de la respuesta)

## 1. Epic 1 — La entrega contiene lo que se entregó (no depende de Active-IA)

- [x] 1.1 Migration: tabla `entrega_artefactos` (`id, tenant_id, entrega_id FK, orden, episode_id, codigo, sha256, created_at`) con RLS `ENABLE` + `FORCE` y policy por tenant, molde `20260510_0001_initial_entregas_calificaciones.py:116-121`
- [x] 1.2 Migration: columna `artefacto_sha256` en `entregas` (hash del conjunto) y flag `legacy`
- [x] 1.3 `make check-rls` verde con la tabla nueva
- [x] 1.4 Sembrar `ejercicio_estados` desde `tp_ejercicios` al crear la entrega — hoy se construye con `[]` en `routes/entregas.py:81`
- [x] 1.5 Validar el submit contra los ejercicios esperados, no contra los presentes — hoy `if estados:` con lista vacía no valida (`routes/entregas.py:236-245`)
- [x] 1.6 Extender el payload de submit para recibir el código por ejercicio, y persistir una fila por ejercicio con su `sha256`
- [x] 1.7 Calcular y guardar el `sha256` del conjunto en el submit; no recalcularlo al leer
- [x] 1.8 Marcar `legacy=true` las entregas existentes en la migration de datos
- [x] 1.9 `GET /api/v1/entregas/{id}/artefacto` con manifiesto (por ejercicio: `orden`, `episode_id`, `sha256`) y gate de membresía de comisión, devolviendo 404 y no 403
- [x] 1.10 Resolver la TP monolítica: persistir el `episode_id` en el submit — ver `routes/episodio.$id.tsx:53-70` (`BUG-1`) y la resolución por `problema_id` que ya hace `CorreccionesView.tsx:1245`
- [x] 1.11 Arreglar el flush del debounce al desmontar el editor (`web-student/src/components/CodeEditor.tsx:490-494` limpia el timeout sin invocar el callback)
- [x] 1.12 Mandar el código de cada ejercicio en el submit desde web-student
- [x] 1.13 Botón "Descargar entrega" en la fila de acciones del form de calificación (`CorreccionesView.tsx:1779`), descarga por Blob (molde `ExportView.tsx:113-131`)
- [x] 1.14 Mostrar el estado LEGACY en la UI, con el aviso de que es una reconstrucción best-effort del CTR
- [x] 1.15 Script de medición: cuántas entregas del piloto son ensamblables, monolíticas y LEGACY
- [x] 1.16 Tests: submit persiste N filas, submit sin código de un ejercicio esperado da 422, hash guardado no se recalcula, docente de otra comisión recibe 404

## 2. Epic 2 — Credenciales y sincronización (requiere 0.1 y 0.2)

- [x] 2.1 Migration: `activeia_credenciales` (`id, tenant_id, user_id, username, encrypted_password BYTEA, created_at, revoked_at, last_login_at, last_login_ok`) con UNIQUE parcial `(tenant_id, user_id) WHERE revoked_at IS NULL`, RLS `ENABLE` + `FORCE` por tenant. Sin columna de fingerprint
- [x] 2.2 Migration: `activeia_rubrica_ejercicio` (`tenant_id, ejercicio_id, external_ref, rubrica_id, rubrica_hash, sincronizado_at`) con la misma receta de RLS
- [x] 2.3 `make check-rls` verde con las dos tablas
- [x] 2.4 Cifrado con `platform_ops/crypto.py` y `ACTIVEIA_MASTER_KEY` propia; agregarla al deploy y al runbook
- [x] 2.5 Cliente HTTP de Active-IA: `POST /auth/login`, token en memoria, re-login ante 401, timeout 90s, cliente efímero por request
- [x] 2.6 Filtro `user_id` explícito en las tres queries de credenciales (la RLS es sólo por tenant — ver design D6) + test que lo cubra
- [x] 2.7 `POST /api/v1/activeia/credenciales` con validación por login real; rechazar con error de autenticación, nunca con "sin rúbricas"
- [x] 2.8 `DELETE` y `GET` de estado de credencial
- [x] 2.9 Entrada nueva en el `ROUTE_MAP` para `/api/v1/activeia` (`api-gateway/routes/proxy.py:33-104`) con comentario y referencia al ADR
- [x] 2.10 Constante `CORRECCION_IA_ROLES` en `auth/dependencies.py`; no tocar el seed de Casbin
- [x] 2.11 Sincronizador: al publicar un TP, empujar TP + ejercicios con `rubrica`, `test_cases`, `peso_en_tp` y `external_ref`; guardar identificador devuelto y `rubrica_hash`
- [x] 2.12 Detección de desincronización comparando `rubrica_hash`
- [x] 2.13 Vista en web-teacher: conectar/desconectar cuenta y estado por ejercicio (sincronizado / desactualizado / sin sincronizar)
- [x] 2.14 Entrada en `helpContent` (`web-teacher/src/utils/helpContent.tsx`) — hay test de cobertura del catálogo
- [x] 2.15 Grep de verificación: el password no aparece en logs, respuestas ni errores
- [x] 2.16 De paso: `/api/v1/calificaciones` está en el ROUTE_MAP (`proxy.py:88`) sin router que lo sirva (`main.py:41-42`) — hoy da 404

## 3. Epic 3 — El disparo por ejercicio (requiere 1 y 2)

- [x] 3.1 Migration: `correcciones_ia` (`id, tenant_id, entrega_id FK sin unique, tp_ejercicio_id, orden, disparado_por, rubrica_id, estado, nota_100 Numeric(5,2), desglose JSONB, tests_snapshot JSONB, artefacto_sha256, error_code, error_detail, timestamps`) con RLS `ENABLE` + `FORCE`
- [x] 3.2 `make check-rls` verde
- [x] 3.3 Config: `activeia_enabled` con default `False` (molde `execution-service/config.py:86-94`) y parámetros de cuota
- [x] 3.4 Cuota por docente y día contando filas en Postgres, que **falla cerrada**: 503 si no se puede leer el contador, 429 si se excedió
- [x] 3.5 Servicio de pre-ejecución: correr los test cases del ejercicio contra el artefacto persistido usando el execution-service, y devolver el detalle por caso
- [x] 3.6 ~~Cortar antes de contactar a Active-IA si el artefacto no compila~~ → **revertido el 19/08**: se manda igual y el estado de compilación viaja explícito (`compila`, `error_compilacion`). Ver ADR/spec.
- [x] 3.7 `POST /api/v1/entregas/{id}/correccion-ia` con `{ejercicio_orden?, confirmado}` → 202 (molde `execution-service/routes/executions.py:162-221`)
- [x] 3.8 Preview con `confirmado=false`: qué ejercicio, qué rúbrica y su estado de sincronización, qué tests, tamaño — sin ejecutar ni contactar ni consumir cuota
- [x] 3.9 Gate de membresía de comisión en los tres endpoints, devolviendo 404 y no 403 (**no** copiar `_assert_can_read`, `routes/entregas.py:585-593`)
- [x] 3.10 Gate: sin artefacto persistido o con entrega LEGACY, no se dispara
- [x] 3.11 Idempotencia por `(entrega_id, tp_ejercicio_id, rubrica_id, artefacto_sha256)`, con re-set del tenant RLS tras el rollback del IntegrityError (molde `routes/entregas.py:50-108`, detalle en `:93-97`)
- [x] 3.12 Trabajo en `BackgroundTasks` con **sesión de DB corta** y **semáforo** de concurrencia — el pool es de 8 (`db/session.py:33-34`)
- [x] 3.13 Presupuesto de tiempo total repartido entre intentos, no N segundos por intento (molde `academic-service/routes/ejercicios.py:300-372`)
- [x] 3.14 Mapear `GEMINI_OVERLOADED` y timeouts a fallo de infraestructura sin `nota_100`; distinguirlo de un rechazo del servicio
- [x] 3.15 Manejo del 409 según lo que responda la tarea 0.3
- [x] 3.16 Reconciliador en el lifespan que levanta las `running` viejas y re-poletea (molde `abandonment_worker.py:91-116`)
- [x] 3.17 `GET .../correccion-ia` y `GET .../correccion-ia/{cid}`
- [x] 3.18 Frontend: botón por ejercicio en las tarjetas de `CorreccionesView`, modal de preview, y polling con `setTimeout` recursivo con limpieza en el unmount (molde `ExportView.tsx:46-76`)
- [x] 3.19 Dos banners distintos (molde `EjerciciosView.tsx:1259-1308`): ámbar para fallo de infraestructura, rojo para rechazo. No mostrar `String(e)` crudo
- [x] 3.20 Tests: doble click = una corrección y una subida; `GEMINI_OVERLOADED` no crea nota; kill switch apagado da 503; docente de otra comisión recibe 404; cuota excedida da 429

## 4. Epic 4 — Mostrar sin decidir (requiere 3)

- [x] 4.1 Card de resultado por ejercicio entre la barra de progreso y las tarjetas (`CorreccionesView.tsx:1487-1531`), con el patrón visual del repo
- [x] 4.2 Mostrar nota /100, desglose si lo hay, rúbrica usada y link al PDF
- [x] 4.3 Promedio ponderado por `peso_en_tp` **mostrando el cálculo**, no sólo el resultado
- [x] 4.4 Si falta la corrección de algún ejercicio, no promediar: mostrar parcial y nombrar los que faltan
- [x] 4.5 Botón "Usar como base" que rellena el campo de nota (÷10, con el redondeo visible) y deja el foco — **no guarda**
- [x] 4.6 Guardrail aritmético: sumar los criterios del desglose y comparar con el total; si difieren, marcarlo
- [x] 4.7 Microcopy con los modos de fallo conocidos del motor: cuenta presencia y no vínculo, puede elogiar código hardcodeado, puede recomendar lo que la cátedra prohíbe
- [x] 4.8 **No** mapear los criterios de Active-IA contra los de la rúbrica local: lado a lado, sin fusionar (`mapSavedToInputs` empareja por string, `CorreccionesView.tsx:738-761`)
- [x] 4.9 Entrada en `helpContent` y tests en `web-teacher/tests/CorreccionesView.test.tsx` (usar el helper `setupFetchMock`)
- [x] 4.10 Test: calificar usando la sugerencia como base y guardar una nota distinta de la propuesta

## 5. Epic 5 — PDF y derecho al olvido (requiere 3)

- [x] 5.1 Extraer `BaseStorage`/`MockStorage`/`S3Storage` y los helpers de key de content-service (`services/storage.py:21-152`) a un paquete compartido — **PR propia**, con el smoke de materiales verde antes de seguir
- [x] 5.2 Bajar el PDF al cerrar la corrección y guardar `pdf_storage_key`: key no adivinable, prefijo propio, nunca el bucket de materiales
- [x] 5.3 `GET .../correccion-ia/{cid}/pdf` con el mismo gate de comisión. Sin link público ni URL firmada de larga vida
- [x] 5.4 Extender `anonymize_student` (`platform_ops/privacy.py:147-192`): rotar el pseudónimo en `correcciones_ia`, borrar el PDF del storage y borrar el artefacto del Epic 1
- [ ] 5.5 Llamar al borrado por alumno de Active-IA dentro del mismo procedimiento (depende del pedido 3.6 del documento de cambios)
- [x] 5.6 Política de retención de PDFs y artefactos, con job o procedimiento manual documentado
- [x] 5.7 Resolver la dep muerta `weasyprint>=62` (`evaluation-service/pyproject.toml:25`, cero imports): usarla o sacarla
- [x] 5.8 Test: `anonymize_student` sobre un alumno con corrección deja el PDF borrado y la fila sin pseudónimo

## 6. Epic 6 — Hardening y cierre

- [x] 6.1 Smoke E2E en `tests/e2e/smoke/` con Active-IA reemplazado por un doble HTTP: camino feliz, 409, `GEMINI_OVERLOADED`, credencial inválida, artefacto ausente
- [x] 6.2 Métricas OTel: disparadas, completadas, `infra_failure` con causa, duración, in-flight, rechazos de cuota (molde `execution-service/services/metrics.py:27-92`)
- [x] 6.3 Rastro structlog `correccion_ia_disparada` / `correccion_ia_completada`, patrón `tp_calificada` (`routes/entregas.py:391-400`) — **meta-evento, NO va al CTR**
- [ ] 6.4 Agregar `ACADEMIC_DB_URL` al env de ctr-service en EasyPanel y verificar que el gate de comisión deja de ser no-op (`ctr-service/auth/dependencies.py:173`, `docs/EASYPANEL-DEPLOY.md:110`)
- [x] 6.5 Extender el filtro por comisión a los cuatro endpoints que hoy no lo tienen: `GET /{id}`, `calificar`, `PATCH /calificacion`, `return`
- [ ] 6.6 Pasar el **ADR-061** (ya escrito: `docs/adr/061-activeia-fuera-del-ai-gateway.md`) de *Propuesto* a *Aceptado*. La personería quedó resuelta el 27/08; falta el borrado por alumno (5.5) y la política de retención de respaldos. `docs/adr/004-ai-gateway-propio.md:9` nombra este caso de uso
- [x] 6.7 `FEATURES.md:59` deja de decir "⛔ vive en active-ia, fuera de scope"
- [x] 6.8 Runbook: kill switch, rotación de `ACTIVEIA_MASTER_KEY` y por qué es distinta de `BYOK_MASTER_KEY`, qué pasa con las `running` durante un deploy, y si evaluation-service se suma a la lista de "nunca redeployar en caliente"
- [x] 6.9 Actualizar la nota viva de Obsidian: **reescribir** frontmatter, Estado actual, Últimos avances y Próximos pasos; **apilar** en Gotchas y Decisiones clave
