#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .dev-logs/pids.txt ]]; then
  while IFS=: read -r pid name port; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" && echo "[stop] $name (pid $pid, :$port)"
    fi
  done < .dev-logs/pids.txt
  rm -f .dev-logs/pids.txt
fi
