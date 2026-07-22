#!/usr/bin/env bash
set -euo pipefail

echo "== Docker disk usage (before) =="
docker system df
echo

echo "== Build cache prune =="
docker builder prune -af
echo

echo "== Dangling image prune =="
docker image prune -f
echo

echo "== Docker disk usage (after) =="
docker system df
echo

cat <<'EOF'
Done.

Safe operations only:
- Pruned build cache
- Pruned dangling images

Intentionally NOT executed:
- docker volume prune
- docker system prune --volumes
EOF
