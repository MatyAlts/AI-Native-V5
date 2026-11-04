"""Codebook versionado por la API (tarea 5.1, design D8, spec codebook-versionado).

App real + Postgres real; commitea bajo un tenant aleatorio (ver `conftest.py`).
Las anclas se insertan con SQL directo en la versión borrador: sus endpoints
son de la tarea 7.3. El contenido y el esquema son los del literal de
`tests/unit/test_estudio_codebook.py`; la primera ancla difiere (ver
`SHA_LITERAL`).
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from classifier_service.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BASE = "/api/v1/interrater/estudios"
CLAVE = "cibse-2027"
# Desde verify-2 (O1) congelar exige anclas COMPLETAS: la primera ancla del
# literal de `tests/unit/test_estudio_codebook.py` (`respuestas: {}`) ya no
# congela. Acá lleva `d1 = "no"` y el literal es otro. Se calculó FUERA de la
# implementación, con la serialización canónica escrita a mano y `sha256sum`;
# el mismo procedimiento con la ancla vieja reproduce el literal de la unidad
# (51c33896...), que no cambia: la fórmula es la misma.
SHA_LITERAL = "69e1c2c273198f8f3209335d8223e585105156aa5b3360f173b9add1c8df34dd"
CONTENIDO = "# Codebook de prueba\nPáramo ñandú"
ESQUEMA = {
    "dimensiones": [
        {"clave": "d1", "nombre": "D1", "valores": ["si", "no"], "cita_requerida_si": ["si"]}
    ],
    "regimenes": [{"clave": "a", "nombre": "A"}, {"clave": "ei", "nombre": "EI"}],
    "regimen_evidencia_insuficiente": "ei",
}
ANCLAS = [
    {
        "uso": "practica",
        "orden": 1,
        "episode_id": "00000000-0000-4000-8000-000000000002",
        "respuesta_esperada": {
            "regimen": "ei",
            "respuestas": {"d1": {"valor": "no", "cita": None}},
        },
        "explicacion_md": "Porque sí",
        "consensuado_por": "C1 y C2",
        "seq_tope": 5,
        "chain_hash_tope": "a" * 64,
    },
    {
        "uso": "ejemplo",
        "orden": 2,
        "episode_id": "00000000-0000-4000-8000-000000000001",
        "respuesta_esperada": {
            "respuestas": {"d1": {"valor": "si", "cita": "turno 2"}},
            "regimen": "a",
        },
        "explicacion_md": "Ejemplo claro",
        "consensuado_por": "C1 y C2",
        "seq_tope": 3,
        "chain_hash_tope": "b" * 64,
    },
]


class Persona:
    def __init__(self, tenant_id: UUID, email: str, roles: str = "estudiante,docente") -> None:
        self.tenant_id = tenant_id
        self.user_id = uuid4()
        self.email = email
        self.roles = roles

    def headers(self) -> dict:
        return {
            "X-User-Id": str(self.user_id),
            "X-Tenant-Id": str(self.tenant_id),
            "X-User-Email": self.email,
            "X-User-Roles": self.roles,
        }


class Estudio:
    def __init__(self, client: AsyncClient, url: str, tenant_id: UUID) -> None:
        self.client = client
        self.url = url
        self.tenant_id = tenant_id
        self.admin = Persona(tenant_id, "admin@utn.test", "estudiante,docente,superadmin")
        self.investigador = Persona(tenant_id, "inv@ejemplo.org")
        self.codificador = Persona(tenant_id, "c1@ejemplo.org")

    async def crear(self) -> Estudio:
        r = await self.client.post(
            BASE, json={"clave": CLAVE, "titulo": "E"}, headers=self.admin.headers()
        )
        assert r.status_code == 201, r.text
        for persona, rol in (
            (self.investigador, "investigador"),
            (self.codificador, "codificador"),
        ):
            r = await self.client.post(
                f"{BASE}/{CLAVE}/membresias",
                json={"email": persona.email, "rol": rol},
                headers=self.admin.headers(),
            )
            assert r.status_code == 201, r.text
        return self

    async def version(self, etiqueta: str, **body):
        return await self.client.post(
            f"{BASE}/{CLAVE}/codebook",
            json={"etiqueta": etiqueta, **body},
            headers=self.investigador.headers(),
        )

    async def editar(self, etiqueta: str, body: dict, persona: Persona | None = None):
        return await self.client.put(
            f"{BASE}/{CLAVE}/codebook/{etiqueta}",
            json=body,
            headers=(persona or self.investigador).headers(),
        )

    async def congelar(self, etiqueta: str, persona: Persona | None = None):
        return await self.client.post(
            f"{BASE}/{CLAVE}/codebook/{etiqueta}/congelar",
            headers=(persona or self.investigador).headers(),
        )

    async def fijar_vigente(self, etiqueta: str, persona: Persona | None = None):
        return await self.client.put(
            f"{BASE}/{CLAVE}/codebook-vigente",
            json={"etiqueta": etiqueta},
            headers=(persona or self.investigador).headers(),
        )

    async def vigente(self, persona: Persona, clave: str = CLAVE):
        return await self.client.get(f"{BASE}/{clave}/codebook/vigente", headers=persona.headers())

    async def sql(self, sql: str, params: dict | None = None, *, commit: bool = False) -> list:
        engine = create_async_engine(self.url)
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(self.tenant_id)},
                )
                resultado = await conn.execute(text(sql), params or {})
                filas = list(resultado.mappings()) if resultado.returns_rows else []
                if commit:
                    await conn.commit()
                return filas
        finally:
            await engine.dispose()

    async def agregar_anclas(self, etiqueta: str, anclas: list[dict]) -> None:
        for ancla in anclas:
            await self.sql(
                "INSERT INTO estudio_ancla (tenant_id, estudio_id, codebook_version_id, episode_id, "
                "seq_tope, chain_hash_tope, events_count_carga, last_chain_hash_carga, estado_carga, "
                "problema_id, ejercicio_id, uso, orden, respuesta_esperada, explicacion_md, "
                "consensuado_por) "
                "SELECT :t, v.estudio_id, v.id, :ep, :seq, :ch, :seq + 1, :ch, 'closed', "
                "gen_random_uuid(), NULL, :uso, :orden, CAST(:resp AS jsonb), :exp, :cons "
                "FROM codebook_version v JOIN estudio_codificacion e ON e.id = v.estudio_id "
                "WHERE e.clave = :clave AND v.etiqueta = :et",
                {
                    "t": self.tenant_id,
                    "ep": ancla["episode_id"],
                    "seq": ancla["seq_tope"],
                    "ch": ancla["chain_hash_tope"],
                    "uso": ancla["uso"],
                    "orden": ancla["orden"],
                    "resp": json.dumps(ancla["respuesta_esperada"]),
                    "exp": ancla["explicacion_md"],
                    "cons": ancla["consensuado_por"],
                    "clave": CLAVE,
                    "et": etiqueta,
                },
                commit=True,
            )

    async def borrador_completo(self, etiqueta: str, anclas: list[dict] | None = None) -> None:
        assert (await self.version(etiqueta)).status_code == 201
        r = await self.editar(etiqueta, {"contenido_md": CONTENIDO, "esquema": ESQUEMA})
        assert r.status_code == 200, r.text
        await self.agregar_anclas(etiqueta, ANCLAS if anclas is None else anclas)


@pytest.fixture
async def estudio(app_db) -> Estudio:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as c:
        yield await Estudio(c, app_db, uuid4()).crear()


# ── Versiones ─────────────────────────────────────────────────────────────


async def test_crear_y_cargar_un_borrador(estudio) -> None:
    r = await estudio.version("v0")
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "borrador"
    r = await estudio.editar("v0", {"contenido_md": CONTENIDO, "esquema": ESQUEMA})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["etiqueta"], cuerpo["estado"], cuerpo["contenido_md"], cuerpo["esquema"]) == (
        "v0",
        "borrador",
        CONTENIDO,
        ESQUEMA,
    )
    assert cuerpo["contenido_sha256"] is None


async def test_etiqueta_repetida_da_409(estudio) -> None:
    assert (await estudio.version("v0")).status_code == 201
    assert (await estudio.version("v0")).status_code == 409


@pytest.mark.parametrize("etiqueta", ["vigente", "", "con espacio", "x" * 41])
async def test_etiqueta_invalida_da_422(estudio, etiqueta) -> None:
    assert (await estudio.version(etiqueta)).status_code == 422


async def test_esquema_invalido_da_400_y_no_cambia_nada(estudio) -> None:
    await estudio.borrador_completo("v0", anclas=[])
    malo = {**ESQUEMA, "regimen_evidencia_insuficiente": "no-existe"}
    r = await estudio.editar("v0", {"contenido_md": "# otro", "esquema": malo})
    assert r.status_code == 400
    assert any("regimen_evidencia_insuficiente" in e for e in r.json()["detail"]["errores"])
    filas = await estudio.sql("SELECT contenido_md, esquema_formulario FROM codebook_version")
    assert filas == [{"contenido_md": CONTENIDO, "esquema_formulario": ESQUEMA}]


@pytest.mark.parametrize(
    "parche",
    [
        # verify-1, F3: listas u objetos donde va una clave de régimen daban 500.
        {"regimen_evidencia_insuficiente": ["ei"]},
        {"regimen_evidencia_insuficiente": {"clave": "ei"}},
        {"regimenes_exentos": [["ei"]]},
        {"notas_obligatorias_si_regimen": [["ei"]]},
        {"dimensiones_opcionales_si_regimen": [{"x": 1}]},
        {
            "reglas_regimen": [
                {"regimen": ["a"], "condicion": [[{"dimension": "d1", "en": ["si"]}]]}
            ],
            "regimen_por_defecto": "a",
        },
        {
            "reglas_regimen": [
                {"regimen": "a", "condicion": [[{"dimension": ["d1"], "en": ["si"]}]]}
            ],
            "regimen_por_defecto": "a",
        },
        {
            "reglas_regimen": [
                {"regimen": "a", "condicion": [[{"dimension": "d1", "en": ["si"]}]]}
            ],
            "regimen_por_defecto": ["a"],
        },
    ],
)
async def test_esquema_con_tipos_invalidos_en_claves_da_400(estudio, parche) -> None:
    await estudio.borrador_completo("v0", anclas=[])
    r = await estudio.editar("v0", {"esquema": {**ESQUEMA, **parche}})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["errores"]
    filas = await estudio.sql("SELECT esquema_formulario FROM codebook_version")
    assert filas == [{"esquema_formulario": ESQUEMA}]


async def test_clonar_copia_texto_esquema_y_anclas_sin_tocar_el_origen(estudio) -> None:
    await estudio.borrador_completo("v0")
    r = await estudio.version("v1", clonar_de="v0")
    assert r.status_code == 201, r.text
    versiones = await estudio.sql(
        "SELECT etiqueta, estado, contenido_md, esquema_formulario FROM codebook_version ORDER BY etiqueta"
    )
    assert versiones == [
        {
            "etiqueta": "v0",
            "estado": "borrador",
            "contenido_md": CONTENIDO,
            "esquema_formulario": ESQUEMA,
        },
        {
            "etiqueta": "v1",
            "estado": "borrador",
            "contenido_md": CONTENIDO,
            "esquema_formulario": ESQUEMA,
        },
    ]
    anclas = await estudio.sql(
        "SELECT v.etiqueta, a.item_id, a.uso, a.orden, a.episode_id::text AS episode_id, "
        "a.explicacion_md, a.seq_tope, a.chain_hash_tope "
        "FROM estudio_ancla a JOIN codebook_version v ON v.id = a.codebook_version_id "
        "ORDER BY v.etiqueta, a.orden"
    )
    v0 = [
        {k: f[k] for k in f if k not in ("etiqueta", "item_id")}
        for f in anclas
        if f["etiqueta"] == "v0"
    ]
    v1 = [
        {k: f[k] for k in f if k not in ("etiqueta", "item_id")}
        for f in anclas
        if f["etiqueta"] == "v1"
    ]
    assert len(v0) == 2
    assert v0 == v1
    assert not {f["item_id"] for f in anclas if f["etiqueta"] == "v0"} & {
        f["item_id"] for f in anclas if f["etiqueta"] == "v1"
    }


async def test_clonar_de_inexistente_da_404(estudio) -> None:
    assert (await estudio.version("v1", clonar_de="nada")).status_code == 404


# ── Congelamiento ─────────────────────────────────────────────────────────


async def test_congelar_fija_sha_literal_fecha_y_autor(estudio) -> None:
    await estudio.borrador_completo("v0")
    r = await estudio.congelar("v0")
    assert r.status_code == 200, r.text
    assert r.json()["contenido_sha256"] == SHA_LITERAL
    assert r.json()["estado"] == "congelada"
    filas = await estudio.sql(
        "SELECT estado, contenido_sha256, congelada_por, congelada_at IS NOT NULL AS con_fecha "
        "FROM codebook_version"
    )
    assert filas == [
        {
            "estado": "congelada",
            "contenido_sha256": SHA_LITERAL,
            "congelada_por": estudio.investigador.user_id,
            "con_fecha": True,
        }
    ]


async def test_anclas_identicas_con_otro_item_id_dan_el_mismo_sha(estudio) -> None:
    await estudio.borrador_completo("v0")
    assert (await estudio.version("v1", clonar_de="v0")).status_code == 201
    sha_v0 = (await estudio.congelar("v0")).json()["contenido_sha256"]
    sha_v1 = (await estudio.congelar("v1")).json()["contenido_sha256"]
    assert sha_v0 == sha_v1 == SHA_LITERAL


async def test_el_sha_cubre_la_explicacion_de_las_anclas(estudio) -> None:
    await estudio.borrador_completo("v0")
    otra = [dict(ANCLAS[0], explicacion_md="Porque no"), ANCLAS[1]]
    await estudio.borrador_completo("v1", anclas=otra)
    sha_v0 = (await estudio.congelar("v0")).json()["contenido_sha256"]
    sha_v1 = (await estudio.congelar("v1")).json()["contenido_sha256"]
    assert sha_v0 == SHA_LITERAL
    assert sha_v1 != sha_v0


@pytest.mark.parametrize(
    "cambio",
    [
        {"contenido_md": "# cambiado"},
        {"esquema": {**ESQUEMA, "regimen_evidencia_insuficiente": "a"}},
    ],
)
async def test_version_congelada_no_se_edita_por_la_api(estudio, cambio) -> None:
    await estudio.borrador_completo("v0")
    assert (await estudio.congelar("v0")).status_code == 200
    r = await estudio.editar("v0", cambio)
    assert r.status_code == 409
    filas = await estudio.sql(
        "SELECT contenido_md, esquema_formulario, contenido_sha256 FROM codebook_version"
    )
    assert filas == [
        {"contenido_md": CONTENIDO, "esquema_formulario": ESQUEMA, "contenido_sha256": SHA_LITERAL}
    ]


async def test_congelar_dos_veces_da_409(estudio) -> None:
    await estudio.borrador_completo("v0")
    assert (await estudio.congelar("v0")).status_code == 200
    assert (await estudio.congelar("v0")).status_code == 409


@pytest.mark.parametrize("contenido", ["", "   \n"])
async def test_congelar_texto_vacio_da_422_y_sigue_en_borrador(estudio, contenido) -> None:
    assert (await estudio.version("v0")).status_code == 201
    assert (
        await estudio.editar("v0", {"contenido_md": contenido, "esquema": ESQUEMA})
    ).status_code == 200
    assert (await estudio.congelar("v0")).status_code == 422
    assert await estudio.sql("SELECT estado FROM codebook_version") == [{"estado": "borrador"}]


async def test_congelar_sin_esquema_da_422(estudio) -> None:
    assert (await estudio.version("v0")).status_code == 201
    assert (await estudio.editar("v0", {"contenido_md": CONTENIDO})).status_code == 200
    assert (await estudio.congelar("v0")).status_code == 422
    assert await estudio.sql("SELECT estado FROM codebook_version") == [{"estado": "borrador"}]


# ── Vigente ───────────────────────────────────────────────────────────────


async def test_sin_vigente_el_miembro_recibe_sin_codebook(estudio) -> None:
    r = await estudio.vigente(estudio.codificador)
    assert r.status_code == 404
    assert r.json()["detail"] == "sin_codebook"


async def test_fijar_vigente_y_leerla_como_codificador(estudio) -> None:
    await estudio.borrador_completo("v0")
    assert (await estudio.fijar_vigente("v0")).status_code == 200
    r = await estudio.vigente(estudio.codificador)
    assert r.status_code == 200
    assert r.json() == {
        "etiqueta": "v0",
        "estado": "borrador",
        "contenido_md": CONTENIDO,
        "esquema": ESQUEMA,
        "contenido_sha256": None,
    }
    assert (await estudio.congelar("v0")).status_code == 200
    r = await estudio.vigente(estudio.codificador)
    assert (r.json()["estado"], r.json()["contenido_sha256"]) == ("congelada", SHA_LITERAL)


async def test_fijar_vigente_inexistente_da_404(estudio) -> None:
    assert (await estudio.fijar_vigente("nada")).status_code == 404


async def test_cambiar_vigente_con_etiquetas_da_409_y_no_cambia(estudio) -> None:
    await estudio.borrador_completo("v0")
    await estudio.borrador_completo("v1")
    assert (await estudio.fijar_vigente("v0")).status_code == 200
    assert (await estudio.fijar_vigente("v1")).status_code == 200
    await estudio.sql(
        "WITH e AS (SELECT id, codebook_vigente_id FROM estudio_codificacion WHERE clave = :c), "
        "i AS (INSERT INTO estudio_muestra (tenant_id, estudio_id, episode_id, seq_tope, chain_hash_tope, "
        "events_count_carga, last_chain_hash_carga, estado_carga, problema_id) "
        "SELECT :t, e.id, gen_random_uuid(), 1, repeat('a', 64), 2, repeat('a', 64), 'closed', "
        "gen_random_uuid() FROM e RETURNING item_id) "
        "INSERT INTO estudio_etiqueta (tenant_id, membresia_id, muestra_item_id, codebook_version_id, "
        "traza_version) SELECT :t, m.id, i.item_id, e.codebook_vigente_id, 'traza_v1' "
        "FROM e, i, estudio_membresia m WHERE m.estudio_id = e.id AND m.rol = 'codificador'",
        {"c": CLAVE, "t": estudio.tenant_id},
        commit=True,
    )
    r = await estudio.fijar_vigente("v0")
    assert r.status_code == 409
    filas = await estudio.sql(
        "SELECT v.etiqueta FROM estudio_codificacion e JOIN codebook_version v ON v.id = e.codebook_vigente_id"
    )
    assert filas == [{"etiqueta": "v1"}]


# ── Quién puede qué ───────────────────────────────────────────────────────


async def test_codificador_no_gestiona_el_codebook(estudio) -> None:
    await estudio.borrador_completo("v0")
    c = estudio.codificador
    assert (
        await estudio.client.post(
            f"{BASE}/{CLAVE}/codebook", json={"etiqueta": "v9"}, headers=c.headers()
        )
    ).status_code == 403
    assert (await estudio.editar("v0", {"contenido_md": "# x"}, persona=c)).status_code == 403
    assert (await estudio.congelar("v0", persona=c)).status_code == 403
    assert (await estudio.fijar_vigente("v0", persona=c)).status_code == 403
    assert await estudio.sql("SELECT etiqueta, estado, contenido_md FROM codebook_version") == [
        {"etiqueta": "v0", "estado": "borrador", "contenido_md": CONTENIDO}
    ]


@pytest.mark.parametrize(
    "roles", ["estudiante,docente", "estudiante,docente,superadmin", "docente_admin"]
)
async def test_sin_membresia_no_lee_el_codebook_aunque_exista(estudio, roles) -> None:
    await estudio.borrador_completo("v0")
    assert (await estudio.fijar_vigente("v0")).status_code == 200
    ajeno = Persona(estudio.tenant_id, "ajeno@utn.test", roles)
    existe = await estudio.vigente(ajeno)
    no_existe = await estudio.vigente(ajeno, clave="no-existe")
    assert existe.status_code == no_existe.status_code == 403
    assert existe.json() == no_existe.json()


async def test_investigador_lee_la_vigente(estudio) -> None:
    await estudio.borrador_completo("v0")
    assert (await estudio.fijar_vigente("v0")).status_code == 200
    assert (await estudio.vigente(estudio.investigador)).status_code == 200
