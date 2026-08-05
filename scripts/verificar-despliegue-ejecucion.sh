#!/usr/bin/env bash
# Verifica sobre el DESPLIEGUE REAL los controles que el ADR-060 exige antes de
# produccion (tareas 8.3 y 8.4 de `java-execution-engine`).
#
# Por que existe: los controles del ADR estan verificados en LOCAL. El ADR-059
# ya dejo la leccion —"un ADR de seguridad se valida solo si se prueba"— cuando
# dio por sentado que Judge0 levantaba y resulto que exige cgroups v1. Contra un
# doble local, "sin red" y "sin privilegios" no significan nada: el doble no
# aisla, no cuesta plata y no tiene una red que deshabilitar.
#
# NO modifica nada. Solo lee y reporta.
#
#   Uso:  bash scripts/verificar-despliegue-ejecucion.sh
#
# Correr EN el host donde vive el execution-runner.

set -uo pipefail

ok=0
fallos=0
avisos=0

titulo() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
pasa()   { printf '  \033[0;32m[OK]\033[0m    %s\n' "$1"; ok=$((ok + 1)); }
falla()  { printf '  \033[0;31m[FALLA]\033[0m %s\n' "$1"; fallos=$((fallos + 1)); }
avisa()  { printf '  \033[0;33m[AVISO]\033[0m %s\n' "$1"; avisos=$((avisos + 1)); }
dato()   { printf '          %s\n' "$1"; }

RUNNER_PORT="${RUNNER_PORT:-8015}"
# `JAVA_IMAGE`, que es la que el servicio lee de verdad (`config.py:33`). Hasta
# el 2026-08-05 esto decia `EXECUTION_IMAGE`, una variable que no existe en
# ningun lado: el gate 4 media algo que nadie configuraba y reportaba contra el
# default. Se acepta `EXECUTION_IMAGE` como alias por si quedo en algun runbook.
IMAGEN="${JAVA_IMAGE:-${EXECUTION_IMAGE:-eclipse-temurin:21-jdk}}"

# ── 0. Rootless: si esta, el runner sobra ────────────────────────────────────
# ADR-060 (Alternativas): "Conviene evaluar rootless en el VPS antes de
# desplegar: si esta disponible, esta pieza sobra". Con el daemon como usuario
# sin privilegios el socket deja de ser root-equivalente y el execution-service
# puede invocar Docker directo.
titulo "0. Docker rootless (decide si el runner hace falta)"
if docker info 2>/dev/null | grep -qi rootless; then
    avisa "Docker corre ROOTLESS — el execution-runner probablemente sobra."
    dato "El socket deja de ser root-equivalente. Ver ADR-060, seccion Alternativas."
else
    pasa "Docker corre como root: el runner (D3) es necesario, como asume el ADR."
fi

# ── 1. Hardware, para leer la prueba de carga ────────────────────────────────
titulo "1. Hardware del host (contexto para la tarea 8.3)"
dato "CPUs:   $(nproc 2>/dev/null || echo '?')"
dato "RAM:    $(free -h 2>/dev/null | awk '/^Mem:/{print $2" total, "$7" disponible"}' || echo '?')"
dato "La medicion local fue 30 concurrentes -> 4,98 s sobre una maquina de"
dato "desarrollo. Si este host tiene menos CPU, el numero que vale es el de aca."

# ── 2. El runner NO puede ser alcanzable desde afuera ────────────────────────
# Es el control mas importante de 8.4. El runner es el UNICO con acceso al
# socket de Docker, y permitir `POST /containers/create` es permitir crear un
# contenedor privilegiado con `/` montado (ADR-060 D3). Si escucha en 0.0.0.0,
# no es "una vulnerabilidad": es acceso al host.
titulo "2. El runner no escucha hacia afuera (8.4 — el control critico)"
listen="$(ss -tlnp 2>/dev/null | grep ":${RUNNER_PORT}" || true)"
if [ -z "$listen" ]; then
    avisa "Nada escuchando en :${RUNNER_PORT} en este host."
    dato "Si el runner corre en un contenedor, correr este script adentro."
elif echo "$listen" | grep -qE '0\.0\.0\.0:'"${RUNNER_PORT}"'|\*:'"${RUNNER_PORT}"; then
    falla "El runner escucha en 0.0.0.0:${RUNNER_PORT} — alcanzable desde afuera."
    dato "$listen"
    dato "Bindear a 127.0.0.1 o a la red interna. Es el punto D3 del ADR-060."
else
    pasa "El runner no escucha en 0.0.0.0."
    dato "$listen"
