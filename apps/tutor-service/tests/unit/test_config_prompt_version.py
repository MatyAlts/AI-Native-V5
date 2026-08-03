"""Test del default_prompt_version del tutor-service (ADR-009 + G12 activacion).

Garantia critica: el `default_prompt_version` efectivo del tutor-service debe
estar alineado con el manifest global del repo de prompts (ADR-009). Ambos
deben apuntar a la misma version, sino:

  - Frontends que consultan `GET /api/v1/active_configs` ven una version,
  - Pero el tutor-service usa otra al abrir episodios → `prompt_system_hash`
    en eventos CTR no coincide con la declarada en active_configs.

Si este test falla, ALINEAR los dos lados antes de mergear.

Este archivo se edita IN-PLACE en cada bump, no se duplica por version. La
version esperada vive en una sola constante (`EXPECTED_TUTOR_VERSION`): un bump
futuro toca un unico lugar y los tres tests lo siguen.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from tutor_service.config import Settings

# Version activa del prompt del tutor. Al bumpear, cambiar SOLO acá.
EXPECTED_TUTOR_VERSION = "v1.3.0"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_default_prompt_version_alineado_con_manifest() -> None:
    """La version efectiva (config del tutor) y la declarada (manifest) coinciden.

    v1.3.0 activado 2026-07-28 (epic java-authoring-experience): generaliza los
    dos ejemplos del prompt que nombraban Python. Metodo identico a v1.2.0.
    """
    s = Settings()
    assert s.default_prompt_version == EXPECTED_TUTOR_VERSION, (
        f"tutor-service.default_prompt_version='{s.default_prompt_version}' "
        f"pero se espera {EXPECTED_TUTOR_VERSION}. ALINEAR los dos lados — ver "
        f"`ai-native-prompts/manifest.yaml` y "
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
    manifest = _repo_root() / "ai-native-prompts" / "manifest.yaml"
    assert manifest.exists(), (
        "ai-native-prompts/manifest.yaml debe existir post-G12-activation; "
        "si fue borrado, el endpoint /active_configs devuelve el default v1.0.0 "
        f"hardcodeado mientras el tutor usa {EXPECTED_TUTOR_VERSION} — "
        "desalineacion silenciosa."
    )
    text = manifest.read_text(encoding="utf-8")
    # Sanity check minimo — no parseamos YAML completo aca, solo verificamos
    # que la version declarada coincide con el config del tutor.
    assert f"tutor: {EXPECTED_TUTOR_VERSION}" in text, (
        f"manifest.yaml debe declarar 'tutor: {EXPECTED_TUTOR_VERSION}' bajo "
        "active.default; contenido actual no incluye esa linea."
    )


def test_version_activa_declara_el_hash_de_su_contenido() -> None:
    """La version ACTIVA debe tener `manifest.yaml` propio con el sha256 correcto.

    Sin manifest de version, `PromptLoader` no verifica nada (la comprobacion es
    `if manifest_path.exists()`), y el contenido se puede editar in-place sin que
    el sistema lo detecte: el identificador de version deja de designar un texto
    unico. Eso fue exactamente lo que paso con v1.2.0, que se edito dos dias
    despues de activarse (commit 0d69d17) sin bump ni hash-lock.

    Este test es el golden de contenido de la version activa: cualquier cambio
    del `system.md` que no re-firme el manifest lo hace fallar.
    """
    version_dir = _repo_root() / "ai-native-prompts" / "prompts" / "tutor" / EXPECTED_TUTOR_VERSION
    system_md = version_dir / "system.md"
    manifest = version_dir / "manifest.yaml"

    assert system_md.exists(), f"falta {system_md}"
    assert manifest.exists(), (
        f"{EXPECTED_TUTOR_VERSION} no declara manifest.yaml. Una version activa "
        "sin hash declarado se puede mutar sin que el loader falle."
    )

    declared = re.search(r"system\.md:\s*([0-9a-f]{64})", manifest.read_text(encoding="utf-8"))
    assert declared is not None, "manifest.yaml no declara el sha256 de system.md"

    actual = hashlib.sha256(system_md.read_bytes()).hexdigest()
    assert actual == declared.group(1), (
        f"el contenido de {EXPECTED_TUTOR_VERSION}/system.md NO coincide con el "
        f"hash declarado.\n  declarado: {declared.group(1)}\n  actual:    {actual}\n"
        "Si el cambio es intencional, bumpear la version y re-firmar el manifest "
        "— NO editar in-place una version ya activa."
    )


def test_prompt_activo_no_ejemplifica_en_un_unico_lenguaje() -> None:
    """El cuerpo del prompt no nombra un lenguaje concreto en sus ejemplos.

    Requisito de `multi-language-prompts`: el metodo socratico no depende del
    lenguaje que el alumno este aprendiendo. Se chequea el CUERPO, no el bloque
    de metadata del pie (que si documenta el historial de versiones).
    """
    system_md = (
        _repo_root()
        / "ai-native-prompts"
        / "prompts"
        / "tutor"
        / EXPECTED_TUTOR_VERSION
        / "system.md"
    )
    cuerpo = system_md.read_text(encoding="utf-8").split("<!--")[0]
    assert "Python" not in cuerpo and "python" not in cuerpo, (
        "el cuerpo del prompt activo menciona Python. Los ejemplos deben valer "
        "para cualquier lenguaje del ejercicio."
    )
