"""Fixtures compartidas para tests de integración contra Postgres real
(`classifier_db` del contenedor de desarrollo local `platform-postgres`).

Ningún test de este directorio commitea: cada uno abre su propia sesión con
un `tenant_id` aleatorio, corre dentro de una única transacción y hace
`rollback()` al final — nunca `commit()`. No se persiste nada.

Excepción declarada: los tests del estudio de codificación
(`test_estudio_*_db.py`) que pegan a la app por HTTP commitean de verdad, bajo
un `tenant_id` aleatorio. Las filas que la base declara inmutables (versiones
de codebook congeladas, historial) no se pueden borrar después: correrlos
contra una base efímera.

`CLASSIFIER_TEST_DB_URL` permite apuntar a otra base (por ejemplo, un Postgres
efímero en otro puerto cuando el 5432 lo ocupa otro proyecto). Sin la variable,
el default es el de siempre. Tiene que ser un usuario NO superuser (dueño de
las tablas, con RLS forzado), o las pruebas de aislamiento pasan sin medir.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DB_URL = os.environ.get(
    "CLASSIFIER_TEST_DB_URL",
    "postgresql+asyncpg://classifier_user:classifier_pass@127.0.0.1:5432/classifier_db",
)


def _postgres_available() -> bool:
    partes = urlsplit(TEST_DB_URL)
    try:
        with socket.create_connection((partes.hostname, partes.port or 5432), timeout=1):
            return True
    except OSError:
        return False


requires_local_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason=f"Postgres de pruebas no disponible en {urlsplit(TEST_DB_URL).netloc.split('@')[-1]}",
)


@pytest.fixture
def test_db_url() -> str:
    """URL de la base de pruebas; saltea el test si no hay Postgres.

    Los archivos nuevos la piden como fixture en vez de importar
    `requires_local_postgres` (importar entre módulos de `tests/` sin
    `__init__.py` de nivel superior es frágil, ver CLAUDE.md)."""
    if not _postgres_available():
        pytest.skip("Postgres de pruebas no disponible")
    return TEST_DB_URL


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id = uuid4()
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        try:
            yield session, tenant_id
        finally:
            await session.rollback()
    await engine.dispose()


@pytest.fixture
async def app_db(test_db_url, monkeypatch):
    """Hace que la app real (`tenant_session`) use la base de pruebas.

    Resetea el engine cacheado del módulo `db` antes y después: un engine
    asyncpg creado en el loop de otro test no se puede reusar."""
    from classifier_service import db as db_module
    from classifier_service.config import settings

    monkeypatch.setattr(settings, "classifier_db_url", test_db_url)
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_session_factory", None)
    yield test_db_url
    if db_module._engine is not None:
        await db_module._engine.dispose()


# ── Estudio de codificación: CTR falso y ayudante HTTP ───────────────────────
# Compartidos por los `test_estudio_*_db.py` de los grupos 6 a 10 vía fixtures
# (no por import entre módulos de test).

import copy as _copy
import hashlib as _hashlib
import json as _json
from datetime import UTC as _UTC
from datetime import datetime as _datetime
from datetime import timedelta as _timedelta
from uuid import UUID as _UUID

_INICIO = _datetime(2026, 9, 1, 10, 0, 0, tzinfo=_UTC)


def _hash(*partes: object) -> str:
    return _hashlib.sha256("|".join(str(p) for p in partes).encode()).hexdigest()


class CTRFalso:
    """Imita `GET /api/v1/episodes/{id}` del ctr-service (shape `EpisodeWithEvents`).

    `modo`: None (responde), "caido" (500) o "timeout". `llamadas` registra
    `(tenant_id, episode_id)` para afirmar qué se pidió."""

    def __init__(self) -> None:
        self.episodios: dict[_UUID, dict] = {}
        self.modo: str | None = None
        self.llamadas: list[tuple[_UUID, _UUID]] = []

    def agregar(
        self,
        *,
        estado: str = "closed",
        cierre: str | None = "episodio_cerrado",
        problema_id: _UUID | None = None,
        ejercicio_id: _UUID | None = None,
        integrity_compromised: bool = False,
        extra: list[tuple[str, dict]] | None = None,
    ) -> _UUID:
        episode_id = uuid4()
        self.episodios[episode_id] = {
            "id": str(episode_id),
            "tenant_id": str(uuid4()),
            "comision_id": str(uuid4()),
            "student_pseudonym": str(uuid4()),
            "problema_id": str(problema_id or uuid4()),
            "estado": estado,
            "opened_at": _INICIO.isoformat(),
            "closed_at": None,
            "events_count": 0,
            "last_chain_hash": "",
            "integrity_compromised": integrity_compromised,
            "prompt_system_hash": "2" * 64,
            "classifier_config_hash": "3" * 64,
            "curso_config_hash": "4" * 64,
            "events": [],
        }
        ep = self.episodios[episode_id]
        self.evento(
            episode_id,
            "episodio_abierto",
            {
                "student_pseudonym": ep["student_pseudonym"],
                "problema_id": ep["problema_id"],
                "comision_id": ep["comision_id"],
                "curso_config_hash": "4" * 64,
                "ejercicio_id": str(ejercicio_id) if ejercicio_id else None,
                "language": "python",
            },
        )
        self.evento(
            episode_id, "prompt_enviado", {"content": "hola tutor", "prompt_kind": "pregunta"}
        )
        self.evento(episode_id, "intento_adverso_detectado", {"category": "overuse", "severity": 1})
        self.evento(episode_id, "tutor_respondio", {"content": "que probaste?", "model_used": "m"})
        for tipo, payload in extra or []:
            self.evento(episode_id, tipo, payload)
        if cierre:
            self.evento(
                episode_id, cierre, {"reason": "timeout"} if cierre == "episodio_abandonado" else {}
            )
        return episode_id

    def evento(
        self, episode_id: _UUID, tipo: str, payload: dict, *, estado: str | None = None
    ) -> None:
        ep = self.episodios[episode_id]
        seq = len(ep["events"])
        prev = ep["events"][-1]["chain_hash"] if ep["events"] else "0" * 64
        self_hash = _hash(episode_id, seq, tipo, _json.dumps(payload, sort_keys=True))
        chain = _hash(self_hash, prev)
        ep["events"].append(
            {
                "event_uuid": str(uuid4()),
                "episode_id": str(episode_id),
                "seq": seq,
                "event_type": tipo,
                "ts": (_INICIO + _timedelta(seconds=10 * seq)).isoformat().replace("+00:00", "Z"),
                "payload": payload,
                "self_hash": self_hash,
                "chain_hash": chain,
                "prev_chain_hash": prev,
                "prompt_system_hash": "2" * 64,
                "prompt_system_version": "v1.0.0",
                "classifier_config_hash": "3" * 64,
                "persisted_at": _INICIO.isoformat(),
            }
        )
        ep["events_count"] = seq + 1
        ep["last_chain_hash"] = chain
        if estado:
            ep["estado"] = estado

    async def episodio(self, tenant_id: _UUID, episode_id: _UUID) -> dict:
        from classifier_service.services.ctr_lectura import (
            CTRNoDisponibleError,
            EpisodioInexistenteError,
        )

        self.llamadas.append((tenant_id, _UUID(str(episode_id))))
        if self.modo in ("caido", "timeout"):
            raise CTRNoDisponibleError(self.modo)
        ep = self.episodios.get(_UUID(str(episode_id)))
        if ep is None:
            raise EpisodioInexistenteError(str(episode_id))
        return _copy.deepcopy(ep)


@pytest.fixture
def ctr_falso():
    from classifier_service.main import app
    from classifier_service.services.ctr_lectura import get_ctr_lector

    falso = CTRFalso()
    app.dependency_overrides[get_ctr_lector] = lambda: falso
    yield falso
    app.dependency_overrides.pop(get_ctr_lector, None)


ESQUEMA_PRUEBA = {
    "dimensiones": [
        {
            "clave": "d1",
            "nombre": "D1",
            "valores": ["presente", "ausente"],
            "cita_requerida_si": ["presente"],
        },
        {
            "clave": "d2",
            "nombre": "D2",
            "valores": ["presente", "ausente"],
            "cita_requerida_si": [],
        },
        {
            "clave": "d4",
            "nombre": "D4",
            "valores": ["interlocutor", "oraculo"],
            "cita_requerida_si": [],
        },
    ],
    "regimenes": [
        {"clave": "reflexiva", "nombre": "Reflexiva"},
        {"clave": "superficial", "nombre": "Superficial"},
        {"clave": "evidencia_insuficiente", "nombre": "Evidencia insuficiente"},
    ],
    "regimen_evidencia_insuficiente": "evidencia_insuficiente",
    "dimensiones_opcionales_si_regimen": ["evidencia_insuficiente"],
    "notas_obligatorias_si_regimen": ["evidencia_insuficiente"],
    "reglas_regimen": [
        {
            "regimen": "reflexiva",
            "condicion": [
                [{"dimension": "d1", "en": ["presente"]}],
                [{"dimension": "d2", "en": ["presente"]}],
                [{"dimension": "d4", "en": ["interlocutor"]}],
            ],
        }
    ],
    "regimen_por_defecto": "superficial",
    "regimenes_exentos": ["evidencia_insuficiente"],
}

ETIQUETA_REFLEXIVA = {
    "respuestas": {
        "d1": {"valor": "presente", "cita": "turno 1"},
        "d2": {"valor": "presente", "cita": None},
        "d4": {"valor": "interlocutor", "cita": None},
    }
}


class PersonaEstudio:
    def __init__(self, tenant_id: _UUID, email: str, roles: str = "estudiante,docente") -> None:
        self.tenant_id = tenant_id
        self.user_id = uuid4()
        self.email = email
        self.roles = roles

    def headers(self) -> dict[str, str]:
        return {
            "X-User-Id": str(self.user_id),
            "X-Tenant-Id": str(self.tenant_id),
            "X-User-Email": self.email,
            "X-User-Roles": self.roles,
        }


class EstudioHTTP:
    """Estudio armado por la API real, con atajos para los grupos 6 a 10."""

    BASE = "/api/v1/interrater/estudios"

    def __init__(self, client, url: str, ctr: CTRFalso, clave: str = "cibse-2027") -> None:
        self.client = client
        self.url = url
        self.ctr = ctr
        self.clave = clave
        self.tenant_id = uuid4()
        self.admin = PersonaEstudio(
            self.tenant_id, "admin@utn.test", "estudiante,docente,superadmin"
        )
        self.investigador = PersonaEstudio(self.tenant_id, "inv@ejemplo.org")
        self.c1 = PersonaEstudio(self.tenant_id, "c1@ejemplo.org")
        self.c2 = PersonaEstudio(self.tenant_id, "c2@ejemplo.org")
        self.ajeno = PersonaEstudio(self.tenant_id, "ajeno@utn.test")

    def ruta(self, sufijo: str = "") -> str:
        return f"{self.BASE}/{self.clave}{sufijo}"

    async def pedir(self, metodo: str, sufijo: str, persona: PersonaEstudio, **kw):
        return await self.client.request(metodo, self.ruta(sufijo), headers=persona.headers(), **kw)

    async def crear(self) -> EstudioHTTP:
        r = await self.client.post(
            self.BASE, json={"clave": self.clave, "titulo": "Estudio"}, headers=self.admin.headers()
        )
        assert r.status_code == 201, r.text
        for persona, rol in (
            (self.investigador, "investigador"),
            (self.c1, "codificador"),
            (self.c2, "codificador"),
        ):
            r = await self.pedir(
                "POST", "/membresias", self.admin, json={"email": persona.email, "rol": rol}
            )
            assert r.status_code == 201, r.text
        return self

    async def codebook(
        self, etiqueta: str = "v0", *, congelar: bool = True, vigente: bool = True
    ) -> None:
        inv = self.investigador
        assert (
            await self.pedir("POST", "/codebook", inv, json={"etiqueta": etiqueta})
        ).status_code == 201
        r = await self.pedir(
            "PUT",
            f"/codebook/{etiqueta}",
            inv,
            json={"contenido_md": "# Codebook", "esquema": ESQUEMA_PRUEBA},
        )
        assert r.status_code == 200, r.text
        if vigente:
            assert (
                await self.pedir("PUT", "/codebook-vigente", inv, json={"etiqueta": etiqueta})
            ).status_code == 200
        if congelar:
            assert (
                await self.pedir("POST", f"/codebook/{etiqueta}/congelar", inv)
            ).status_code == 200

    @staticmethod
    def csv_muestra(episodios: list[_UUID]) -> str:
        filas = ["estrato,origen,tp,episode_id"]
        filas += [f"E{i % 3},origen-{i},TP-{i % 2},{ep}" for i, ep in enumerate(episodios)]
        return "\n".join(filas) + "\n"

    async def cargar_muestra(
        self, episodios: list[_UUID], persona: PersonaEstudio | None = None, **params
    ):
        return await self.client.post(
            self.ruta("/muestra"),
            content=self.csv_muestra(episodios).encode("utf-8"),
            headers={**(persona or self.investigador).headers(), "Content-Type": "text/csv"},
            params=params,
        )

    @staticmethod
    def csv_enunciados(filas: list[tuple[str, _UUID, str]]) -> str:
        lineas = ["tipo,tp_id,ejercicio_id,enunciado"]
        for tipo, fuente_id, texto in filas:
            texto_csv = '"' + texto.replace('"', '""') + '"'
            if tipo == "tp":
                lineas.append(f"tp,{fuente_id},,{texto_csv}")
            else:
                lineas.append(f"ejercicio,,{fuente_id},{texto_csv}")
        return "\n".join(lineas) + "\n"

    async def cargar_enunciados(self, filas, persona: PersonaEstudio | None = None):
        return await self.client.post(
            self.ruta("/enunciados"),
            content=self.csv_enunciados(filas).encode("utf-8"),
            headers={**(persona or self.investigador).headers(), "Content-Type": "text/csv"},
        )

    def requeridos(self, episodios: list[_UUID]) -> list[tuple[str, _UUID, str]]:
        filas: dict[tuple[str, _UUID], str] = {}
        for ep in episodios:
            datos = self.ctr.episodios[ep]
            filas[("tp", _UUID(datos["problema_id"]))] = f"Consigna TP {datos['problema_id'][:4]}"
            ejercicio = datos["events"][0]["payload"].get("ejercicio_id")
            if ejercicio:
                filas[("ejercicio", _UUID(ejercicio))] = f"Consigna ejercicio {ejercicio[:4]}"
        return [(t, i, texto) for (t, i), texto in filas.items()]

    async def revisar_todos(self) -> None:
        r = await self.pedir("GET", "/enunciados", self.investigador)
        assert r.status_code == 200, r.text
        for enunciado in r.json()["enunciados"]:
            if not enunciado["revisado"]:
                rr = await self.pedir(
                    "POST",
                    f"/enunciados/{enunciado['id']}/revision",
                    self.investigador,
                    json={"contenido_mostrado_md": None},
                )
                assert rr.status_code == 200, rr.text

    async def preparar(self, n: int = 2, *, congelar: bool = True) -> list[_UUID]:
        """Estudio listo para codificar: muestra de `n`, enunciados revisados,
        codebook vigente (congelado salvo `congelar=False`)."""
        episodios = [self.ctr.agregar() for _ in range(n)]
        r = await self.cargar_muestra(episodios)
        assert r.status_code == 200, r.text
        assert (await self.cargar_enunciados(self.requeridos(episodios))).status_code == 200
        await self.revisar_todos()
        await self.codebook(congelar=congelar)
        return episodios

    async def items(self, persona: PersonaEstudio | None = None) -> list[dict]:
        r = await self.pedir("GET", "/items", persona or self.c1)
        assert r.status_code == 200, r.text
        return r.json()

    async def insertar_item_sql(self, episode_id: _UUID, *, ancla_de: str | None = None) -> _UUID:
        """Ítem de muestra (o ancla de la versión `ancla_de`) con la evidencia
        fija leída del CTR falso, por SQL directo: para tareas previas a los
        endpoints de carga (7.1, 7.3)."""
        ep = self.ctr.episodios[episode_id]
        tope = ep["events"][-1]
        valores = {
            "t": self.tenant_id,
            "c": self.clave,
            "ep": episode_id,
            "seq": tope["seq"],
            "ch": tope["chain_hash"],
            "n": ep["events_count"],
            "last": ep["last_chain_hash"],
            "estado": ep["estado"],
            "prob": _UUID(ep["problema_id"]),
            "ejer": ep["events"][0]["payload"].get("ejercicio_id"),
        }
        comunes = (
            "episode_id, seq_tope, chain_hash_tope, events_count_carga, last_chain_hash_carga, "
            "estado_carga, problema_id, ejercicio_id"
        )
        if ancla_de is None:
            filas = await self.sql(
                f"INSERT INTO estudio_muestra (tenant_id, estudio_id, {comunes}) "
                "SELECT :t, e.id, :ep, :seq, :ch, :n, :last, :estado, :prob, CAST(:ejer AS uuid) "
                "FROM estudio_codificacion e WHERE e.clave = :c RETURNING item_id",
                valores,
                commit=True,
            )
        else:
            filas = await self.sql(
                f"INSERT INTO estudio_ancla (tenant_id, estudio_id, codebook_version_id, {comunes}, "
                "uso, orden, respuesta_esperada) "
                "SELECT :t, e.id, v.id, :ep, :seq, :ch, :n, :last, :estado, :prob, CAST(:ejer AS uuid), "
                "'practica', 1, '{}'::jsonb FROM estudio_codificacion e "
                "JOIN codebook_version v ON v.estudio_id = e.id "
                "WHERE e.clave = :c AND v.etiqueta = :et RETURNING item_id",
                {**valores, "et": ancla_de},
                commit=True,
            )
        return filas[0]["item_id"]

    async def insertar_enunciado_sql(
        self,
        fuente: str,
        fuente_id: _UUID,
        texto: str,
        *,
        revisado: bool = True,
        mostrado: str | None = None,
    ) -> None:
        await self.sql(
            "INSERT INTO estudio_enunciado (tenant_id, estudio_id, fuente, fuente_id, archivo_sha256, "
            "cargado_por, contenido_original_md, sha256_original, contenido_mostrado_md, sha256_mostrado, "
            "revisado_por, revisado_at) "
            "SELECT :t, e.id, :f, :fid, repeat('a', 64), gen_random_uuid(), :txt, repeat('b', 64), "
            "CASE WHEN :rev THEN :mostrado END, CASE WHEN :rev THEN repeat('c', 64) END, "
            "CASE WHEN :rev THEN gen_random_uuid() END, CASE WHEN :rev THEN now() END "
            "FROM estudio_codificacion e WHERE e.clave = :c",
            {
                "t": self.tenant_id,
                "c": self.clave,
                "f": fuente,
                "fid": fuente_id,
                "txt": texto,
                "rev": revisado,
                "mostrado": mostrado if mostrado is not None else texto,
            },
            commit=True,
        )

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


@pytest.fixture
async def estudio_http(app_db, ctr_falso):
    from classifier_service.main import app
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        yield await EstudioHTTP(client, app_db, ctr_falso).crear()


@pytest.fixture
def esquema_prueba() -> dict:
    return _copy.deepcopy(ESQUEMA_PRUEBA)


@pytest.fixture
def etiqueta_reflexiva() -> dict:
    return _copy.deepcopy(ETIQUETA_REFLEXIVA)
