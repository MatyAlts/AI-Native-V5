# ADR-048 — Schema pedagógico del Ejercicio (banco N1-N4, misconceptions, tutor_rules)

- **Estado**: Propuesto
- **Fecha**: 2026-05-14
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: datos, schema, jsonb, pedagogía, tutor-service, PID-UTN
- **Sucede a / depende de**: ADR-034 (test_cases JSONB), ADR-047 (Ejercicio primera clase), ADR-023 (override labeler v1.1.0)

## Contexto y problema

El PID Línea 5 "Trazabilidad Cognitiva N4 e IA Generativa" (UTN-FRM × UTN-FRSN) produjo **tres bancos docentes operativos** que codifican la doctrina pedagógica del tutor socrático ejercicio por ejercicio:

- `b1.docx` — TP1 Estructuras Secuenciales (10 ejercicios)
- `condi.docx` — TP2 Estructuras Condicionales (10 ejercicios)
- `mixtos.docx` — TP Integrador Secuenciales + Condicionales + Repetitivas (5 ejercicios)

Cada banco contiene, por ejercicio:

1. **Banco de preguntas socráticas por fase N1-N4**, con señal de comprensión (✓) y señal de alerta (✗) por pregunta.
2. **Misconceptions anticipadas** (con probabilidad estimada y pregunta diagnóstica para hacerlas observables).
3. **Respuestas-pista** (anti-soluciones) catalogadas — la única respuesta legítima cuando el estudiante pide código.
4. **Heurística de cierre del episodio** — condiciones verificables para declarar terminado.
5. **Anti-patrones del tutor** específicos del ejercicio (qué nunca decir).
6. **Prerrequisitos sintácticos y conceptuales**.
7. **Reglas operativas del tutor** específicas del ejercicio (ej. "prohibido aceptar lista en E3 del integrador", "fase 5 obligatoria en banda avanzada").

Hoy el `tutor-service` (`tutor_core.py::open_episode`) inyecta al system message del LLM **solo** el `enunciado_md` + `inicial_codigo` + `rubrica` del ejercicio. Toda la doctrina pedagógica de arriba **no existe en el sistema** — vive en `.docx` que ningún servicio consume. El tutor cumple un rol genérico ("sos un tutor socrático"), no el rol específico del banco PID-UTN para ese ejercicio.

ADR-047 introdujo la tabla `ejercicios` como entidad de primera clase reusable. Este ADR define **qué campos pedagógicos** de los bancos PID-UTN se persisten en esa tabla, **cómo se estructuran** (JSONB tipados vs tablas relacionales separadas), y **qué validación** se aplica.

## Drivers de la decisión

- **Doctrina pedagógica como dato, no como código**: las reglas socráticas son contenido editable por el docente, no lógica de servicio. Tienen que vivir en DB y poder evolucionar sin redeploy.
- **Trazabilidad cognitiva por ejercicio**: la tesis necesita poder reconstruir "qué pregunta socrática se inyectó, ante qué misconception del estudiante, en qué turno" para validar el modelo N4. El system message del tutor debe incluir el banco completo para que la trazabilidad sea posible.
- **Validación tipada de los campos**: el contenido pedagógico es estructurado (preguntas tienen "señal ✓" y "señal ✗"; misconceptions tienen "probabilidad estimada"). Persistir como `dict[str, Any]` libre pierde garantías.
- **Reuso del patrón JSONB**: ADR-034 estableció que JSONB con validación Pydantic en boundary es el patrón del proyecto para datos semi-estructurados con baja queryability cross-row. Los campos pedagógicos cumplen ese perfil — se leen siempre en el contexto de un ejercicio específico, no cross-ejercicio.
- **Volumen esperado**: por ejercicio, ~10-15 preguntas N1-N4, ~5-10 misconceptions, ~5 anti-patrones, ~5 anti-soluciones. Total <50 entradas por ejercicio. No hay queries del tipo "todas las misconceptions del corpus" — irrelevante para el piloto.
- **Costos del wizard IA** (ADR-050 cuando se redacte): un solo prompt LLM debe generar todos los campos del ejercicio coherentemente. JSONB unificado por ejercicio facilita esto; tablas relacionales separadas complican el prompt-engineering.

