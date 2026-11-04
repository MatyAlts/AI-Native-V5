# Informe verify-2-planner-specs

- Change: `cibse-codificacion-ciega`
- Rol: planner (corrección menor de specs posterior a la construcción, pedida por el orquestador)
- Ejecutor declarado: subagente nativo de Claude Code (role planner), familia Anthropic.
- Revisión leída: árbol de trabajo sobre `b32e621` con la corrección del constructor F (`informes/apply-2-constructor-F.md`, tasks grupo 14). No se tocó código, proposal, design ni tasks.
- Archivos modificados: `specs/codebook-versionado/spec.md` (sha256 12 primeros `6f4b9592f56a`) y `specs/estudio-codificacion/spec.md` (`79f98a10fe2f`).

## Disposición

| Pedido | Spec y ubicación | Forma tomada del código |
|---|---|---|
| (a) F1 aviso en el PUT y 422 al congelar | codebook-versionado, requisito nuevo "Revalidación de anclas al editar el esquema y al congelar" con 3 escenarios | `routes/estudio.py`: `VersionEditadaOut.anclas_invalidas: list[AnclaInvalidaOut]` con `item_id`, `uso`, `orden`, `motivos` (l. 445-458, 555-578); `congelar_version` responde `HTTP_422` con `detail={"codigo": "anclas_invalidas", "anclas": [...], "errores": [...]}` y no cambia estado (l. 620-640). Casos de los escenarios: los 4 de `test_ancla_que_no_valida_contra_el_esquema_vigente_impide_congelar` (regla, dimensión renombrada, valor quitado, regla sin d4) y `test_ancla_exenta_sigue_valida_con_otra_regla` |
| (b) F4 cerrar sin muestra | estudio-codificacion, requisito "Cierre de la codificación", escenario nuevo "Cierre sin muestra cargada" | `routes/estudio_trabajo.py:769`: `raise _conflicto("sin_muestra")`, y `_conflicto` (l. 94-95) es `HTTPException(409, detail=codigo)`: el `detail` es la cadena `sin_muestra`, no un objeto. El chequeo ocurre después de `bloquear_para_codificar` y `vigente_congelada`, así que el escenario parte de un codebook vigente congelado (igual que `test_cerrar_sin_muestra_cargada_da_409_sin_muestra`, que llama `estudio_http.codebook()` antes) |
| (c) F5 TRUNCATE bloqueado | estudio-codificacion, requisito nuevo "Tablas inmutables protegidas contra TRUNCATE" con 3 escenarios | Migración `20261104_0007_estudio_codificacion.py:430-524`: función `estudio_sin_truncate` con mensaje `estudio_inmutable: TRUNCATE de % rechazado` y trigger `BEFORE TRUNCATE ... FOR EACH STATEMENT` en las 6 tablas de `_TABLAS_SIN_TRUNCATE`. Escenarios según `test_estudio_inmutabilidad_db.py:390-450` (las 6 tablas con `CASCADE`, cascada desde `estudio_codificacion`, historial que sobrevive) |

## EVIDENCIA

| Comando / lectura | Momento | Resultado |
|---|---|---|
| `rg anclas_invalidas|sin_muestra|TRUNCATE` en `apps/classifier-service/{src,alembic,tests}` | 04/11 ~14:20 | ubicaciones citadas arriba |
| Lectura de `tasks.md` grupo 14 (14.1 F1) | 04/11 | coincide con el código: el PUT avisa y congelar rechaza con `{codigo, anclas, errores}` |
| `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T14:24:32-03:00 | `Change 'cibse-codificacion-ciega' is valid` |

## JUICIO

Autor: planner. Comparé el informe del breaker (`verify-1-breaker.md`, filas F1, F4 y F5) y la tarea 14.1 con el código y los tests. **No encontré diferencias de comportamiento** (confianza alta).

Dos precisiones de forma, que no son discrepancias:
- F4: el `detail` del 409 es la cadena `"sin_muestra"`, no un objeto con `codigo`, a diferencia del 422 de F1.
- F5: el trigger cubre seis tablas, más que las dos que reprodujo el breaker (historial y entrenamiento). Coincide con lo que D2 declara inmutable.

## SUPOSICIÓN

- No ejecuté los tests: me apoyo en el código leído y en los registros RED/GREEN del constructor en tasks 14.1. No corrí Postgres.
- No leí `apply-2-constructor-F.md` entero; solo la tarea 14.1 de tasks y las filas F1, F4 y F5 del breaker.

## Fuentes leídas

- `apps/classifier-service/src/classifier_service/routes/estudio.py:445-640`, `routes/estudio_trabajo.py:94-95, 599-640, 750-790`.
- `apps/classifier-service/alembic/versions/20261104_0007_estudio_codificacion.py:430-524`.
- `apps/classifier-service/tests/integration/{test_estudio_anclas_db.py:210-285, test_estudio_etiquetas_db.py:190-200, test_estudio_inmutabilidad_db.py:390-450}`.
- `tasks.md` grupo 14; `informes/verify-1-breaker.md` (tabla de hallazgos y conclusiones).

## Contaminación por informes ajenos

El encargo proviene del informe del breaker y del registro del constructor. Contrasté las afirmaciones relevantes contra el código; no quedan conclusiones copiadas sin verificar, salvo el resultado de los tests (ver SUPOSICIÓN).
