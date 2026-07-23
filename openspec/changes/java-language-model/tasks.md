## 0. Antes de escribir código

- [x] 0.1 **Medir el daño potencial de la validación nueva.** Hecho el 2026-07-23 contra la base del piloto. Resultado: **169 de 169** asociaciones ejercicio–TP con peso `1.0000`; **25 de 27** TPs publicadas con suma de pesos ≠ 1.0; las 2 que cumplen lo hacen por tener un único ejercicio. Ningún cálculo de calificación consume el campo. **Consecuencia: la regla de pesos sale del scope** (D9). Con las reglas restantes, ninguna TP del piloto queda bloqueada.
- [x] 0.2 Confirmar en `packages/contracts` si `TpEjercicioCreate` se usa en algún caller fuera de `academic-service` antes de tocar la firma del validador.
- [ ] 0.3 Anotar como tickets propios los tres hallazgos fuera de scope del design: `peso_en_tp` decorativo, el "Peso: 100%" que ve el alumno hoy, y el valor por defecto del formulario que los origina.

## 1. Contratos (`packages/contracts`)

- [x] 1.1 `TestCaseSchema.type`: agregar `junit_assert` al `Literal` (`academic/ejercicio.py:142`).
- [x] 1.2 `_EjercicioBase`: agregar `language: Literal["python", "java"] = "python"` (`academic/ejercicio.py:152`).
- [x] 1.3 `TpEjerciciosValidator`: agregar la regla de no-vacío. Ojo con `validate_set()`, que hoy retorna conforme ante lista vacía (`ejercicio.py:278-279`) — la regla correcta es "tiene ejercicios **o** `test_cases` propios", no "tiene ejercicios".
- [x] 1.3b **Retirar la regla de suma de pesos** del validador, o dejarla inaplicable desde el llamador. Ver 0.1 y D9: es incompatible con el 100% de los datos del piloto y guarda un campo que ninguna calificación consume. Documentar el porqué en el docstring del validador, para que nadie la reintroduzca creyendo que fue un olvido.
- [x] 1.4 `TpEjerciciosValidator`: método nuevo que reciba los lenguajes ya resueltos por el servicio y valide unicidad + coincidencia con el de la TP. **No** extender `TpEjercicioCreate` con `language` — es un campo derivado y el cliente podría mentir (D6).
- [x] 1.5 Tests unitarios del validador: orden duplicado + ejercicio duplicado + no-vacío + monolítica válida + TP de un solo ejercicio + mezcla de lenguajes + TP declarada en un lenguaje con ejercicio de otro. **Más un test explícito de que pesos que no suman 1.0 NO bloquean** — es la regla que se retiró, y un test que lo afirme evita que vuelva por descuido.

**Aceptación**: `uv run pytest packages/contracts/tests -v` en verde.

## 2. Modelo y migración (`academic-service`)

- [x] 2.1 `Ejercicio.language` y `TareaPractica.language`: `String(20)`, `nullable=False`, `server_default="python"` (`models/operacional.py:408,214`). **Sin `CheckConstraint`** — D2.
- [x] 2.2 Migración `20260722_0001_ejercicio_tp_language.py`, `down_revision` apuntando al head vigente de academic (verificarlo, no asumirlo).
- [x] 2.3 **Migración idempotente desde el día uno**: chequear `information_schema.columns` antes de cada `ADD COLUMN`. No es paranoia — el PR #33 encontró una columna agregada a mano en prod salteándose Alembic, y no se sabe cuánta deriva más hay.
- [x] 2.4 Sin cambios de RLS: ambas tablas ya tienen policy activa; es `ADD COLUMN` sobre tabla existente (patrón de `20260615_0002_tarea_practica_permite_pausa`). Confirmar con `make check-rls`.
- [x] 2.5 `downgrade()` simétrico y guardado (dropear solo si existe).

**Aceptación**: `alembic upgrade head` y `alembic downgrade -1` corren limpios contra base limpia **y** contra una copia del schema de prod. `alembic check` no propone drift nuevo.

## 3. Schemas y endpoints (`academic-service`)

