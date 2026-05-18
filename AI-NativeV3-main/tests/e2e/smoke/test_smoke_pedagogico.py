"""Smoke #3 — flujo pedagógico mínimo: open episode + abandon.

Atrapa simultáneamente:
  - migration faltante de `tareas_practicas.test_cases`/`created_via_ai`
    (sin esas columnas, GET /tareas-practicas/{id} da 500 → cascada en tutor)
  - `byok_keys` table missing (cascada similar al resolver del ai-gateway)
  - casbin policies missing (rol tutor_service, etc)
  - chain del academic→tutor→ctr rota
  - validación de TP por tutor.open_episode (6 condiciones del invariante)

NO valida persistencia del evento en DB porque los partition workers son
single-writer asíncronos y pueden no estar corriendo en el ambiente de smoke.
Lo que SÍ validamos: el endpoint open_episode devuelve 201 con un UUID
parseable, y el endpoint abandoned acepta el mismo UUID con 204.

Test del audit alias va por separado (test_smoke_audit.py).
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from _helpers import tail_log  # type: ignore[import-not-found]

# Hashes del classifier_config y curso_config en el seed actual.
# Hardcoded para no depender de un endpoint que los exponga (no lo hay public).
SEEDED_CLASSIFIER_CONFIG_HASH = (
    "9dd96894fc88e68390b0d078d19c98acdb1b9810fec9757b0c05d577495c6edd"
)
SEEDED_CURSO_CONFIG_HASH = (
    "fd7ab31baa147f2c15a52947af98b11aa3b1f1c99e4cba00afa242bb5698832a"
)


@pytest.mark.smoke
def test_open_episode_returns_uuid(
    client: httpx.Client,
    auth_headers,
    student_id: str,
    comision_id: str,
    tarea_practica_id: str,
) -> None:
    """POST /api/v1/episodes con TP published + comision válida → 201 + UUID.

    Si la migration de test_cases/created_via_ai NO está aplicada en
    academic_main, el academic-service tira 500 al validar la TP, y el
    tutor-service propaga error. Este test atrapa esa cascada.
    """
    payload = {
        "comision_id": comision_id,
        "problema_id": tarea_practica_id,
        "curso_config_hash": SEEDED_CURSO_CONFIG_HASH,
        "classifier_config_hash": SEEDED_CLASSIFIER_CONFIG_HASH,
    }
    resp = client.post(
        "/api/v1/episodes",
        json=payload,
        headers=auth_headers("estudiante", user_id=student_id),
    )
    if resp.status_code != 201:
        pytest.fail(
            f"POST /api/v1/episodes falló — flow pedagógico principal roto. "
            f"status={resp.status_code} body={resp.text[:500]}\n\n"
            f"Si el body menciona 'tareas-practicas' 500: aplicar migrations academic_main.\n"
            f"Si menciona 'casbin' o 403: re-seedear casbin policies.\n"
            f"Si timeout: ver tutor-service log.\n\n"
            f"tutor-service.log (últimas 20):\n{tail_log('tutor-service')}\n\n"
            f"academic-service.log (últimas 20):\n{tail_log('academic-service')}"
        )
    body = resp.json()
    episode_id = body.get("episode_id")
    assert episode_id, f"esperado episode_id en response, got {body}"
    UUID(episode_id)  # raises if no es UUID


@pytest.mark.smoke
def test_open_then_abandon_episode_idempotent(
    client: httpx.Client,
    auth_headers,
    student_id: str,
    comision_id: str,
    tarea_practica_id: str,
) -> None:
    """ADR-025 (G10-A): abandoned debe ser idempotente."""
    headers = auth_headers("estudiante", user_id=student_id)
    payload = {
        "comision_id": comision_id,
        "problema_id": tarea_practica_id,
        "curso_config_hash": SEEDED_CURSO_CONFIG_HASH,
        "classifier_config_hash": SEEDED_CLASSIFIER_CONFIG_HASH,
    }
    open_resp = client.post("/api/v1/episodes", json=payload, headers=headers)
    if open_resp.status_code != 201:
        pytest.skip(f"open_episode failing — ver test_open_episode_returns_uuid: {open_resp.text[:200]}")

    episode_id = open_resp.json()["episode_id"]

    # Primera llamada → debe responder 204
    abandon1 = client.post(
        f"/api/v1/episodes/{episode_id}/abandoned",
        json={"reason": "explicit", "last_activity_seconds_ago": 0.0},
        headers=headers,
    )
    assert abandon1.status_code == 204, (
        f"primer POST /abandoned debería 204 (sesión activa). "
        f"status={abandon1.status_code} body={abandon1.text[:300]}"
    )

    # Segunda llamada → ADR-025: idempotente, devuelve 204 sin emitir
    abandon2 = client.post(
        f"/api/v1/episodes/{episode_id}/abandoned",
        json={"reason": "explicit", "last_activity_seconds_ago": 0.0},
        headers=headers,
    )
    assert abandon2.status_code == 204, (
        f"segundo POST /abandoned debería 204 (idempotente). "
        f"status={abandon2.status_code} body={abandon2.text[:300]}"
    )


@pytest.mark.smoke
def test_abandon_unknown_episode_idempotent(
    client: httpx.Client, auth_headers, student_id: str, unique_uuid: str
) -> None:
    """ADR-025: abandoned con episode_id inexistente NO debe dar 500.

    El endpoint es idempotente por estado de sesión Redis: si la sesión no
    existe, responde 204 silenciosamente. Esto cubre la carrera del browser
    `beforeunload` con el worker de timeout.
    """
    resp = client.post(
        f"/api/v1/episodes/{unique_uuid}/abandoned",
        json={"reason": "explicit", "last_activity_seconds_ago": 0.0},
        headers=auth_headers("estudiante", user_id=student_id),
    )
    # 204 (idempotente) o 404 — ambos son aceptables. Lo que NO es aceptable
    # es 500 (que indicaría stack trace por session=None mal manejado).
    assert resp.status_code in (204, 404), (
        f"abandoned con episode_id desconocido debería 204 o 404, no {resp.status_code}. "
        f"body={resp.text[:300]}"
    )
