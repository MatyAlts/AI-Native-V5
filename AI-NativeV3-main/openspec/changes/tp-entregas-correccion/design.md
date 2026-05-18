## Context

La plataforma tiene un flujo episodio-centric: el alumno abre un episodio por TP, interactúa con el tutor, cierra, y el CTR registra la traza. No existe concepto de ejercicios individuales dentro de una TP, ni de entregas formales, ni de corrección docente, ni de calificación.

El `evaluation-service` es un esqueleto reservado en puerto 8004 que ya apunta a `academic_main`. El modelo `TareaPractica` tiene `rubrica: JSONB` sin uso real y `test_cases: JSONB` para validación automática.

## Goals / Non-Goals

**Goals:**
- TPs con N ejercicios secuenciales, cada uno con su propio enunciado, código inicial y test cases
- Flujo secuencial del alumno: hacer ejercicio 1, luego 2, etc. Cada ejercicio = 1 episodio
- Entrega formal de la TP (submission) con estado tracked
- Corrección docente con rúbrica estructurada y feedback por criterio
- Vista de nota para el alumno
- Eventos CTR `tp_entregada` y `tp_calificada` para trazabilidad
- Analytics del docente basados en el trabajo real del alumno (ejercicios hechos, entregas, notas)

**Non-Goals:**
- Corrección automática con IA (agenda futura)
- Corrección entre pares (peer review)
- Múltiples entregas/revisiones del mismo TP (v1 es una entrega por TP por alumno)
- Exportación de notas a SIU Guaraní u otros SIS
- Rubrica con niveles de desempeño complejos (v1 es puntaje numérico por criterio)

## Decisions

### D1: Ejercicios como JSONB array en TareaPractica (no tabla separada)

Los ejercicios son sub-entidades de una TP. Normalizarlos en tabla propia agrega complejidad (FK, joins, migrations) sin beneficio real: siempre se leen/escriben junto con la TP, no se consultan por separado, y el orden importa.

```
TareaPractica.ejercicios: JSONB = [
  {
    "orden": 1,
    "titulo": "Filtrar pares",
    "enunciado_md": "Dada una lista...",
    "inicial_codigo": "def filtrar_pares(lista):\n    pass",
    "test_cases": [...],  // mismo schema que TP.test_cases actual
    "peso": 0.5
  },
  { "orden": 2, ... }
]
```

Si `ejercicios` es null o vacío, la TP funciona como hoy (monolítica). Backwards-compatible.

### D2: Entregas y Calificaciones en evaluation-service con tablas en academic_main

El evaluation-service ya apunta a `academic_main`. Crear tablas `entregas` y `calificaciones` en esa misma DB evita cross-DB joins y mantiene la referencia FK a `tareas_practicas`.

```
entregas
├── id: UUID PK
├── tenant_id: UUID (RLS)
├── tarea_practica_id: UUID FK → tareas_practicas.id
├── student_pseudonym: UUID
├── comision_id: UUID FK → comisiones.id
├── estado: VARCHAR(20) CHECK (draft, submitted, graded, returned)
├── ejercicio_estados: JSONB [{orden, episode_id, completado, completed_at}]
├── submitted_at: TIMESTAMPTZ NULL
├── created_at: TIMESTAMPTZ DEFAULT now()
├── deleted_at: TIMESTAMPTZ NULL
└── UNIQUE (tenant_id, tarea_practica_id, student_pseudonym)

calificaciones
├── id: UUID PK
├── tenant_id: UUID (RLS)
├── entrega_id: UUID FK → entregas.id UNIQUE
├── graded_by: UUID (user_id del docente)
├── nota_final: NUMERIC(5,2) CHECK (0-10)
├── feedback_general: TEXT NULL
├── detalle_criterios: JSONB [{criterio, puntaje, max_puntaje, comentario}]
├── graded_at: TIMESTAMPTZ DEFAULT now()
└── deleted_at: TIMESTAMPTZ NULL
```

RLS en ambas tablas con `tenant_id`. Migration Alembic en academic-service (comparte DB).

### D3: Un episodio por ejercicio, vinculado via campo en el payload CTR

El evento `episodio_abierto` ya tiene `problema_id` (TP). Se agrega `ejercicio_orden: int | null` al payload para vincular el episodio con el ejercicio específico. Si es null, es una TP monolítica (backwards-compatible).

El `TareaSelector` del web-student resuelve si la TP tiene ejercicios: si sí, muestra la lista secuencial; si no, muestra el flujo actual.

### D4: Entrega automática en draft, submit explícito

Cuando el alumno abre el primer ejercicio de una TP, se crea una `Entrega` en estado `draft` automáticamente. Los `ejercicio_estados` se actualizan conforme el alumno cierra episodios (marcando ejercicios como completados).

Cuando todos los ejercicios están completados, el alumno puede clickear "Entregar TP" → estado pasa a `submitted` → evento CTR `tp_entregada`.

### D5: Corrección en evaluation-service, vista en web-teacher

Nuevos endpoints en evaluation-service:
- `GET /api/v1/entregas?comision_id=X&estado=submitted` — lista entregas pendientes
- `GET /api/v1/entregas/{id}` — detalle con ejercicios y episodios
- `POST /api/v1/entregas/{id}/calificar` — crea calificación, cambia estado a graded
- `GET /api/v1/entregas/{id}/calificacion` — lee calificación

Casbin policies: `entrega:read` para docente/estudiante (filtrado por scope), `calificacion:create` para docente/docente_admin/superadmin.

El estudiante solo ve SUS entregas (filtrado por `student_pseudonym` del header).

### D6: Dos eventos CTR nuevos, excluidos del classifier

- `tp_entregada`: emitido al submit. Payload: `{tarea_practica_id, n_ejercicios, exercise_episode_ids}`. 
- `tp_calificada`: emitido al calificar. Payload: `{entrega_id, nota_final, graded_by}`.

Ambos se agregan a `_EXCLUDED_FROM_FEATURES` en el classifier (mismo patrón que `reflexion_completada`). Son meta-eventos, no actividad pedagógica.

### D7: Analytics del docente basados en entregas

La progresión del docente incorpora datos de entregas:
- Dashboard de comisión muestra: X entregas pendientes, Y corregidas, nota promedio
- La vista de progresión por alumno incluye: ejercicios completados, entregas, notas
- Drill-down: desde la entrega se puede navegar a cada episodio del ejercicio (traza CTR completa)

### D8: ROUTE_MAP del api-gateway

Agregar `/api/v1/entregas` y `/api/v1/calificaciones` → evaluation-service (puerto 8004).

## Risks / Trade-offs

- **Complejidad incremental**: agregar entregas + calificaciones duplica la superficie de API. Mitigación: evaluation-service aislado, modelos simples en v1.
- **Migration en academic_main**: las tablas nuevas van en la misma DB que usa academic-service. Hay que coordinar que el Alembic del academic-service genere las migrations (o crear Alembic propio para evaluation-service sobre la misma DB).
- **Una entrega por TP por alumno**: si el alumno necesita re-entregar, hay que definir el flujo (estado `returned` permite re-submit? o nueva entrega?). V1: una sola entrega, si el docente pone `returned` el alumno puede re-enviar actualizando la misma.
- **Ejercicios opcionales vs obligatorios**: v1 asume todos obligatorios. Si un docente quiere ejercicios opcionales, necesita flag `opcional: bool` en el JSONB — diferible.
- **Performance de JSONB `ejercicio_estados`**: con N<20 ejercicios por TP, JSONB inline es suficiente. Si alguna TP tuviera 100+ ejercicios, se necesitaría tabla normalizada — improbable en el piloto.
