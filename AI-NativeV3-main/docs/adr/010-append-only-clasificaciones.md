# ADR-010 — Append-only para clasificaciones

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: datos, tesis, auditoría

## Contexto y problema

El clasificador N4 produce clasificaciones de apropiación (`delegacion_pasiva` / `apropiacion_superficial` / `apropiacion_reflexiva`) junto con las tres coherencias (temporal, código-discurso, inter-iteración) para cada episodio cerrado.

Estas clasificaciones son **datos que alimentan la tesis**: decisiones estadísticas, publicaciones, retrospectivas de docente. Dos tensiones:

1. El clasificador evoluciona: ajustes de umbrales, nuevas reglas en el árbol de decisión, calibración de reference_profiles. Cada cambio podría reclasificar episodios viejos con resultados distintos.
2. Los dashboards y actas dependen de clasificaciones "actuales" para su operación diaria.

¿Cómo reconciliamos evolución del clasificador con auditabilidad histórica?

## Opciones consideradas

### Opción A — Tabla `classifications` con UPDATE
La clasificación vigente se sobrescribe cuando hay reclasificación. Simple pero **destruye evidencia histórica**: ¿qué clasificación vio el docente hace 6 meses cuando puso la nota? Se perdió.

### Opción B — Append-only con `is_current` booleano
Cada reclasificación es una nueva fila en `classifications`. La fila anterior queda con `is_current = false`. La nueva tiene `is_current = true`. Queries de dashboards filtran por `is_current`.

### Opción C — Tabla separada de historial
`classifications` vigente + `classifications_history`. Overhead de mantener dos tablas sincronizadas.

## Decisión

**Opción B — Append-only con `is_current`.**

Schema:

```sql
CREATE TABLE classifications (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    episode_id UUID NOT NULL,
    classifier_config_hash CHAR(64) NOT NULL,
    appropriation TEXT NOT NULL,
    appropriation_reason TEXT NOT NULL,
    ct_summary FLOAT,
    ccd_mean FLOAT,
    ccd_orphan_ratio FLOAT,
    cii_stability FLOAT,
    cii_evolution FLOAT,
    classified_at TIMESTAMPTZ NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (episode_id, classifier_config_hash)
);

CREATE INDEX ON classifications (episode_id, is_current) WHERE is_current;
```

Reglas de operación:

1. **Nunca `UPDATE`** de filas existentes, excepto para `is_current = false` al reclasificar.
2. **Nunca `DELETE`** de filas (ni siquiera en retention: el costo de almacenamiento es bajo).
3. Toda clasificación lleva `classifier_config_hash` que identifica exactamente qué reglas + umbrales + reference_profiles la produjeron.
4. Al reclasificar (porque cambiaron umbrales o reference_profile): se insertan filas nuevas con el nuevo `classifier_config_hash`, se setea `is_current = false` en las viejas.
5. Dashboards y actas operan siempre sobre `is_current = true`.

Lo mismo aplica a:
- `rubricas` (una rúbrica asignada a correcciones queda congelada; cambios crean nueva versión).
- `corrections` (un docente puede "revisar" una corrección pero queda fila nueva con `is_current`).
- `classifier_configs` en el governance-service.

## Consecuencias

### Positivas
- Auditabilidad total: siempre se puede responder "qué clasificación vio el docente el día D".
- Base para estudios longitudinales del propio clasificador (cómo evolucionaron las clasificaciones al ajustar umbrales).
- Compatible con la exigencia de la tesis de reproducibilidad.
- Evita "silent updates" que podrían alterar notas ya publicadas.

### Negativas
- Tabla crece más rápido que con UPDATE. Con 10k episodios/mes y 1-2 reclasificaciones/año, son ~120k filas/año. Manejable.
- Queries deben recordar filtrar por `is_current`. Mitigación: view `current_classifications` que lo hace automáticamente.
- Pequeña complejidad adicional en el código del clasificador (transacción que invalida vieja + inserta nueva).

### Neutras
- Archivado de filas con `is_current = false` más viejas que N años es posible, aunque inicialmente mantenemos todo.

## Referencias

- `apps/classifier-service/alembic/versions/` (schema definitivo)
- ADR-009 (classifier_config_hash viene del governance)
- `docs/plan-detallado-fases.md` → F3.4 semana 4
