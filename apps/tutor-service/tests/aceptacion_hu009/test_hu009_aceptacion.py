"""Aceptacion HU-009, lado tutor (orquestador, antes de construir; el
constructor no la modifica).

Sale de la prueba 2 como alumno en produccion (20/11/2026). Juani levanto,
para esta historia, la regla de prompts intactos: "los promts podes tocarlos
tranquilo". Va como version nueva; las anteriores no cambian.

C06  El contexto del tutor no trae la entrada ni la salida esperada de ningun
     caso oculto (el tutor dio 250 km / 8 l, los datos del oculto del ej13).
N04  Los casos publicos siguen llegando completos.
C07  Despues de Probar, el proximo turno del tutor recibe el resultado, y se
     reemplaza en cada Probar (no se acumula).
C08  Tutor v1.11.0 activo, con las reglas nuevas.
N03  Las versiones anteriores del prompt no cambian ni un byte.

Limite conocido (igual que el resto de los tests de prompt del repo): C08 ancla
frases; prueba que la regla esta escrita, no que el modelo la cumpla. Eso se ve
en la demo, repitiendo en produccion los ej2, ej4, ej13 y ej17.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
import yaml
from tutor_service.services.clients import PromptConfig, RetrievalResult
from tutor_service.services.session import SessionManager
from tutor_service.services.tutor_core import TutorCore

RAIZ = Path(__file__).resolve().parents[4]
PROMPTS = RAIZ / "ai-native-prompts/prompts/tutor"
VERSION = "v1.11.0"

OCULTO_ENTRADA = "250\n8"
OCULTO_SALIDA = "Consumo: 20.00 litros"
PUBLICO_ENTRADA = "100\n5"
PUBLICO_SALIDA = "Consumo: 5.00 litros"


def _ejercicio() -> dict:
    return {
        "titulo": "Viaje en auto",
        "enunciado_md": "Calcula los litros que consume un viaje.",
        "test_cases": [
            {
                "id": "p1",
                "name": "caso del enunciado",
                "type": "stdin_stdout",
                "code": PUBLICO_ENTRADA,
                "expected": PUBLICO_SALIDA,
                "is_public": True,
            },
            {
                "id": "o1",
                "name": "viaje largo",
                "type": "stdin_stdout",
                "code": OCULTO_ENTRADA,
                "expected": OCULTO_SALIDA,
                "is_public": False,
            },
        ],
    }


class _Gov:
    async def get_prompt(self, name: str, version: str) -> PromptConfig:
        return PromptConfig(name=name, version=version, content="Tutor.", hash="a" * 64)


class _Content:
    async def retrieve(self, **kw: Any) -> RetrievalResult:
        return RetrievalResult(chunks=[], chunks_used_hash="0" * 64, latency_ms=1.0)


class _AI:
    def __init__(self) -> None:
        self.last_messages: list[dict] = []

    async def stream(self, messages: list[dict], **kw: Any):
        self.last_messages = messages
        yield {"type": "chunk", "content": "ok"}


class _CTR:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish_event(self, event: dict, tenant_id: UUID, caller_id: UUID) -> str:
        self.published.append(event)
        return "id"

    async def find_open_episode(self, **kw: Any) -> None:
        return None


@pytest.fixture
async def redis():
    c = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield c
    await c.aclose()


@pytest.fixture
def ai() -> _AI:
    return _AI()


@pytest.fixture
def tutor(redis, ai) -> TutorCore:
    return TutorCore(
        governance=_Gov(),
        content=_Content(),
        ai_gateway=ai,
        ctr=_CTR(),
        sessions=SessionManager(redis),
    )


# ── C06 / N04 ───────────────────────────────────────────────────────────────
def test_c06_el_contexto_no_trae_los_datos_del_caso_oculto(tutor: TutorCore) -> None:
    ctx = tutor._build_ejercicio_context(_ejercicio(), 13)
    assert "250" not in ctx, ctx
    assert OCULTO_SALIDA not in ctx and "20.00" not in ctx, ctx


def test_n04_los_casos_publicos_siguen_completos(tutor: TutorCore) -> None:
    ctx = tutor._build_ejercicio_context(_ejercicio(), 13)
    assert "100" in ctx and PUBLICO_SALIDA in ctx, ctx


# ── C07: el tutor ve Probar ─────────────────────────────────────────────────
async def _abrir(tutor: TutorCore) -> tuple[UUID, UUID]:
    student = uuid4()
    ep = await tutor.open_episode(
        tenant_id=uuid4(),
        comision_id=uuid4(),
        student_pseudonym=student,
        problema_id=uuid4(),
        curso_config_hash="c" * 64,
        classifier_config_hash="b" * 64,
    )
    return ep, student


async def _turno(tutor: TutorCore, ep: UUID, texto: str) -> None:
    async for _ in tutor.interact(ep, texto):
        pass


async def _probar(tutor: TutorCore, ep: UUID, student: UUID, total: int, passed: int) -> None:
    await tutor.emit_tests_ejecutados(
        episode_id=ep,
        user_id=student,
        test_count_total=total,
        test_count_passed=passed,
        test_count_failed=total - passed,
        tests_publicos=total,
        tests_hidden=0,
        ejecucion_ms=10,
    )


def _bloques_probar(msgs: list[dict]) -> list[str]:
    return [
        m["content"]
        for m in msgs
        if m["role"] == "system"
        and re.search(r"probar", m["content"], re.IGNORECASE)
        and re.search(r"\d+ de \d+", m["content"])
    ]


async def test_c07_el_turno_siguiente_a_probar_trae_el_resultado(tutor: TutorCore, ai: _AI) -> None:
    ep, student = await _abrir(tutor)
    await _probar(tutor, ep, student, total=2, passed=2)
    await _turno(tutor, ep, "pasó la prueba, ¿ya está?")
    bloques = _bloques_probar(ai.last_messages)
    assert len(bloques) == 1, ai.last_messages
    assert "2 de 2" in bloques[0], bloques[0]


async def test_c07_cada_probar_reemplaza_al_anterior(tutor: TutorCore, ai: _AI) -> None:
    ep, student = await _abrir(tutor)
    await _probar(tutor, ep, student, total=2, passed=1)
    await _turno(tutor, ep, "falla uno")
    primero = _bloques_probar(ai.last_messages)
    assert len(primero) == 1, ai.last_messages
    assert "1 de 2" in primero[0], primero[0]
    await _probar(tutor, ep, student, total=2, passed=2)
    await _turno(tutor, ep, "ahora sí")
    bloques = _bloques_probar(ai.last_messages)
    assert len(bloques) == 1, bloques
    assert "2 de 2" in bloques[0], bloques[0]


async def test_c07_sin_probar_no_aparece_el_bloque(tutor: TutorCore, ai: _AI) -> None:
    ep, _ = await _abrir(tutor)
    await _turno(tutor, ep, "hola")
    assert _bloques_probar(ai.last_messages) == []


# ── C08: prompt v1.11.0 activo ──────────────────────────────────────────────
def _plano(t: str) -> str:
    return re.sub(r"\s+", " ", t).lower()


def _prompt() -> str:
    ruta = PROMPTS / VERSION / "system.md"
    if not ruta.exists():
        pytest.fail(f"falta {ruta}")
    return _plano(ruta.read_text(encoding="utf-8"))


def test_c08_version_activa_alineada() -> None:
    from tutor_service.config import Settings

    assert Settings().default_prompt_version == VERSION
    raiz = yaml.safe_load((RAIZ / "ai-native-prompts/manifest.yaml").read_text())
    assert raiz["active"]["default"]["tutor"] == VERSION
    man = yaml.safe_load((PROMPTS / VERSION / "manifest.yaml").read_text())
    sha = hashlib.sha256((PROMPTS / VERSION / "system.md").read_bytes()).hexdigest()
    assert man["files"]["system.md"] == sha
    assert man["parent_version"] == "v1.10.0"


@pytest.mark.parametrize(
    ("regla", "patrones"),
    [
        # ej17: "¡Claro que me acuerdo!" con recuerdos inventados.
        ("no finge recordar otros ejercicios", [r"otros? ejercicios?", r"(record|acord|memoria)"]),
        # ej4 y ej11: insiste con errores que no hay con 2/2 en Probar.
        (
            "no inventa errores si Probar paso todo",
            [r"probar", r"(pasa|pasaron|pas[oó])", r"invent"],
        ),
        # ej8: recomienda pegar el "²" con pegar bloqueado.
        ("nunca sugiere pegar y explica como tipear", [r"pegar", r"teclado"]),
        # ej2: dicta la linea exacta de la solucion.
        ("no dicta la linea de la solucion", [r"l[ií]nea", r"soluci[oó]n"]),
        # ej6: no ve el resultado escrito a mano.
        ("senala el resultado escrito a mano", [r"(a mano|hardcode|literal)"]),
    ],
)
def test_c08_reglas_nuevas_escritas(regla: str, patrones: list[str]) -> None:
    texto = _prompt()
    parrafos = re.split(r"(?<=[.:])\s", texto)
    ventana = [" ".join(parrafos[i : i + 3]) for i in range(len(parrafos))]
    assert any(all(re.search(p, v) for p in patrones) for v in ventana), regla


def test_c08_es_una_version_nueva_y_no_una_copia() -> None:
    ruta = PROMPTS / VERSION / "system.md"
    assert ruta.exists(), f"falta {ruta}"
    nuevo = ruta.read_bytes()
    viejo = (PROMPTS / "v1.10.0" / "system.md").read_bytes()
    assert nuevo != viejo


# ── N03: lo anterior intacto ────────────────────────────────────────────────
def _huella(raiz: Path, excluir: str) -> str:
    h = hashlib.sha256()
    for f in sorted(raiz.rglob("*")):
        rel = f.relative_to(raiz)
        if f.is_file() and rel.parts[0] != excluir:
            h.update(str(rel).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def test_n03_versiones_anteriores_del_tutor_intactas() -> None:
    assert _huella(PROMPTS, VERSION) == (
        "d862193c219a9f45bceb3cfcdc42e2441c6327d2c5d5cf11a15ea8102c0dc595"
    )


def test_n03_f15_intacto() -> None:
    f15 = RAIZ / "apps/evaluation-service/src/evaluation_service/services/correccion_nativa.py"
    assert hashlib.sha256(f15.read_bytes()).hexdigest() == (
        "bf5463c59f9df30e1aa2eaa45f2da70bbaa6e7663d4e6fd91a5cb064af3d5745"
    )
