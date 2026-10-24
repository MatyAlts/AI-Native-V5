#!/bin/sh
# Supervisor de UN partition_worker (CTR_MODE=server).
#
# Uso: ctr-supervise-worker <particion>
#
# Corre el worker en FOREGROUND dentro de un loop: si el proceso termina por
# cualquier motivo, espera un backoff creciente y lo relanza. Un supervisor por
# particion + relanzo serial (el siguiente lanzamiento ocurre recien cuando el
# anterior ya termino) => nunca hay dos procesos de la misma particion y se
# preserva el single-writer de ADR-010. Un worker colgado-pero-vivo NO se
# relanza (eso lo detecta el heartbeat de /health/ready): relanzar algo vivo si
# romperia single-writer.
#
# Contexto: 2026-10-16 y 2026-10-23 los 8 workers murieron al arrancar y nada
# los volvio a levantar mientras el HTTP seguia devolviendo 202.
#
# Variables (todas opcionales):
#   CTR_VENV_PY                 python a usar (default /app/.venv/bin/python;
#                               los tests inyectan un worker falso)
#   CTR_SUPERVISE_BACKOFF_MAX   tope del backoff en segundos (default 30)
#   CTR_SUPERVISE_RESET_AFTER   si el worker vivio >= N s, el backoff vuelve a 1
#                               (default 60)
#   CTR_SUPERVISE_MAX_RESTARTS  tope de LANZAMIENTOS y luego sale con el rc del
#                               ultimo; vacio = infinito. Solo para tests.
#
# Logs en ASCII a stdout.

p="${1:?uso: ctr-supervise-worker <particion>}"
VENV_PY="${CTR_VENV_PY:-/app/.venv/bin/python}"
BACKOFF_MAX="${CTR_SUPERVISE_BACKOFF_MAX:-30}"
RESET_AFTER="${CTR_SUPERVISE_RESET_AFTER:-60}"
MAX_LAUNCHES="${CTR_SUPERVISE_MAX_RESTARTS:-}"

delay=1
launches=0
while true; do
  launches=$((launches + 1))
  t0=$(date +%s)
  "$VENV_PY" -m ctr_service.workers.partition_worker --partition "$p"
  rc=$?
  vivio=$(($(date +%s) - t0))

  # Si estuvo vivo un buen rato no era un crash-loop: arrancar de nuevo rapido.
  if [ "$vivio" -ge "$RESET_AFTER" ]; then
    delay=1
  fi

  if [ -n "$MAX_LAUNCHES" ] && [ "$launches" -ge "$MAX_LAUNCHES" ]; then
    echo "[ctr-supervisor] partition=$p salio rc=$rc tras ${vivio}s; tope de lanzamientos ($MAX_LAUNCHES) alcanzado, no relanzo"
    exit "$rc"
  fi

  echo "[ctr-supervisor] partition=$p salio rc=$rc tras ${vivio}s; relanzo en ${delay}s"
  sleep "$delay"
  delay=$((delay * 2))
  if [ "$delay" -gt "$BACKOFF_MAX" ]; then
    delay="$BACKOFF_MAX"
  fi
done
