#!/usr/bin/env bash
# Reset el estado a "recien clonado + seeds canonicos corridos".
#
# Borra lo generado por uso/testing (TPs creadas, unidades, episodios,
# clasificaciones, ejercicios IA) pero PRESERVA los seeds canonicos:
#   - 5 comisiones + docentes + alumnos (seed-3-comisiones.py)
#   - 25 ejercicios del piloto (seed-ejercicios-piloto.py)
#   - Policies Casbin
#   - BYOK keys (las cargo cada uno con su API key)
#
# Util para:
#   - Reproducir el estado base antes de demos
#   - Limpiar entre sesiones de testing
#   - Onboardar a un compañero sin polucion previa
#
# Uso:
#   bash scripts/reset-to-seed.sh

set -euo pipefail

DB_ACADEMIC="academic_main"
DB_CTR="ctr_store"
DB_CLASSIFIER="classifier_db"

echo "==> Borrando estado generado (preserva seeds canonicos)..."

# Episodios + eventos CTR (cascada: events -> episodes)
docker exec platform-postgres psql -U postgres -d "$DB_CTR" -c "
  SET row_security = off;
  TRUNCATE TABLE events, episodes RESTART IDENTITY CASCADE;
" >/dev/null
echo "  [OK] ctr_store: events + episodes vacios"

# Clasificaciones N4
docker exec platform-postgres psql -U postgres -d "$DB_CLASSIFIER" -c "
  SET row_security = off;
  TRUNCATE TABLE classifications RESTART IDENTITY CASCADE;
" >/dev/null
echo "  [OK] classifier_db: classifications vacias"

# Vinculos TP-ejercicio, Tareas Practicas, Entregas, Calificaciones, Unidades
# (orden importa por FKs)
docker exec platform-postgres psql -U postgres -d "$DB_ACADEMIC" -c "
  SET row_security = off;
  TRUNCATE TABLE tp_ejercicios RESTART IDENTITY CASCADE;
  DELETE FROM calificaciones;
  DELETE FROM entregas;
  DELETE FROM tareas_practicas;
  DELETE FROM tareas_practicas_templates;
  DELETE FROM unidades;
  -- Ejercicios generados por IA (los 25 del seed quedan: created_via_ai=false)
  DELETE FROM ejercicios WHERE created_via_ai = true;
" >/dev/null
echo "  [OK] academic_main: TPs, unidades, entregas, ejercicios-IA borrados"

echo ""
echo "==> Estado final:"
docker exec platform-postgres psql -U postgres -d "$DB_ACADEMIC" -c "
  SET row_security = off;
  SELECT
    (SELECT COUNT(*) FROM comisiones)          AS comisiones,
    (SELECT COUNT(*) FROM inscripciones)       AS inscripciones,
    (SELECT COUNT(*) FROM usuarios_comision)   AS docentes_asignados,
    (SELECT COUNT(*) FROM ejercicios)          AS ejercicios_banco,
    (SELECT COUNT(*) FROM unidades)            AS unidades,
    (SELECT COUNT(*) FROM tareas_practicas)    AS tps;
"

echo ""
echo "[DONE] Reset OK. Recargar el web-teacher/student para ver el estado limpio."