fi

# ── 3. RUNNER_TOKEN configurado ──────────────────────────────────────────────
titulo "3. RUNNER_TOKEN configurado (8.4)"
if [ -n "${RUNNER_TOKEN:-}" ]; then
    pasa "RUNNER_TOKEN presente en el entorno (largo: ${#RUNNER_TOKEN})."
    [ "${#RUNNER_TOKEN}" -lt 32 ] && avisa "Menos de 32 chars — conviene uno mas largo."
else
    avisa "RUNNER_TOKEN no esta en ESTE shell."
    dato "No prueba que falte: puede estar solo en el entorno del contenedor."
    dato "Verificar ahi:  docker exec <runner> printenv RUNNER_TOKEN"
fi

# Se prueba con un body VALIDO y un token INVALIDO. Con el token configurado la
# respuesta tiene que ser 401 y no se ejecuta nada, asi que no hay efecto. Si
# llega a ejecutar, eso mismo ES el hallazgo: el token no se esta exigiendo.
#
# Un body vacio no sirve para esto: FastAPI valida `RunRequest` ANTES de correr
# el handler, entonces devuelve 422 sin llegar nunca al chequeo de token. Con
# `runner_token` vacio (modo dev) `_check_token` ademas sale temprano, asi que
# un 422 no distingue "no exige token" de "body invalido".
if [ -n "$listen" ]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
        -X POST "http://127.0.0.1:${RUNNER_PORT}/run" \
        -H 'Content-Type: application/json' \
        -H 'X-Runner-Token: token-invalido-de-verificacion' \
        -d '{"source_code":"public class Main{public static void main(String[] a){}}","stdin":""}' \
        2>/dev/null || echo 000)"
    case "$code" in
        401|403) pasa "POST /run con token invalido devuelve ${code}: el token se exige." ;;
        000)     avisa "No se pudo consultar /run (sin curl, o el runner no responde)." ;;
        200)     falla "POST /run EJECUTO con un token invalido: RUNNER_TOKEN no configurado." ;;
        422)     falla "422 con body valido — el contrato de /run cambio; revisar el script." ;;
        *)       falla "POST /run con token invalido devuelve ${code} — deberia ser 401." ;;
    esac
fi

# ── 4. Imagen pineada por digest ─────────────────────────────────────────────
# Un tag es mutable: `21-jdk` de hoy no es el de manana. Para un sandbox que
# ejecuta codigo de terceros, el digest es lo que hace reproducible QUE se corrio.
titulo "4. Imagen del sandbox pineada por digest (8.4)"
# El digest se valida ENTERO, no por la presencia del `@sha256:`. El 2026-08-05
# produccion tenia uno de 55 de los 64 caracteres —cortado en un paste— y pasaba
# igual, porque el chequeo era `grep '@sha256:'`. Un control que se satisface con
# un valor roto no es un control, y este es de los que el ADR-060 declara "falla
# cerrado". Mismo arreglo en `runner_main.py`.
DIGEST="${IMAGEN##*@sha256:}"
if printf '%s' "$IMAGEN" | grep -q '@sha256:' &&
    printf '%s' "$DIGEST" | grep -qE '^[0-9a-f]{64}$'; then
    pasa "JAVA_IMAGE pineada por digest, 64 chars hex."
    dato "$IMAGEN"
elif printf '%s' "$IMAGEN" | grep -q '@sha256:'; then
    falla "El digest esta MAL FORMADO: ${#DIGEST} chars, deberian ser 64."
    dato "$IMAGEN"
    dato "Se corta facil al pegarlo. Obtenerlo entero con:"
    dato "  docker images --digests ${IMAGEN%%@*}"
else
    falla "La imagen usa un TAG mutable, no un digest: ${IMAGEN}"
    dato "Un tag puede cambiar debajo tuyo. Obtener el digest con:"
    dato "  docker inspect --format='{{index .RepoDigests 0}}' ${IMAGEN}"
    if command -v docker >/dev/null 2>&1; then
        d="$(docker inspect --format='{{index .RepoDigests 0}}' "$IMAGEN" 2>/dev/null || true)"
        [ -n "$d" ] && dato "Digest actual en este host: $d"
    fi
fi

# ── 5. La imagen tiene que estar bajada ──────────────────────────────────────
# Si no esta, el `docker pull` (~450MB) entra en el presupuesto de 10s de la
# corrida del alumno y se come su timeout. Es lo que rompia el smoke en CI.
titulo "5. Imagen ya presente en el host (evita comerse el timeout del alumno)"
if docker image inspect "$IMAGEN" >/dev/null 2>&1; then
    pasa "La imagen esta local: ninguna corrida paga la descarga."
