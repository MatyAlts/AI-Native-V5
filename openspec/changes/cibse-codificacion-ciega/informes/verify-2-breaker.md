# verify-2-breaker: rompedor, intento 2

- Rol: breaker. Ejecutor: subagente nativo Claude Code (familia Anthropic, la misma que todos los roles previos, incluido el constructor F). Sin independencia por proveedor.
- Fecha: 04/11/2026, 14:23 a 14:34 (-03:00). Nivel CRITICAL. Gate verify, intento 2.
- Revisión atacada: árbol sobre HEAD `b32e621` (rama `feat/cibse-codificacion-ciega`), sin commits. Huella (`scratchpad/hash-arbol.sh`, excluye `openspec/changes/cibse-codificacion-ciega/`):
  - 14:23:57 `diff_HEAD_sha256=ad796f2631fd9e3eed469fb3de876f37fdddcca871210aae21956ca49b6d795a untracked_n=59 untracked_list_sha256=4b1db26112d7e4aacfe16ec245fa9f8d5bf5ab3708ae52d86a7b18fdb259d9c5 arbol=291628b1211abf5a`
  - 14:33:20 idéntica. **La huella no cambió.** Los tests temporales se copiaron, se corrieron y se borraron (`git status` sin restos); los originales están en `scratchpad/breaker/`.
- Lecciones L-NNN: no existen en el repo. Ruta leída: ninguna.
- No edité código de producción ni corrí mutantes sobre la entrega. Ataqué primero y leí `apply-2-constructor-F.md` al final (ver Contaminación).

## Veredicto

**FALLAS**: F1 a F7 corregidas; 2 fallas nuevas MENOR reproducidas. Ninguna BLOQUEANTE ni MAYOR.

| # | Severidad | Lente | Falla | Estado |
|---|---|---|---|---|
| F1 | MAYOR | integridad | Anclas no revalidadas al cambiar el esquema | **Corregida** |
| F2 | MENOR | bordes | Régimen no hashable da 500 | **Corregida** |
| F3 | MENOR | bordes | Esquema con lista donde va clave da 500 | **Corregida** |
| F4 | MENOR | bordes / cableado | Cerrar sin muestra "faltan 0" | **Corregida** |
| F5 | MENOR | integridad | TRUNCATE salta el append-only | **Corregida** |
| F6 | MENOR | bordes | CTR 200 no JSON da 500 | **Corregida en parte**: ver N2 |
| F7 | MENOR | docs | Referencia circular del meta-esquema | **Corregida** |
| N1 | MENOR | integridad / concurrencia | Deadlock entre el primer uso de una membresía y su revocación: 500 (era S1) | Nueva, reproducida |
| N2 | MENOR | bordes | La validación de forma del CTR no cubre `ts` ni los UUID: `ts` no ISO o `problema_id` que no es UUID siguen dando 500 | Nueva, reproducida |

## EVIDENCIA

Entorno: `cibse-test-pg` (`127.0.0.1:55432`, `CLASSIFIER_TEST_DB_URL=postgresql+asyncpg://classifier_user:***@127.0.0.1:55432/classifier_db`); para el smoke, `cibse-smoke-pg` (`:55433`) y `cibse-smoke-redis` (`:6379`) del constructor E, con su `scratchpad/smoke/start.sh` y `env.sh`. No toqué `seguridad_jwt_db` (5432), producción ni EasyPanel. Esquema v0: `/home/juanisarmiento/Documentos/MTAC/CIbSE2027_muestra_150/codebook/esquema_v0.json`.

### Corridas propias (453 tests ejecutados por mí, más 2 skips del smoke)

