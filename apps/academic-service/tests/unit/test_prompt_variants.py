"""Tests de la resolucion de variante de prompt por lenguaje (epic java-authoring-experience).

Dos garantias:
  1. El lenguaje por omision NO cambia de nombre de familia — el docente que
     genera en el lenguaje preexistente obtiene el mismo prompt que antes.
  2. Cada variante declarada tiene su `system.md` en disco y esta listada en el
     manifest global. Una familia sin archivo hace fallar la generacion en
     runtime con un 502 que no dice por que.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from academic_service.services.prompt_variants import resolve_prompt_name
from platform_contracts.academic.ejercicio import DEFAULT_LANGUAGE

BASE_NAMES = ("ejercicio_generator", "tp_generator")


def _repo_root() -> Path:
    # apps/academic-service/tests/unit/<este archivo> -> 4 niveles hasta la raiz.
    return Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("base", BASE_NAMES)
def test_lenguaje_default_conserva_el_nombre_historico(base: str) -> None:
    """Escenario «la generacion en el lenguaje preexistente no cambia»."""
    assert resolve_prompt_name(base, DEFAULT_LANGUAGE) == base


@pytest.mark.parametrize("base", BASE_NAMES)
@pytest.mark.parametrize("ausente", [None, ""])
def test_lenguaje_ausente_cae_al_default(base: str, ausente: str | None) -> None:
    """Un caller viejo que no manda lenguaje sigue funcionando igual."""
    assert resolve_prompt_name(base, ausente) == base


@pytest.mark.parametrize("base", BASE_NAMES)
def test_java_resuelve_a_la_variante(base: str) -> None:
    assert resolve_prompt_name(base, "java") == f"{base}_java"


@pytest.mark.parametrize("base", BASE_NAMES)
@pytest.mark.parametrize("language", ["python", "java"])
def test_la_familia_resuelta_existe_en_disco(base: str, language: str) -> None:
    """Toda variante alcanzable desde la API tiene su prompt en el repo.

    Si esto falla, `POST /generate` para ese lenguaje devuelve 502 al no poder
    resolver el prompt — y el docente ve "no se pudo resolver el prompt activo"
    sin ninguna pista de que falta un archivo.
    """
    name = resolve_prompt_name(base, language)
    system_md = _repo_root() / "ai-native-prompts" / "prompts" / name / "v1.0.0" / "system.md"
    assert system_md.exists(), f"falta {system_md}"
    assert system_md.stat().st_size > 0, f"{system_md} esta vacio"


@pytest.mark.parametrize("base", BASE_NAMES)
@pytest.mark.parametrize("language", ["python", "java"])
def test_la_familia_resuelta_esta_en_el_manifest_global(base: str, language: str) -> None:
    """El manifest declara la version activa de cada variante alcanzable."""
    manifest = (_repo_root() / "ai-native-prompts" / "manifest.yaml").read_text(encoding="utf-8")
    name = resolve_prompt_name(base, language)
    assert f"{name}: v1.0.0" in manifest, f"manifest.yaml no declara '{name}'"


def test_la_variante_java_no_pide_el_tipo_de_test_de_python() -> None:
    """`pytest_assert` no debe aparecer como tipo sugerido en los prompts Java.

    El contrato admite los tres tipos y no valida el tipo contra el lenguaje del
    ejercicio (la coherencia es responsabilidad del servicio), asi que si el
    prompt lo sugiere el modelo lo va a emitir — y el caso terminaria corriendo
    contra el runner equivocado.
    """
    for base in BASE_NAMES:
        name = resolve_prompt_name(base, "java")
        content = (
            _repo_root() / "ai-native-prompts" / "prompts" / name / "v1.0.0" / "system.md"
        ).read_text(encoding="utf-8")
        assert "junit_assert" in content, f"{name} no menciona junit_assert"
        # Se admite nombrarlo para PROHIBIRLO explicitamente, no para sugerirlo.
        for linea in content.splitlines():
            if "pytest_assert" not in linea:
                continue
            assert "NUNCA" in linea or "NO " in linea, (
                f"{name} menciona pytest_assert sin prohibirlo: {linea!r}"
            )