else
    falla "La imagen NO esta bajada — la primera corrida se come el pull en su timeout."
    dato "docker pull ${IMAGEN}"
fi

# ── 6. INTERNAL_SERVICE_TOKEN coincide entre los dos servicios ───────────────
# El modo de falla que este paso ataca: si el token NO coincide,
# `_es_emisor_interno` da False (falla cerrado, correcto), el tutor rechaza el
# `tests_ejecutados` con 422 y `TutorClient` falla soft. Neto: los ejercicios
# CON CASOS OCULTOS pierden su evento. No se cae nada — queda un agujero en el
# corpus, justo en los ejercicios que sostienen el claim del ADR-060.
#
# Hoy eso se detecta DESPUES, mirando `execution_ctr_emissions_failed_total`.
# O sea: contando lo que ya se perdio. Este paso lo detecta ANTES de habilitar.
#
# Por que NO se prueba emitiendo un `tests_ejecutados` sintetico, que seria lo
# obvio: `emit_tests_ejecutados` valida la SESION primero (tutor_core.py:1489,
# raise en la 1491) y recien despues mira `tests_hidden`/`emisor_interno`. Con
# un episodio inventado nunca se llega al chequeo de token; para llegar haria
# falta un episodio real, y eso escribe en el CTR. Este script no modifica nada.
#
# Se comparan HUELLAS (sha256 corto), nunca los valores: un secreto no se
# imprime ni siquiera en una verificacion.
titulo "6. INTERNAL_SERVICE_TOKEN coincide entre execution-service y tutor-service"

descubrir_contenedor() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -i -m1 "$1" || true
}

huella_token() {
    local valor
    valor="$(docker exec "$1" printenv INTERNAL_SERVICE_TOKEN 2>/dev/null || true)"
    [ -n "$valor" ] && printf '%s' "$valor" | sha256sum | cut -c1-12
}

EXEC_CONTAINER="${EXEC_CONTAINER:-$(descubrir_contenedor 'execution-service')}"
TUTOR_CONTAINER="${TUTOR_CONTAINER:-$(descubrir_contenedor 'tutor-service')}"

if ! command -v docker >/dev/null 2>&1; then
    avisa "Sin docker en este host: no puedo comparar los tokens."
elif [ -z "$EXEC_CONTAINER" ] || [ -z "$TUTOR_CONTAINER" ]; then
    avisa "No encontre los dos contenedores (execution-service: '${EXEC_CONTAINER:-?}', tutor-service: '${TUTOR_CONTAINER:-?}')."
    dato "Nombrarlos a mano:  EXEC_CONTAINER=x TUTOR_CONTAINER=y bash $0"
else
    h_exec="$(huella_token "$EXEC_CONTAINER")"
    h_tutor="$(huella_token "$TUTOR_CONTAINER")"
    if [ -z "$h_exec" ] && [ -z "$h_tutor" ]; then
        falla "INTERNAL_SERVICE_TOKEN vacio en LOS DOS: los casos ocultos van a perder su evento."
        dato "Sin token, _es_emisor_interno da False y el tutor rechaza con 422 (falla soft)."
    elif [ -z "$h_exec" ] || [ -z "$h_tutor" ]; then
        falla "INTERNAL_SERVICE_TOKEN falta en uno de los dos."
        dato "execution-service: ${h_exec:-VACIO} · tutor-service: ${h_tutor:-VACIO}"
    elif [ "$h_exec" != "$h_tutor" ]; then
        falla "Los tokens NO coinciden (huellas ${h_exec} vs ${h_tutor})."
        dato "Mismo valor en ambos servicios. Es la fila marcada en docs/EASYPANEL-DEPLOY.md."
    else
        pasa "Los tokens coinciden (huella ${h_exec})."
    fi
fi

# ── Resumen ─────────────────────────────────────────────────────────────────
printf '\n\033[1m== Resumen ==\033[0m\n'
printf '  %s ok · %s fallas · %s avisos\n' "$ok" "$fallos" "$avisos"
if [ "$fallos" -gt 0 ]; then
    printf '\n  \033[0;31mNO cerrar 8.4 con fallas abiertas.\033[0m\n'
    printf '  Es lo que decide si el runner queda expuesto.\n\n'
    exit 1
fi
printf '\n  Sin fallas. Falta la carga (8.3) sobre ESTE hardware:\n'
printf '    uv run python scripts/spike-docker-runner.py\n\n'