## Opciones consideradas

### Opción A — Un único JSONB `metadata_pedagogica` por ejercicio

Un campo `metadata_pedagogica: dict[str, Any]` que contiene un dict monolítico con todos los conceptos pedagógicos adentro.

**Ventajas**: schema mínimo, sin sub-tipos.

**Desventajas**:
- Sin tipado de los sub-conceptos. El consumidor (tutor-service) tiene que parsear claves dict sin garantías.
- Hace inviable la validación Pydantic granular (no se puede validar "todas las preguntas N1 tienen `senal_comprension` y `senal_alerta`" desde un blob amorfo).
- Edición desde frontend complicada (un solo campo gigante en el form).
- Rechazada.

### Opción B — Campos JSONB tipados separados por concepto + sub-schemas Pydantic

Múltiples columnas JSONB en la tabla `ejercicios`: `tutor_rules`, `banco_preguntas`, `misconceptions`, `respuesta_pista`, `heuristica_cierre`, `anti_patrones`, `prerequisitos`, `rubrica`. Cada uno tipado por un sub-schema Pydantic en `packages/contracts/`.

**Ventajas**:
- Tipado por concepto — el consumidor sabe el shape de cada campo.
- Validación Pydantic en la boundary (POST/PATCH valida cada sub-schema).
- El frontend puede tener forms separados por concepto (UX más manejable).
- Mantiene el patrón ADR-034.
- El wizard IA puede ser un solo prompt cuyo output Pydantic parsea y disecciona en los campos correspondientes.

**Desventajas**:
- 8 columnas JSONB en la tabla en lugar de 1 — pero el ALTER TABLE es trivial y el costo de almacenamiento es comparable.

### Opción C — Tablas relacionales separadas para cada concepto

Tabla `ejercicio_preguntas_socraticas`, `ejercicio_misconceptions`, `ejercicio_anti_patrones`, etc. con FK a `ejercicios.id`.

**Ventajas**: máxima normalización; queries SQL clásicas sobre preguntas individuales.

**Desventajas**:
- Sobre-ingeniería para la escala del piloto (<50 entradas por ejercicio, ~1250 entradas totales con 25 ejercicios).
- Cargar un ejercicio para el tutor requiere ~7 queries adicionales (JOIN o roundtrip por tabla).
- El wizard IA produce el output completo de un ejercicio; insertar significa ~7 INSERT batched.
- No hay caso de uso de "queries cross-ejercicio por pregunta" que justifique la normalización.
- Rechazada por el mismo razonamiento que ADR-034 rechazó tablas separadas para test_cases.

## Decisión

Opción elegida: **B** — campos JSONB tipados separados con validación Pydantic, alineado con el patrón establecido por ADR-034.

### Shape de los campos pedagógicos

Todos los sub-schemas viven en `packages/contracts/src/platform_contracts/academic/ejercicio.py`.

#### `tutor_rules: dict | None` (column JSONB nullable)

```python
class TutorRulesSchema(BaseModel):
    """Reglas operativas del tutor para este ejercicio.

    Se inyectan al system message del tutor al abrir el episodio.
    """
    prohibido_dar_solucion: bool = True
    forzar_pregunta_antes_de_hint: bool = False
    nivel_socratico_minimo: int = Field(ge=1, le=4, default=1)
    instrucciones_adicionales: str | None = None
    # ej. instrucciones_adicionales = "Prohibido aceptar lista en este
    # ejercicio. El enunciado prohíbe listas explícitamente."
```

#### `banco_preguntas: dict | None` (column JSONB nullable)

```python
class PreguntaSocraticaSchema(BaseModel):
    texto: str = Field(min_length=1)
    senal_comprension: str = Field(min_length=1)  # señal ✓
    senal_alerta: str = Field(min_length=1)        # señal ✗

class BancoPreguntasSchema(BaseModel):
    """Banco de preguntas socráticas estratificadas por fase N1-N4.

    Replica la estructura de los bancos PID-UTN (b1.docx, condi.docx,
    mixtos.docx). El tutor selecciona preguntas según el nivel cognitivo
    inferido del turno actual.
    """
    n1: list[PreguntaSocraticaSchema] = Field(default_factory=list)
    n2: list[PreguntaSocraticaSchema] = Field(default_factory=list)
    n3: list[PreguntaSocraticaSchema] = Field(default_factory=list)
    n4: list[PreguntaSocraticaSchema] = Field(default_factory=list)
```

