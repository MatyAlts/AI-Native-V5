# apply-1-constructor-B: tanda B (grupos 6 a 10, más 5.2, 5.3 y A4-2)

- Rol: constructor. Fase apply, intento 1, tanda B: 6 traza ciega; 7 muestra, orden, enunciados y anclas; 8 etiquetado, cierre, concurrencia, aislamiento y separación; 9 entrenamiento; 10 exportación. Agregados del orquestador, dentro del alcance aprobado: (a) A4-2 del plan-reviewer (alertas de rúbrica, tests, pistas y solución), (b) tareas nuevas 5.2 y 5.3 (lecturas para el panel 11.8), (c) propuesta para correr los tests `_db` en CI (abajo, sin cambiar CI).
- Ejecutor: subagente nativo Claude Code (familia Anthropic; el mismo que la tanda A). Fecha: 04/11/2026, 12:50 a 13:25 (-03:00).
- Revisión: árbol de trabajo sobre `origin/main b32e621` (rama `feat/cibse-codificacion-ciega`), sin commits. Archivos de esta tanda y sha256 (primeros 16 hex) al cierre (bajo `apps/classifier-service/`):

| Archivo | Estado | sha256 |
|---|---|---|
| `src/classifier_service/routes/estudio_trabajo.py` | nuevo (router de grupos 6 a 10) | `900524444d623a49` |
| `src/classifier_service/routes/estudio.py` | modificado: 5.2, 5.3, `versiones` reservada, `investigador_con_estudio_bloqueado` y `version_out` públicos | `b6d588d093e58e3d` |
| `src/classifier_service/main.py` | modificado: registra `estudio_trabajo.router` | `f9d543669d2b10fa` |
| `src/classifier_service/services/traza_ciega.py` | completado (lista blanca y `filtrar_traza`) | `4824aa5555626b61` |
| `src/classifier_service/services/ctr_lectura.py` | nuevo | `85c0050d630a33a9` |
| `src/classifier_service/services/estudio_enunciados.py` | nuevo | `39fbb59926aa277b` |
| `src/classifier_service/services/estudio_muestra.py` | nuevo | `a2e5fcafb188f036` |
| `src/classifier_service/services/estudio_orden.py` | nuevo | `55ad5dfaace7a4d7` |
| `src/classifier_service/services/estudio_export.py` | nuevo | `cfd08f986a68320b` |
| `src/classifier_service/services/estudio_esquema.py` | sin cambios desde la tanda A | `4e1ea7ac8730427a` |
| `tests/integration/conftest.py` | modificado: `CTRFalso`, `EstudioHTTP`, fixtures `ctr_falso`, `estudio_http`, `esquema_prueba`, `etiqueta_reflexiva` | `540494227b2805ea` |
| `tests/integration/test_estudio_traza_db.py` | nuevo, 17 | `df18a581bcbfba32` |
| `tests/integration/test_estudio_muestra_db.py` | nuevo, 21 | `ca7459717f586bb5` |
| `tests/integration/test_estudio_enunciados_db.py` | nuevo, 14 | `9761d6da2b35a380` |
| `tests/integration/test_estudio_anclas_db.py` | nuevo, 16 | `1395a48375a5fc1d` |
| `tests/integration/test_estudio_etiquetas_db.py` | nuevo, 18 | `f77a24bd16215686` |
| `tests/integration/test_estudio_concurrencia_db.py` | nuevo, 3 | `2781c4bc9e8a7b7d` |
| `tests/integration/test_estudio_separacion_db.py` | nuevo, 1 | `57f4bd17204e82b7` |
| `tests/integration/test_estudio_entrenamiento_db.py` | nuevo, 11 | `108aad4f12490bb7` |
| `tests/integration/test_estudio_exportacion_db.py` | nuevo, 11 | `cdce0136e5b31c6f` |
| `tests/integration/test_estudio_panel_db.py` | nuevo, 10 | `b37883fde9a47991` |
| `tests/integration/test_estudio_acceso_db.py` | modificado: +7 rutas en el test de 401 | `ea209e7cb7af9820` |
| `tests/unit/test_traza_ciega.py` | nuevo, 17 | `61c2d9fe50627437` |
| `tests/unit/test_ctr_lectura.py` | nuevo, 9 | `128552e879e534ea` |
| `tests/unit/test_estudio_enunciados.py` | nuevo, 35 | `d6258e9eb1434665` |
| `tests/unit/test_estudio_orden.py` | nuevo, 5 | `4a924dcd42c7bcc4` |
| `tests/unit/test_estudio_export.py` | nuevo, 13 | `4c38ccd6b3243750` |

