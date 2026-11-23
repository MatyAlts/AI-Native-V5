"""Aceptacion HU-017 parte 1, classifier (orquestador, antes de construir; el
constructor no la modifica). Juani (23/11): "sisi" a los criterios (nivel L).

Hallazgo del plan de seguridad: `POST /api/v1/classifications/{id}/review`
exige un rol que incluye `docente` y no chequea membresia. Con Clerk toda cuenta
trae `estudiante,docente`: un alumno podria REEMPLAZAR la etiqueta oficial de
cualquier episodio. Lo mismo para la cola de revision y el GET de una
clasificacion.

Contrato nuevo, modulo `classifier_service.auth.acceso`:
  - seams (las pruebas los reemplazan):
      `async es_miembro_de_comision(tenant_id, user_id, comision_id) -> bool`
        (membresia real en `usuarios_comision` de academic_main);
      `async es_duenio_del_episodio(user, episode_id) -> bool`
        (el constructor elige como; la clasificacion no guarda al alumno).
  - `async assert_docente_de_comision(user, comision_id) -> None`
  - `async assert_puede_ver_clasificacion(user, episode_id, comision_id) -> None`
  Ambas dejan pasar a oversight (`superadmin`, `docente_admin`) sin consultar;
  con `settings.enforce_comision_access = False` (opt-out de dev) son no-op; sin
  `settings.academic_db_url` cortan con 503 (falla CERRADO), salvo el duenio en
  la de ver; si no, 403. `settings` es `classifier_service.config.settings`, que
  declara `academic_db_url: str` (de `ACADEMIC_DB_URL`) y
  `enforce_comision_access: bool = True`.
Las rutas `post_review`, `get_review_queue` y `get_current_classification` las
usan.

C05  Un alumno (Clerk: estudiante,docente) no miembro no puede cambiar la
     etiqueta: 403 y `submit_review` no se llama.
C06  Docente miembro revisa como hoy; docente no miembro 403.
C07  La cola de revision solo muestra episodios de comisiones del docente.
C08  GET de una clasificacion: duenio y miembro pasan; cualquier otro 403.
N01  Sin `academic_db_url`, un tercero recibe 503 (no pasa).
N05  Con el opt-out de dev no se bloquea.
"""

from __future__ import annotations

import importlib
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from classifier_service.auth import User
from classifier_service.config import settings
from classifier_service.models import Classification
from classifier_service.routes import classify_ep as ruta_clasif
from classifier_service.routes import review as ruta_review
from classifier_service.services.review import ReviewQueueItem, ReviewResult
from fastapi import HTTPException

TENANT = UUID("11111111-1111-1111-1111-111111111111")
COM_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COM_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CLERK = {"estudiante", "docente"}
VEREDICTO = sorted(ruta_review.VALID_VERDICTS)[0]


def _user(roles: set[str]) -> User:
    return User(
        id=uuid4(), tenant_id=TENANT, email="x@y.z", roles=frozenset(roles), realm=str(TENANT)
    )


def _acceso() -> Any:
    try:
        return importlib.import_module("classifier_service.auth.acceso")
    except ModuleNotFoundError:
        pytest.fail("falta classifier_service.auth.acceso")


def _prod(monkeypatch, *, miembro: set[UUID] | None, duenio: bool = False) -> None:
    """Produccion: base academica cargada; `miembro` = comisiones del usuario."""
    acceso = _acceso()
    monkeypatch.setattr(settings, "enforce_comision_access", True, raising=False)
    monkeypatch.setattr(settings, "academic_db_url", "postgresql://x", raising=False)

    async def _membresia(tenant_id: UUID, user_id: UUID, comision_id: UUID) -> bool:
        if miembro is None:
            raise AssertionError("no debia consultar usuarios_comision")
        return comision_id in miembro

    async def _duenio(user: User, episode_id: UUID) -> bool:
        return duenio

    monkeypatch.setattr(acceso, "es_miembro_de_comision", _membresia, raising=False)
    monkeypatch.setattr(acceso, "es_duenio_del_episodio", _duenio, raising=False)


def _clasificacion(comision_id: UUID = COM_A) -> Classification:
    return Classification(
        id=1,
        episode_id=uuid4(),
        comision_id=comision_id,
        classifier_config_hash="h" * 64,
        appropriation="apropiacion_reflexiva",
        appropriation_reason="x",
        is_current=True,
        features={},
    )


def _sesion(monkeypatch, modulo: Any, resultado: Any = None) -> None:
    class _Res:
        def scalar_one_or_none(self) -> Any:
            return resultado

    class _S:
        async def execute(self, *_a: Any, **_k: Any) -> _Res:
            return _Res()

    @asynccontextmanager
    async def _ts(_tenant: UUID):
        yield _S()

    monkeypatch.setattr(modulo, "tenant_session", _ts)


def _submit_espia(monkeypatch, clasif: Classification) -> list[UUID]:
    llamadas: list[UUID] = []

    async def _submit(session: Any, **kw: Any) -> ReviewResult:
        llamadas.append(kw["episode_id"])
        return ReviewResult(review_id=1, previous_classification_id=1, new_classification_id=2)

    monkeypatch.setattr(ruta_review, "submit_review", _submit)
    _sesion(monkeypatch, ruta_review, clasif)
    return llamadas


async def _revisar(user: User, clasif: Classification) -> Any:
    body = ruta_review.ReviewIn(verdict=VEREDICTO, reason="prueba")
    return await ruta_review.post_review(clasif.episode_id, body, user=user)