| Hora | Qué | Resultado |
|---|---|---|
| 14:24:05 | Reproducciones de verify-1 (`test_zz_breaker_unit.py`, `test_zz_breaker_ctr.py`, `test_zz_breaker_db.py`), sin cambios | `32 passed, 3 failed`. Las 3 fallan por **oráculos míos obsoletos**, no por defectos: F1 x2 congelan ahora con **422** (mis tests leían el ancla después de un congelado que ya no ocurre) y F4 responde **409 `"sin_muestra"`** (mi test esperaba un `detail` objeto). Salida: `regimen=list -> 400`, `ei=list -> 400`, `congelar -> 422`, `cerrar sin muestra -> 409 {"detail":"sin_muestra"}`, `TRUNCATE ... rechazado`; F6 (`200 no JSON`) pasa |
| 14:26:02 | `test_zz_breaker2_unit.py` (fuzz y cuerpos del CTR) | `16 passed, 5 failed`. Fuzz de `validar_esquema` (1188 sustituciones con dict, número, null, bool, listas, texto en cada nodo del v0): 0 excepciones. Fuzz de `evaluar_pedido` (209): solo 400/422. `errores_respuesta_esperada`: nunca lanza. Ejemplo del runbook y v0: `[]`. Cuerpos del CTR: vacío, HTML, `null`, `[]`, `events` dict o str, payload lista y `seq` str dan `CTRNoDisponibleError`; **sin `ts`, `ts` no ISO, `ts` número, `problema_id` no UUID y `ejercicio_id` basura pasan la validación y lanzan aguas abajo** (N2, 5 fallas por aserción) |
| 14:26:48 | `test_zz_breaker2_db.py` (HTTP) | `69 passed, 2 failed`. Detalle abajo |
| 14:27:09 | vitest `CodificacionEstudioView`, `mensajesError`, `AdministracionEstudioView` | `3 files, 55 passed` |
| 14:27:31 | `test_zz_breaker2_s1_db.py` (40 rondas guardar vs revocar) | `1 failed`: `{(200, 200): 1, (200, 500): 38, (500, 200): 1}` (N1) |
| 14:28:27 | script de S2 sobre `leer_episodios` | `502 devuelto con 0 lecturas terminadas`; `despues de responder siguieron 19 lecturas al CTR` |
| 14:28:37 | consumidores: `test_pedagogia_distribucion`, los 4 de `create_all`, `test_estudio_separacion_db`, `test_estudio_inmutabilidad_db` | `73 passed` |
| 14:28:47 | `apps/classifier-service/tests/test_auth.py` | `8 passed` |
| 14:28:47 | vitest `KappaRatingViewDotColor`, `rutasEstudio`, `rootModoRestringido`, `navegacionAlcanzable`, `docenteOnboarding` | `5 files, 89 passed` |
| 14:29:02 | `cibse-smoke-pg` classifier: `alembic downgrade 20260906_0006` con 16 estudios cargados, luego `upgrade head` | downgrade limpio: 0 tablas, 0 funciones `estudio_%`, 0 triggers; upgrade: `20261104_0007`, 6 triggers `sin_truncate`, RLS habilitado y forzado en las 9 tablas |
| 14:32:31 | `make test-smoke` (13 servicios + 8 workers de `start.sh`, gateway 503 por Keycloak ausente como en E) | **`100 passed, 2 skipped, 20 deselected`**, exit 0. Log: `scratchpad/breaker/smoke-verify2.log` |
| 14:33 | limpieza | servicios detenidos; maté 2 contenedores `eclipse-temurin:21-jdk` que dejó mi corrida (`test_smoke_java_execution`, el mismo síntoma que reportó E) |

### Ataques sobre las correcciones (`test_zz_breaker2_db.py`, todos verdes salvo N2)

- **F1**: el `PUT` con la regla cambiada responde 200 con `anclas_invalidas` (el ancla y el motivo `"regimen: la regla da 'superficial'..."`). Congelar da 422 `anclas_invalidas`, la versión queda en borrador y sin sha. Después de corregir el ancla, congela y el ancla es coherente con la regla congelada. Con una dimensión renombrada el motivo es `dimensión desconocida 'd1'`; si se vuelve al esquema original, el aviso queda vacío y congela. Un ancla exenta (`evidencia_insuficiente` con notas) sobrevive al cambio de regla, y un exento renombrado la invalida (422). Una v1 clonada de una v0 congelada, con esquema nuevo, también da 422 al congelar.
- **F2**: `PUT mi-etiqueta` con `{"a":1}`, `7`, `null`, `[["x"]]` y `true` en `regimen`, `regimen_propuesto`, `confianza`, `notas`, `es_frontera` y `respuestas`: 30 casos, todos 200, 400 o 422 y ningún 500.
- **F3**: `PUT codebook` con 14 sustituciones de tipo (dict, número y null en `regimen_evidencia_insuficiente` y `regimen_por_defecto`, entre otras): todas 400.
- **F4**: cerrar sin muestra da 409 `sin_muestra`; el investigador recibe 403. En el panel, el estado vacío y el 409 están cubiertos por los tests del constructor, que corrí (55 passed). `faltantesDe` ya no convierte una lista vacía en "Faltan 0".
- **F5**: `TRUNCATE` sin y con `CASCADE` sobre las 9 tablas del estudio. Sin `CASCADE`, las tablas referenciadas fallan por FK y las tres hojas inmutables por el trigger. Con `CASCADE`, las 9 dan `estudio_inmutable: TRUNCATE de <tabla> rechazado`. El downgrade lo verifiqué sobre una base con datos (arriba).
- **F6**: los cuerpos raros de forma ya dan 502. Lo que queda es N2.