`ruff format` también reformateó archivos de la tanda A (`test_estudio_codebook_db.py`, etc.) sin cambiar su comportamiento; los demás sha de la tanda A siguen como en su informe salvo `routes/estudio.py`, `main.py` y `conftest.py`. Además: `tasks.md` (evidencia bajo 6.1 a 10.2, tareas nuevas 5.2 y 5.3, cierre de la tanda en "Registro del constructor"; "Estado de orquestación" sin tocar) y la fila en `informes/LEEME.md`. No se tocó `apps/web-teacher` ni otros servicios.

## EVIDENCIA

Detalle por tarea (comandos, timestamps, salidas, mutantes) en `tasks.md`. Resumen:

- **Entorno**: Postgres efímero `cibse-test-pg` (`127.0.0.1:55432`, migrado a `20261104_0007`), `CLASSIFIER_TEST_DB_URL` apuntando ahí; CTR reemplazado por un falso inyectado con `app.dependency_overrides[get_ctr_lector]`.
- **RED por aserción antes de producción en cada tarea**: 6.1 (12:52:36), 6.3 cliente (12:54:50) y endpoint (12:56:45), 7.0 (12:58:40), 7.2 (12:59:53), 7.1 (13:01:32), 7.2b (13:05:20), 8.1 y 8.3 (13:06:54), 7.3 (13:09:43), 9.1 (13:13:55), 10.1 (13:15:22), 10.2 (13:16:30), 5.2 y 5.3 (13:19:30). En 7 archivos el primer RED tenía fallos por `KeyError`/`IndexError`/`TypeError`/`StopIteration` del propio test; se reescribieron y se volvió a observar RED por aserción antes de escribir producción. Stubs sin comportamiento declarados en 6.1, 6.3, 7.0, 7.2 y 10.1.
- **Nacidos verdes** (declarados en cada tarea y cubiertos por mutantes): casos de 404 que coincidían con "ruta inexistente" (6.3, 7.2b, 8.1, 9.1), controles triviales con stub (6.1, 7.0, 7.2), y los tests de 8.2 y 8.4, que verifican propiedades del código de 8.1.
- **Concurrencia (8.2)**: barrera real. El test toma `FOR UPDATE` del estudio, espera en `pg_stat_activity` a que los dos pedidos estén bloqueados (con `pg_stat_clear_snapshot()` en cada sondeo; sin eso la vista queda congelada en la transacción) y suelta. Si los pedidos no se bloquean, el test falla. El mutante del plan (sin `FOR UPDATE` de la membresía) produjo `(200, 200)`: cierre con una etiqueta incompleta.
- **Mutantes**: 73 únicos en la tanda, todos muertos por aserción al final y todos revertidos (búsqueda de restos en `src/`: ninguno). Tres sobrevivieron y obligaron a reforzar tests: `disiente_de_regla` = "hay propuesto" (10.1), posición calculada sin la semilla con 2 ítems (10.2) y `vigente` = "congelada" (5.3). Seis murieron primero por excepción del test y se re-corrieron tras agregar `_sd(r)`. Una tanda de 3 mutantes (7.2) fue inválida por un error mío al invocar el script; se endureció `mutar.py`: exige archivo de test existente, `-k` no vacío, `returncode == 1` y una línea `E` de aserción, y se re-corrió.
- **Cierre de la tanda (una vez, árbol entregado)**:
  - 13:20:54 `uv run pytest apps/classifier-service -q -rs` -> `4 failed, 617 passed`, sin skips (+208 contra la tanda A). Los 4 son los de la línea de base (URL `:5432` fija en su propio archivo).
  - 13:21:59 los 4 archivos de `create_all` -> `36 passed`. 13:22:01 analytics -> `182 passed`. 13:18:45 `test_pedagogia_distribucion.py` -> `2 passed`.
  - 13:23:34 `make check-rls` -> `[OK]`; `alembic current` -> `20261104_0007 (head)`.
  - `ruff check apps/classifier-service` -> limpio; `ruff format --check` -> `93 files already formatted`; `mypy apps/classifier-service/src` -> `no issues found in 39 source files`.

