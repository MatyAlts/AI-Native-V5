## Why

El sistema asume Python en toda la cadena de datos. No existe ningún campo `language` en `Ejercicio` ni en `TareaPractica` (`apps/academic-service/src/academic_service/models/operacional.py:408,214`), así que hoy es imposible expresar "este ejercicio es de Java" — ni siquiera para mostrarlo, mucho menos para ejecutarlo.

Esta change es la **fundación de datos** del soporte multi-lenguaje (Fase 2 Java). No agrega ejecución ni toca UI: deja el modelo, los contratos y las reglas de composición listos para que las changes siguientes (`java-authoring-experience`, `java-execution-engine`) tengan dónde apoyarse.

Dos hallazgos de la exploración justifican meter la validación de TP acá y no después:

1. **El banco de ejercicios es reusable entre TPs** (`tp_ejercicios` N:M). Nada impide componer una TP con un ejercicio Python y uno Java. El editor no puede cargar dos runtimes — la mezcla rompe la experiencia del alumno, no es un detalle cosmético. Apenas exista el segundo ejercicio Java en el banco, el bug es inmediato.
2. **`publish()` no valida nada** (`apps/academic-service/src/academic_service/services/tarea_practica_service.py:216`): solo verifica `estado == "draft"`. Se puede publicar una TP vacía y le llega así al alumno. Existe `TpEjerciciosValidator` (`packages/contracts/src/platform_contracts/academic/ejercicio.py:263`) escrito para eso y **nunca se invoca**. Es el mismo punto de código donde va la regla mono-lenguaje: hacerlos por separado es fabricar un conflicto.

   **Pero no todas sus reglas se adoptan.** Medición previa contra la base del piloto: las 169 asociaciones ejercicio–TP tienen peso `1.0000`, ninguna calificación consume ese campo, y aplicar la regla de "los pesos suman 1.0" habría impedido republicar 25 de 27 TPs. Queda fuera de scope y documentado como hallazgo.

## What Changes

- **Campo `language` en `Ejercicio` y `TareaPractica`** (`String(20)`, `NOT NULL`, `server_default='python'`) + migración Alembic. El `server_default` hace que las filas existentes del banco —100% Python hoy— queden correctas sin backfill separado. Sin cambios de RLS: ambas tablas ya tienen policy activa, es `ADD COLUMN` sobre tabla existente (patrón de `20260615_0002_tarea_practica_permite_pausa`).
- **`language` en los contratos Pydantic**: `_EjercicioBase` (`ejercicio.py:152`) y el schema de `TareaPractica`.
- **Nuevo tipo de test case `junit_assert`** en `TestCaseSchema.type` (`ejercicio.py:142`, hoy `Literal["stdin_stdout","pytest_assert"]`). **Y en el schema de TP**: `TareaPractica.test_cases` está tipado como `list[dict[str, Any]]` suelto (`apps/academic-service/src/academic_service/schemas/tarea_practica.py`) y no reusa `TestCaseSchema` — agregar el tipo solo en `ejercicio.py` no cubre las TPs monolíticas sin ejercicios de banco.
- **Filtro `?language=` en `GET /ejercicios`** (`apps/academic-service/src/academic_service/routes/ejercicios.py:57`). Mecánicamente idéntico al filtro `materia_id` ya existente: entra por el dict `filters` y el repositorio genérico lo resuelve sin cambios (`repositories/base.py:58-61`).
- **Validación de composición de TP, enganchada de verdad** — con las reglas que aplican a los datos reales, no todas las que el validador contempla:
  - `TpEjerciciosValidator` invocado desde `publish()`, **sin la regla de suma de pesos** (ver arriba).
  - **Regla nueva mono-lenguaje**: todos los `Ejercicio` de una TP deben compartir `language`, y coincidir con el de la TP. El validador actual no puede hacerlo — solo ve `ejercicio_id/orden/peso_en_tp`, nunca el `Ejercicio` real.
  - **Regla nueva no-vacía**: `validate_set()` hace `if not self.tp_ejercicios: return self` — retorna OK ante lista vacía. Enchufarlo tal cual dejaría el bug de "TP vacía" igual de roto. Hace falta chequear que haya `tp_ejercicios` **o** `test_cases` propios.
  - **Validación temprana en `add_ejercicio`** (`tp_ejercicio_service.py:75-111`): bloquear la mezcla al agregar, no recién al publicar. Ese método ya carga el `Ejercicio` real, así que tiene el `language` a mano.

