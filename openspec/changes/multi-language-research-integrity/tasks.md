## 1. Gate de decisión (bloquea el resto)

- [ ] 1.1 Llevarle a Cortez la pregunta del constructo: ¿apropiación es transferible entre lenguajes? Presentar las tres salidas del design (covariable / dos variables / recalibración) con su costo respectivo.
- [ ] 1.2 Registrar la respuesta como ADR nuevo. El número siguiente libre es 058 — verificarlo, no asumirlo: ADR-034 ya está tomado por `034-test-cases-como-jsonb-en-tareas-practicas.md`.
- [ ] 1.3 Si la respuesta es "dos variables", agregar al scope el bloqueo de exports mixtos (hoy solo se declara la mezcla, no se rechaza).

## 2. Lenguaje en el payload de apertura

- [x] 2.1 Agregar el campo de lenguaje a `EpisodioAbiertoPayload` con default, en `packages/contracts/src/platform_contracts/ctr/events.py:46-81`.
- [x] 2.2 Test que confirme que un evento histórico sin el campo sigue deserializando.
- [x] 2.3 Test golden de `self_hash`: un evento previo al cambio conserva su hash calculado contra el modelo viejo.
- [x] 2.4 Resolver el lenguaje en `tutor-service` al abrir el episodio, desde la respuesta de `AcademicClient` que ya se consulta para validar las 6 condiciones de apertura. Implementado para ambos caminos (Ejercicio del banco vía `get_ejercicio_by_id` y TP monolítica vía `get_tarea_practica_full` — ambos exponen `language` desde epic `java-language-model`, cerrado y verificado contra código real).
- [x] 2.5 Ignorar explícitamente cualquier lenguaje que venga en el cuerpo de la petición, con test que lo cubra.
- [x] 2.6 Test de que reabrir o reanudar un episodio no reescribe el lenguaje del evento de apertura original.

## 3. Verificación de neutralidad sobre la tesis

- [x] 3.1 `uv run pytest apps/classifier-service/tests/unit/test_pipeline_reproducibility.py -v` en verde.
- [x] 3.2 Confirmar que `classifier_config_hash` no cambió para un mismo `(tree_version, reference_profile)`.
- [x] 3.3 Confirmar que `LABELER_VERSION` no cambió.
- [x] 3.4 Verificar la cadena criptográfica de un episodio anterior al cambio y confirmar que pasa sin discrepancias.

## 4. Segmentación en analytics

- [ ] 4.1 Resolver el lenguaje por episodio en `analytics-service`. Existe el patrón de dos sesiones separadas combinadas en Python (`routes/analytics.py:2270-2280`) — reusarlo, no inventar un join cross-base.
- [ ] 4.2 Declaración de lenguajes en la respuesta de progresión de cohorte.
- [ ] 4.3 Declaración en concordancia entre evaluadores (kappa).
- [ ] 4.4 Declaración en evolución longitudinal.
- [ ] 4.5 Declaración en eventos adversariales de cohorte.
- [ ] 4.6 Declaración en alertas de estudiante.
- [ ] 4.7 Declaración en distribución de niveles.
- [ ] 4.8 Parámetro opcional de filtro por lenguaje en los 6 endpoints anteriores.
- [ ] 4.9 Test de que un filtro sin resultados devuelve ausencia de datos, no métricas calculadas sobre conjunto vacío.
- [ ] 4.10 Test de que la ausencia del parámetro preserva el comportamiento actual de cada endpoint.

## 5. Export académico

- [ ] 5.1 Incluir el lenguaje por episodio en `packages/platform-ops/src/platform_ops/academic_export.py`.
- [ ] 5.2 Declarar los lenguajes presentes en el encabezado del export.
- [ ] 5.3 Test de que la anonimización vigente no se debilita: el lenguaje no aporta a la reidentificación.

## 6. Guard de CEC

- [ ] 6.1 Extender el contrato de resultados de `cec_features.py` para distinguir tres estados: medido, error transitorio, no aplicable.
- [ ] 6.2 Verificación de lenguaje antes de `ast.parse` (`packages/platform-ops/src/platform_ops/cec_features.py:27,74`), devolviendo no-aplicable en vez de los defaults.
- [ ] 6.3 Test de que código Java devuelve no-aplicable y **ninguna** puntuación numérica.
- [ ] 6.4 Test de regresión: código Python produce resultados idénticos a los previos al cambio.
- [ ] 6.5 Test de que un fragmento Python a medio escribir sigue tratándose como error transitorio y no como lenguaje no soportado.
- [ ] 6.6 Test de que un agregado excluye los no-aplicables y declara cuántos excluyó.
- [ ] 6.7 Confirmar que el guard vive en el módulo y no en los invocadores, con test que llame directo a la función sin pasar por ningún wrapper.

## 7. Documentación del sesgo

- [ ] 7.1 Documentar el confound de calibración donde lo lea quien interpreta los datos, no solo en comentarios de código. Citar `subgrupo.py:14-18` como fuente de la calibración original sobre Pyodide.
- [ ] 7.2 Enumerar qué métricas están afectadas y en qué dirección: `dim_experimentacion` a la baja para Java por `EXEC_SCALE`, y las ventanas de `PAUSE_THRESHOLD` (5min) y `CORRELATION_WINDOW` (2min) infladas por latencia de compilación.
- [ ] 7.3 Referenciar el ADR de la decisión de constructo de la tarea 1.2.

## 8. Cierre

- [ ] 8.1 Smoke test que abra un episodio sobre un ejercicio Java y verifique que el lenguaje llega al evento de apertura.
- [ ] 8.2 Smoke test de un endpoint de analytics sobre cohorte mixta, verificando la declaración de ambos lenguajes.
- [ ] 8.3 `make test-fast` en verde.
- [ ] 8.4 Actualizar `CLAUDE.md` si cambió el conteo de smoke tests (lo verifica `scripts/check-claude-md.py` en CI).
