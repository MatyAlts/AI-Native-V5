"""HU-017 (ronda de arreglos): pruebas de los seams REALES de
`classifier_service.auth.acceso` (la aceptación los reemplaza con monkeypatch,
así que acá se prueba lo que corre en producción) y dos fallas cerradas de las
rutas sin base académica.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from classifier_service.auth import User, acceso
from classifier_service.config import settings
from classifier_service.models import Classification
from classifier_service.routes import classify_ep as ruta_clasif
from classifier_service.routes import review as ruta_review
from fastapi import HTTPException
from platform_observability import verify_gateway_signature

TENANT = UUID("11111111-1111-1111-1111-111111111111")
CLERK = frozenset({"estudiante", "docente"})


def _user(uid: UUID | None = None) -> User:
    return User(id=uid or uuid4(), tenant_id=TENANT, email="a@b.c", roles=CLERK, realm="r")


# ── es_duenio_del_episodio ─────────────────────────────────────────────────


def _con_transporte(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    pedidos: list[httpx.Request] = []

    def _registrar(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return handler(request)

    real = httpx.AsyncClient

    def _cliente(*a: Any, **k: Any) -> httpx.AsyncClient:
        return real(*a, transport=httpx.MockTransport(_registrar), **k)

    monkeypatch.setattr(acceso.httpx, "AsyncClient", _cliente)
    return pedidos


async def test_duenio_200_propio_es_true(monkeypatch: pytest.MonkeyPatch) -> None:
    u = _user()
    pedidos = _con_transporte(
        monkeypatch, lambda r: httpx.Response(200, json={"student_pseudonym": str(u.id)})
    )
    ep = uuid4()
    assert await acceso.es_duenio_del_episodio(u, ep) is True
    assert pedidos[0].url.path == f"/api/v1/episodes/{ep}"
    assert pedidos[0].headers["X-User-Id"] == str(u.id)


async def test_duenio_200_de_otro_es_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_transporte(
        monkeypatch, lambda r: httpx.Response(200, json={"student_pseudonym": str(uuid4())})
    )
    assert await acceso.es_duenio_del_episodio(_user(), uuid4()) is False


async def test_duenio_403_es_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_transporte(monkeypatch, lambda r: httpx.Response(403, json={"detail": "no"}))
    assert await acceso.es_duenio_del_episodio(_user(), uuid4()) is False


async def test_duenio_timeout_es_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento", request=request)

    _con_transporte(monkeypatch, _timeout)
    assert await acceso.es_duenio_del_episodio(_user(), uuid4()) is False


async def test_duenio_json_roto_es_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_transporte(monkeypatch, lambda r: httpx.Response(200, content=b"<html>proxy</html>"))
    assert await acceso.es_duenio_del_episodio(_user(), uuid4()) is False


async def test_duenio_firma_el_pedido_si_hay_secreto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gateway_shared_secret", "s" * 32)
    u = _user()
    pedidos = _con_transporte(
        monkeypatch, lambda r: httpx.Response(200, json={"student_pseudonym": str(u.id)})
    )
    assert await acceso.es_duenio_del_episodio(u, uuid4()) is True
    h = pedidos[0].headers
    assert verify_gateway_signature(
        "s" * 32,
        h["X-User-Id"],
        h["X-Tenant-Id"],
        h["X-User-Roles"],
        int(h["X-Gateway-Ts"]),
        h["X-Gateway-Signature"],
    )


async def test_duenio_sin_secreto_no_manda_firma(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gateway_shared_secret", "")
    u = _user()
    pedidos = _con_transporte(
        monkeypatch, lambda r: httpx.Response(200, json={"student_pseudonym": str(u.id)})
    )
    await acceso.es_duenio_del_episodio(u, uuid4())
    assert "X-Gateway-Signature" not in pedidos[0].headers


# ── es_miembro_de_comision ─────────────────────────────────────────────────


class _SesionAcademica:
    def __init__(self, fila: Any) -> None:
        self.fila = fila
        self.sql: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> Any:
        self.sql.append((str(stmt), params or {}))
        fila = self.fila

        class _R:
            def first(self) -> Any:
                return fila

        return _R()

    async def __aenter__(self) -> _SesionAcademica:
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None


def _con_sesion(monkeypatch: pytest.MonkeyPatch, fila: Any) -> tuple[_SesionAcademica, list]:
    sesion = _SesionAcademica(fila)
    rls: list[UUID] = []

    async def _rls(_s: Any, tenant_id: UUID) -> None:
        rls.append(tenant_id)

    import platform_ops

    monkeypatch.setattr(platform_ops, "set_tenant_rls", _rls)
    monkeypatch.setattr(acceso, "_get_academic_engine", object)
    monkeypatch.setattr(acceso, "async_sessionmaker", lambda *_a, **_k: lambda: sesion)
    return sesion, rls


async def test_miembro_filtra_por_usuario_comision_vigencia_y_borrado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sesion, rls = _con_sesion(monkeypatch, (1,))
    u, c = uuid4(), uuid4()
    assert await acceso.es_miembro_de_comision(TENANT, u, c) is True
    assert rls == [TENANT]
    sql, params = sesion.sql[0]
    normal = " ".join(sql.split())
    assert "FROM usuarios_comision" in normal
    assert "user_id = :u" in normal
    assert "comision_id = :c" in normal
    assert "deleted_at IS NULL" in normal
    assert "(fecha_hasta IS NULL OR fecha_hasta >= CURRENT_DATE)" in normal
    assert params == {"c": str(c), "u": str(u)}


async def test_sin_fila_no_es_miembro(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_sesion(monkeypatch, None)
    assert await acceso.es_miembro_de_comision(TENANT, uuid4(), uuid4()) is False


# ── Rutas sin base académica ───────────────────────────────────────────────


def _sin_base(monkeypatch: pytest.MonkeyPatch, *, duenio: bool) -> None:
    monkeypatch.setattr(settings, "enforce_comision_access", True)
    monkeypatch.setattr(settings, "academic_db_url", "")

    async def _duenio(_u: User, _e: UUID) -> bool:
        return duenio

    async def _miembro(*_a: Any) -> bool:
        raise AssertionError("sin base no debia consultar usuarios_comision")

    monkeypatch.setattr(acceso, "es_duenio_del_episodio", _duenio)
    monkeypatch.setattr(acceso, "es_miembro_de_comision", _miembro)


def _tenant_session(monkeypatch: pytest.MonkeyPatch, modulo: Any, resultado: Any) -> list[int]:
    abiertas: list[int] = []

    class _S:
        async def execute(self, *_a: Any, **_k: Any) -> Any:
            class _R:
                def scalar_one_or_none(self) -> Any:
                    return resultado

            return _R()

    @asynccontextmanager
    async def _ts(_t: UUID):
        abiertas.append(1)
        yield _S()

    monkeypatch.setattr(modulo, "tenant_session", _ts)
    return abiertas


async def test_sin_base_el_duenio_igual_ve_su_clasificacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sin_base(monkeypatch, duenio=True)
    clasif = Classification(
        id=1,
        episode_id=uuid4(),
        comision_id=uuid4(),
        classifier_config_hash="h" * 64,
        appropriation="apropiacion_reflexiva",
        appropriation_reason="x",
        is_current=True,
        features={},
    )
    _tenant_session(monkeypatch, ruta_clasif, clasif)
    out = await ruta_clasif.get_current_classification(clasif.episode_id, user=_user())
    assert out.episode_id == clasif.episode_id


async def test_sin_base_la_cola_da_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _sin_base(monkeypatch, duenio=False)
    abiertas = _tenant_session(monkeypatch, ruta_review, None)

    async def _list(_s: Any, comision_id: UUID | None = None) -> list:
        return []

    monkeypatch.setattr(ruta_review, "list_review_queue", _list)
    with pytest.raises(HTTPException) as exc:
        await ruta_review.get_review_queue(comision_id=None, user=_user())
    assert exc.value.status_code == 503
    assert abiertas == []


async def test_sin_base_la_cola_de_oversight_responde(monkeypatch: pytest.MonkeyPatch) -> None:
    _sin_base(monkeypatch, duenio=False)
    _tenant_session(monkeypatch, ruta_review, None)

    async def _list(_s: Any, comision_id: UUID | None = None) -> list:
        return []

    monkeypatch.setattr(ruta_review, "list_review_queue", _list)
    admin = User(
        id=uuid4(), tenant_id=TENANT, email="a@b.c", roles=frozenset({"docente_admin"}), realm="r"
    )
    out = await ruta_review.get_review_queue(comision_id=None, user=admin)
    assert out.n == 0