### N1 (MENOR): deadlock entre primer uso y revocación

Pasos: estudio listo (`preparar(1)`). En 40 rondas, el investigador da de alta un codificador nuevo, sin atar, y en paralelo (`asyncio.gather`) el codificador hace su primer `PUT mi-etiqueta` y el investigador lo revoca.
```
BREAKER2 S1 (guardar, revocar): {(200, 200): 1, (200, 500): 38, (500, 200): 1}
E       AssertionError: ...
```
Log de Postgres (`docker logs cibse-test-pg`):
```
ERROR:  deadlock detected
DETAIL:  Process 10152 waits for ShareLock on transaction 24881; blocked by process 10153.
	Process 10153 waits for ShareLock on transaction 24880; blocked by process 10152.
	Process 10152: UPDATE estudio_membresia SET revocada_at=... RETURNING ...
	Process 10153: SELECT estudio_codificacion... FOR SHARE
```
Causa: `require_membresia` ata el `user_id` (`UPDATE estudio_membresia`) **antes** de que `bloquear_para_codificar` tome el estudio `FOR SHARE`. La revocación toma el estudio `FOR UPDATE` y después actualiza la membresía. Es el orden inverso de D10b ("siempre: fila del estudio, luego fila de la membresía"). El mismo patrón está en `investigador_con_estudio_bloqueado` (primer uso del investigador contra una revocación del admin). No es una falla de integridad: Postgres aborta una de las dos transacciones y la otra queda bien. Pero el usuario recibe 500. En producción es poco probable, porque el primer uso suele ser `mis-membresias` al entrar al panel.

### N2 (MENOR): forma del CTR incompleta

`ctr_lectura.py::tiene_forma_de_episodio` valida tipos de `estado`, `problema_id` (str), `events_count`, `last_chain_hash`, `events` y, por evento, `seq`, `event_type`, `chain_hash` y `payload`. No valida `ts` ni que `problema_id` y `ejercicio_id` sean UUID. Por HTTP, con un `CTRLector` real sobre `httpx.MockTransport`:
```
BREAKER2 F6 traza ts basura -> 500 Internal Server Error
E       assert 500 == 502
BREAKER2 F6 muestra problema no UUID -> 500 Internal Server Error
E       assert 500 in (422, 502)
```
Por unidad: `sin_ts` y `ts_numero` dan `AttributeError`, y `ts_basura`, `problema_no_uuid` y `ejercicio_basura` dan `ValueError` en `filtrar_traza` o `evidencia_fija`. El ctr-service real serializa con Pydantic (`EventOut.ts: datetime`, `problema_id: UUID`), así que solo pasa con un intermediario o un CTR roto. La spec pide 502 genérico ante un error del registro.

## Cobertura por lente (sobre lo que tocaron las correcciones)

1. **Ciego**: LIMPIO. `anclas_invalidas` y el 422 de congelar solo los ve el investigador (`investigador_con_estudio_bloqueado`). `sin_muestra` no lleva datos. Los 502 del CTR siguen genéricos.
2. **Acceso**: LIMPIO. Sin cambios en `require_membresia`; `test_auth.py` y el test de firma siguen verdes. El investigador recibe 403 al cerrar.
3. **Integridad**: F1 y F5 corregidas; N1 nueva. La migración nueva baja y sube limpia con datos.
4. **Régimen**: `errores_respuesta_esperada` usa `evaluar_pedido` y agrega que el régimen guardado sea el de la regla de hoy; los exentos explícitos valen. Ver la observación O1.
5. **Bordes**: F2, F3 y F4 corregidas; F6 corregida en parte (N2).
6. **Exportación**: sin cambios en esta tanda; el smoke la recorre (100 passed).
7. **Cableado**: el front consume `anclas_invalidas` (`AdministracionEstudioView.tsx:392`, `avisoDeAnclas`) y `sin_muestra` (`mensajesError.ts`). Consumidores del piloto: `test_pedagogia_distribucion`, `create_all`, `test_auth`, `KappaRatingViewDotColor`, `navegacionAlcanzable`, `docenteOnboarding` y `rootModoRestringido`, todos verdes. Smoke completo verde con la migración nueva aplicada.
8. **Docs**: F7 corregida. La sección "Forma exacta del meta-esquema" del runbook es la canónica, su ejemplo valida (`[]`) y el ADR apunta ahí. El runbook documenta el aviso del `PUT` y el 422 de congelar. Observación menor: la tabla de tablas del runbook ("Inmutabilidad (trigger)") no menciona `TRUNCATE`.

