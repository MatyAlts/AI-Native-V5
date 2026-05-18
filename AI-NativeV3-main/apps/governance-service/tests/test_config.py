"""F14: parity test entre `.env.example` y `Settings()` del governance-service.

Bloquea regresión del typo histórico `GOVERNANCE_REPO_PATH` (template) vs
`PROMPTS_REPO_PATH` (código). Si alguien rota el nombre de la env var
en uno de los dos lados sin tocar el otro, este test rompe.
"""

from __future__ import annotations

from pathlib import Path

from governance_service.config import Settings

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"


def _parse_env_example() -> dict[str, str]:
    """Parser line-based mínimo (mismo enfoque que governance prompt_loader)."""
    pairs: dict[str, str] = {}
    if not _ENV_EXAMPLE.exists():
        return pairs
    for raw in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


def test_env_example_declares_prompts_repo_path() -> None:
    pairs = _parse_env_example()
    assert "PROMPTS_REPO_PATH" in pairs, (
        ".env.example debe declarar PROMPTS_REPO_PATH (deuda histórica F14)."
    )
    assert pairs["PROMPTS_REPO_PATH"], "PROMPTS_REPO_PATH no debe quedar vacía en el ejemplo."


def test_env_example_does_not_use_old_governance_repo_path() -> None:
    pairs = _parse_env_example()
    assert "GOVERNANCE_REPO_PATH" not in pairs, (
        "GOVERNANCE_REPO_PATH es el nombre histórico (F14). El código lee PROMPTS_REPO_PATH."
    )


def test_env_example_var_matches_settings_field(monkeypatch) -> None:
    """Settings() lee PROMPTS_REPO_PATH y respeta el valor del entorno."""
    fixture_path = "/tmp/test-prompts-fixture"
    monkeypatch.setenv("PROMPTS_REPO_PATH", fixture_path)
    # Aislamos el lookup del .env del CWD para no contaminar el test
    monkeypatch.chdir(_REPO_ROOT.parent if _REPO_ROOT.parent.exists() else _REPO_ROOT)
    settings = Settings()
    assert settings.prompts_repo_path == fixture_path, (
        "Settings.prompts_repo_path debería leer la env var PROMPTS_REPO_PATH."
    )


def test_settings_field_name_is_prompts_repo_path() -> None:
    """El field name del modelo es prompts_repo_path (no governance_repo_path)."""
    field_names = set(Settings.model_fields.keys())
    assert "prompts_repo_path" in field_names
    assert "governance_repo_path" not in field_names
