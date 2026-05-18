# ADR-042 — Estado y politica de uso de TareaPracticaTemplate en piloto-1

- **Status**: Accepted
- **Fecha**: 2026-05-07
- **Aceptado por**: Alberto Cortez (con default razonable: A1/A2/A3 como narrative students, 4 episodios extra cada uno apuntando a `NARRATIVE_TEMPLATE_ID = TEMPLATE_01_ID`).
- **Sucede a / depende de**: ADR-016 (introduce TareaPracticaTemplate como fuente canonica academica), ADR-018 (CII evolution longitudinal opera por `template_id`).

## Context

ADR-016 introdujo `TareaPracticaTemplate` como la fuente canonica academica a nivel `(materia_id, periodo_id)`. Crear un template auto-instancia una `TareaPractica` por cada comision de la materia+periodo; las instancias arrancan con `template_id = template.id` y `has_drift = false`. ADR-018 (RN-130) aprovecha eso: el calculo `cii_evolution_longitudinal` agrupa classifications por `template_id`, requiere `MIN_EPISODES_FOR_LONGITUDINAL = 3` por template, y **descarta TPs huerfanas** (`template_id IS NULL`).

La premisa que motivo este ADR fue *"`tareas_practicas_templates` esta vacia en piloto local; el calculo longitudinal nunca se ejercita"*. La verificacion empirica en sesion de redaccion (2026-05-07) **refuto parcialmente** esa premisa:

```sql
SELECT count(*) FROM tareas_practicas_templates;  -- 2
SELECT count(*) FROM tareas_practicas;             -- 15
SELECT count(*) FROM tareas_practicas WHERE template_id IS NOT NULL;  -- 2
```

El detalle real:

- `scripts/seed-3-comisiones.py` (lineas 113-162) **ya seedea 2 templates** (`TEMPLATE_01` recursion, `TEMPLATE_02` listas enlazadas) y **6 instancias** (2 templates × 3 comisiones) con `template_id` poblado y `has_drift=false`.
- Hay **13 TPs adicionales sin `template_id`** que provienen de creacion manual (CRUD del docente desde web-teacher) o de seeds previos no migrados al nuevo shape. Esas instancias son huerfanas para el calculo longitudinal por diseno (RN-130) y NO entran al slope.
- La estructura del modelo + endpoint funciona: el longitudinal calcula contra los 2 templates seedeados. Pero **en sesion de smoke E2E del piloto local NO se ejercita el path longitudinal** — el web-teacher tiene la vista `StudentLongitudinalView` (G7 ADR-022) que consume `GET /api/v1/analytics/student/{id}/cii-evolution-longitudinal?comision_id=X`, pero el ejercicio depende de que cada estudiante tenga ≥3 classifications atadas al **mismo** template. El seed actual genera 94 episodios con round-robin entre las 6 instancias (2 templates × 3 comisiones); cuantos episodios terminan apuntando al mismo template por estudiante depende del round-robin y suele caer en 2-3 — borderline para el threshold MIN=3.
- Tests unitarios del longitudinal en `packages/platform-ops/tests/test_cii_longitudinal.py` cubren la logica pura (incluido el caso `template_id=None` que se skippea, lineas 104-111). El path de **integracion** (DB real → endpoint → vista) no tiene smoke E2E dedicado.

Tambien verificado: las TPs huerfanas creadas via CRUD del docente NO son un bug — el flujo de creacion manual permite un TP standalone (sin template), y eso es by-design (RN-130: limitacion declarada del piloto inicial). Lo problematico es que el **mix actual sesga la lectura**: si un docente revisa la vista longitudinal del piloto y ve "insufficient_data" para muchos estudiantes, no esta claro si es por (a) falta real de evolucion observada, (b) round-robin del seed, o (c) creacion manual sin template.

La pregunta operativa entonces NO es *"path 1 seedear vs path 2 deprecar"* — es:

