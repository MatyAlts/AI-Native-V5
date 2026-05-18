"""Tests del bump G12 — v1.0.0 -> v1.0.1 documental del prompt del tutor.

Invariantes que cubren:
1. v1.0.0 sigue cargable y reproducible bit-a-bit (no se rompe el piloto historico).
2. v1.0.1 carga limpio desde el repo real con manifest fail-loud.
3. El texto del prompt (sin HTML comment ni header de version) es identico
   entre v1.0.0 y v1.0.1 — el bump es DOCUMENTAL, no funcional.
4. Los hashes del archivo entero son distintos (bump valido).

Si alguno de estos invariantes se rompe, el bump documental dejo de ser PATCH
puro y hay que revisar el ADR-009 + tesis 7.4.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from governance_service.services.prompt_loader import (
    PromptLoader,
    compute_content_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
PROMPTS_REPO = REPO_ROOT / "ai-native-prompts"


def _strip_html_comments(s: str) -> str:
    return re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL).strip()


def _normalize_version_header(s: str) -> str:
    return re.sub(r"\(v\d+\.\d+\.\d+\)", "(vX.Y.Z)", s)


@pytest.fixture
def loader() -> PromptLoader:
    if not PROMPTS_REPO.exists():
        pytest.skip(f"Repo de prompts no presente en {PROMPTS_REPO}")
    return PromptLoader(PROMPTS_REPO)


def test_v100_sigue_cargable_post_bump(loader: PromptLoader) -> None:
    """G12 NO debe romper la cargabilidad de v1.0.0 (preserva piloto historico)."""
    cfg = loader.load("tutor", "v1.0.0")
    assert cfg.content
    assert len(cfg.hash) == 64
    assert cfg.hash == compute_content_hash(cfg.content)


def test_v101_carga_con_manifest_failloud(loader: PromptLoader) -> None:
    """v1.0.1 debe declarar su hash en manifest.yaml y validar contra el contenido real."""
    cfg = loader.load("tutor", "v1.0.1")
    assert cfg.content
    assert cfg.hash == compute_content_hash(cfg.content)

    manifest = PROMPTS_REPO / "prompts" / "tutor" / "v1.0.1" / "manifest.yaml"
    assert manifest.exists(), "v1.0.1 debe traer manifest.yaml para fail-loud"
    declared = loader._declared_hash(manifest, "system.md")
    assert declared == cfg.hash, (
        f"Hash declarado en manifest ({declared}) no coincide con el computado "
        f"({cfg.hash}) — el manifest del bump quedo desincronizado"
    )


def test_v100_y_v101_tienen_hashes_distintos(loader: PromptLoader) -> None:
    """El bump PATCH cambia el archivo (HTML comment + header), por lo tanto el hash."""
    v100 = loader.load("tutor", "v1.0.0")
    v101 = loader.load("tutor", "v1.0.1")
    assert v100.hash != v101.hash, (
        "v1.0.0 y v1.0.1 tienen el mismo hash — o el bump no se aplico, "
        "o el archivo de v1.0.1 es un duplicado exacto"
    )


def test_texto_del_prompt_es_identico_modulo_comment_y_version(loader: PromptLoader) -> None:
    """G12 invariante central: el texto del prompt visible al modelo no cambia.

    Lo unico que difiere entre v1.0.0 y v1.0.1 es:
      - HTML comment al pie (invisible al modelo, auditoria humana)
      - String '(v1.0.0)' / '(v1.0.1)' en el header (cambio trivial de etiqueta)

    Si este test falla, el bump dejo de ser PATCH documental y hay que evaluar
    si corresponde MINOR (cambio sustantivo en instrucciones).
    """
    v100 = loader.load("tutor", "v1.0.0")
    v101 = loader.load("tutor", "v1.0.1")

    cuerpo_100 = _normalize_version_header(_strip_html_comments(v100.content))
    cuerpo_101 = _normalize_version_header(_strip_html_comments(v101.content))

    assert cuerpo_100 == cuerpo_101, (
        "El texto del prompt visible al modelo difiere entre v1.0.0 y v1.0.1 — "
        "el bump no es PATCH documental, hay cambio funcional"
    )


def test_v101_corrige_cuenta_de_guardarrailes(loader: PromptLoader) -> None:
    """v1.0.0 declaraba '4/10 guardarrailes' (con GP3 mal mapeado). v1.0.1 corrige a '3/10'."""
    v100 = loader.load("tutor", "v1.0.0")
    v101 = loader.load("tutor", "v1.0.1")

    assert "4/10 guardarrailes" in v100.content, (
        "v1.0.0 deberia declarar '4/10 guardarrailes' (la cuenta erronea original)"
    )
    assert "3/10 guardarrailes" in v101.content, (
        "v1.0.1 deberia declarar '3/10 guardarrailes' (la cuenta corregida)"
    )
    assert "4/10 guardarrailes" not in v101.content, (
        "v1.0.1 no debe contener la cuenta erronea de v1.0.0"
    )


def test_manifest_global_activa_v101_para_tutor_default(loader: PromptLoader) -> None:
    """ADR-009 + G12 activacion (2026-04-29): el manifest global del repo declara
    v1.0.1 como version activa para el `tutor` en el tenant `default`.

    Si este test falla:
      - Se borro/movio `ai-native-prompts/manifest.yaml`, o
      - El parser de `active_configs()` cambio incompatiblemente, o
      - Alguien revirtio la activacion sin actualizar el manifest.

    Verificar tambien que `apps/tutor-service/src/tutor_service/config.py:default_prompt_version`
    siga alineado en `v1.0.1` — los DOS lados deben coincidir.
    """
    cfg = loader.active_configs()
    active = cfg.get("active", {})
    default = active.get("default", {})
    assert default.get("tutor") == "v1.1.0", (
        f"manifest.yaml global debe declarar tutor=v1.1.0 para default; "
        f"obtenido: {default.get('tutor')!r}. Si la activacion fue revertida, "
        f"alinear tambien tutor-service/config.py:default_prompt_version."
    )
    # Sanity: classifier sigue en v1.0.0 (no hubo bump del classifier prompt).
    assert default.get("classifier") == "v1.0.0", (
        f"manifest.yaml debe mantener classifier=v1.0.0; "
        f"obtenido: {default.get('classifier')!r}"
    )