#### `misconceptions: list[dict]` (column JSONB, default `[]`)

```python
class MisconceptionSchema(BaseModel):
    """Misconception anticipada del estudiante en este ejercicio.

    Sigue el formato del catálogo de los bancos PID-UTN.
    """
    descripcion: str = Field(min_length=1)
    probabilidad_estimada: float = Field(ge=0.0, le=1.0)
    pregunta_diagnostica: str = Field(min_length=1)
```

#### `respuesta_pista: list[dict]` (column JSONB, default `[]`)

```python
class PistaSchema(BaseModel):
    """Anti-solución: lo que el tutor dice cuando el estudiante pide código.

    El nivel indica cuánto del razonamiento el estudiante ya construyó
    (N1-N4); pistas de nivel más alto contienen más estructura sin entregar
    la solución directa.
    """
    nivel: int = Field(ge=1, le=4)
    pista: str = Field(min_length=1)
```

#### `heuristica_cierre: dict | None` (column JSONB nullable)

```python
class HeuristicaCierreSchema(BaseModel):
    """Cuándo el tutor puede declarar el episodio cerrado."""
    tests_min_pasados: int = Field(ge=0, default=0)
    heuristica: str = Field(min_length=1)
    # ej. heuristica = "Estudiante explica con sus palabras por qué eligió
    # if/elif y no if/if; tabla de prueba con caso límite verificado."
```

#### `anti_patrones: list[dict]` (column JSONB, default `[]`)

```python
class AntiPatronSchema(BaseModel):
    """Anti-patrones específicos de este ejercicio que el tutor NO debe hacer."""
    patron: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    mensaje_orientacion: str = Field(min_length=1)
    # ej. patron = "Pregunta cerrada sobre umbral inclusive"
    #     descripcion = "Convierte al tutor en verificador de memorización"
    #     mensaje_orientacion = "Devolver: '¿El enunciado lo dice explícitamente o lo deja implícito?'"
```

#### `prerequisitos: dict` (column JSONB, default `{}`)

```python
class PrerequisitosSchema(BaseModel):
    sintacticos: list[str] = Field(default_factory=list)   # ej. ["if", "while", "len()"]
    conceptuales: list[str] = Field(default_factory=list)  # ej. ["umbrales inclusive/exclusive"]
```

#### `rubrica: dict | None` (column JSONB nullable)

```python
class CriterioRubricaSchema(BaseModel):
    nombre: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    puntaje_max: Decimal = Field(gt=0)

class RubricaEjercicioSchema(BaseModel):
    criterios: list[CriterioRubricaSchema] = Field(default_factory=list)
```

Nota: la rúbrica baja de nivel TP a nivel ejercicio. El campo `TareaPractica.rubrica` (JSONB nullable) se mantiene para compatibilidad y para rúbricas que evaluen la TP en su conjunto (no por ejercicio), pero la calificación por ejercicio usa `Ejercicio.rubrica`.

### Cómo se consume desde el tutor-service

`tutor_core.py::open_episode` resuelve el `Ejercicio` por UUID (ADR-047) y compone el system message agregando bloques en este orden:

1. Prompt base del tutor (de governance-service, versión activa `tutor/v1.1.0`).
2. **Contexto del ejercicio**:
   - `titulo`, `enunciado_md`, `inicial_codigo`.
3. **Reglas operativas del ejercicio** (`tutor_rules.instrucciones_adicionales` si existe).
4. **Mapa privado de navegación pedagógica**:
   - `rubrica.criterios` — para que el tutor sepa qué evaluar.
   - `heuristica_cierre.heuristica` — para que sepa cuándo cerrar.
   - `prerequisitos` — para no introducir conceptos fuera de banda.