## JUICIO

Autor: constructor B. Comparación: implementación contra design D4, D4b, D5, D6, D7, D9, D10, D10b, D11, D12 y D14, las specs `traza-ciega-episodio`, `estudio-codificacion`, `entrenamiento-calibracion` y `estudio-codificacion-exportacion`, y el contrato que asumió el front (`informes/apply-1-constructor-C.md`, "Contrato HTTP asumido"). Confianza: alta en lo cubierto por tests y mutantes; media en la integración con el front, por las diferencias de abajo.

- Tareas cerradas: 5.2, 5.3, 6.1, 6.2, 6.3, 7.0 (con A4-2), 7.1, 7.2, 7.2b, 7.3, 8.1, 8.2, 8.3, 8.4, 9.1, 10.1, 10.2. Abiertas: ninguna de esta tanda.
- **Defensa en profundidad observada**: tres mutantes que sacaban un control de la API murieron con 500 en vez del 409 esperado, porque la base igual frenó la operación: anclas en versión congelada (trigger), texto distinto sobre un enunciado revisado (trigger) y reemplazo de muestra con etiquetas (FK). La aserción sobre el 409 es la que detecta la falta del control de aplicación.
- **Decisiones de interpretación**:
  1. La traza resuelve solo `item_id` de muestra o anclas del estudio del caller. El chequeo de `traza_version` va después de resolver el ítem y antes de pedir al CTR; un enunciado pendiente da 409 sin llamar al CTR. Un episodio que desapareció del CTR se trata como `evidencia_alterada`.
  2. `GET mi-etiqueta` sin guardar devuelve la etiqueta vacía (spec "Pedir la etiqueta de otro"), no 404 como asumió el front.
  3. El bloqueo por enunciados de la codificación usa solo los requeridos por la MUESTRA. La cobertura y la carga incluyen además los de las anclas. El entrenamiento filtra ancla por ancla.
  4. Respuesta esperada de un ancla: se guarda normalizada con el régimen DERIVADO por la regla (`{respuestas, regimen, regimen_propuesto, es_frontera, confianza, notas}`); eso es lo que entra al sha del codebook.
  5. Solo se responden prácticas (`uso = practica`) de la vigente con enunciados listos. La devolución agrega `coincide` (régimen derivado igual al esperado).
  6. 5.3: el codificador ve versiones no vigentes con texto y esquema, pero de las anclas solo `item_id`, uso y orden. La explicación de una práctica revela la respuesta, y el `episode_id` no se expone (D5).
  7. Exportación de entrenamiento: las columnas de dimensiones son la unión de los esquemas de las versiones respondidas, en orden de aparición.

### Forma exacta del meta-esquema (para el esquema JSON del codebook v0)

Validado por `services/estudio_esquema.py::validar_esquema`. Objeto cerrado: una clave desconocida en cualquier nivel es error 400.