# ── C05 ────────────────────────────────────────────────────────────────


async def test_c05_alumno_no_puede_cambiar_la_etiqueta(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _prod(monkeypatch, miembro=set())
    llamadas = _submit_espia(monkeypatch, clasif)
    with pytest.raises(HTTPException) as exc:
        await _revisar(_user(CLERK), clasif)
    assert exc.value.status_code == 403
    assert llamadas == []


# ── C06 ────────────────────────────────────────────────────────────────


async def test_c06_docente_miembro_revisa(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _prod(monkeypatch, miembro={COM_A})
    llamadas = _submit_espia(monkeypatch, clasif)
    out = await _revisar(_user({"docente"}), clasif)
    assert out.new_classification_id == 2
    assert llamadas == [clasif.episode_id]


async def test_c06_docente_de_otra_comision_recibe_403(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _prod(monkeypatch, miembro={COM_B})
    llamadas = _submit_espia(monkeypatch, clasif)
    with pytest.raises(HTTPException) as exc:
        await _revisar(_user({"docente"}), clasif)
    assert exc.value.status_code == 403
    assert llamadas == []


async def test_c06_oversight_revisa_sin_consultar(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _prod(monkeypatch, miembro=None)
    llamadas = _submit_espia(monkeypatch, clasif)
    await _revisar(_user({"superadmin"}), clasif)
    assert llamadas == [clasif.episode_id]


# ── C07 ────────────────────────────────────────────────────────────────


def _cola(monkeypatch) -> None:
    items = [
        ReviewQueueItem(
            episode_id=uuid4(),
            comision_id=c,
            classification_id=i,
            appropriation="apropiacion_superficial",
            needs_review_reason="x",
            estado_juez=None,
        )
        for i, c in enumerate([COM_A, COM_B, COM_A], start=1)
    ]

    async def _list(session: Any, comision_id: UUID | None = None) -> list[ReviewQueueItem]:
        return [x for x in items if comision_id is None or x.comision_id == comision_id]

    monkeypatch.setattr(ruta_review, "list_review_queue", _list)
    _sesion(monkeypatch, ruta_review)


async def test_c07_la_cola_solo_muestra_comisiones_propias(monkeypatch) -> None:
    _prod(monkeypatch, miembro={COM_A})
    _cola(monkeypatch)
    out = await ruta_review.get_review_queue(comision_id=None, user=_user(CLERK))
    assert {i.comision_id for i in out.items} == {COM_A}
    assert out.n == 2


async def test_c07_pedir_la_cola_de_otra_comision_no_la_muestra(monkeypatch) -> None:
    _prod(monkeypatch, miembro={COM_A})
    _cola(monkeypatch)
    try:
        out = await ruta_review.get_review_queue(comision_id=COM_B, user=_user(CLERK))
    except HTTPException as exc:
        assert exc.status_code == 403
        return
    assert out.items == []


# ── C08 ────────────────────────────────────────────────────────────────


async def _ver(monkeypatch, user: User, clasif: Classification) -> Any:
    _sesion(monkeypatch, ruta_clasif, clasif)
    return await ruta_clasif.get_current_classification(clasif.episode_id, user=user)


async def test_c08_el_duenio_ve_su_clasificacion(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _prod(monkeypatch, miembro=set(), duenio=True)
    out = await _ver(monkeypatch, _user(CLERK), clasif)
    assert out.episode_id == clasif.episode_id


async def test_c08_el_docente_miembro_la_ve(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _prod(monkeypatch, miembro={COM_A}, duenio=False)
    out = await _ver(monkeypatch, _user({"docente"}), clasif)
    assert out.episode_id == clasif.episode_id


async def test_c08_un_tercero_recibe_403(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _prod(monkeypatch, miembro=set(), duenio=False)
    with pytest.raises(HTTPException) as exc:
        await _ver(monkeypatch, _user(CLERK), clasif)
    assert exc.value.status_code == 403


# ── N01 ────────────────────────────────────────────────────────────────


def _sin_base(monkeypatch, duenio: bool = False) -> None:
    acceso = _acceso()
    monkeypatch.setattr(settings, "enforce_comision_access", True, raising=False)
    monkeypatch.setattr(settings, "academic_db_url", "", raising=False)

    async def _duenio(user: User, episode_id: UUID) -> bool:
        return duenio

    monkeypatch.setattr(acceso, "es_duenio_del_episodio", _duenio, raising=False)


async def test_n01_sin_base_un_tercero_no_revisa(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _sin_base(monkeypatch)
    llamadas = _submit_espia(monkeypatch, clasif)
    with pytest.raises(HTTPException) as exc:
        await _revisar(_user(CLERK), clasif)
    assert exc.value.status_code == 503
    assert llamadas == []


async def test_n01_sin_base_un_tercero_no_ve(monkeypatch) -> None:
    clasif = _clasificacion(COM_A)
    _sin_base(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await _ver(monkeypatch, _user(CLERK), clasif)
    assert exc.value.status_code == 503


# ── N05 ────────────────────────────────────────────────────────────────


async def test_n05_opt_out_de_dev_no_bloquea(monkeypatch) -> None:
    _acceso()
    monkeypatch.setattr(settings, "enforce_comision_access", False, raising=False)
    monkeypatch.setattr(settings, "academic_db_url", "", raising=False)
    clasif = _clasificacion(COM_A)
    llamadas = _submit_espia(monkeypatch, clasif)
    await _revisar(_user(CLERK), clasif)
    assert llamadas == [clasif.episode_id]
