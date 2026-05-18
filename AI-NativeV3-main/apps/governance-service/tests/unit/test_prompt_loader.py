"""Tests del PromptLoader.

El test crítico: si el manifest declara un hash que no coincide con el
contenido real, el loader falla fail-loud. Esta es la defensa contra
manipulación en runtime (ADR-009).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from governance_service.services.prompt_loader import (
    PromptLoader,
    compute_content_hash,
)


def _make_repo(tmp_path: Path, content: str, declared_hash: str | None = None) -> Path:
    """Crea estructura mínima de repo de prompts."""
    prompt_dir = tmp_path / "prompts" / "tutor" / "v1.0.0"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "system.md").write_text(content)

    if declared_hash is not None:
        (prompt_dir / "manifest.yaml").write_text(f"files:\n  system.md: {declared_hash}\n")

    return tmp_path


def test_load_sin_manifest_calcula_hash(tmp_path: Path) -> None:
    content = "Sos un tutor socrático. Guiá al estudiante sin dar la respuesta directa."
    repo = _make_repo(tmp_path, content)

    loader = PromptLoader(repo)
    cfg = loader.load("tutor", "v1.0.0")

    assert cfg.content == content
    assert cfg.hash == compute_content_hash(content)
    assert len(cfg.hash) == 64


def test_load_con_manifest_correcto(tmp_path: Path) -> None:
    content = "prompt de ejemplo"
    h = compute_content_hash(content)
    repo = _make_repo(tmp_path, content, declared_hash=h)

    loader = PromptLoader(repo)
    cfg = loader.load("tutor", "v1.0.0")
    assert cfg.hash == h


def test_load_con_hash_incorrecto_falla(tmp_path: Path) -> None:
    """CRÍTICO: si alguien altera el archivo sin actualizar el manifest,
    el loader detecta el mismatch y se niega a operar."""
    content = "prompt modificado maliciosamente"
    wrong_hash = "a" * 64
    repo = _make_repo(tmp_path, content, declared_hash=wrong_hash)

    loader = PromptLoader(repo)
    with pytest.raises(ValueError) as exc_info:
        loader.load("tutor", "v1.0.0")
    assert "Hash mismatch" in str(exc_info.value)


def test_load_prompt_inexistente_falla(tmp_path: Path) -> None:
    loader = PromptLoader(tmp_path)
    with pytest.raises(FileNotFoundError):
        loader.load("tutor", "v9.9.9")


def test_cache_evita_relectura(tmp_path: Path) -> None:
    content = "x"
    repo = _make_repo(tmp_path, content)
    loader = PromptLoader(repo)

    cfg1 = loader.load("tutor", "v1.0.0")
    cfg2 = loader.load("tutor", "v1.0.0")
    # Mismo objeto → cache hit
    assert cfg1 is cfg2


def test_hash_es_determinista() -> None:
    h1 = compute_content_hash("abc")
    h2 = compute_content_hash("abc")
    assert h1 == h2
    assert compute_content_hash("abc") != compute_content_hash("abd")


def test_active_configs_con_manifest(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text(
        "active:\n"
        "  default:\n"
        "    tutor: v1.0.0\n"
        "    classifier: v1.0.0\n"
        "  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:\n"
        "    tutor: v1.1.0-unsl\n"
    )
    loader = PromptLoader(tmp_path)
    cfg = loader.active_configs()
    assert "active" in cfg
    assert cfg["active"]["default"]["tutor"] == "v1.0.0"
    assert cfg["active"]["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]["tutor"] == "v1.1.0-unsl"