```json
{
  "dimensiones": [                       // obligatorio, 1 a 8
    {"clave": "d1",                      // ^[a-z][a-z0-9_]{0,39}$, única
     "nombre": "Texto visible",          // no vacío
     "valores": ["presente", "ausente"], // 2 a 6 textos distintos
     "cita_requerida_si": ["presente"]}  // subconjunto de valores ([] si ninguno)
  ],
  "regimenes": [{"clave": "reflexiva", "nombre": "Reflexiva"}],   // obligatorio, 2 a 6, misma regla de clave
  "regimen_evidencia_insuficiente": "evidencia_insuficiente",    // obligatorio, una clave de regimenes
  "regimenes_exentos": ["evidencia_insuficiente"],               // opcional; default [regimen_evidencia_insuficiente]; debe incluirlo
  "dimensiones_opcionales_si_regimen": ["evidencia_insuficiente"], // opcional; claves de régimen
  "notas_obligatorias_si_regimen": ["evidencia_insuficiente"],     // opcional; claves de régimen
  "marca_frontera": true,                                          // opcional, bool (default false)
  "notas_obligatorias_si_frontera": true,                          // opcional, bool; exige marca_frontera = true
  "confianza": null,                                               // opcional: null o {"valores": [1+ textos distintos], "obligatoria": bool}
  "reglas_regimen": [                                              // opcional, lista ORDENADA; [] = el codificador elige
    {"regimen": "reflexiva",                                       // régimen declarado y NO exento
     "condicion": [                                                // conjunción (AND), lista no vacía de cláusulas
       [{"dimension": "d1", "en": ["presente"]}],                  // cláusula = disyunción (OR), lista no vacía de átomos
       [{"dimension": "d2", "en": ["presente"]}, {"dimension": "d3", "en": ["presente"]}],
       [{"dimension": "d4", "en": ["interlocutor"]}]
     ]},
    {"regimen": "pasiva",
     "condicion": [[{"dimension": "d4", "en": ["transferencia"], "con_cita": true}],
                   [{"dimension": "d1", "en": ["ausente"]}]]}
  ],
  "regimen_por_defecto": "superficial"   // obligatorio si hay reglas, PROHIBIDO si no hay; declarado y no exento
}
```

Semántica:
- Átomo: se cumple si el valor de la dimensión está en `en`; con `con_cita: true` además exige cita no vacía (sin contar espacios).
- Régimen de la regla: `null` si alguna dimensión referenciada por CUALQUIER regla no tiene valor. Si no, es el de la primera regla que se cumple, o `regimen_por_defecto`.
- Un exento elegido explícitamente se persiste y `regimen_regla` se calcula igual.
- Cierre: exige régimen. Exige las dimensiones salvo si el régimen está en `dimensiones_opcionales_si_regimen`. Exige cita cuando el valor está en `cita_requerida_si`. Exige notas si el régimen está en `notas_obligatorias_si_regimen`, si hay frontera con `notas_obligatorias_si_frontera`, o si hay `regimen_propuesto`. Exige confianza si es obligatoria.
- Los comentarios `//` del bloque son explicativos: el JSON real no los lleva.

### Diferencias de contrato con el front (para corregir `apps/web-teacher/src/lib/estudioApi.ts`; rutas relativas a `/api/v1/interrater/estudios`)

