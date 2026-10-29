# Prueba local reproducible — publicar-nota-y-pedir-correccion

Hecha el 2026-10-28 contra Postgres/Redis reales (Docker) y el api-gateway, academic-service y evaluation-service reales
(no mocks de DB). Todo desde la raiz de `rama desarrollo/`, en Git Bash.

## Resultado

| Paso del design | Como se verifico | Resultado |
|---|---|---|
| 1 Stack | Docker Desktop prendido; gateway :8000, academic :8002, evaluation :8004 (`DEV_TRUST_HEADERS=true`, `LLM_PROVIDER=mock`, keys en blanco) | OK (los 3 `/health` = ready) |
| 2 TP de 3 ejercicios | SQL de abajo (TP `LOCAL-PNPC`, sin fecha limite) | OK |
| 3 Entrega del alumno | `prueba-local-api.py` (API, ejercicios con codigo distinto) | OK |
| 4 Publicar nota | API: el alumno lee la nota; estado `graded`; ningun ejercicio reabierto | OK |
| 5 Pedir correccion del 2 | API: 422 con `[]`, `[2,2]`, `[9]`; con `[2]` queda `returned` | OK |
| 6 Lo que ve el alumno | API: 1 y 3 completados con su `episode_id`, 2 reabierto y marcado; PATCH al 1 = 409 en ambos sentidos | OK |
| 7 Re-entrega | API: manda solo el 2 y pasa | OK |
| 8 Lo que ve el docente | API `GET /artefacto`: `print(1)`, `print(22)`, `print(3)`, episode_id originales en 1 y 3 | OK |
| 8b/8c | Re-calificar (#124) + pedir solo el 3; y devolver SIN body reabre los 3 (compat) | OK |
| 9 Compatibilidad | SQL: la devolucion vieja de la base no tiene `reabierto_por_docente` | OK |
| 10 CTR | Conteo de `events` por `event_type` en `ctr_store` antes y despues: identico | OK (0 diferencias) |

**NO verificado por mi (sin navegador): los clicks de UI** — que en web-teacher el boton diga "Publicar nota", que "Pedir correccion" abra el
modal con checkboxes, y que web-student muestre el badge "A corregir" y el ejercicio 4 bloqueado. Eso esta cubierto por tests de componente
(`CorreccionesPedirCorreccion.test.tsx`, `ExerciseListViewParcial.test.tsx`) pero falta un humano que lo mire. Pasos 4-8 de `design.md`
con la UI real (`pnpm turbo dev`, web-teacher :5174, web-student :5175) siguen siendo la prueba manual.

## Como repetirla

```bash
# 0) Docker Desktop prendido. Si el Postgres 18 nativo de Windows ocupa el 5432, frenarlo (admin).
docker ps | grep platform-postgres        # tiene que estar healthy

# 1) Servicios minimos (en una terminal)
export DEV_TRUST_HEADERS=true LLM_PROVIDER=mock OPENAI_API_KEY= ANTHROPIC_API_KEY= GEMINI_API_KEY=
uv run uvicorn api_gateway.main:app --host 127.0.0.1 --port 8000 &
uv run uvicorn academic_service.main:app --host 127.0.0.1 --port 8002 &
uv run uvicorn evaluation_service.main:app --host 127.0.0.1 --port 8004 &

# 2) Sembrar la TP de 3 ejercicios (idempotente solo la primera vez; si ya existe, saltear)
docker exec -i platform-postgres psql -U postgres -d academic_main -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
CREATE TEMP TABLE t AS SELECT * FROM tareas_practicas WHERE codigo='SMK-J4EED';
UPDATE t SET id='5e5e0001-0000-4000-8000-000000000001', codigo='LOCAL-PNPC',
  titulo='Prueba local: publicar nota y pedir correccion', estado='published', fecha_fin=NULL, fecha_inicio=NULL;
INSERT INTO tareas_practicas SELECT * FROM t;
INSERT INTO tp_ejercicios (tenant_id,tarea_practica_id,ejercicio_id,orden,peso_en_tp)
SELECT 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','5e5e0001-0000-4000-8000-000000000001', id,
  row_number() over (order by id), 0.3333
FROM (SELECT id FROM ejercicios WHERE tenant_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' ORDER BY id LIMIT 3) x;
COMMIT;
SQL

# 3) Correr el ciclo (si la entrega de ese alumno para la TP ya existe, borrarla antes:
#    DELETE FROM entregas WHERE tarea_practica_id='5e5e0001-0000-4000-8000-000000000001';)
python openspec/changes/publicar-nota-y-pedir-correccion/prueba-local-api.py   # termina con "OK: todos los pasos..."

# 4) Paso 9 (compatibilidad) y paso 10 (CTR sin eventos nuevos)
docker exec platform-postgres psql -U postgres -d academic_main -Atc "select id, estado, (ejercicio_estados::text like '%reabierto_por_docente%') from entregas where estado='returned'"
docker exec platform-postgres psql -U postgres -d ctr_store -Atc "select event_type||':'||count(*) from events group by 1 order by 1"
# (correr la ultima ANTES y DESPUES del paso 3: los conteos tienen que ser iguales)
```

Para la prueba con UI: ademas `pnpm turbo dev` y seguir los pasos 2-8 de `design.md`.
Notas del entorno: con 403 "de otro tenant" -> `UPDATE universidades SET tenant_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' WHERE id='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';`.
