# Design: sobreuso-no-es-delegacion

## Context

`subgrupo.py` decide `dependiente_sobreuso` con ≥ 2 eventos `intento_adverso_detectado(category=overuse)`, y `pipeline.py` lo rollea a `appropriation = "delegacion_pasiva"`. Eso se persiste y alimenta: la vista del episodio (web-teacher), el feedback del alumno (web-student), `APPROPRIATION_ORDINAL` (0) en `platform_ops/longitudinal.py` y `cii_longitudinal.py`. El estudio de 150 muestra que ese rollup sobrediagnostica (ver proposal).

Decisión de Neyén (20/11/2026): **opción a**, no tocar lo persistido.

## Goals / Non-Goals

**Goals**: que ningún docente ni alumno lea "delegación" donde solo hubo frecuencia; que el progreso no castigue esos episodios.

**Non-Goals**: cambiar el árbol, el umbral, `appropriation`, el hash, la exportación, el inter-rater, el kappa, ni reclasificar.

## Decisions

### D1. Un único predicado, en dos lenguajes
`es_pasiva_por_sobreuso(appropriation, subgrupo_key)` en `platform_ops/longitudinal.py` (Python) y `esPasivaPorSobreuso(appropriation, subgrupoKey)` en `web-teacher/src/utils/docenteLabels.ts`. Requiere **ambas** condiciones: si una revisión humana cambió la etiqueta, el subgrupo viejo no la pisa. La constante `SUBGRUPO_SOBREUSO = "dependiente_sobreuso"` se declara una vez por lenguaje con comentario apuntando a `subgrupo.py`.

*Alternativa descartada*: crear un sexto valor de `appropriation` en la API. Rompe consumidores que hacen `if/elif` sobre los cinco valores y se parece demasiado a cambiar la etiqueta.

### D2. Ordinal: helper `ordinal_progreso(appropriation, subgrupo_key) -> int | None`
Devuelve `None` para pasiva por sobreuso, `autonomo`, `sin_clasificar` o desconocidos. Reemplaza los accesos directos `APPROPRIATION_ORDINAL[...]` con chequeo `in` en `longitudinal.py` (tercios, máximo) y `cii_longitudinal.py` (por template, por unidad, general). `APPROPRIATION_ORDINAL` no cambia de valores.

### D3. El subgrupo viaja como campo aditivo
`real_datasources.py` suma `"subgrupo_key": (c.features or {}).get("subgrupo", {}).get("key")` a las filas de las consultas usadas por progreso y trayectoria. `ClassificationPoint` gana `subgrupo_key: str | None = None`. Las salidas de analytics que listan puntos suman `subgrupo_key` opcional. Los campos son aditivos: un cliente viejo los ignora.

La exportación académica no usa estas consultas, así que no cambia (lo cubre un test).

### D4. Presentación
- Docente: `APPROPRIATION_DISPLAY` gana una entrada `uso_intensivo_tutor` que se elige por el predicado antes de indexar por `appropriation`; `SUBGRUPO_DOCENTE` y `SUBGRUPO_RESUMEN_DOCENTE` ganan `dependiente_sobreuso`. Color: `warning` (alerta), no `danger`.
- Puntos de progresión y trayectoria: color y leyenda por el predicado.
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
