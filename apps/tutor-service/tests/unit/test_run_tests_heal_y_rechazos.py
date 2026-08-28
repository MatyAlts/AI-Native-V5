"""`run-tests`: qué se sana, qué se rechaza, y quién decide cuál es cuál.

Dos cosas que estaban sin fijar y que fallan en silencio:

**1. El acoplamiento por texto.** `_es_rechazo_de_payload` decide 422 vs 409
buscando `"Conteos inconsistentes"` y `"tests_hidden"` dentro del mensaje de un
`ValueError`. El core NO distingue el tipo: los tres motivos —sesión ausente,
conteos que no cierran, ocultos desde el browser— salen como el mismo
`ValueError`. Si alguien reescribe uno de esos dos mensajes en `tutor_core`, la
clasificación se invierte sin que nada se rompa: un payload inválido pasa a
responder 409 y, de yapa, dispara un `resume_episode` que no arregla nada.

Por eso los mensajes de estos tests NO son literales inventados. Se los pido al
core de verdad (`TutorCore.emit_tests_ejecutados`) y le paso a la función pura
lo que ese método produjo. Un literal copiado a mano acá fijaría el test contra
sí mismo, que es exactamente cómo aparecieron los siete tests vacuos del epic:
el fixture dejaba de parecerse al dato real y nadie se enteraba.

**2. Los bordes del heal.** El heal de la sesión vencida ya tiene cobertura por
el camino feliz; lo que faltaba es que no se pase de rosca: que sane UNA vez y
no duplique, que no tape un episodio cerrado ni uno ajeno, y —el más
importante— que NO corra ante un payload inválido. Sanar un payload inválido no
arregla nada, y sobre un episodio cerrado el `resume_episode` del heal
devolvería 409 tapando el 422 que corresponde.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from tutor_service.routes.episodes import _es_rechazo_de_payload
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

PROMPT_HASH = "abc" + "0" * 61
_HEADER_IDEMPOTENCIA = "Idempotency-Key"


# ── Dobles ────────────────────────────────────────────────────────────


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="prompt-sistema", hash=PROMPT_HASH)


class _FakeContent:
    async def retrieve(
        self,
        query: str,
        comision_id: UUID,
        top_k: int,
        tenant_id: UUID,
        caller_id: UUID,
        materia_id: UUID | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="d" * 64, latency_ms=1.0)


class _FakeAI:
    async def stream(
        self,
        messages: list[dict],
        model: str,
        tenant_id: UUID,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        materia_id: UUID | None = None,
    ) -> AsyncIterator[dict]:
        if False:
            yield {"type": "chunk", "content": ""}


class _FakeCTR:
    """CTR fake con `get_episode` configurable (forma `EpisodeWithEvents`).

    Molde tomado de `test_resume_episode.py`: el heal llama a `resume_episode`,
    que arranca leyendo el episodio del CTR.
    """

    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
        self.episodes: dict[str, dict] = {}

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def get_episode(self, episode_id: UUID, tenant_id: UUID, caller_id: UUID) -> dict | None:
        return self.episodes.get(str(episode_id))


def _ts(seq: int) -> str:
    return datetime(2026, 8, 27, 12, 0, seq, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _episodio_persistido(
    episode_id: UUID,
    tenant_id: UUID,
    student_id: UUID,
    *,
    estado: str = "open",
) -> dict:
    """El episodio como lo tiene el CTR: abierto y con un evento en la cadena.

    `estado="open"` es el caso real del bug: al alumno se le venció el TTL de
    la sesión Redis mientras el episodio seguía vivo del lado del CTR.
    """
    comision_id = uuid4()
    problema_id = uuid4()
    return {
        "id": str(episode_id),
        "tenant_id": str(tenant_id),
        "comision_id": str(comision_id),
        "student_pseudonym": str(student_id),
        "problema_id": str(problema_id),
        "estado": estado,
        "opened_at": _ts(0),
        "closed_at": None,
        "events_count": 1,
        "last_chain_hash": "e" * 64,
        "integrity_compromised": False,
        "prompt_system_hash": PROMPT_HASH,
        "classifier_config_hash": "b" * 64,
        "curso_config_hash": "c" * 64,
        "events": [
            {
                "event_uuid": str(uuid4()),
                "episode_id": str(episode_id),
                "seq": 0,
                "event_type": "episodio_abierto",
                "ts": _ts(0),
                "payload": {
                    "student_pseudonym": str(student_id),
                    "problema_id": str(problema_id),
                    "comision_id": str(comision_id),
                    "curso_config_hash": "c" * 64,
                    "model": "claude-haiku-test",
                },
                "prompt_system_hash": PROMPT_HASH,
                "prompt_system_version": "v1.0.0",
                "classifier_config_hash": "b" * 64,
            }
        ],
    }


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def fake_ctr() -> _FakeCTR:
    return _FakeCTR()


@pytest.fixture
def tutor(redis_client, fake_ctr) -> TutorCore:
    return TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=_FakeAI(),
        ctr=fake_ctr,
        sessions=SessionManager(redis_client),
    )


@pytest.fixture
def http_client(monkeypatch, tutor: TutorCore):
    from tutor_service import main
    from tutor_service.routes import episodes as episodes_module

    monkeypatch.setattr(episodes_module, "_get_tutor", lambda: tutor)
    yield TestClient(main.app), tutor


def _student_headers(user_id: UUID, tenant_id: UUID, idempotency_key: str | None = None) -> dict:
    headers = {
        "X-User-Id": str(user_id),
        "X-Tenant-Id": str(tenant_id),
        "X-User-Email": "alumno@utn.edu.ar",
        "X-User-Roles": "estudiante",
    }
    if idempotency_key is not None:
        headers[_HEADER_IDEMPOTENCIA] = idempotency_key
    return headers


def _body() -> dict:
    """Corrida real de Pyodide: 3 públicos, todos pasando."""
    return {
        "test_count_total": 3,
        "test_count_passed": 3,
        "test_count_failed": 0,
        "tests_publicos": 3,
        "tests_hidden": 0,
        "ejecucion_ms": 412,
    }


async def _abrir(tutor: TutorCore, fake_ctr: _FakeCTR, tenant_id: UUID, student_id: UUID) -> UUID:
    """Abre el episodio de verdad y lo registra en el CTR fake.

    El registro importa: sin él, el heal recibe `None` de `get_episode` y
    contesta 404 en vez de sanar.
    """
    episode_id = await tutor.open_episode(
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=student_id,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    fake_ctr.episodes[str(episode_id)] = _episodio_persistido(episode_id, tenant_id, student_id)
    return episode_id


# ── 1. El acoplamiento con los mensajes que el core produce de verdad ──


async def _mensaje_del_core(tutor: TutorCore, episode_id: UUID, **kwargs: Any) -> str:
    """Corre `emit_tests_ejecutados` esperando que falle y devuelve SU mensaje.

    Toda la gracia del bloque está acá: el string no lo escribo yo.
    """
    with pytest.raises(ValueError) as e:
        await tutor.emit_tests_ejecutados(episode_id=episode_id, user_id=uuid4(), **kwargs)
    return str(e.value)


class TestLaClasificacionSigueAlCore:
    async def test_los_conteos_inconsistentes_del_core_son_rechazo_de_payload(
        self, tutor: TutorCore, fake_ctr: _FakeCTR
    ) -> None:
        """`passed + failed != total` — el primero de los dos guards de 422."""
        episode_id = await _abrir(tutor, fake_ctr, uuid4(), uuid4())
        msg = await _mensaje_del_core(
            tutor,
            episode_id,
            test_count_total=3,
            test_count_passed=1,
            test_count_failed=0,
            tests_publicos=3,
            tests_hidden=0,
            ejecucion_ms=100,
        )
        assert _es_rechazo_de_payload(msg), (
            f"el core cambió el mensaje y el clasificador quedó atrás: {msg!r}. "
            "Ese payload inválido ahora responde 409 y dispara un resume_episode inútil."
        )

    async def test_los_ocultos_desde_el_browser_son_rechazo_de_payload(
        self, tutor: TutorCore, fake_ctr: _FakeCTR
    ) -> None:
        """`tests_hidden != 0` sin emisor interno — el segundo guard de 422."""
        episode_id = await _abrir(tutor, fake_ctr, uuid4(), uuid4())
        msg = await _mensaje_del_core(
            tutor,
            episode_id,
            test_count_total=3,
            test_count_passed=2,
            test_count_failed=1,
            tests_publicos=2,
            tests_hidden=1,
            ejecucion_ms=100,
        )
        assert _es_rechazo_de_payload(msg), (
            f"el core cambió el mensaje y el clasificador quedó atrás: {msg!r}"
        )

    async def test_la_sesion_ausente_del_core_NO_es_rechazo_de_payload(
        self, tutor: TutorCore, fake_ctr: _FakeCTR
    ) -> None:
        """La otra mitad, la que hace que el test no sea vacuo.

        Sin esta, un `_es_rechazo_de_payload` que devuelva siempre `True`
        pasaría los dos de arriba. Y el costo de confundirse acá es el bug que
        el heal vino a arreglar: la sesión ausente clasificada como 422 no
        gatilla el heal y el `tests_ejecutados` se pierde.
        """
        episode_id = await _abrir(tutor, fake_ctr, uuid4(), uuid4())
        await tutor.sessions.delete(episode_id)  # TTL vencido
        msg = await _mensaje_del_core(
            tutor,
            episode_id,
            test_count_total=3,
            test_count_passed=3,
            test_count_failed=0,
            tests_publicos=3,
            tests_hidden=0,
            ejecucion_ms=100,
        )
        assert not _es_rechazo_de_payload(msg), (
            f"la sesión ausente se está clasificando como payload inválido: {msg!r}. "
            "Con eso el heal nunca corre y el evento se pierde."
        )

    async def test_los_tres_mensajes_del_core_son_distinguibles_entre_si(
        self, tutor: TutorCore, fake_ctr: _FakeCTR
    ) -> None:
        """Cierra el triángulo: los dos de 422 y el de 409 salen del MISMO
        `ValueError`, así que lo único que los separa es el texto. Si el core
        unificara los mensajes, este test cae antes que ninguno."""
        episode_id = await _abrir(tutor, fake_ctr, uuid4(), uuid4())
        conteos = await _mensaje_del_core(
            tutor,
            episode_id,
            test_count_total=3,
            test_count_passed=1,
            test_count_failed=0,
            tests_publicos=3,
            tests_hidden=0,
            ejecucion_ms=100,
        )
        ocultos = await _mensaje_del_core(
            tutor,
            episode_id,
            test_count_total=3,
            test_count_passed=2,
            test_count_failed=1,
            tests_publicos=2,
            tests_hidden=1,
            ejecucion_ms=100,
        )
        await tutor.sessions.delete(episode_id)
        sin_sesion = await _mensaje_del_core(
            tutor,
            episode_id,
            test_count_total=3,
            test_count_passed=3,
            test_count_failed=0,
            tests_publicos=3,
            tests_hidden=0,
            ejecucion_ms=100,
        )
        assert len({conteos, ocultos, sin_sesion}) == 3
        assert [_es_rechazo_de_payload(m) for m in (conteos, ocultos, sin_sesion)] == [
            True,
            True,
            False,
        ]


# ── 2. Los bordes del heal ─────────────────────────────────────────────


class TestSesionVencidaConEpisodioVivo:
    async def test_emite_202_y_exactamente_un_evento(self, http_client, fake_ctr: _FakeCTR) -> None:
        """El bug: al alumno se le venció el TTL justo al correr los tests.

        Antes esto era 409, el `ctr-client` lo descartaba (un 4xx que no sea
        408/429 no se reintenta) y el `tests_ejecutados` se perdía — y de ese
        evento el labeler v1.2.0 deriva N3 vs N4.

        "Exactamente un evento" no es decoración: el heal reintenta el emit
        después del `resume_episode`, así que un heal mal compuesto emitiría
        dos veces y el labeler contaría dos corridas donde hubo una.
        """
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)
        await tutor.sessions.delete(episode_id)

        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=_body(),
            headers=_student_headers(student_id, tenant_id),
        )

        assert r.status_code == 202, r.text
        tipos = [ev["event_type"] for ev in fake_ctr.published_events]
        assert tipos.count("tests_ejecutados") == 1, f"el heal emitió de más: {tipos}"

    async def test_con_idempotency_key_tampoco_duplica(
        self, http_client, fake_ctr: _FakeCTR
    ) -> None:
        """El heal compone con la idempotencia, que es donde podía romperse.

        `_emitir_con_heal` reenvía la clave tal cual (prefijo `tests:`
        incluido) y `reserve_or_get_seq` libera el claim con HDEL cuando el
        emit falla. Si NO lo liberara, el reintento post-heal encontraría el
        claim tomado y devolvería el seq fantasma sin emitir nada; si lo
        liberara pero el heal usara otra clave, emitiría dos veces. Dos POST
        con la misma key tienen que dejar UN evento y el MISMO seq.
        """
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)
        await tutor.sessions.delete(episode_id)
        headers = _student_headers(student_id, tenant_id, str(uuid4()))

        r1 = client.post(f"/api/v1/episodes/{episode_id}/run-tests", json=_body(), headers=headers)
        r2 = client.post(f"/api/v1/episodes/{episode_id}/run-tests", json=_body(), headers=headers)

        assert r1.status_code == 202, r1.text
        assert r2.status_code == 202, r2.text
        assert r1.json()["seq"] == r2.json()["seq"]
        tipos = [ev["event_type"] for ev in fake_ctr.published_events]
        assert tipos.count("tests_ejecutados") == 1, f"el reintento duplicó la corrida: {tipos}"


class TestLoQueElHealNoTapa:
    async def test_episodio_cerrado_sigue_siendo_409(self, http_client, fake_ctr: _FakeCTR) -> None:
        """El heal separa "sesión ausente pero episodio vivo" (recuperable) de
        "episodio cerrado" (definitivo). El segundo no se sana: `resume_episode`
        rechaza el estado y su 409 es la respuesta."""
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)
        fake_ctr.episodes[str(episode_id)]["estado"] = "closed"
        await tutor.sessions.delete(episode_id)

        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=_body(),
            headers=_student_headers(student_id, tenant_id),
        )

        assert r.status_code == 409, r.text
        tipos = [ev["event_type"] for ev in fake_ctr.published_events]
        assert "tests_ejecutados" not in tipos

    async def test_episodio_de_otro_alumno_es_403(self, http_client, fake_ctr: _FakeCTR) -> None:
        """El heal reconstruye una sesión: sin el gate de dueño de
        `resume_episode`, cualquiera con el `episode_id` podría hacerla
        reconstruir y meterle un `tests_ejecutados` a la cadena de otro. El 403
        es más preciso que el 409 genérico y sale del propio `resume_episode`.
        """
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)
        await tutor.sessions.delete(episode_id)

        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=_body(),
            headers=_student_headers(uuid4(), tenant_id),  # otro alumno
        )

        assert r.status_code == 403, r.text
        assert await tutor.sessions.get(episode_id) is None
        tipos = [ev["event_type"] for ev in fake_ctr.published_events]
        assert "tests_ejecutados" not in tipos

    async def test_episodio_inexistente_es_404(self, http_client, fake_ctr: _FakeCTR) -> None:
        """Sin sesión y sin episodio en el CTR no hay nada que sanar."""
        client, _tutor = http_client
        r = client.post(
            f"/api/v1/episodes/{uuid4()}/run-tests",
            json=_body(),
            headers=_student_headers(uuid4(), uuid4()),
        )
        assert r.status_code == 404, r.text


class TestElPayloadInvalidoNoGatillaElHeal:
    async def test_conteos_inconsistentes_con_sesion_viva_son_422_sin_resume(
        self, http_client, fake_ctr: _FakeCTR, monkeypatch
    ) -> None:
        """El 422 tiene que salir de `_emitir_tests` ANTES de que el
        `ValueError` llegue a `_emitir_con_heal`.

        Espiar `resume_episode` es la parte que hace este test no-vacuo: si la
        traducción a `HTTPException` se moviera al `except` del handler, el
        código de respuesta seguiría siendo 422 —el test pasaría igual— pero
        el heal habría corrido primero, reconstruyendo una sesión por un
        payload que nunca iba a entrar. Y sobre un episodio cerrado ese
        `resume_episode` devuelve 409 y TAPA el 422 que corresponde.
        """
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)

        llamadas: list[UUID] = []
        original = tutor.resume_episode

        async def _espia(*, episode_id: UUID, tenant_id: UUID, user_id: UUID):
            llamadas.append(episode_id)
            return await original(episode_id=episode_id, tenant_id=tenant_id, user_id=user_id)

        monkeypatch.setattr(tutor, "resume_episode", _espia)

        malo = _body() | {"test_count_passed": 1}  # 1 + 0 != 3
        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=malo,
            headers=_student_headers(student_id, tenant_id),
        )

        assert r.status_code == 422, r.text
        assert "Conteos inconsistentes" in r.json()["detail"]
        assert llamadas == [], "el payload inválido gatilló el heal"

    async def test_ocultos_desde_el_browser_con_sesion_viva_son_422_sin_resume(
        self, http_client, fake_ctr: _FakeCTR, monkeypatch
    ) -> None:
        """El otro motivo de 422. Un browser no puede reportar casos ocultos:
        el academic-service no se los manda, así que `tests_hidden > 0` desde
        el cliente es un cliente mintiendo — y sanarle la sesión no lo
        convierte en válido."""
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)

        llamadas: list[UUID] = []

        async def _espia(*, episode_id: UUID, tenant_id: UUID, user_id: UUID):
            llamadas.append(episode_id)
            raise AssertionError("el heal no debería correr")

        monkeypatch.setattr(tutor, "resume_episode", _espia)

        malo = _body() | {"test_count_passed": 2, "test_count_failed": 1, "tests_hidden": 1}
        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=malo,
            headers=_student_headers(student_id, tenant_id),
        )

        assert r.status_code == 422, r.text
        assert "tests_hidden" in r.json()["detail"]
        assert llamadas == [], "el payload inválido gatilló el heal"


class TestElPayloadInvalidoConSesionVencida:
    """El hueco que los dos tests de arriba no cubrían: sesión AUSENTE.

    Los guards del payload corrían DESPUÉS del de la sesión, así que con la
    sesión vencida el `ValueError` que salía era el de la SESIÓN.
    `_es_rechazo_de_payload` no lo matchea, `_emitir_con_heal` lo leía como
    "sesión ausente" y arrancaba el heal — por un body que nunca iba a entrar.

    Dos daños, y el caro no es el costo:

    (a) **El 409 tapaba al 422.** Es textualmente el escenario que el docstring
        del endpoint declara evitado ("sobre un episodio cerrado el
        `resume_episode` del heal devolvería 409 tapando el 422 que
        corresponde"). El código hacía exactamente lo que su comentario decía
        que no hacía.

    (b) **Un evento espúreo en la cadena append-only.** La sesión resucitada
        (TTL 6h) refresca `last_activity_at`, así que el `abandonment_worker`
        la barre 30 min después y emite `episodio_abandonado`. Eso rompe la
        idempotencia del ADR-025, que está fundada en el estado de sesión ("la
        primera emisión borra la sesión; la segunda encuentra `session=None` y
        no emite"): el heal recrea la sesión y desarma el guard. Un episodio ya
        abandonado recibía un SEGUNDO `episodio_abandonado`, disparado por un
        payload malformado.

    El fix es de orden, no de lógica: los guards del payload son las únicas dos
    validaciones que no dependen de estado, así que van primero. Un payload
    inconsistente es 422 siempre, exista o no la sesión.
    """

    async def test_episodio_abierto_con_sesion_vencida_es_422_y_no_resucita(
        self, http_client, fake_ctr: _FakeCTR, monkeypatch
    ) -> None:
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)
        await tutor.sessions.delete(episode_id)  # TTL vencido

        llamadas: list[UUID] = []
        original = tutor.resume_episode

        async def _espia(*, episode_id: UUID, tenant_id: UUID, user_id: UUID):
            llamadas.append(episode_id)
            return await original(episode_id=episode_id, tenant_id=tenant_id, user_id=user_id)

        monkeypatch.setattr(tutor, "resume_episode", _espia)

        malo = _body() | {"test_count_passed": 99}  # 99 + 0 != 3
        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=malo,
            headers=_student_headers(student_id, tenant_id),
        )

        assert r.status_code == 422, r.text
        assert "Conteos inconsistentes" in r.json()["detail"]
        assert llamadas == [], "el payload inválido con sesión vencida gatilló el heal"
        assert await tutor.sessions.get(episode_id) is None, (
            "la sesión quedó resucitada con TTL 6h por un request que terminó en 422; "
            "el abandonment_worker la va a barrer y va a emitir un episodio_abandonado "
            "de más en una cadena append-only (ADR-025)"
        )

    async def test_episodio_cerrado_con_payload_invalido_es_422_y_no_409(
        self, http_client, fake_ctr: _FakeCTR
    ) -> None:
        """El caso (a): el 409 del heal tapaba el 422 que le corresponde al body.

        Comparado contra su gemelo `test_episodio_cerrado_sigue_siendo_409`,
        que fija la otra mitad: con el payload VÁLIDO el 409 sigue siendo la
        respuesta correcta. Los dos juntos son lo que dice que el fix separa
        por el motivo real, y no que simplemente cambió todos los códigos.
        """
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)
        fake_ctr.episodes[str(episode_id)]["estado"] = "closed"
        await tutor.sessions.delete(episode_id)

        malo = _body() | {"test_count_passed": 99}
        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=malo,
            headers=_student_headers(student_id, tenant_id),
        )

        assert r.status_code == 422, (
            f"el episodio cerrado tapó el rechazo del body con un 409: {r.text}"
        )
        assert "Conteos inconsistentes" in r.json()["detail"]
        tipos = [ev["event_type"] for ev in fake_ctr.published_events]
        assert "tests_ejecutados" not in tipos

    async def test_el_payload_valido_con_sesion_vencida_SIGUE_sanando(
        self, http_client, fake_ctr: _FakeCTR
    ) -> None:
        """La otra mitad del fix: el heal legítimo no se tocó.

        Sin esto, adelantar los guards del payload podría haber cortado el
        camino que el heal vino a arreglar —sesión vencida, episodio vivo,
        alumno trabajando— y el `tests_ejecutados` volvería a perderse.
        """
        client, tutor = http_client
        tenant_id, student_id = uuid4(), uuid4()
        episode_id = await _abrir(tutor, fake_ctr, tenant_id, student_id)
        await tutor.sessions.delete(episode_id)

        r = client.post(
            f"/api/v1/episodes/{episode_id}/run-tests",
            json=_body(),
            headers=_student_headers(student_id, tenant_id),
        )

        assert r.status_code == 202, r.text
        tipos = [ev["event_type"] for ev in fake_ctr.published_events]
        assert tipos.count("tests_ejecutados") == 1