- [x] 3.1 `language` en los schemas de `Ejercicio` (create / update / out).
- [x] 3.2 `language` en los schemas de `TareaPractica`.
- [x] 3.3 `junit_assert` aplicado al `test_cases` de TP. Hoy es `list[dict[str, Any]]` suelto y no reusa `TestCaseSchema` (`schemas/tarea_practica.py`) — sin esto, las TPs monolíticas siguen aceptando cualquier `type` (D4). **No** unificar los dos caminos de tipado en esta change; es un refactor con radio propio.
- [x] 3.4 Filtro `?language=` en `GET /ejercicios` (`routes/ejercicios.py:57`) → `EjercicioService.list()` (`ejercicio_service.py:102-125`). El repositorio genérico lo resuelve sin cambios (`repositories/base.py:58-61`); es el mismo patrón que `materia_id`.

**Aceptación**: `GET /ejercicios?language=java` filtra; sin el parámetro devuelve todo; compone con `dificultad` y `materia_id`.

## 4. Validación de composición (`academic-service`)

- [x] 4.1 `TpEjercicioService.add_ejercicio()` (`tp_ejercicio_service.py:75-111`): bloquear lenguaje distinto. **La línea `await self.ejercicio_repo.get_or_404(ejercicio_id)` ya carga el `Ejercicio` y descarta el resultado** — capturarlo da el `language` sin ninguna query nueva.
- [x] 4.2 `TareaPracticaService.publish()` (`tarea_practica_service.py:216`): invocar el validador.
- [x] 4.3 🟢 **No escribir el SELECT explícito: reusar `TpEjercicioService.list_by_tp()`** (`tp_ejercicio_service.py:56`). Ya hace `select(TpEjercicio).options(selectinload(TpEjercicio.ejercicio))` y devuelve tuplas `(par, ejercicio)` — carga los pares con su ejercicio embebido, que es exactamente lo que necesita la validación de pesos y de lenguaje.
- [x] 4.3b 🔴 Lo que sigue siendo trampa: **nunca iterar `tp.tp_ejercicios`**. `get_or_404()` no hace eager-load, y el propio código de `new_version()` (`tarea_practica_service.py:324-328`) documenta que esa relación lazy revienta con `MissingGreenlet` en el driver async. Un `if not tp.tp_ejercicios` parece lo natural y falla en runtime (D7).
- [x] 4.4 Errores 422 con mensaje accionable: qué regla se violó y con qué valores. Un "422 Unprocessable Entity" pelado le hace perder la tarde al docente.

**Aceptación**: tests de integración cubriendo los 4 rechazos (orden duplicado, ejercicio duplicado, vacía, lenguajes mezclados) + los 4 caminos felices (TP compuesta válida, TP monolítica, TP de un solo ejercicio, ejercicio del mismo lenguaje) + el no-rechazo por pesos. Incluir un test que cubra el camino de carga de 4.3.

**Verificación contra datos reales**: con las reglas finales, las 27 TPs publicadas del piloto deben poder republicarse. Es el criterio que la medición de 0.1 dejó establecido.

## 5. Verificación de que la tesis no se movió

- [ ] 5.1 `uv run pytest apps/classifier-service/tests/unit/test_pipeline_reproducibility.py -v` en verde.
- [ ] 5.2 Confirmar que `LABELER_VERSION` no cambió y que `classifier_config_hash` para un mismo `(tree_version, reference_profile)` es idéntico al anterior.
- [ ] 5.3 Confirmar por grep que ningún archivo de `apps/classifier-service/src/` empezó a leer `language`. La invariante es que el clasificador no lo consuma — el día que lo haga deja de ser agnóstico y hay que auditar reproducibilidad de nuevo.

## 6. Smoke y cierre

- [ ] 6.1 Smoke test nuevo en `tests/e2e/smoke/`: crear ejercicio Java → crear TP Java → agregar el ejercicio → publicar → verificar 200. Y el camino negativo: agregar un ejercicio Python a esa TP → 422. Es lo que atrapa la clase de bug que escapa a los unit tests con DB mockeada.
- [ ] 6.2 `make test-fast` y `make check-rls` en verde.
- [ ] 6.3 Actualizar `CLAUDE.md` si el conteo de smoke tests cambió (lo verifica `scripts/check-claude-md.py` en CI).

## Fuera de scope (a propósito)

- UI del docente y del alumno → `java-authoring-experience`
- Ejecución de Java → `java-execution-engine`
- Segmentación por lenguaje en analytics → `multi-language-research-integrity`
- Unificar el tipado de `test_cases` entre `Ejercicio` y `TareaPractica` → refactor aparte
- Sacar el `|| echo 'WARN: alembic failed, continuing'` de los Dockerfiles → ticket propio, heredado de la revisión del PR #33
