"""`classify_ep.py::_find_current_classification` — sync con la idempotencia
ampliada de `persist_classification` (hallazgo de QA, 2026-09-27, MEDIA).

`persist_classification` (`pipeline.py`) dejó de filtrar por `is_current` en
su chequeo de idempotencia (ronda de revisión anterior): busca CUALQUIER fila
con `(episode_id, classifier_config_hash)`, vigente o no. Pero
`_find_current_classification` —el pre-check del handler HTTP, que decide si
hace falta pegarle al ctr-service y qué status code devolver— seguía
filtrando `is_current.is_(True)`. El propio docstring de la función llama a
esa duplicación "intencional"; lo que no hizo nadie es mantenerla
sincronizada tras ampliar la otra mitad.

Síntoma reproducido: clasificar un episodio con hash H1, anularlo
humanamente (H1 queda no-vigente), y volver a pedir esa misma clasificación
con el mismo H1 (config sin cambios — el caso normal). El pre-check no
encuentra la fila (sigue exigiendo `is_current=true`), así que el handler
haría el roundtrip completo al ctr-service de más, y cuando
`persist_classification` le devuelve la fila existente como no-op, el
handler no tiene forma de saber que fue un no-op — devolvería 201 en vez de
200 (el docstring de la ruta promete 200 para este caso).

Este archivo prueba el HELPER directamente (no el endpoint HTTP completo,
que exigiría mockear el ctr-service y el juez) — es la unidad mínima donde
el bug realmente vive: la ausencia de `is_current` en el filtro.
"""

from __future__ import annotations

import socket
from uuid import uuid4

import pytest
from classifier_service.models import Classification
from classifier_service.routes.classify_ep import _find_current_classification
from classifier_service.services.review import submit_review
from sqlalchemy import text


def _postgres_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            return True
    except OSError:
        return False


# Duplicado a propósito — ver el comentario equivalente en
# `test_review_service_db.py`.
requires_local_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="platform-postgres no está corriendo en 127.0.0.1:5432",
)

MACHINE_HASH = "hash-maquina-sync-precheck"


@requires_local_postgres
@pytest.mark.asyncio
async def test_precheck_encuentra_hash_de_maquina_no_vigente_tras_anulacion_humana(
    db_session,
) -> None:
    """RED verificado contra `classify_ep.py::_find_current_classification`
    SIN el fix: el assert final falla con `AssertionError` porque la función
    devuelve `None` — no es un fallo de setup, `submit_review` corre
    completo y deja la fila con el hash de máquina no-vigente exactamente
    como se espera; lo que falla es la BÚSQUEDA subsiguiente."""
    session, tenant_id = db_session
    comision_id = uuid4()
    episode_id = uuid4()

    session.add(
        Classification(
            tenant_id=tenant_id,
            episode_id=episode_id,
            comision_id=comision_id,
            classifier_config_hash=MACHINE_HASH,
            appropriation="apropiacion_superficial",
            appropriation_reason="original (máquina)",
            features={"needs_review": True, "needs_review_reason": "test"},
            is_current=True,
        )
    )
    await session.flush()

    await submit_review(
        session,
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=uuid4(),
        reviewer_role="docente",
        verdict="apropiacion_reflexiva",
        reason="Anulación previa al re-POST con el mismo hash de máquina.",
    )

    # Confirmar el setup: la fila con MACHINE_HASH efectivamente quedó
    # no-vigente (si esto fallara, sería un fallo de SETUP, no del helper).
    check = await session.execute(
        text(
            "SELECT is_current FROM classifications "
            "WHERE episode_id = :ep AND classifier_config_hash = :h"
        ),
        {"ep": str(episode_id), "h": MACHINE_HASH},
    )
    assert check.scalar_one() is False

    found = await _find_current_classification(session, episode_id, MACHINE_HASH)

    assert found is not None, (
        "El pre-check debe encontrar la fila con este hash aunque no sea "
        "is_current=true — persist_classification ya la trata como "
        "'ya persistida' (idempotencia ampliada); si el pre-check no la "
        "encuentra, el handler hace un roundtrip de más al ctr-service y "
        "termina devolviendo 201 en vez de 200 para el caso normal "
        "(config sin cambios, tras una anulación humana)."
    )
    assert found.classifier_config_hash == MACHINE_HASH
