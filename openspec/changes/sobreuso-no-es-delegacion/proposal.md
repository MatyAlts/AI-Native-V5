# Proposal: sobreuso-no-es-delegacion

## Why

El estudio de los 150 episodios (CIbSE 2027) mostró que la regla de sobreuso sobrediagnostica: producción marcó `delegacion_pasiva` en 47 de los 50 episodios del grupo de sobreuso, mientras que Claude no marcó ninguno como pasivo, ChatGPT marcó 1 y los docentes 2/18 (Ariel) y 1/18 (Cinthia). Hoy los docentes ven "Delegación pasiva" y el **alumno** lee "la mayor parte del trabajo cognitivo lo hizo el tutor" en episodios donde lo único observado es una **frecuencia** alta de consultas. Además, esa pasiva entra como 0 en la escala de progreso y puede mostrar a un alumno como "en riesgo" sin serlo.

Es el P1 y el A1 del *Plan de actualización: paper CIbSE 2027, plataforma y aprendizaje entre episodios* (19/11/2026). Es lo más urgente del plan porque afecta a alumnos reales hoy.

## What Changes

Solo **presentación** y **cálculo de progreso**. La etiqueta persistida NO cambia (decisión de Neyén, 20/11: opción a).

- **P1, vista docente**: un episodio con `appropriation = delegacion_pasiva` **y** subgrupo `dependiente_sobreuso`, que ni un docente ni el juez confirmaron (HU-007, ver design D1), se muestra como **"Uso intensivo del tutor"**, con color de alerta (no de peligro) y un texto que dice que es una alerta de frecuencia y no un régimen. Aplica al veredicto del episodio, al resumen por subgrupo y a los puntos de las vistas longitudinales.
- **P1, vista alumno**: el feedback del episodio deja de decirle al alumno que "el tutor hizo el trabajo" cuando la pasiva vino del sobreuso; recibe un mensaje sobre el ritmo de consultas.
- **A1, progreso**: esos episodios **no entran a la escala ordinal** (igual que hoy `autonomo` y `sin_clasificar`): no cuentan en tercios, pendiente ni "máximo alcanzado". Afecta a la progresión de cohorte, la trayectoria del alumno (docente y "Mi progreso") y los cuartiles.
- Las clasificaciones viejas sin subgrupo se siguen viendo como hoy.

**No cambia**: `subgrupo.py`, `OVERUSE_DEP_THRESHOLD`, `pipeline.py`, la columna `appropriation`, el hash del clasificador, la exportación académica, el inter-rater ni el kappa.

## Capabilities

### New Capabilities
- `apropiacion-sobreuso-presentacion`: cómo se presenta y cómo pondera en el progreso un episodio cuya pasiva proviene únicamente de la regla de sobreuso.

### Modified Capabilities
- Ninguna (no hay spec previa de presentación de apropiación ni de progresión).

## Impact

- **platform-ops**: `longitudinal.py` (`pasiva_por_sobreuso`, único lugar de la regla) y `cii_longitudinal.py`, `real_datasources.py` (las filas suman `pasiva_por_sobreuso` y `subgrupo_key`, campos aditivos).
- **analytics-service**: la salida de puntos longitudinales suma `pasiva_por_sobreuso` y `subgrupo_key` (aditivos, opcionales).
- **classifier-service**: `GET /classifications/{episode_id}` suma `pasiva_por_sobreuso` (aditivo).
- **web-teacher**: `docenteLabels.ts`, `EpisodeNLevelView.tsx`, `ProgressionView.tsx`, `StudentLongitudinalView.tsx`.
- **web-student**: `EpisodePage.tsx` (feedback por subgrupo).
- **Datos**: ninguna migración y ninguna reclasificación. Reversible con un revert.
- **Gobernanza**: MEDIUM (lógica de negocio visible para docentes y alumnos). No toca prompts del tutor, `tutor-service` ni `ctr-service`.
- **Fuera de alcance**: juez nuevo (P2/HU-001, rama propia), regla como señal al juez (P3), cola de revisión de pasivas (P7), resto de A2–A7.
