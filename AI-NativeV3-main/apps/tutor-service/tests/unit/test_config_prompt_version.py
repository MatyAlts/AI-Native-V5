"""Test del default_prompt_version del tutor-service (ADR-009 + G12 activacion).

Garantia critica: el `default_prompt_version` efectivo del tutor-service debe
estar alineado con el manifest global del repo de prompts (ADR-009). Ambos
deben apuntar a la misma version, sino:

  - Frontends que consultan `GET /api/v1/active_configs` ven una version,
  - Pero el tutor-service usa otra al abrir episodios → `prompt_system_hash`
    en eventos CTR no coincide con la declarada en active_configs.

Si este test falla, ALINEAR los dos lados antes de mergear.
"""

from __future__ import annotations

from pathlib import Path

from tutor_service.config import Settings


def test_default_prompt_version_es_v101_post_g12_activation() -> None:
    """ADR-009 + G12 (2026-04-29): la version activa del prompt tutor es v1.1.0.

    El manifest global (`ai-native-prompts/manifest.yaml`) declara `default.tutor: v1.1.0`.
    Esta config debe coincidir.
    """
    s = Settings()
    assert s.default_prompt_version == "v1.1.0", (
        f"tutor-service.default_prompt_version='{s.default_prompt_version}' "
        f"pero el manifest global del repo apunta a v1.1.0. ALINEAR los dos "
        f"lados — ver `ai-native-prompts/manifest.yaml` y "
        f"`apps/tutor-service/src/tutor_service/config.py`."
    )


def test_default_prompt_name_sigue_siendo_tutor() -> None:
    """Sanity: el name del prompt no cambia con bumps de version."""
    s = Settings()
    assert s.default_prompt_name == "tutor"


def test_manifest_yaml_existe_y_se_parsea() -> None:
    """El manifest del repo de prompts debe existir y declarar la misma version
    que el config del tutor-service. Si NO existe, el `prompt_loader.active_configs()`
    cae al default hardcodeado del codigo (v1.0.0) y los frontends ven una version
    distinta a la que el tutor usa en runtime.
    """
    repo_root = Path(__file__).resolve().parents[4]
    manifest = repo_root / "ai-native-prompts" / "manifest.yaml"
    assert manifest.exists(), (
        f"ai-native-prompts/manifest.yaml debe existir post-G12-activation; "
        f"si fue borrado, el endpoint /active_configs devuelve el default v1.0.0 "
        f"hardcodeado mientras el tutor usa v1.1.0 — desalineacion silenciosa."
    )
    text = manifest.read_text(encoding="utf-8")
    # Sanity check minimo — no parseamos YAML completo aca, solo verificamos
    # que la version declarada coincide con el config del tutor.
    assert "tutor: v1.1.0" in text, (
        f"manifest.yaml debe declarar 'tutor: v1.1.0' bajo active.default; "
        f"contenido actual no incluye esa linea."
    )
