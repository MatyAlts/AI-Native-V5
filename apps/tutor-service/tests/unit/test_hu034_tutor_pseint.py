"""Aceptacion HU-034 (orquestador, antes de construir; el constructor no la
modifica). Juani (24/11): "el tutor debe saber que es el ejercicio de pseint, y
ser mas didactico con este lenguaje".

El prompt del tutor NO se toca (coautoria Ana Garis, intacto byte a byte): la
guia de PSeInt se agrega en el contexto del ejercicio que arma
`TutorCore._build_ejercicio_context`, igual que `tutor_rules` o el banco
socratico (ADR-048), y SOLO para ejercicios y TPs en PSeInt.

C01  En un ejercicio PSeInt el contexto dice que el lenguaje es PSeInt, aunque
     no tenga codigo inicial. Tambien en una TP monolitica en PSeInt.
C02  La guia es didactica y especifica de PSeInt: responder con la sintaxis de
     PSeInt y nunca con la de Python u otro lenguaje; las reglas del perfil que
     mas confunden (asignacion con <-, arreglos desde 1 con Dimension, Y/O/NO
     son operadores, Definir ... Como); vocabulario en castellano de PSeInt; y
     las herramientas que el alumno tiene: Paso a paso / prueba de escritorio
     y la pestaña Diagrama, y que los errores dicen la linea.
C03  La guia esta versionada: `CONTEXTO_PSEINT_VERSION` (semver) vive junto al
     texto, para que un cambio de la guia quede trazable.
N01  Python, Java y un ejercicio sin lenguaje arman EXACTAMENTE el mismo
     contexto que antes (huellas tomadas de feat/hu-030-pseint, ad4e280).
N02  La guia aparece una sola vez y el prompt del tutor sigue intacto (la
     huella de los prompts la fija test_hu030_despliegue.py).
"""

from __future__ import annotations

import hashlib
import re
from unittest.mock import MagicMock

from tutor_service.services import tutor_core
from tutor_service.services.tutor_core import TutorCore

EJ = {
    "titulo": "Doble",
    "enunciado_md": "Lee un numero y escribi el doble.",
    "inicial_codigo": "n = int(input())",
    "language": "python",
    "tutor_rules": {"prohibido_dar_solucion": True},
    "test_cases": [
        {
            "id": "t1",
            "name": "caso 1",
            "type": "stdin_stdout",
            "code": "3",
            "expected": "6",
            "is_public": True,
            "weight": 1,
        }
    ],
}

# Huellas sha256 del contexto en feat/hu-030-pseint (ad4e280), antes de HU-034.
HUELLAS = {
    "python": "10400040f3ee66a16ecfd7bab7be7c4a59ff4b2b2ccd0db31b8951ed797244c1",
    "java": "cfef60395f5d1028374b415ebb49146263e49aa1537028f350cf0a6a3dd35359",
    "sin_language": "10400040f3ee66a16ecfd7bab7be7c4a59ff4b2b2ccd0db31b8951ed797244c1",
    "tp_python": "3df82ea68151c897832c3c0e9559c2d20c7e7d608889bf51180bac311a233e38",
}


def _tutor() -> TutorCore:
    return TutorCore(
        governance=MagicMock(),
        content=MagicMock(),
        ai_gateway=MagicMock(),
        ctr=MagicMock(),
        sessions=MagicMock(),
        academic=None,
        default_prompt_version="v1.0.0",
        default_model="m",
    )


def _ctx(ej: dict, kind: str = "Ejercicio") -> str:
    return _tutor()._build_ejercicio_context(ej, 1 if kind == "Ejercicio" else None, kind=kind)


def _pseint(**extra) -> dict:
    base = {
        **EJ,
        "language": "pseint",
        "inicial_codigo": None,
        "enunciado_md": "Lee un numero y escribi el doble en PSeInt.",
    }
    return {**base, **extra}


# ── C01 ────────────────────────────────────────────────────────────────


def test_c01_sin_codigo_inicial_igual_dice_pseint() -> None:
    ctx = _ctx(_pseint())
    assert "PSeInt" in ctx
    assert re.search(r"lenguaje[^\n]{0,40}PSeInt", ctx, re.IGNORECASE), ctx


def test_c01_tp_monolitica_en_pseint() -> None:
    ctx = _ctx(
        {"titulo": "TP 1", "enunciado": "Hace el TP.", "language": "pseint"},
        kind="Trabajo Práctico",
    )
    assert re.search(r"lenguaje[^\n]{0,40}PSeInt", ctx, re.IGNORECASE), ctx


# ── C02 ────────────────────────────────────────────────────────────────


def test_c02_pide_sintaxis_de_pseint_y_no_de_otro_lenguaje() -> None:
    ctx = _ctx(_pseint())
    assert "Python" in ctx, "la guia tiene que decir explicitamente que no use Python"
    assert re.search(r"(nunca|no) .{0,60}(Python|otro lenguaje)", ctx, re.IGNORECASE)


def test_c02_reglas_del_perfil_que_mas_confunden() -> None:
    ctx = _ctx(_pseint())
    assert "<-" in ctx
    assert "Dimension" in ctx
    assert re.search(r"desde 1|empiezan en 1|base 1", ctx, re.IGNORECASE)
    assert re.search(r"\bY\b.{0,20}\bO\b", ctx), "Y / O como operadores reservados"
    assert re.search(r"Definir .{0,10}Como", ctx)


def test_c02_vocabulario_de_pseint() -> None:
    ctx = _ctx(_pseint())
    for palabra in ("Leer", "Escribir", "Si", "Mientras", "Para"):
        assert re.search(rf"\b{palabra}\b", ctx), palabra


def test_c02_herramientas_del_alumno() -> None:
    ctx = _ctx(_pseint())
    assert re.search(r"paso a paso", ctx, re.IGNORECASE)
    assert re.search(r"prueba de escritorio", ctx, re.IGNORECASE)
    assert re.search(r"diagrama", ctx, re.IGNORECASE)
    assert re.search(r"l[ií]nea", ctx, re.IGNORECASE), "los errores dicen la linea"


# ── C03 ────────────────────────────────────────────────────────────────


def test_c03_guia_versionada() -> None:
    version = getattr(tutor_core, "CONTEXTO_PSEINT_VERSION", None)
    assert isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version), version


# ── N01 / N02 ──────────────────────────────────────────────────────────


def test_n01_python_java_y_sin_lenguaje_no_cambian() -> None:
    casos = {
        "python": _ctx(EJ),
        "java": _ctx({**EJ, "language": "java", "inicial_codigo": "class Main {}"}),
        "sin_language": _ctx({k: v for k, v in EJ.items() if k != "language"}),
        "tp_python": _ctx(
            {"titulo": "TP 1", "enunciado": "Hace el TP.", "language": "python"},
            kind="Trabajo Práctico",
        ),
    }
    for nombre, ctx in casos.items():
        assert "PSeInt" not in ctx, nombre
        assert hashlib.sha256(ctx.encode()).hexdigest() == HUELLAS[nombre], nombre


def test_n02_la_guia_aparece_una_sola_vez() -> None:
    ctx = _ctx(_pseint(inicial_codigo="Algoritmo doble\nFinAlgoritmo"))
    assert len(re.findall(r"lenguaje[^\n]{0,40}PSeInt", ctx, re.IGNORECASE)) == 1
    # El codigo inicial sigue rotulado como pseint (HU-030).
    assert "```pseint" in ctx