## JUICIO

Autor: breaker verify-2. Comparación: código y docs del árbol `291628b1211abf5a` contra mis reproducciones de verify-1, el design D2, D9 y D10b, las specs y el runbook. Confianza alta en las correcciones (verifiqué cada una por HTTP y por fuzz) y en N1 y N2 (salida propia y log de Postgres).

- La corrección de F1 es buena: el gate quedó en congelar, que es lo que certifica el sha, y el aviso del `PUT` le deja al investigador una salida en los renombres.
- N1 contradice D10b y da 500 con una frecuencia alta cuando la carrera ocurre (39 de 40 rondas en proceso). Su probabilidad real es baja y no corrompe datos: MENOR. Se corrige atando después de los locks, o tomando el estudio antes de atar.
- N2 es el resto de F6: la validación cubre la forma pero no el formato de los campos que se parsean. MENOR.
- **O1 (observación, no falla)**: un ancla con `respuesta_esperada = {"respuestas": {}}` (sin dimensiones ni régimen) se crea y se congela (200). En la práctica, `coincide` le da siempre `false` al codificador. El constructor F decidió explícitamente no exigir completitud ("sería alcance nuevo"). Lo dejo para el planner o como DEUDA, no como defecto contra la spec.
- **S2 confirmada como comportamiento, no como defecto**: con un episodio que da 502, `leer_episodios` responde y deja 19 lecturas al CTR corriendo en segundo plano. No afecta datos ni la spec; es desperdicio contra el CTR.

## SUPOSICIÓN (sin reproducir)

- **S3**: celdas CSV que empiezan con LF o con espacios antes de `=` no se prefijan. La spec no las exige y no verifiqué el comportamiento de las planillas. Sigue igual.
- **S4 y S5** (régimen nulo con D3 vacía aunque la regla ya esté determinada; pasiva parcial sin cita deriva superficial): son coherentes con D9 y se mantienen como notas para el investigador, sin cambios.
- Las specs no tienen escenarios para "congelar con ancla inválida da 422" ni "cerrar sin muestra da 409". El constructor F también lo marcó.
- No ejecutado: CI, firma real del gateway contra ctr-service, Clerk, la suite completa del classifier (reusé `681 passed + 4 ambientales`, 14:19:25, del constructor F), analytics completo, `ruff` y `mypy` del repo.

## Fuentes leídas

Código del árbol nuevo: `services/estudio_esquema.py` (`_es_clave_de`, `_errores_de_campos`, `evaluar_pedido`, `errores_respuesta_esperada`), `routes/estudio.py` (`editar_version`, `_anclas_invalidas`, `congelar_version`), `routes/estudio_trabajo.py` (`cerrar_mi_codificacion`, `leer_episodios`), `services/ctr_lectura.py`, la migración 0007 (triggers de TRUNCATE y downgrade), `services/estudio_export.py` (`PELIGROSOS`); web-teacher `CodificacionEstudioView.tsx` (`faltantesDe` y el estado vacío), `mensajesError.ts`, `rg` de `anclas_invalidas` en `src`; `tests/integration/test_estudio_schema_db.py` (ciclo de migración); `docs/servicios/classifier-service.md` §12.2 y §12.6; `rg` del ADR-063; `scratchpad/smoke/{env.sh,start.sh}`. Mis informes y tests de verify-1.

## Contaminación

- Leí `informes/apply-2-constructor-F.md` **después** de atacar y de recalcular la huella final (14:33). Las reproducciones y los ataques los diseñé desde el código y desde el mensaje del orquestador, que listaba qué había cambiado. Del informe F tomé solo, para esta redacción, que la suite completa dio `681 passed` (no la repetí), que no exigir completitud de la respuesta esperada fue una decisión explícita (O1) y que re-migró `cibse-test-pg`. No leí el grupo 14 de `tasks.md`.
- Mismo proveedor y familia que todos los roles: no hay independencia por proveedor; sí por ejecución propia.