## Capabilities

### New Capabilities

- `ejercicio-language`: el lenguaje de programación como atributo de primera clase del banco de ejercicios y de las TPs. Campo en modelo y contratos, migración con default retrocompatible, filtro por lenguaje en el listado del banco, y el tipo de test case `junit_assert` en ambos schemas (el tipado y el suelto).
- `tp-composicion-validada`: `publish()` valida la composición de la TP antes de exponerla al alumno — órdenes y ejercicios sin duplicar, TP no vacía, y un solo lenguaje por TP. Incluye la validación temprana en `add_ejercicio` para bloquear la mezcla en el momento de componer, no al publicar. **Excluye deliberadamente la regla de suma de pesos**, incompatible con el 100% de los datos del piloto y guardiana de un campo que ningún cálculo consume.

### Modified Capabilities

Ninguna. Las 13 capabilities de `openspec/specs/` no cubren el banco de ejercicios ni la composición de TPs.

## Impact

- **academic-service**: migración nueva sobre `ejercicios` y `tareas_practicas`; `EjercicioService.list()` acepta el filtro; `TareaPracticaService.publish()` pasa a validar; `TpEjercicioService.add_ejercicio()` bloquea mezcla de lenguajes. Riesgo técnico conocido: `TareaPracticaRepository.get_or_404()` **no hace eager-load** de `tp_ejercicios`, y el propio código de `new_version()` (`tarea_practica_service.py:324-328`) documenta que iterar esa relación lazy revienta con `MissingGreenlet` en el driver async — la validación en `publish()` tiene que replicar el patrón de SELECT explícito, no un `if obj.tp_ejercicios`.
- **packages/contracts**: `_EjercicioBase` gana `language`; `TestCaseSchema.type` gana `junit_assert`; `TpEjerciciosValidator` gana las reglas de no-vacío y mono-lenguaje (y por lo tanto necesita acceso a los `Ejercicio` reales, no solo a sus IDs).
- **CTR y clasificador**: **cero cambios**. Verificado que el clasificador no lee `payload.language` ni `payload.runtime` en ningún punto (`pipeline.py`, `ccd.py`, `cii.py`, `ct.py`, `tree.py`, `subgrupo.py`, `event_labeler.py`), y que `classifier_config_hash` es `f(tree_version, reference_profile)` únicamente. No hay bump de `LABELER_VERSION` ni re-clasificación.
- **Frontends**: **cero cambios en esta change**. El campo viaja por la API pero ninguna UI lo lee todavía — eso es `java-authoring-experience`.
- **Analytics / export académico**: **cero cambios acá, pero con una dependencia dura**. Ver "Riesgo de orden".

## Riesgo de orden (restricción no negociable)

Esta change **no** hace que un ejercicio Java sea alcanzable por un alumno — no hay UI para crearlo ni runtime para ejecutarlo. Pero deja la puerta abierta a nivel API.

**`multi-language-research-integrity` tiene que estar mergeada antes de que shippee `java-authoring-experience`.** Desde el primer episodio Java entran eventos al CTR, y hoy ningún endpoint de analytics (`kappa`, `progression`, `cii-evolution-longitudinal`, `cohort-adversarial`, `alerts`, `export-academic`) filtra ni etiqueta por lenguaje. Si eso no existe cuando llega el primer dato Java, el corpus de la tesis se mezcla **sin un solo error visible** — se descubre meses después, analizando datos, cuando ya no hay vuelta atrás.

## Decisión abierta (no bloquea esta change, conviene cerrarla acá)

**¿`language` lleva `CHECK` constraint a nivel DB?** El patrón de `dificultad` (`ck_ejercicios_dificultad`) dice que sí. Pero el precedente más reciente va en contra: la migración `20260611_0001_ejercicio_unidad_tematica_texto_libre` **eliminó** el CHECK de `unidad_tematica` justamente para hacerlo texto libre, con el argumento de que "cada materia define las suyas". Un enum cerrado `('python','java')` obliga a una migración por cada lenguaje nuevo (Go, C, JS). Recomendación: **sin CHECK en DB, validación en el contrato Pydantic** — se valida igual, y agregar un lenguaje no requiere tocar la base.