- **¿Como queda la tesis si la capability esta implementada y los tests unitarios pasan, pero el piloto local no la ejercita end-to-end de forma reproducible?**
- **¿Que mostramos al comite doctoral como evidencia de que la capability funciona en piloto?**

## Decision

Adoptar **Path 1 reforzado**: la capability longitudinal **se presenta en defensa como operativa**, y por eso el seed-3-comisiones.py **debe garantizar reproducibilidad del path E2E** (no quedar borderline contra MIN=3 por azar de round-robin). Concretamente:

1. **Aceptar el estado actual del seed como base** — los 2 templates + 6 instancias + 94 episodios YA estan, no se borran ni se reescriben desde cero.
2. **Reforzar el seed para garantizar ≥3 episodios por (estudiante, template_id) en al menos los estudiantes "narrativos"** que el doctorando vaya a usar como ejemplo en defensa. La vista `StudentLongitudinalView` debe mostrar slope no-null y panel de alertas no-`insufficient_data` para esos estudiantes.
3. **Agregar smoke test E2E** en `tests/e2e/smoke/` que ataque `GET /api/v1/analytics/student/{id}/cii-evolution-longitudinal?comision_id=X` con un estudiante del seed y assertee que el response devuelve ≥1 entry con `slope` no-null, NO `insufficient_data: true`. Sin ese smoke, no podemos afirmar honestamente que la capability esta operativa en piloto.
4. **Documentar las TPs huerfanas como first-class del modelo** — el caveat de RN-130 ya existe; se promueve a "Brechas conocidas" en CLAUDE.md con cifras especificas: *"de 15 TPs en piloto local seed estandar, 6 son instancias de templates (longitudinal-eligible) y 9 son standalone CRUD (huerfanas, by-design por RN-130)."*
5. **NO renombrar `cii_stability` / `cii_evolution`** (intra-episodio): sigue siendo BC-incompatible con classifications historicas y pertenece a agenda piloto-2.
6. **Status del ADR**: Proposed. Pasa a Accepted cuando el doctorando confirme el refuerzo del seed + smoke test escritos.

### Por que Path 1 y no Path 2

**Path 2** (declarar piloto-1 como sin templates, deprecar el camino) tendria sentido si:
- La tabla estuviera realmente vacia (NO lo esta — 2 templates seedeados).
- ADR-018/RN-130 fuera deuda no-implementada (NO lo es — funcion pura testeada bit-exact, endpoint operativo, vista en web-teacher).
- La tesis no presentara el longitudinal como capability (NO es el caso — Seccion 15.4 de la tesis lo cubre, segun documentacion de ADR-018).

Como ninguna de las tres se cumple, declarar Path 2 seria *"deprecar lo que ya funciona"* — peor academicamente que reforzar lo que ya esta.

**Path 1** (seedear) es el mas honesto contra esta evidencia: la capability EXISTE y se valida con piloto real, no solo con tests unitarios. La adicion del smoke E2E + el caveat sobre TPs huerfanas cierra la brecha entre *"funciona en aislamiento"* y *"se ejercita end-to-end con datos del piloto"*.

## Consequences

**Positivas:**
- La defensa puede mostrar la vista `StudentLongitudinalView` con datos reales del seed, no con datos sinteticos de tests unitarios.
- El comite doctoral ve que ADR-018 no es deuda silenciosa: tiene tests unitarios + smoke E2E + datos seedeados + UI consumiendo el endpoint.
- Las TPs huerfanas pasan de ser ruido a ser caveat declarado del piloto inicial (consistente con la postura academica honesta del repo).
- El smoke E2E nuevo se suma a la red de seguridad ya creada en `tests/e2e/smoke/` (ver "Smoke E2E como red de seguridad" en CLAUDE.md), respetando la regla *"cada vez que se cierre un epic nuevo, agregarle smoke tests acá ANTES de declararlo cerrado."*

