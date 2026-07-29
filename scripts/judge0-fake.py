"""Doble de Judge0 para desarrollo local del execution-service (ADR-059).

**NO es un sandbox.** No aisla nada y no ejecuta codigo: replica el CONTRATO
HTTP de Judge0 (`/about`, `POST /submissions`, `GET /submissions/{token}`) con
una heuristica minima, para poder desarrollar y probar el `execution-service`
sin el sandbox real.

## Por que existe

Judge0 usa `isolate`, que exige **cgroups v1**. Las distribuciones modernas
traen **v2** por omision, y con v2 `isolate` directamente no levanta. Es el
riesgo que el ADR-059 (D3) documenta como pre-condicion dura antes de contratar
cualquier servidor, y se confirmo en la practica el 2026-07-28 sobre Pop!_OS:

    $ stat -fc %T /sys/fs/cgroup/
    cgroup2fs          # v2 -> Judge0 no arranca

Comprobalo antes de asumir que podes levantar Judge0 real en tu maquina:
`tmpfs` = v1 (sirve), `cgroup2fs` = v2 (no sirve sin tocar GRUB y rebootear).

## Como se usa

    uv run uvicorn judge0_fake:app --host 127.0.0.1 --port 2358
    # con PYTHONPATH=scripts, o desde el directorio scripts/

El `execution-service` lo toma por `JUDGE0_BASE_URL` (default `:2358`), asi que
no hay que tocar codigo para alternar entre el doble y Judge0 real.

## Que simula y que no

Simula: los status ids reales, el encoding base64 de los campos de texto, y el
flujo de dos pasos (submit -> token -> poll).

NO simula: aislamiento, limites de CPU/memoria, timeouts reales, ni la
compilacion de Java. La heuristica solo distingue tres casos —compila y acierta,
compila y falla, no compila— que es lo que hace falta para ejercitar las tres
ramas del `result_mapper`.

Status ids de Judge0 (son los reales):
  1 In Queue · 2 Processing · 3 Accepted · 4 Wrong Answer
  5 Time Limit Exceeded · 6 Compilation Error · 7-12 runtime errors
"""

from __future__ import annotations

import base64
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="judge0-fake", description="Doble local de Judge0 (ADR-059)")

_submissions: dict[str, dict] = {}


class Submission(BaseModel):
    source_code: str
    language_id: int
    stdin: str | None = None
    expected_output: str | None = None
    cpu_time_limit: float | None = None
    wall_time_limit: float | None = None
    memory_limit: int | None = None
    max_processes_and_or_threads: int | None = None
    enable_network: bool | None = None


def _b64(value: str | None) -> str | None:
    if value is None:
        return None
    return base64.b64encode(value.encode()).decode()


@app.get("/about")
async def about() -> dict[str, str]:
    # La version dice "fake" a proposito: si alguien chequea el control C1 del
    # ADR-059 (version minima 1.13.1) contra esto, tiene que ser evidente que
    # no es Judge0 de verdad.
    return {"version": "1.13.1-fake", "homepage": "local", "source_code": "fake"}


@app.post("/submissions")
async def create_submission(sub: Submission, base64_encoded: bool = False) -> dict[str, str]:
    token = str(uuid.uuid4())

    def _in(value: str | None) -> str:
        """Con base64_encoded=true TODOS los campos de texto vienen codificados,
        no solo el source. Compararlos sin decodificar da falsos negativos."""
        if value is None:
            return ""
        return base64.b64decode(value).decode() if base64_encoded else value

    src = _in(sub.source_code)
    esperado = _in(sub.expected_output)

    if "class" not in src:
        result = {
            "status": {"id": 6, "description": "Compilation Error"},
            "compile_output": _b64("error: class, interface, or enum expected"),
            "stdout": None,
            "stderr": None,
            "time": None,
            "memory": None,
        }
    else:
        stdout = ""
        if "System.out.println" in src:
            inicio = src.find('println("')
            if inicio != -1:
                fin = src.find('"', inicio + 9)
                stdout = src[inicio + 9 : fin] + "\n"
        ok = stdout.strip() == esperado.strip() if esperado else True
        result = {
            "status": (
                {"id": 3, "description": "Accepted"}
                if ok
                else {"id": 4, "description": "Wrong Answer"}
            ),
            "compile_output": None,
            "stdout": _b64(stdout),
            "stderr": None,
            "time": "0.42",
            "memory": 14032,
        }

    _submissions[token] = result
    return {"token": token}


@app.get("/submissions/{token}")
async def get_submission(token: str, base64_encoded: bool = False) -> dict:
    # Un token desconocido responde "In Queue" en vez de 404, igual que Judge0:
    # asi se ejercita el camino de polling del cliente.
    return _submissions.get(token, {"status": {"id": 1, "description": "In Queue"}})
