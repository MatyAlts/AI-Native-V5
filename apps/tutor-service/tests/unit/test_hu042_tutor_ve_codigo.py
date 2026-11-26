"""Aceptacion HU-042 (orquestador, antes de construir; el constructor NO la
modifica). El tutor ve el codigo del editor y no lo pide.

Evidencia de produccion (25/11/2026, episodio 2e6315b9, PSeInt): el editor
mando 8 `edicion_codigo` con el codigo, el alumno escribio "mira ya defini las
variables" y el tutor pidio "¿podrias mostrarme como quedaron definidas?" y
despues dijo "No tengo acceso directo a tu editor". El codigo llegaba (bloque
4.quater de `tutor_core.interact`, como mensaje `system`), pero el ai-gateway
concatena todos los `system` al final de un `system_instruction` largo y el
modelo lo ignora. Otro episodio: el tutor sostuvo que en PSeInt "las comas de
Escribir separan con espacio" (falso: `Escribir a, b` los pega, ver
`packages/pseint/PERFIL.md`).

Criterios que fija este archivo (nivel tutor_core, con fakes del ai-gateway,
de sesiones —fakeredis— y del CTR; se recorre open_episode -> edicion_codigo
-> interact, sin atajos sobre el estado):

C01  En cada turno, el ULTIMO mensaje `user` del payload hacia el ai-gateway
     lleva: (a) el texto del alumno tal cual; (b) el `snapshot` del ULTIMO
     `edicion_codigo`, con numero de linea (cada linea del codigo aparece
     precedida por su numero, en orden); (c) una indicacion explicita de que
     el tutor TIENE ese codigo: que no pida que se lo copien/peguen/muestren y
     que no diga que no lo ve o que no tiene acceso. Un snapshot anterior NO
     aparece. Se verifica en dos turnos seguidos (el segundo con codigo nuevo).
N01  El evento CTR `prompt_enviado` lleva en `payload.content` exactamente el
     texto del alumno, sin el codigo (la traza no cambia).
N02  `state.messages` guardado despues del turno tiene el turno del alumno
     con el texto tal cual (sin el bloque de codigo), y en el turno 2 ningun
     mensaje `user` del historial (todos menos el ultimo) arrastra codigo.
C02  En un episodio PSeInt el contexto que recibe el modelo (cualquier mensaje
     del payload) incluye una referencia breve del lenguaje de la plataforma
     que dice, en una misma linea, que `Escribir` con varios valores los pega
     "sin espacio(s)".
N03  En un episodio Python esa referencia NO aparece (ni "Escribir").

Contrato de la indicacion de C01 (regex, insensible a mayusculas, dentro del
ultimo mensaje user):
  - no pedir el codigo:  (no|nunca|jamás) ... (pid|pedi|solicit) ... (cop|peg|mostr|compart|mand|envi)
    dentro de UNA misma oracion (sin . ! ? ni salto de linea entre medio);
  - no decir que no lo ve: (no|nunca|jamás) ... (dig|afirm|respond) ...
    ("no (lo )?ve(s|n)" | "no ten.s acceso" | "sin acceso" | "no pod.s ver"),
    dentro de UNA misma oracion.
  Ejemplo que cumple: "Tenés este código. No le pidas que te lo copie, pegue o
  muestre, y no digas que no lo ves ni que no tenés acceso a su editor."
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from tutor_service.services.academic_client import TareaPracticaResponse
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

PROMPT_HASH = "abc" + "0" * 61

TEXTO_ALUMNO_1 = "mira ya definí las variables"
TEXTO_ALUMNO_2 = "y ahora le agregué la suma, ¿está bien?"

# Snapshot viejo: no tiene que aparecer en el turno (solo cuenta el ULTIMO).
CODIGO_VIEJO = "Algoritmo borrador_xq\nFinAlgoritmo"
CODIGO_1 = (
    "Algoritmo suma_hu042\n"
    "    Definir num_a_hu042, num_b_hu042 Como Entero\n"
    "    Leer num_a_hu042\n"
    "FinAlgoritmo"
)
CODIGO_2 = (
    "Algoritmo suma_hu042\n"
    "    Definir num_a_hu042, num_b_hu042 Como Entero\n"
    "    Leer num_a_hu042, num_b_hu042\n"
    "    total_hu042 <- num_a_hu042 + num_b_hu042\n"
    "FinAlgoritmo"
)

RE_NO_PEDIR = re.compile(
    r"\b(no|nunca|jam[aá]s)\b[^\n.!?]{0,80}?\b(pid|pedi|solicit)\w*[^\n.!?]{0,80}?"
    r"\b(cop|peg|mostr|compart|mand|envi)\w*",
    re.IGNORECASE,
)
RE_NO_DECIR_QUE_NO_VE = re.compile(
    r"\b(no|nunca|jam[aá]s)\b[^\n.!?]{0,60}?\b(dig|afirm|respond)\w*[^\n.!?]{0,120}?"
    r"(no (lo |el c[oó]digo )?ve[sn]?\b|no ten[eé]s acceso|no tiene[sn]? acceso|sin acceso|"
    r"no pod[eé]s ver|no puede[sn]? ver)",
    re.IGNORECASE,
)
RE_ESCRIBIR_SIN_ESPACIO = re.compile(r"\bEscribir\b[^\n]{0,200}?\bsin espacios?\b")


# ── Fakes ─────────────────────────────────────────────────────────────


class _FakeGov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(
            name=name,
            version=version,
            content="Eres un tutor socrático. Guía sin dar la respuesta.",
            hash=PROMPT_HASH,
        )


class _FakeContent:
    async def retrieve(self, **kwargs) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class _FakeAI:
    def __init__(self) -> None:
        self.llamadas: list[list[dict]] = []

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[dict]:
        # Copia profunda superficial: que una mutacion posterior no cambie lo medido.
        self.llamadas.append([dict(m) for m in messages])
        yield {"type": "chunk", "content": "¿Qué valor esperás en total?"}


class _FakeCTR:
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published_events.append(event)
        return f"msg-{len(self.published_events)}"

    async def find_open_episode(self, **kwargs) -> dict | None:
        return None


def _published_tp(comision_id: UUID, tenant_id: UUID) -> TareaPracticaResponse:
    now = datetime.now(UTC)
    return TareaPracticaResponse(
        id=uuid4(),
        tenant_id=tenant_id,
        comision_id=comision_id,
        estado="published",
        fecha_inicio=now - timedelta(hours=1),
        fecha_fin=now + timedelta(hours=1),
    )


class _Escenario:
    def __init__(self, tutor: TutorCore, ai: _FakeAI, ctr: _FakeCTR, sessions: SessionManager):
        self.tutor = tutor
        self.ai = ai
        self.ctr = ctr
        self.sessions = sessions
        self.episode_id: UUID | None = None
        self.alumno = uuid4()

    async def abrir(self, language: str) -> None:
        tenant_id = uuid4()
        comision_id = uuid4()
        tp = _published_tp(comision_id, tenant_id)
        academic = AsyncMock()
        academic.get_tarea_practica.return_value = tp
        academic.get_comision.return_value = None
        academic.get_ejercicio_by_id.return_value = {
            "titulo": "Suma de dos números",
            "enunciado_md": "Leé dos números enteros y mostrá su suma.",
            "language": language,
            "tutor_rules": {"prohibido_dar_solucion": True},
        }
        academic.resolve_ejercicio_orden_in_tp.return_value = 1
        self.tutor.academic = academic
        self.episode_id = await self.tutor.open_episode(
            tenant_id=tenant_id,
            comision_id=comision_id,
            student_pseudonym=self.alumno,
            problema_id=tp.id,
            curso_config_hash="b" * 64,
            classifier_config_hash="c" * 64,
            ejercicio_id=uuid4(),
        )

    async def editar(self, codigo: str, language: str = "pseint") -> None:
        assert self.episode_id is not None
        await self.tutor.record_edicion_codigo(
            episode_id=self.episode_id,
            snapshot=codigo,
            diff_chars=len(codigo),
            language=language,
            user_id=self.alumno,
            origin="student_typed",
        )

    async def preguntar(self, texto: str) -> list[dict]:
        assert self.episode_id is not None
        antes = len(self.ai.llamadas)
        async for _ in self.tutor.interact(self.episode_id, texto):
            pass
        assert len(self.ai.llamadas) == antes + 1, "el turno no llego al ai-gateway"
        return self.ai.llamadas[-1]


@pytest.fixture
def escenario() -> _Escenario:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ai = _FakeAI()
    ctr = _FakeCTR()
    sessions = SessionManager(redis)
    tutor = TutorCore(
        governance=_FakeGov(),
        content=_FakeContent(),
        ai_gateway=ai,
        ctr=ctr,
        sessions=sessions,
        academic=None,
        default_prompt_version="v1.0.0",
        default_model="m",
        rag_enabled=False,
    )
    return _Escenario(tutor, ai, ctr, sessions)


# ── Helpers de aserción ──────────────────────────────────────────────


def _ultimo_user(mensajes: list[dict]) -> str:
    users = [m for m in mensajes if m.get("role") == "user"]
    assert users, f"el payload no tiene ningun mensaje user: {mensajes!r}"
    contenido = users[-1]["content"]
    assert isinstance(contenido, str)
    return contenido


def _afirmar_codigo_numerado(texto: str, codigo: str) -> None:
    """Cada linea del codigo aparece precedida por su numero, en orden."""
    pos = 0
    for n, linea in enumerate(codigo.splitlines(), start=1):
        patron = re.compile(
            rf"(?m)^[ \t]*{n}\b[ \t]*[|:.)\]-]?[ \t]*{re.escape(linea.strip())}[ \t]*$"
        )
        m = patron.search(texto, pos)
        assert m is not None, (
            f"falta la linea {n} numerada ({linea.strip()!r}) despues de la posicion {pos} "
            f"en el ultimo mensaje user:\n{texto}"
        )
        pos = m.end()


def _afirmar_indicacion_tiene_el_codigo(texto: str) -> None:
    assert RE_NO_PEDIR.search(texto), (
        "el ultimo mensaje user no le indica al modelo que NO pida que le copien/peguen/"
        f"muestren el codigo:\n{texto}"
    )
    assert RE_NO_DECIR_QUE_NO_VE.search(texto), (
        "el ultimo mensaje user no le indica al modelo que NO diga que no ve el codigo / "
        f"que no tiene acceso:\n{texto}"
    )


def _prompts_enviados(ctr: _FakeCTR) -> list[dict]:
    return [e for e in ctr.published_events if e["event_type"] == "prompt_enviado"]


# ── C01 ──────────────────────────────────────────────────────────────


async def test_c01_ultimo_user_lleva_texto_codigo_numerado_e_indicacion(escenario) -> None:
    await escenario.abrir("pseint")
    await escenario.editar(CODIGO_VIEJO)
    await escenario.editar(CODIGO_1)

    payload = await escenario.preguntar(TEXTO_ALUMNO_1)
    ultimo = _ultimo_user(payload)

    assert TEXTO_ALUMNO_1 in ultimo, ultimo
    _afirmar_codigo_numerado(ultimo, CODIGO_1)
    _afirmar_indicacion_tiene_el_codigo(ultimo)
    assert "borrador_xq" not in ultimo, "va el ULTIMO snapshot, no uno anterior"


async def test_c01_segundo_turno_lleva_el_codigo_nuevo(escenario) -> None:
    await escenario.abrir("pseint")
    await escenario.editar(CODIGO_1)
    await escenario.preguntar(TEXTO_ALUMNO_1)
    await escenario.editar(CODIGO_2)

    payload = await escenario.preguntar(TEXTO_ALUMNO_2)
    ultimo = _ultimo_user(payload)

    assert TEXTO_ALUMNO_2 in ultimo, ultimo
    _afirmar_codigo_numerado(ultimo, CODIGO_2)
    _afirmar_indicacion_tiene_el_codigo(ultimo)


# ── N01 ──────────────────────────────────────────────────────────────


async def test_n01_prompt_enviado_lleva_solo_el_texto_del_alumno(escenario) -> None:
    await escenario.abrir("pseint")
    await escenario.editar(CODIGO_1)
    await escenario.preguntar(TEXTO_ALUMNO_1)
    await escenario.editar(CODIGO_2)
    await escenario.preguntar(TEXTO_ALUMNO_2)

    prompts = _prompts_enviados(escenario.ctr)
    assert [p["payload"]["content"] for p in prompts] == [TEXTO_ALUMNO_1, TEXTO_ALUMNO_2]


# ── N02 ──────────────────────────────────────────────────────────────


async def test_n02_el_codigo_no_se_acumula_en_el_historial(escenario) -> None:
    await escenario.abrir("pseint")
    await escenario.editar(CODIGO_1)
    await escenario.preguntar(TEXTO_ALUMNO_1)

    state = await escenario.sessions.get(escenario.episode_id)
    assert state is not None
    users = [m["content"] for m in state.messages if m.get("role") == "user"]
    assert users == [TEXTO_ALUMNO_1], users

    await escenario.editar(CODIGO_2)
    payload = await escenario.preguntar(TEXTO_ALUMNO_2)

    state = await escenario.sessions.get(escenario.episode_id)
    assert state is not None
    users = [m["content"] for m in state.messages if m.get("role") == "user"]
    assert users == [TEXTO_ALUMNO_1, TEXTO_ALUMNO_2], users

    # En el payload del turno 2, los user del historial no arrastran codigo.
    historial_users = [m["content"] for m in payload if m.get("role") == "user"][:-1]
    assert historial_users == [TEXTO_ALUMNO_1], historial_users


# ── C02 / N03 ────────────────────────────────────────────────────────


async def test_c02_pseint_referencia_escribir_pega_sin_espacio(escenario) -> None:
    await escenario.abrir("pseint")
    await escenario.editar(CODIGO_1)
    payload = await escenario.preguntar(TEXTO_ALUMNO_1)

    textos = [m["content"] for m in payload]
    assert any(RE_ESCRIBIR_SIN_ESPACIO.search(t) for t in textos), (
        "ningun mensaje del contexto del modelo dice que Escribir con varios valores "
        "los pega sin espacio"
    )


async def test_n03_python_no_lleva_la_referencia_de_pseint(escenario) -> None:
    await escenario.abrir("python")
    await escenario.editar("a = int(input())\nprint(a * 2)", language="python")
    payload = await escenario.preguntar("¿está bien mi print?")

    for m in payload:
        assert not RE_ESCRIBIR_SIN_ESPACIO.search(m["content"]), m["content"]
        assert not re.search(r"\bEscribir\b", m["content"]), m["content"]
