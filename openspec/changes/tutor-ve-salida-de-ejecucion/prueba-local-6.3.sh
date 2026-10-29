#!/usr/bin/env bash
# Prueba local 6.3: el tutor ve la salida de la ultima ejecucion.
# Requiere: stack arriba (prueba-local-arrancar.sh). Correr desde la raiz del repo.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
PY=.venv/Scripts/python.exe
LOG=.dev-logs/espejo-requests.jsonl
T=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa           # tenant y comision del seed
TP=211f7eba-4be8-456b-80fc-26b5d98f6403          # TP publicada sin deadline (SMK-LPF8CD)
U=e19354fb-c05a-4535-a0bf-a7d3ea09692d           # DEV_STUDENT_UUID
H=(-H "X-Tenant-Id: $T" -H "X-User-Id: $U" -H "X-User-Email: dev@test.local" -H "X-User-Roles: estudiante" -H "Content-Type: application/json")
HASH=$(printf 'a%.0s' $(seq 64))
API=localhost:8006/api/v1/episodes
ok=0; fail=0
chk() { if [ "$2" = "1" ]; then echo "  [OK]   $1"; ok=$((ok+1)); else echo "  [FALLA] $1"; fail=$((fail+1)); fi; }

# Imprime el mensaje `system` de la salida en la ultima request al LLM y devuelve flags.
ultimo() { "$PY" -I - "$LOG" <<'PYEOF'
import json, sys
lineas = open(sys.argv[1], encoding="utf-8").read().splitlines()
msgs = json.loads(lineas[-1])["messages"]
bloque = [m["content"] for m in msgs if m["role"] == "system" and m["content"].startswith("Salida de la ultima ejecucion")]
print("--- request #%d al LLM: %d mensajes; bloque de salida:" % (len(lineas), len(msgs)))
for l in (bloque[0].splitlines() if bloque else ["(SIN BLOQUE)"]):
    print("    | " + l)
orden = [i for i, m in enumerate(msgs) if m["role"] == "system" and m["content"].startswith("Salida de la ultima")]
print("--- posicion del bloque: %s de %d; ultimo mensaje es el del alumno: %s" % (orden, len(msgs), msgs[-1]["role"] == "user"))
PYEOF
}
tiene() { "$PY" -I -c "
import json,sys
m=json.loads(open('$LOG',encoding='utf-8').read().splitlines()[-1])['messages']
s=' '.join(x['content'] for x in m if x['role']=='system')
sys.exit(0 if sys.argv[1] in s else 1)" "$1"; }

echo "== 0. Episodio"
EP=$(curl -s $API "${H[@]}" -d "{\"comision_id\":\"$T\",\"problema_id\":\"$TP\",\"curso_config_hash\":\"$HASH\",\"classifier_config_hash\":\"$HASH\"}" | "$PY" -I -c "import json,sys;print(json.load(sys.stdin)['episode_id'])")
echo "  episode_id=$EP"; sleep 3

CODE='def dividir(a, b):\n    return a / b\n\nprint(dividir(1, 0))\n'
ERR='Traceback (most recent call last):\n  File \"main.py\", line 4, in <module>\n    print(dividir(1, 0))\n  File \"main.py\", line 2, in dividir\n    return a / b\nZeroDivisionError: division by zero\n'
echo "== 1. Ejecuta codigo con error y manda mensaje"
curl -s -o /dev/null -w "  codigo_ejecutado -> HTTP %{http_code}\n" $API/$EP/events/codigo_ejecutado "${H[@]}" -d "{\"code\":\"$CODE\",\"stdout\":\"\",\"stderr\":\"$ERR\",\"duration_ms\":12}"
curl -s -N $API/$EP/message "${H[@]}" -d '{"content":"me tira error"}' >/dev/null; sleep 1
ultimo
tiene "<salida_stderr>" && tiene "ZeroDivisionError: division by zero" && chk "el request al LLM lleva <salida_stderr> con el traceback" 1 || chk "el request al LLM lleva <salida_stderr> con el traceback" 0
tiene "edito el codigo despues de ejecutarlo" && chk "sin edicion posterior NO hay aviso de desactualizacion" 0 || chk "sin edicion posterior NO hay aviso de desactualizacion" 1

echo "== 2. Se pierde la sesion Redis y se reanuda"
docker exec platform-redis redis-cli -n 2 del "tutor:session:$EP"
echo "  existe la clave tras borrarla: $(docker exec platform-redis redis-cli -n 2 exists tutor:session:$EP) (0 = borrada)"
curl -s -o /dev/null -w "  resume -> HTTP %{http_code}\n" -X POST $API/$EP/resume "${H[@]}"
curl -s -N $API/$EP/message "${H[@]}" -d '{"content":"sigue sin andar"}' >/dev/null; sleep 1
ultimo
tiene "<salida_stderr>" && tiene "ZeroDivisionError: division by zero" && chk "tras reanudar, el bloque sigue llegando al LLM" 1 || chk "tras reanudar, el bloque sigue llegando al LLM" 0

echo "== 3. El alumno edita el codigo despues de ejecutar (sha distinto)"
curl -s -o /dev/null -w "  edicion_codigo -> HTTP %{http_code}\n" $API/$EP/events/edicion_codigo "${H[@]}" -d '{"snapshot":"def dividir(a, b):\n    return a / b\n\nprint(dividir(4, 2))\n","diff_chars":3,"origin":"student_typed"}'
curl -s -N $API/$EP/message "${H[@]}" -d '{"content":"ahora que pasa?"}' >/dev/null; sleep 1
ultimo
tiene "edito el codigo despues de ejecutarlo" && chk "con edicion posterior aparece el aviso de desactualizacion" 1 || chk "con edicion posterior aparece el aviso de desactualizacion" 0

echo "== 4. Cierra el episodio (limpieza)"
curl -s -o /dev/null -w "  close -> HTTP %{http_code}\n" -X POST $API/$EP/close "${H[@]}" -d '{"reason":"student_closed"}'
echo; echo "RESULTADO: $ok OK, $fail FALLAS"; [ "$fail" = "0" ]
