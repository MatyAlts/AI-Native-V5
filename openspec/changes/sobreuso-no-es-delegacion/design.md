# Design: sobreuso-no-es-delegacion

## Context

`subgrupo.py` decide `dependiente_sobreuso` con ≥ 2 eventos `intento_adverso_detectado(category=overuse)`, y `pipeline.py` lo rollea a `appropriation = "delegacion_pasiva"`. Eso se persiste y alimenta: la vista del episodio (web-teacher), el feedback del alumno (web-student), `APPROPRIATION_ORDINAL` (0) en `platform_ops/longitudinal.py` y `cii_longitudinal.py`. El estudio de 150 muestra que ese rollup sobrediagnostica (ver proposal).

Decisión de Neyén (20/11/2026): **opción a**, no tocar lo persistido.

## Goals / Non-Goals

**Goals**: que ningún docente ni alumno lea "delegación" donde solo hubo frecuencia; que el progreso no castigue esos episodios.

**Non-Goals**: cambiar el árbol, el umbral, `appropriation`, el hash, la exportación, el inter-rater, el kappa, ni reclasificar.

## Decisions

### D1. Un único predicado, en el backend (revisado en HU-007)
`pasiva_por_sobreuso(appropriation, features) -> bool` en `platform_ops/longitudinal.py`, exportado en `platform_ops/__init__.py`. Es el **único** lugar de la regla. Exige las cuatro condiciones:

1. `appropriation == "delegacion_pasiva"` (si una revisión humana cambió la etiqueta, el subgrupo viejo no la pisa);
2. `features.subgrupo.key == "dependiente_sobreuso"`;
3. sin `features.revision_humana`: `services/review.py` copia `features` al anular, así que un docente que **confirmó** la pasiva conserva el subgrupo;
4. sin `features.regimen_llm.estado == "ok"`: si el juez del eje fino gobernó, la pasiva la decidió él, no la regla de frecuencia.

Es defensiva: con `features` ausente o de forma rara devuelve `False` (se ve como delegación, como antes del change).

*Versión anterior descartada (PR #139 original)*: un predicado `es_pasiva_por_sobreuso(appropriation, subgrupo_key)` copiado en Python, en `docenteLabels.ts`, en `EpisodePage.tsx` y en `MiProgresoPage.tsx`. Miraba solo etiqueta + subgrupo, así que escondía como "uso intensivo" pasivas que un docente había confirmado o que el juez había decidido, y cuatro copias se iban a desincronizar con la primera corrección.

*Alternativa descartada*: crear un sexto valor de `appropriation` en la API. Rompe consumidores que hacen `if/elif` sobre los cinco valores y se parece demasiado a cambiar la etiqueta.

*Alternativa descartada*: crear un sexto valor de `appropriation` en la API. Rompe consumidores que hacen `if/elif` sobre los cinco valores y se parece demasiado a cambiar la etiqueta.

### D2. Ordinal: helper `ordinal_progreso(appropriation, pasiva_por_sobreuso=False) -> int | None`
Recibe el booleano ya calculado por D1 (no vuelve a decidir la regla). Devuelve `None` para pasiva por sobreuso, `autonomo`, `sin_clasificar` o desconocidos. Reemplaza los accesos directos `APPROPRIATION_ORDINAL[...]` con chequeo `in` en `longitudinal.py` (tercios, máximo) y `cii_longitudinal.py` (por template, por unidad, general). `APPROPRIATION_ORDINAL` no cambia de valores.

### D3. El booleano viaja ya calculado (campos aditivos)
`real_datasources.py` (las tres consultas de progreso y trayectoria) y `analytics_service/services/cohort_slopes.py` suman `"pasiva_por_sobreuso": pasiva_por_sobreuso(c.appropriation, c.features)` y, como dato informativo, `"subgrupo_key"`. `ClassificationPoint` gana `pasiva_por_sobreuso: bool = False` (y `subgrupo_key`). `TrajectoryPoint` y `StudentEpisodeOut` de analytics exponen `pasiva_por_sobreuso: bool = False`. `GET /api/v1/classifications/{episode_id}` del classifier-service (`ClassificationOut`) devuelve `pasiva_por_sobreuso` calculado con la misma función (el classifier-service declara `platform-ops` como dependencia). Los frontends usan el booleano y no recalculan desde `appropriation` + subgrupo; ausente (backend viejo) = `false`. Los campos son aditivos: un cliente viejo los ignora.

La exportación académica no usa estas consultas, así que no cambia (lo cubre un test).

### D4. Presentación
- Docente: `APPROPRIATION_DISPLAY` gana una entrada `uso_intensivo_tutor` que se elige por `classification.pasiva_por_sobreuso` antes de indexar por `appropriation`; `SUBGRUPO_DOCENTE` y `SUBGRUPO_RESUMEN_DOCENTE` ganan `dependiente_sobreuso`. Color: `warning` (alerta), no `danger`.
- Puntos de progresión y trayectoria: color y leyenda por `pasiva_por_sobreuso` del punto.
- Alumno: `FEEDBACK_SUBGRUPO` gana `dependiente_sobreuso` con tono `neutro`.
- Texto sin tildes (convención de `docenteLabels.ts`).

## Risks / Trade-offs

- **Cache de progresión en proceso** (TTL en analytics): tras el deploy, hasta un TTL de datos viejos. Aceptable.
- **Delegación real enmascarada**: un alumno que de verdad delegó y además disparó sobreuso queda como `dependiente_sobreuso` (la regla se chequea primero en el árbol). Es el mismo sesgo que el estudio midió, ahora en la dirección conservadora; lo resuelve el juez nuevo (P2), no este cambio.
- **El paper describe la etiqueta persistida**: no se toca, así que las cifras del estudio siguen reproducibles.

## Migration Plan

Sin migración. Deploy de analytics-service, web-teacher y web-student. Rollback: revert del PR.

## Open Questions

- Ninguna bloqueante. El texto exacto para el alumno queda para revisión en el PR.
