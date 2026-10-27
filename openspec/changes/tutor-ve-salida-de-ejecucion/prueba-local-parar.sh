#!/usr/bin/env bash
# Baja los servicios de la prueba 6.3 (por puerto: el launcher del venv deja procesos hijos).
for port in 8010 8011 8007 8002 8009 8111 8006; do
  for pid in $(netstat -ano | grep ":$port .*LISTENING" | awk '{print $NF}' | sort -u); do
    powershell -c "Stop-Process -Id $pid -Force" 2>/dev/null
  done
done
# Workers del CTR: no escuchan puerto, se matan por linea de comando.
powershell -c "Get-CimInstance Win32_Process | ? { \$_.CommandLine -match 'partition_worker' } | % { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo "Servicios bajados."