| # | Función del front | Asumido por el front | Backend entregado | Motivo |
|---|---|---|---|---|
| 1 | `revocarMembresia` | `DELETE /{clave}/membresias` con `{email}` en el cuerpo | `DELETE /{clave}/membresias/{membresia_id}`, sin cuerpo; el id sale de `GET /{clave}/membresias` (5.2) | Tanda A, D3: el email no viaja en URL ni en logs; DELETE con cuerpo no es portable |
| 2 | `listarVersiones` | `GET /{clave}/codebook` | `GET /{clave}/codebook/versiones` (mismos campos `{etiqueta, estado, contenido_sha256, congelada_at, vigente}`); detalle en `GET /{clave}/codebook/versiones/{etiqueta}` | Pedido del orquestador (5.3) |
| 3 | `fijarVigente` | `POST /{clave}/codebook/{etiqueta}/vigente` | `PUT /{clave}/codebook-vigente` con `{etiqueta}` | Tanda A, ya probada; no la cambié por estar fuera de esta tanda |
| 4 | `editarVersion` (400) | `detail` = lista de errores FastAPI | `detail` = `{mensaje, errores: [str]}` | Tanda A |
| 5 | `miEtiqueta` | ítem nunca guardado: 404 | 200 con etiqueta vacía (`respuestas: {}`, regímenes `null`, `updated_at: null`) | Spec "Pedir la etiqueta de otro": etiqueta vacía de A |
| 6 | `miEtiqueta` / `guardarMiEtiqueta` | `notas: string` | `notas: string \| null`; agrega `disiente_de_regla` | Persistencia real; el campo extra no rompe |
| 7 | `cerrarMiCodificacion` (422) | `{codigo: "incompleta", faltantes: [{item_id, posicion, motivos}]}` | igual, más `faltan` (cantidad) | Alineado |
| 8 | `enunciados` | `cobertura: {requeridos, cargados, revisados, faltantes}`; enunciado sin sha | agrega `cobertura.sin_revisar` y `sha256_original`/`sha256_mostrado` por enunciado | Campos extra |
| 9 | `responderPractica` | `{regimen, regimen_regla, regimen_propuesto, esperada, explicacion_md}` | igual, más `coincide` | Campo extra |
| 10 | códigos de error | conoce `evidencia_alterada`, `traza_version_distinta`, `enunciado_pendiente`, `enunciados_pendientes`, `sin_codebook`, `codebook_borrador`, `codificacion_cerrada` | además: 409 `enunciado_revisado`, `episodio_es_ancla`, `muestra_con_etiquetas`, `episodio_en_muestra`, `version_congelada`, `ancla_con_respuestas`; 422 con `detail: {codigo}` en `sha256_distinto`, `csv_invalido` (+`errores`), `episodios_invalidos` (+`errores`), `pedido_invalido` (+`errores`), `episodio_inexistente`, `episodio_no_terminado`, `incompleta` | El panel cae a `formatApiError`: funciona, pero conviene mapearlos |
| 11 | anclas | GET, POST y DELETE | además `PUT /{clave}/codebook/{etiqueta}/anclas/{item_id}` (edición en borrador) | El plan pide edición (7.3) |
| 12 | choque de rutas que señaló el front | `GET /{clave}/codebook/vigente` contra `/{etiqueta}` | no hay choque: son métodos distintos (GET contra PUT) y `vigente` y `versiones` son etiquetas reservadas (422 al crearlas) | |

Sin diferencias en: traza (`{traza_version, enunciado: {tp_md, ejercicio_md}, elementos: [{n, tipo, t_seg, k, datos}]}`), `misItems`, `cargarMuestra` (cuerpo crudo `text/csv`, `?sha256_esperado=`, `{items, sha256}`), `cargarEnunciados` (crudo, `{cobertura, ignoradas}`), `revisarEnunciado`, `progreso`, `entrenamiento`, `exportar`, `codebookVigente`, `crearEstudio`, `asignarMembresia`, `misMembresias`, `crearVersion`, `congelarVersion`.

### (c) Propuesta para correr los tests `_db` en CI (sin cambios hechos; DEUDA o decisión)

Hoy el job `test-unit` corre solo `apps/*/tests/*.py` y `apps/*/tests/unit/`, y `migrations-dry-run` solo migra academic. Ningún test `_db` del classifier ni la migración `0007` se verifican en CI. Propuesta:
1. Job nuevo `test-classifier-db` con servicio `pgvector/pgvector:pg16` en 5432 (la misma imagen del dev local) y, como `test-unit`, `psql -f infrastructure/postgres/init-dbs.sql`.
2. `cd apps/classifier-service && CLASSIFIER_DB_URL=postgresql+asyncpg://classifier_user:classifier_pass@localhost:5432/classifier_db uv run alembic upgrade head`, con el usuario dueño y NO superuser, para que RLS forzado aplique.
3. `CLASSIFIER_TEST_DB_URL=<la misma> CLASSIFIER_TEST_MIGRATION_CYCLE=1 uv run pytest apps/classifier-service/tests/integration -rs`.
4. Convertir el skip en falla en CI. Hoy, sin Postgres, `requires_local_postgres` y la fixture `test_db_url` saltean, y un skip no rompe el job. Propuesta: una variable `CLASSIFIER_TEST_REQUIRE_DB=1` que haga que `test_db_url` llame a `pytest.fail` en vez de `pytest.skip`. Queda como cambio de `conftest.py` en un change propio.
5. Agregar classifier a `migrations-dry-run` (`upgrade head`, `downgrade -1`, `upgrade head`) y correr `make check-rls` después.