5. **Banco socrático del ejercicio**:
   - `banco_preguntas.n1`/`n2`/`n3`/`n4` — repertorio del que el tutor puede sacar preguntas.
   - `misconceptions` — confusiones anticipadas con su pregunta diagnóstica.
   - `respuesta_pista` — qué decir si el estudiante pide código directo.
6. **Anti-patrones**:
   - `anti_patrones` — qué NO hacer.

Todos estos bloques son **inyección de contexto**, no cambios al prompt base. Por lo tanto **no requieren bumpear la versión del prompt** del governance-service (ver ADR-037).

### Validación en boundary

Los endpoints `POST /api/v1/ejercicios` y `PATCH /api/v1/ejercicios/{id}` reciben `EjercicioCreate` / `EjercicioUpdate` (definidos en ADR-047), que internamente usan los sub-schemas de este ADR. Pydantic valida en deserialización.

Para la persistencia, los sub-schemas se serializan a dict via `model_dump(mode="json")` y se guardan en las columnas JSONB. Al leer, `model_validate(jsonb_dict)` reconstruye los modelos tipados.

## Consecuencias

### Positivas

- **Doctrina pedagógica como dato editable**: el docente puede ajustar el banco socrático de un ejercicio sin redeploy.
- **Trazabilidad cognitiva completa**: cualquier evento del CTR puede referenciar el `ejercicio_id` (ADR-049) y reconstruir el banco socrático completo que se inyectó al tutor en ese momento — necesario para validar la tesis con datos reales.
- **Tipado granular**: el frontend, el wizard IA y el tutor-service comparten el schema y trabajan con objetos tipados.
- **Forms del web-teacher manejables**: una vista por concepto (banco socrático, misconceptions, anti-patrones, etc.) en lugar de un único form gigante.
- **Wizard IA tractable**: un solo prompt que devuelve un JSON con el shape de `EjercicioCreate`, Pydantic valida, se persiste.
- **Material pedagógico canónico institucional**: los 25 ejercicios PID-UTN entran al sistema con su doctrina socrática completa, no solo el enunciado.

### Negativas / trade-offs

- **El wizard IA debe generar contenido pedagógicamente correcto**: si el LLM inventa misconceptions implausibles o preguntas socráticas mal construidas, el tutor las inyecta tal cual. **Mitigación**: el wizard devuelve borrador para revisión humana del docente; no auto-publica. El prompt del wizard incluye instrucciones explícitas + few-shot examples extraídos de los bancos PID-UTN.
- **Schema rígido vs evolución del banco**: si el PID descubre que las misconceptions necesitan un campo nuevo (ej. `unidad_relacionada`), hay que bumpear los schemas Pydantic y migrar los JSONB existentes. **Mitigación**: el JSONB es flexible — campos nuevos opcionales se agregan sin migration data (el Pydantic los marca como `Field(default=None)`).
- **Carga inicial de los 25 ejercicios PID-UTN incompleta**: los `.docx` originales tienen el material en formato narrativo. La transformación a JSONB tipado no es automática — requiere transcripción manual o un pipeline asistido por IA con revisión humana. **Decisión**: cargar primero los campos base (`titulo`, `enunciado_md`, `unidad_tematica`); los campos pedagógicos se completan iterativamente con el wizard IA en modo "enriquecer ejercicio existente" o a mano por el docente.
- **Validación de coherencia entre campos**: hoy no se valida que `misconceptions[i].pregunta_diagnostica` matchee semánticamente con `banco_preguntas.n1`. Esto es coherencia de contenido, no de schema — vive en revisión humana, no en Pydantic.
- **El tutor recibe mucho contexto en el system message**: con todos los campos pedagógicos inyectados, el system message crece significativamente (~2-5k tokens dependiendo del banco). **Costo**: tokens de input por turno. **Mitigación**: el contexto se inyecta una sola vez al abrir el episodio (system message); los turnos subsiguientes solo agregan history. ai-gateway con prompt caching (cuando se implemente para los providers que lo soportan) lo amortiza fuerte. Hoy el costo es absorbible para la escala del piloto.

### Neutras