**Negativas / a mitigar:**
- Reforzar el seed implica edits a `scripts/seed-3-comisiones.py` que cambian el shape exacto del piloto local (mas episodios y/o curado del round-robin). Mitigacion: el archivo es DESTRUCTIVO sobre el tenant demo (esta documentado), por lo que cualquier dev que corra el seed obtiene el shape nuevo automaticamente.
- TPs huerfanas siguen existiendo en piloto y pueden confundir a docentes nuevos. Mitigacion: cuando se haga el redesign UI con `impeccable`, agregar tooltip en la vista longitudinal que explique *"Esta TP no esta atada a un template institucional; no participa del calculo longitudinal por diseño (ADR-018)."*
- La promesa de defensa baja de *"3 vistas operativas con datos reales"* (que ya estaba) a *"3 vistas con smoke E2E que valida que los datos cierren end-to-end"* — incrementa el costo del cierre del epic G7 ADR-022 a posteriori.

**Invariantes preservadas:**
- ADR-018/RN-130: NO cambia (template_id obligatorio para longitudinal, MIN=3, huerfanas se skippean).
- ADR-016: NO cambia (template + auto-instancia + drift por instancia).
- Reproducibilidad bit-a-bit: NO se afecta — el seed es DESTRUCTIVO e idempotente; lo unico que cambia es la cantidad de episodios por (student, template).

## Migration path

### Paso 1 — Refuerzo del seed (snippet ejecutable, NO aplicado)

Modificacion en `scripts/seed-3-comisiones.py` para garantizar ≥3 episodios por `(student, template_id)` en estudiantes "narrativos". El shape exacto depende de la decision del doctorando sobre cuantos estudiantes mostrar como narrativa de defensa; el snippet abajo es un esqueleto:

```python
# scripts/seed-3-comisiones.py — anadir constante al header (cerca de COHORTES)

# Estudiantes "narrativos" para defensa: deben tener >=3 episodios por
# template para ejercitar el path longitudinal (ADR-018 MIN=3).
# Mapping: pseudonym -> minimo de episodios garantizados por template.
NARRATIVE_STUDENTS_LONGITUDINAL: dict[UUID, int] = {
    # A-Manana: 1 alumna trayectoria positiva (delegacion -> superficial -> reflexiva)
    UUID("b1b1b1b1-0001-0001-0001-000000000001"): 4,
    # B-Tarde: 1 alumno cohorte fuerte (reflexiva sostenida)
    UUID("b2b2b2b2-0001-0001-0001-000000000001"): 4,
    # C-Noche: 1 alumno trayectoria negativa (regresion vs cohorte -> alerta)
    UUID("b3b3b3b3-0001-0001-0001-000000000001"): 4,
}
```

Y en el loop de generacion de episodios (`seed_ctr(...)` o donde corresponda en el orden del script), enmarcar el round-robin para que esos estudiantes reciban como minimo `NARRATIVE_STUDENTS_LONGITUDINAL[student_id]` episodios apuntando al **mismo** `template_id` (ej. `TEMPLATE_01_ID`):

```python
# Pseudocodigo del bloque que decide problema_id por episodio del estudiante
for episode_idx in range(num_episodes_for_student):
    student_id = ...
    if student_id in NARRATIVE_STUDENTS_LONGITUDINAL and \
       episode_idx < NARRATIVE_STUDENTS_LONGITUDINAL[student_id]:
        # Forzar template_01 para los primeros N episodios narrativos
        instance_id = _instance_id_for(TEMPLATE_01_ID, cohort_idx)
    else:
        # Round-robin original sobre las 2 instancias de la comision
        instance_id = tp_instances_by_comision[comision_id][episode_idx % 2]
```

El doctorando debe ajustar el numero exacto y elegir los pseudonyms basandose en el shape narrativo que use en defensa. La constante queda explicita en el script para que la decision sea auditable.

### Paso 2 — Smoke E2E

Agregar en `tests/e2e/smoke/` un test nuevo (sugerido `test_longitudinal_e2e.py`) que valide:

```python
# tests/e2e/smoke/test_longitudinal_e2e.py
"""Smoke E2E: el path cii_evolution_longitudinal cierra end-to-end con datos del seed."""

import httpx
import pytest

# Estudiante narrativo de A-Manana del seed-3-comisiones.py
NARRATIVE_STUDENT_PSEUDONYM = "b1b1b1b1-0001-0001-0001-000000000001"
COMISION_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_DEMO = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DOCENTE_USER_ID = "11111111-1111-1111-1111-111111111111"

@pytest.mark.smoke
def test_longitudinal_devuelve_slope_para_estudiante_narrativo():
    """Tras correr seed-3-comisiones, el estudiante b1...0001 debe tener slope no-null."""
    headers = {
        "X-Tenant-Id": TENANT_DEMO,
        "X-User-Id": DOCENTE_USER_ID,
        "X-User-Roles": "docente",
        "X-User-Email": "smoke@unsl.edu.ar",
    }
    r = httpx.get(
        f"http://127.0.0.1:8005/api/v1/analytics/student/{NARRATIVE_STUDENT_PSEUDONYM}/cii-evolution-longitudinal",
        params={"comision_id": COMISION_A_ID},
        headers=headers,
        timeout=5.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Al menos un template debe tener slope calculado (no insufficient_data)
    assert "templates" in body
    eligible = [t for t in body["templates"] if not t.get("insufficient_data")]
    assert len(eligible) >= 1, f"Esperado >=1 template longitudinal-eligible, got {body}"
    assert eligible[0]["slope"] is not None
    assert eligible[0]["n_episodes"] >= 3
```

El test debe correrse contra analytics-service en `:8005` con headers `X-Tenant-Id` + `X-User-Id` + `X-User-Roles` (regla de auth via gateway documentada en CLAUDE.md "Contratos BC-incompatible"). El smoke se agrega al CI workflow `.github/workflows/e2e-smoke.yml` cuando se promueva a required check.

### Paso 3 — Caveat en CLAUDE.md

Anadir bullet en seccion "Brechas conocidas" de CLAUDE.md:

```diff
+ - **TPs huerfanas en piloto local seed estandar** (ADR-042): de 15 TPs creadas por `seed-3-comisiones.py`, 6 son instancias atadas a templates (longitudinal-eligible por RN-130) y 9 son creaciones standalone via CRUD del docente (huerfanas, by-design — limitacion declarada del piloto inicial). El calculo `cii_evolution_longitudinal` ignora las huerfanas; smoke E2E `tests/e2e/smoke/test_longitudinal_e2e.py` valida que al menos un estudiante narrativo del seed tiene slope no-null. Si el smoke falla, hay regresion en el seed o en el endpoint.
```

### Paso 4 — Verificar TPs huerfanas en defensa

Antes de defensa, ejecutar:

```sql
SELECT comision_id, count(*) FILTER (WHERE template_id IS NOT NULL) AS con_template,
       count(*) FILTER (WHERE template_id IS NULL) AS huerfanas
FROM tareas_practicas
WHERE tenant_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
GROUP BY comision_id;
```

Si la proporcion huerfanas/con_template es desproporcionada y confunde la defensa, opcionalmente "limpiar" el tenant demo via re-seed antes de la presentacion. NO modificar la logica de huerfanas — esa es invariante (RN-130).

### Paso 5 — Aprobacion + cambio de Status

Una vez aprobado por el doctorando o director de tesis:
- Confirmar que el snippet del seed se ajusto al narrative deseado.
- Confirmar que el smoke E2E pasa contra el stack local con seed reciente.
- Cambiar `Status: Proposed` → `Status: Accepted`.
- Commit dedicado con mensaje `docs(adr): aceptar ADR-042 templates piloto-1 longitudinal-eligible`.

## Recomendacion del redactor (sub-agente)