Costo estimado: un job de alrededor de 1 min (hoy la suite de integración del classifier tarda unos 30 s contra la base local). Los 4 tests previos con URL `:5432` fija pasarían en CI, porque ahí el 5432 es el Postgres del job.

## SUPOSICIÓN

- No medí la latencia real del CTR: la carga simulada de 150 ítems tarda 0,04 s con el CTR falso (concurrencia 8). El riesgo frente al timeout de 120 s del gateway sigue sin verificar.
- No verifiqué contra un ctr-service real la forma de la respuesta (`EpisodeWithEvents`) ni el rol `classifier_worker` con `REQUIRE_GATEWAY_SIGNATURE` encendido. Lo leí en el código (`schemas`, `auth/dependencies.py`), no lo ejecuté. El follow-up del plan ya lo pide.
- `ejercicio_id` se toma del payload de `episodio_abierto`; `problema_id`, del episodio. Leído en `contracts/ctr/events.py` y en `EpisodeOut`; con datos reales no se verificó.
- La barrera de 8.2 depende de que la cuenta de pruebas vea `pg_stat_activity` de su propio rol (cierto para `classifier_user`). Con otro usuario de CI habría que revisarlo.
- No ejecutado: tests del web-teacher (tanda C), `ruff`/`mypy` del repo entero, `make test-smoke`, recorrido con Clerk real.
- Los tests HTTP commitean bajo tenants aleatorios y dejan filas inmutables en la base efímera (declarado en `conftest.py`).

## Fuentes leídas

`proposal.md`, `design.md`, `tasks.md`; `specs/traza-ciega-episodio/spec.md`, `specs/entrenamiento-calibracion/spec.md`, `specs/estudio-codificacion-exportacion/spec.md` y `specs/estudio-codificacion/spec.md` (releída de la tanda A); `CLAUDE.md` del repo; código: `services/clients.py`, `routes/classify_ep.py::_fetch_episode_from_ctr`, `routes/interrater.py` (ratings y my-progress), `apps/ctr-service/src/ctr_service/schemas` (`EventOut`, `EpisodeOut`, `EpisodeWithEvents`), `apps/ctr-service/src/ctr_service/auth/dependencies.py` (headers y `READ_ROLES`), `packages/contracts/src/platform_contracts/ctr/events.py` (payloads y `Literal` de `event_type`), `packages/observability/.../gateway_trust.py::sign_headers`; `.github/workflows/ci.yml` (jobs `test-unit` y `migrations-dry-run`, leídos en la tanda A). Lecciones L-NNN: no existen en el repo (búsqueda de la tanda A, sin cambios).

## Contaminación por informes previos

- Leí, por pedido explícito del orquestador, el hallazgo A4-2 de `informes/propose-4-plan-reviewer.md` (solo esa sección y su contexto inmediato) y la tabla "Contrato HTTP asumido" de `informes/apply-1-constructor-C.md` (líneas 150 a 200). También leí, sin modificarlo, `apps/web-teacher/src/lib/estudioApi.ts`, para alinear formas de respuesta. Esa lectura orientó las formas de los grupos 6 a 10 donde el design dejaba margen; las diferencias están listadas arriba.
- No usé conclusiones de otros informes como evidencia: todo lo afirmado arriba sale de corridas propias.
