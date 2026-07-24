# Respuesta a Neyén — estado de la epic 1 y qué podés usar ya

**Fecha**: 2026-07-23
**De**: Juani
**Sobre**: dependencia de `multi-language-research-integrity` (epic 2) respecto de `java-language-model` (epic 1)
**Rama**: `desarrollo-java`

---

## Respuesta corta

**Sí, `language` está definido — y más que el contrato. Arrancá por la 2.4.**

No hace falta que esperes a que "cerremos el contrato del `AcademicClient`": **no hay contrato que cerrar**. Detalle abajo.

---

## Qué está hecho y mergeado

| Capa | Estado | Dónde |
|---|---|---|
| Contrato Pydantic | ✅ | `packages/contracts/src/platform_contracts/academic/ejercicio.py` |
| Modelo SQLAlchemy | ✅ | `apps/academic-service/src/academic_service/models/operacional.py` |
| Migración | ✅ | `apps/academic-service/alembic/versions/20260723_0001_ejercicio_tp_language.py` |

```python
from platform_contracts.academic import Language, DEFAULT_LANGUAGE

# Language = Literal["python", "java"]
# DEFAULT_LANGUAGE = "python"
```

Columna: `String(20)`, `NOT NULL`, `server_default='python'`.

**Sin `CheckConstraint` a propósito.** El conjunto admitido vive en el contrato, que es el gate real de la API. Cerrarlo en la base obligaría a una migración por cada lenguaje futuro — mismo criterio que llevó a `20260611_0001` a sacarle el CHECK a `unidad_tematica`.

La migración se probó contra Postgres real (contenedor descartable con el `init-dbs.sql` del repo, nunca contra prod): upgrade desde cero, downgrade, re-upgrade, e idempotencia en el escenario mixto (una tabla con la columna puesta a mano, la otra sin ella). RLS intacto, `relrowsecurity` y `relforcerowsecurity` en `t` en ambas tablas.

---

## Sobre el `AcademicClient` — que es lo que realmente preguntabas

Los dos métodos que te importan son **passthrough**: devuelven `resp.json()` crudo del academic-service, sin DTO tipado ni whitelist de campos.

**`get_ejercicio_by_id()`** (`apps/tutor-service/src/tutor_service/services/academic_client.py:219`)
→ **Ya te devuelve `language` hoy.** `EjercicioRead` hereda de `_EjercicioBase`, que ya lo tiene. Cero trabajo de mi lado, cero espera tuya.

**`get_tarea_practica_full()`** (mismo archivo, `:186`)
→ **Todavía no.** Pega a `GET /api/v1/tareas-practicas/{id}`, y `TareaPracticaOut` (`apps/academic-service/src/academic_service/schemas/tarea_practica.py:73`) aún no expone el campo. Es mi tarea 3.2, en curso.

---

## Traducción práctica

**Arrancá por la 2.4 con el camino del ejercicio.** Está 100% disponible: cuando el episodio abre sobre un ejercicio del banco (`ejercicio_id` presente en el payload de apertura), el lenguaje ya lo tenés resuelto.

El camino de la **TP monolítica** —la que no tiene ejercicios de banco y lleva sus propios `test_cases`— te lo destrabo en el próximo push. Si no querés bloquearte, dejá ese branch con un `TODO` y lo cerrás cuando te avise.

No veo motivo para que arranques por las tareas de cero-acople (guard de CEC, sección 6, doc del sesgo). Están bien como están y no dependen de nadie, pero la 2.4 tampoco te bloquea.

---

## Una advertencia que te ahorra tiempo

Cuando resuelvas el lenguaje en `open_episode`, **tomalo del ejercicio o de la TP, nunca de la request**.

Es un dato derivado. Si lo aceptás del cliente, deja de servir como evidencia de procedencia para la tesis — que es justamente el punto de tu epic.

El precedente está a la vista: hoy el frontend manda `language: "python"` **hardcodeado** en el payload de `edicion_codigo` (`apps/web-student/src/pages/EpisodePage.tsx:799`). Es exactamente el tipo de dato que parece real y no lo es. Los 169 ejercicios del banco son Python, así que nadie lo notó nunca.

---

## Dato que te puede servir para dimensionar

Medí la base del piloto el 2026-07-23 antes de escribir código:

- **169** ejercicios en el banco, **31** TPs (27 publicadas, 2 borradores)
- **Todos** Python — el corpus histórico es homogéneo
- Ya existe una currícula completa de **Programación 2**: 8 TPs de POO, herencia, polimorfismo, interfaces, excepciones, genéricos y conexión a bases

Esa currícula de Prog 2 se queda en Python (decisión tomada). Los ejercicios Java van a nacer nuevos, posiblemente sobre los mismos temas. Es decir: **cuando lleguen datos Java, van a convivir con datos Python de la misma materia y los mismos temas** — que es el escenario donde tu segmentación pasa de deseable a imprescindible.

---

## Avance de la epic 1

13 de 29 tareas. Contratos y migración cerrados; voy por schemas y endpoints.

Te aviso apenas empuje la 3.2 y quede disponible el camino de la TP.