- **No requiere bumpear `tutor` prompt version**: la inyección es contexto, no cambio estructural del prompt base. Sigue `v1.1.0`. Si en algún momento se decide que el prompt base debe referenciar explícitamente `tutor_rules` (ej. con sección "Reglas operativas específicas del ejercicio"), eso sí requiere bumpear a `v1.2.0`. Por ahora se compone como bloques de contexto agregados.
- **`classifier_config_hash` no se afecta**: este ADR no toca el labeler ni el classifier config. Los campos pedagógicos del ejercicio son contexto para el tutor, no input del classifier.
- **El reflexion-flow (ADR-035, post-cierre) puede consumir `rubrica.criterios` del ejercicio** para generar prompts de reflexión más específicos. Cambio opcional, fuera del scope de este ADR.

## Migration path

Acoplado al de ADR-047. La migration Alembic que crea la tabla `ejercicios` ya incluye todas las columnas JSONB definidas en este ADR.

### Seed asistido de los 25 ejercicios PID-UTN

El flujo recomendado:

1. **Fase 1 — campos base**: YAML `scripts/data/ejercicios-piloto.yaml` con los 25 ejercicios completos en `titulo`, `enunciado_md`, `inicial_codigo`, `unidad_tematica`, `dificultad`, `prerequisitos`, `test_cases`. Sin campos pedagógicos.
2. **Fase 2 — wizard IA enriquece**: por cada ejercicio, llamar a `POST /api/v1/ejercicios/{id}/enrich` (endpoint nuevo, fuera de scope inmediato) que invoca el LLM con el contenido del ejercicio + los anexos relevantes del banco PID-UTN como contexto, y devuelve borrador de `banco_preguntas`, `misconceptions`, `anti_patrones`, `respuesta_pista`, `heuristica_cierre`, `tutor_rules`. El docente revisa, edita y aprueba.
3. **Fase 3 — completar a mano** los ejercicios donde el wizard no es suficiente.

La Fase 1 es seed determinista. Las Fases 2-3 son trabajo del docente — no bloquean el sistema, que funciona con campos pedagógicos vacíos (el tutor opera con el comportamiento socrático genérico del prompt base, sin las particularidades del banco PID-UTN para ese ejercicio).

## Riesgos identificados

- **Volumen del system message**: si el banco pedagógico de un ejercicio es muy denso, el system message puede pasar de los 8k tokens. Riesgo de costo y latencia. **Mitigación**: el `EjercicioService` puede ofrecer un modo "compacto" que serializa solo los campos críticos para los turnos no iniciales (esto es optimización, no requisito).
- **Calidad pedagógica del contenido generado por IA**: el wizard puede producir misconceptions de baja calidad o sesgadas. **Mitigación**: revisión humana obligatoria pre-publicación. El campo `created_via_ai` queda marcado y filtrable en la biblioteca para auditoría.
- **Coherencia entre `Ejercicio.rubrica` y `TareaPractica.rubrica`**: hoy la rúbrica vive a nivel TP. Con este ADR, baja a ejercicio. **Mitigación**: documentar explícitamente que la calificación por ejercicio en `Entrega.detalle_criterios` usa `Ejercicio.rubrica`; `TareaPractica.rubrica` queda como rúbrica global (ej. evaluación de presentación general) si aplica, opcional.
- **Drift entre los bancos `.docx` originales y el schema JSONB persistido**: los `.docx` son la fuente del PID; el sistema persiste una proyección. Cualquier actualización del PID requiere re-sincronización manual o un pipeline de import. **Mitigación**: documentar como deuda. No es bloqueante.

## Referencias

- ADR-034 — test_cases como JSONB (patrón seguido).
- ADR-047 — Ejercicio como entidad de primera clase reusable.
- ADR-049 (paralelo) — `ejercicio_id` en CTR payload.
- ADR-023 — override labeler v1.1.0 (interacción potencial con `banco_preguntas` para inferir nivel del turno).
- Bancos PID-UTN: `Descargas/b1.docx`, `Descargas/condi.docx`, `Descargas/mixtos.docx`.
- ADR-037 — governance UI read-only (justifica no bumpear prompt versión).
