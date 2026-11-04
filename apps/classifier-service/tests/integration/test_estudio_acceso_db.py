"""Acceso al estudio y membresías (tarea 4.1, design D3, spec estudio-codificacion-acceso).

Contra la app real (`ASGITransport`) y Postgres real: `tenant_session`,
`require_gateway_auth`, el router y la base sin mocks. Cada test usa un
`tenant_id` aleatorio y COMMITEA (ver `conftest.py`): correr contra una base
efímera.

La identidad llega como la manda el gateway: `X-User-Id`, `X-Tenant-Id`,
`X-User-Email`, `X-User-Roles`. En producción, con Clerk, toda cuenta trae
`estudiante,docente`: por eso ningún rol genérico alcanza para el estudio.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

import pytest
from classifier_service.config import settings
from classifier_service.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BASE = "/api/v1/interrater/estudios"
LOGGER = "classifier_service.routes.estudio"


class Persona:
    def __init__(self, tenant_id: UUID, email: str, roles: str = "estudiante,docente") -> None:
        self.tenant_id = tenant_id
        self.user_id = uuid4()
        self.email = email
        self.roles = roles

    def headers(self, *, user_id: UUID | None = None, email: str | None = None) -> dict:
        return {
            "X-User-Id": str(user_id or self.user_id),
            "X-Tenant-Id": str(self.tenant_id),
            "X-User-Email": email or self.email,
            "X-User-Roles": self.roles,
        }


@pytest.fixture
async def client(app_db):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def tenant() -> UUID:
    return uuid4()


@pytest.fixture
def admin(tenant) -> Persona:
    return Persona(tenant, "admin@utn.test", "estudiante,docente,superadmin")


async def _fila(url: str, tenant_id: UUID, sql: str, params: dict) -> list:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)}
            )
            return list((await conn.execute(text(sql), params)).mappings())
    finally:
        await engine.dispose()


async def _estudio(client, admin: Persona, clave: str = "cibse-2027") -> str:
    r = await client.post(BASE, json={"clave": clave, "titulo": "Estudio"}, headers=admin.headers())
    assert r.status_code == 201, r.text
    return clave


async def _alta(client, autor: Persona, clave: str, email: str, rol: str):
    return await client.post(
        f"{BASE}/{clave}/membresias", json={"email": email, "rol": rol}, headers=autor.headers()
    )


async def _con_investigador(client, admin, tenant, clave="cibse-2027") -> Persona:
    await _estudio(client, admin, clave)
    investigador = Persona(tenant, "inv@ejemplo.org")
    r = await _alta(client, admin, clave, investigador.email, "investigador")
    assert r.status_code == 201, r.text
    return investigador


# ── Alta de estudio ───────────────────────────────────────────────────────


async def test_administrador_crea_estudio_con_traza_vigente(client, admin, app_db) -> None:
    r = await client.post(
        BASE, json={"clave": "cibse-2027", "titulo": "CIbSE 2027"}, headers=admin.headers()
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"clave": "cibse-2027", "titulo": "CIbSE 2027", "traza_version": "traza_v1"}
    filas = await _fila(
        app_db,
        admin.tenant_id,
        "SELECT traza_version, created_by FROM estudio_codificacion WHERE clave = 'cibse-2027'",
        {},
    )
    assert filas == [{"traza_version": "traza_v1", "created_by": admin.user_id}]


@pytest.mark.parametrize("roles", ["estudiante,docente", "docente", "classifier_worker"])
async def test_sin_rol_administrativo_no_crea_estudio(client, tenant, app_db, roles) -> None:
    persona = Persona(tenant, "doc@utn.test", roles)
    r = await client.post(
        BASE, json={"clave": "cibse-2027", "titulo": "x"}, headers=persona.headers()
    )
    assert r.status_code == 403
    filas = await _fila(app_db, tenant, "SELECT id FROM estudio_codificacion", {})
    assert filas == []


async def test_clave_repetida_da_409(client, admin) -> None:
    await _estudio(client, admin)
    r = await client.post(
        BASE, json={"clave": "cibse-2027", "titulo": "otro"}, headers=admin.headers()
    )
    assert r.status_code == 409


@pytest.mark.parametrize(
    "clave", ["mis-membresias", "CIbSE 2027", "ab", "membresias", "codebook", "-abc"]
)
async def test_clave_reservada_o_invalida_da_422(client, admin, app_db, clave) -> None:
    r = await client.post(BASE, json={"clave": clave, "titulo": "x"}, headers=admin.headers())
    assert r.status_code == 422
    filas = await _fila(app_db, admin.tenant_id, "SELECT id FROM estudio_codificacion", {})
    assert filas == []


# ── Membresías ────────────────────────────────────────────────────────────


async def test_investigador_asigna_codificador_con_alias_y_semilla(
    client, admin, tenant, app_db
) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    r = await _alta(client, investigador, "cibse-2027", "Ana@Ejemplo.org", "codificador")
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["rol"] == "codificador"
    assert cuerpo["alias"] == "C1"
    filas = await _fila(
        app_db,
        tenant,
        "SELECT email, rol, alias, semilla, user_id, revocada_at FROM estudio_membresia WHERE id = :m",
        {"m": cuerpo["membresia_id"]},
    )
    assert len(filas) == 1
    fila = filas[0]
    assert fila["email"] == "ana@ejemplo.org"
    assert (fila["rol"], fila["alias"], fila["user_id"], fila["revocada_at"]) == (
        "codificador",
        "C1",
        None,
        None,
    )
    assert 0 <= fila["semilla"] < 2**63


async def test_dos_codificadores_tienen_alias_y_semillas_distintos(
    client, admin, tenant, app_db
) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    r1 = await _alta(client, investigador, "cibse-2027", "c1@ejemplo.org", "codificador")
    r2 = await _alta(client, investigador, "cibse-2027", "c2@ejemplo.org", "codificador")
    assert (r1.json()["alias"], r2.json()["alias"]) == ("C1", "C2")
    filas = await _fila(
        app_db,
        tenant,
        "SELECT semilla FROM estudio_membresia WHERE rol = 'codificador'",
        {},
    )
    assert len({f["semilla"] for f in filas}) == 2


@pytest.mark.parametrize("rol", ["codificador", "investigador"])
async def test_email_con_membresia_activa_da_409(client, admin, tenant, rol) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    assert (
        await _alta(client, investigador, "cibse-2027", "ana@ejemplo.org", "codificador")
    ).status_code == 201
    r = await _alta(client, investigador, "cibse-2027", "ANA@ejemplo.org", rol)
    assert r.status_code == 409


async def test_codificador_no_asigna_membresias(client, admin, tenant) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    codificador = Persona(tenant, "c1@ejemplo.org")
    await _alta(client, investigador, "cibse-2027", codificador.email, "codificador")
    r = await _alta(client, codificador, "cibse-2027", "otro@ejemplo.org", "codificador")
    assert r.status_code == 403


async def test_docente_sin_membresia_no_asigna_membresias(client, admin, tenant) -> None:
    await _estudio(client, admin)
    docente = Persona(tenant, "doc@utn.test", "estudiante,docente")
    r = await _alta(client, docente, "cibse-2027", "otro@ejemplo.org", "codificador")
    assert r.status_code == 403


async def test_sin_membresia_403_igual_exista_o_no_el_estudio(client, admin, tenant) -> None:
    await _estudio(client, admin)
    docente = Persona(tenant, "doc@utn.test")
    existe = await _alta(client, docente, "cibse-2027", "x@ejemplo.org", "codificador")
    no_existe = await _alta(client, docente, "no-existe", "x@ejemplo.org", "codificador")
    assert existe.status_code == no_existe.status_code == 403
    assert existe.json() == no_existe.json()


@pytest.mark.parametrize(
    ("email_alta", "email_token"),
    [("Inv@Ejemplo.org", "inv@ejemplo.org"), ("inv@ejemplo.org", "INV@Ejemplo.ORG")],
)
async def test_email_con_mayusculas_distintas_reconoce_la_membresia(
    client, admin, tenant, email_alta, email_token
) -> None:
    await _estudio(client, admin)
    assert (await _alta(client, admin, "cibse-2027", email_alta, "investigador")).status_code == 201
    investigador = Persona(tenant, email_token)
    r = await _alta(client, investigador, "cibse-2027", "c1@ejemplo.org", "codificador")
    assert r.status_code == 201, r.text


async def test_revocada_pierde_acceso_y_la_realta_crea_membresia_nueva(
    client, admin, tenant, app_db
) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    vieja = (await _alta(client, admin, "cibse-2027", "inv2@ejemplo.org", "investigador")).json()
    segundo = Persona(tenant, "inv2@ejemplo.org")
    assert (
        await _alta(client, segundo, "cibse-2027", "c9@ejemplo.org", "codificador")
    ).status_code == 201

    r = await client.delete(
        f"{BASE}/cibse-2027/membresias/{vieja['membresia_id']}", headers=investigador.headers()
    )
    assert r.status_code == 200, r.text
    assert (
        await _alta(client, segundo, "cibse-2027", "c8@ejemplo.org", "codificador")
    ).status_code == 403

    nueva = (
        await _alta(client, investigador, "cibse-2027", "inv2@ejemplo.org", "investigador")
    ).json()
    assert nueva["membresia_id"] != vieja["membresia_id"]
    assert nueva["alias"] != vieja["alias"]
    filas = await _fila(
        app_db,
        tenant,
        "SELECT id, semilla, user_id, revocada_at FROM estudio_membresia WHERE email = 'inv2@ejemplo.org' "
        "ORDER BY created_at",
        {},
    )
    assert [str(f["id"]) for f in filas] == [vieja["membresia_id"], nueva["membresia_id"]]
    assert filas[0]["revocada_at"] is not None
    assert filas[0]["user_id"] == segundo.user_id
    assert filas[1]["revocada_at"] is None
    assert filas[1]["user_id"] is None
    assert filas[0]["semilla"] != filas[1]["semilla"]


async def test_revocar_membresia_inexistente_da_404(client, admin, tenant) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    r = await client.delete(
        f"{BASE}/cibse-2027/membresias/{uuid4()}", headers=investigador.headers()
    )
    assert r.status_code == 404


# ── Atadura al user_id del primer uso ─────────────────────────────────────


async def test_primer_uso_ata_y_otra_cuenta_con_el_mismo_email_recibe_403(
    client, admin, tenant, app_db, caplog
) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    assert (
        await _alta(client, investigador, "cibse-2027", "c1@ejemplo.org", "codificador")
    ).status_code == 201
    filas = await _fila(
        app_db,
        tenant,
        "SELECT id, user_id FROM estudio_membresia WHERE email = 'inv@ejemplo.org'",
        {},
    )
    assert filas[0]["user_id"] == investigador.user_id

    impostor = uuid4()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        r = await client.post(
            f"{BASE}/cibse-2027/membresias",
            json={"email": "c2@ejemplo.org", "rol": "codificador"},
            headers=investigador.headers(user_id=impostor),
        )
    assert r.status_code == 403
    eventos = [
        rec for rec in caplog.records if rec.getMessage() == "estudio_membresia_user_id_distinto"
    ]
    assert len(eventos) == 1
    assert eventos[0].membresia_id == str(filas[0]["id"])
    assert "@" not in repr(vars(eventos[0]))
    sigue = await _fila(
        app_db,
        tenant,
        "SELECT count(*) AS n FROM estudio_membresia WHERE email = 'c2@ejemplo.org'",
        {},
    )
    assert sigue == [{"n": 0}]


# ── Mis membresías ────────────────────────────────────────────────────────


async def test_mis_membresias_vacia_para_quien_no_tiene(client, tenant) -> None:
    r = await client.get(
        f"{BASE}/mis-membresias", headers=Persona(tenant, "nadie@utn.test").headers()
    )
    assert r.status_code == 200
    assert r.json() == []


async def test_mis_membresias_lista_activas_y_ata_el_usuario(client, admin, tenant, app_db) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    await _alta(client, investigador, "cibse-2027", "c1@ejemplo.org", "codificador")
    await _estudio(client, admin, "otro-estudio")
    revocada = (await _alta(client, admin, "otro-estudio", "c1@ejemplo.org", "codificador")).json()
    await client.delete(
        f"{BASE}/otro-estudio/membresias/{revocada['membresia_id']}", headers=admin.headers()
    )

    codificador = Persona(tenant, "C1@ejemplo.org")
    r = await client.get(f"{BASE}/mis-membresias", headers=codificador.headers())
    assert r.status_code == 200
    assert r.json() == [
        {"clave": "cibse-2027", "titulo": "Estudio", "rol": "codificador", "cerrada": False}
    ]
    filas = await _fila(
        app_db,
        tenant,
        "SELECT user_id FROM estudio_membresia WHERE email = 'c1@ejemplo.org' AND revocada_at IS NULL",
        {},
    )
    assert filas == [{"user_id": codificador.user_id}]

    otra_cuenta = codificador.headers(user_id=uuid4())
    r = await client.get(f"{BASE}/mis-membresias", headers=otra_cuenta)
    assert r.json() == []


# ── Logs sin emails ───────────────────────────────────────────────────────


async def test_alta_y_revocacion_se_registran_sin_emails(client, admin, tenant, caplog) -> None:
    investigador = await _con_investigador(client, admin, tenant)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        alta = (
            await _alta(client, investigador, "cibse-2027", "secreto@ejemplo.org", "codificador")
        ).json()
        await client.delete(
            f"{BASE}/cibse-2027/membresias/{alta['membresia_id']}", headers=investigador.headers()
        )
    registros = {rec.getMessage(): rec for rec in caplog.records if rec.name == LOGGER}
    assert {"estudio_membresia_alta", "estudio_membresia_revocada"} <= set(registros)
    alta_log = registros["estudio_membresia_alta"]
    assert (
        alta_log.estudio,
        alta_log.rol,
        alta_log.membresia_id,
        alta_log.alias,
        alta_log.autor_user_id,
    ) == (
        "cibse-2027",
        "codificador",
        alta["membresia_id"],
        "C1",
        str(investigador.user_id),
    )
    for rec in caplog.records:
        assert "secreto" not in repr(vars(rec))
        assert "@ejemplo.org" not in repr(vars(rec))


# ── Procedencia ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("GET", f"{BASE}/mis-membresias"),
        ("POST", BASE),
        ("POST", f"{BASE}/cibse-2027/membresias"),
        ("DELETE", f"{BASE}/cibse-2027/membresias/{uuid4()}"),
        ("GET", f"{BASE}/cibse-2027/membresias"),
        ("GET", f"{BASE}/cibse-2027/codebook/versiones"),
        ("GET", f"{BASE}/cibse-2027/items"),
        ("GET", f"{BASE}/cibse-2027/items/{uuid4()}/traza"),
        ("POST", f"{BASE}/cibse-2027/muestra"),
        ("GET", f"{BASE}/cibse-2027/exportacion?contenido=etiquetas&formato=json"),
        ("GET", f"{BASE}/cibse-2027/entrenamiento"),
    ],
)
async def test_con_firma_exigida_un_pedido_sin_firma_da_401(
    app_db, monkeypatch, metodo, ruta
) -> None:
    # `app_db`: sin el gate, el pedido llega a la base de pruebas y la
    # respuesta es otra (201/200/403/404), no un error de conexión.
    monkeypatch.setattr(settings, "require_gateway_signature", True)
    monkeypatch.setattr(settings, "gateway_shared_secret", "secreto-de-prueba")
    monkeypatch.setattr(settings, "internal_service_token", "")
    headers = Persona(uuid4(), "admin@utn.test", "superadmin").headers()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as c:
        r = await c.request(
            metodo, ruta, json={"clave": "cibse-2027", "titulo": "x"}, headers=headers
        )
    assert r.status_code == 401
