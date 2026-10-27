#!/usr/bin/env bash
# Levanta los servicios que la prueba 6.3 necesita. Correr desde la raiz del repo.
# Requiere Docker con platform-postgres y platform-redis arriba (make dev-bootstrap).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
D=openspec/changes/tutor-ve-salida-de-ejecucion
mkdir -p .dev-logs; : > .dev-logs/pids-6.3.txt
PY=.venv/Scripts/python.exe
export LLM_PROVIDER=mock EMBEDDER=mock RERANKER=identity STORAGE=mock
# Sin keys: si no, el ai-gateway cae al provider real (el .env trae sk-REPLACE_ME) y devuelve 401.
export OPENAI_API_KEY= OPENROUTER_API_KEY= ANTHROPIC_API_KEY= GEMINI_API_KEY= MISTRAL_API_KEY=
export PROMPTS_REPO_PATH="$(cygpath -w "$PWD/ai-native-prompts")"
export ESPEJO_LOG="$PWD/.dev-logs/espejo-requests.jsonl"; : > "$ESPEJO_LOG"
sv() { # modulo puerto nombre [env extra]
  env ${4:-} "$PY" -m uvicorn "$1:app" --host 127.0.0.1 --port "$2" --log-level info > ".dev-logs/6.3-$3.log" 2>&1 &
  echo "$! $3" >> .dev-logs/pids-6.3.txt
}
sv governance_service.main 8010 governance
sv ai_gateway.main 8011 ai-gateway
sv ctr_service.main 8007 ctr
sv academic_service.main 8002 academic
sv content_service.main 8009 content
sv ai_gateway_espejo 8111 espejo "PYTHONPATH=$D"
sv tutor_service.main 8006 tutor "AI_GATEWAY_URL=http://127.0.0.1:8111"
for p in 0 1 2 3 4 5 6 7; do
  "$PY" -m ctr_service.workers.partition_worker --partition "$p" > ".dev-logs/6.3-ctr-worker-$p.log" 2>&1 &
  echo "$! ctr-worker-$p" >> .dev-logs/pids-6.3.txt
done
echo "Arrancados. PIDs en .dev-logs/pids-6.3.txt"