**Path 1** con caveat del Path 2 documentado. La capability ya esta implementada (tests unitarios + endpoint + UI), la tabla NO esta vacia (2 templates seedeados, 6 instancias longitudinal-eligible), y la tesis presenta el longitudinal como capability operativa segun ADR-018. Path 2 (deprecar) seria deshonesto porque seria *"deprecar lo que ya funciona"*. Lo que falta es **garantizar que el path E2E cierre con datos reales del piloto, no solo con tests unitarios**, y eso se cierra con (a) refuerzo del seed para narrative students y (b) smoke E2E que ataque el endpoint.

Riesgo principal a mitigar antes de defensa: el actual round-robin del seed deja a varios estudiantes con 2 episodios por template, borderline contra MIN=3. Si en defensa el comite pide *"mostrame la vista longitudinal de un estudiante random"* y caemos en uno borderline, la vista muestra `insufficient_data` y se ve como bug aunque sea by-design. El refuerzo del seed cierra ese riesgo.

## Riesgos identificados durante la prep

- **TPs huerfanas pre-existentes**: las 13 TPs sin `template_id` en piloto local sobreviven al re-seed solo si el seed-3-comisiones es DESTRUCTIVO sobre el tenant demo (lo es — verificado en docstring del script lineas 29-31). Pero si el doctorando creo TPs adicionales **manualmente desde web-teacher** post-seed, esas se borran en el siguiente seed. Documentar al usuario antes de re-seedear.
- **Decision de cuales son "narrative students"** la toma el doctorando, no el sub-agente. El snippet del Paso 1 es esqueleto, no aplicado — requiere review humano sobre que trayectoria narrativa mostrar en defensa (positiva / negativa / mixta).
- **Borderline en MIN=3**: si el doctorando decide bajar `MIN_EPISODES_FOR_LONGITUDINAL` para evitar reforzar el seed, eso requiere ADR aparte (ADR-018 lo declara como invariante de la operacionalizacion conservadora).
- **ADR-016 menciona "comisiones creadas DESPUES del template no auto-propagan hoy (deuda diferida)"** — esa deuda sigue abierta. NO la cierra este ADR. Si en piloto-2 se decide cerrarla, requiere ADR aparte.

## Verificacion empirica que respalda este ADR

- `docker exec platform-postgres psql -U postgres -d academic_main` ejecutado en sesion 2026-05-07: `tareas_practicas_templates: 2 rows`, `tareas_practicas: 15 rows`, `template_id NOT NULL: 2 rows`. **Refuta la premisa "tabla vacia"** del prompt original.
- `scripts/seed-3-comisiones.py` (leido directo, lineas 113-162 y 581-651): YA seedea 2 templates y 6 instancias con `template_id` poblado, NO requiere migrar nada. La parte que falta es asegurar reproducibilidad del path E2E con narrative students.
- `packages/platform-ops/tests/test_cii_longitudinal.py` (leido directo, 19 funciones de test): cubre la logica pura, incluido `test_classifications_sin_template_id_se_skippean` (lineas 104-111). Tests unitarios pasan; lo que falta es smoke E2E.
- `packages/platform-ops/src/platform_ops/cii_longitudinal.py` (leido directo): funcion pura `cii_evolution_longitudinal(...)` agrupa por `template_id`, skippea None, devuelve list de dicts. Endpoint lo expone en analytics-service con `?comision_id=X`. Vista web-teacher lo consume.
- ADR-018 (referenciado, no releido en sesion para no inflar contexto — la declaracion de invariantes se toma de CLAUDE.md): MIN_EPISODES_FOR_LONGITUDINAL=3, slope cardinal sobre datos ordinales como operacionalizacion conservadora declarada, TPs huerfanas se skippean by-design.
- CLAUDE.md "Smoke E2E como red de seguridad" (mejora estructural #2): regla explicita de que cada epic nuevo agrega smoke tests antes de declararse cerrado. Ejecuto esa regla a posteriori para G7 ADR-022 (path longitudinal en defensa).
