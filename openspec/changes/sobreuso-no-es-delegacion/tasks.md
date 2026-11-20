# Tasks: sobreuso-no-es-delegacion

## 1. Predicado y ordinal (platform-ops)

- [x] 1.1 `longitudinal.py`: `SUBGRUPO_SOBREUSO`, `es_pasiva_por_sobreuso()` y `ordinal_progreso()`; `ClassificationPoint.subgrupo_key`; `build_trajectories` lo lee de la fila; `tercile_means` y `max_appropriation_reached` usan `ordinal_progreso`. Exportarlos en `__init__.py`.
- [x] 1.2 `cii_longitudinal.py`: por template, por unidad y general usan `ordinal_progreso(c["appropriation"], c.get("subgrupo_key"))`.
- [x] 1.3 Tests unit: los escenarios del spec (sobreuso excluido, delegador cuenta, revisión humana manda, clasificación vieja sin subgrupo).

## 2. Datos (platform-ops + analytics-service)

- [x] 2.1 `real_datasources.py`: sumar `subgrupo_key` en `list_classifications_grouped_by_student`, `list_episodes_with_classifications_for_student` y `list_classifications_with_templates_for_student`.
- [x] 2.2 `analytics_service/services/cohort_slopes.py`: sumar `subgrupo_key` en la consulta batch.
- [x] 2.3 `routes/analytics.py`: `TrajectoryPoint` y `StudentEpisodeOut` suman `subgrupo_key: str | None = None`.
- [x] 2.4 La exportación académica no usa las consultas tocadas; su suite (`test_academic_export.py`) pasa sin cambios.

## 3. Vista docente (web-teacher)

- [x] 3.1 `docenteLabels.ts`: `esPasivaPorSobreuso()`, labels `uso_intensivo_tutor`, entradas `dependiente_sobreuso` en `SUBGRUPO_DOCENTE` y en el resumen por subgrupo.
- [x] 3.2 `EpisodeNLevelView.tsx`: veredicto "Uso intensivo del tutor" con estilo warning.
- [x] 3.3 `ProgressionView.tsx` y `StudentLongitudinalView.tsx`: color y leyenda de los puntos por el predicado; tipos de `api.ts` con `subgrupo_key?`.
- [x] 3.4 Tests vitest del predicado y del veredicto.

## 4. Vista alumno (web-student)

- [x] 4.1 `EpisodePage.tsx`: `FEEDBACK_SUBGRUPO.dependiente_sobreuso` con tono neutro.
- [x] 4.2 `MiProgresoPage.tsx`: el chip del episodio dice "Muchas consultas" (color de alerta) en vez de "Delegacion" (hallazgo durante apply: también lo ve el alumno).

## 5. HU-007: la regla en un solo lugar y sin esconder pasivas confirmadas

- [x] 5.1 `longitudinal.py`: `pasiva_por_sobreuso(appropriation, features)` (excluye revisión humana y juez con `estado == "ok"`) reemplaza a `es_pasiva_por_sobreuso`; `ordinal_progreso` recibe el booleano; `ClassificationPoint.pasiva_por_sobreuso`.
- [x] 5.2 `real_datasources.py`, `cohort_slopes.py`, `TrajectoryPoint`, `StudentEpisodeOut` y `ClassificationOut` (classifier-service, que suma la dependencia `platform-ops`) traen el booleano.
- [x] 5.3 web-teacher y web-student usan `pasiva_por_sobreuso` del backend; se borran las tres copias de la regla en TypeScript.
- [x] 5.4 Aceptación HU-007 (`test_hu007_aceptacion.py`, `Hu007Aceptacion.test.tsx`, `Hu007Aceptacion.test.ts`).

## 6. Verificación

- [x] 6.1 pytest de platform-ops y analytics-service (scope del change) y vitest de web-teacher/web-student.
- [x] 6.2 ruff + biome + typecheck.
- [ ] 6.3 PR contra `main` (el merge lo hace Neyén).
