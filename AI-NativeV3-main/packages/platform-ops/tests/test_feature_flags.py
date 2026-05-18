"""Tests de feature flags por tenant."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from platform_ops.feature_flags import (
    FeatureFlags,
    FeatureNotDeclaredError,
)

UNSL_UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


SAMPLE_CONFIG = """\
# Comentarios deben ignorarse

default:
  enable_code_execution: false
  enable_claude_opus: false
  max_episodes_per_day: 50
  welcome_message: Bienvenido por default

tenants:
  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:
    enable_code_execution: true
    enable_claude_opus: true
    max_episodes_per_day: 200
  bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb:
    enable_code_execution: true
"""


@pytest.fixture
def flags_file(tmp_path: Path) -> Path:
    path = tmp_path / "feature_flags.yaml"
    path.write_text(SAMPLE_CONFIG)
    return path


@pytest.fixture
def flags(flags_file: Path) -> FeatureFlags:
    return FeatureFlags(flags_file, reload_interval_seconds=0)


# ── Lectura básica ────────────────────────────────────────────────────


def test_tenant_con_override_devuelve_el_override(flags: FeatureFlags) -> None:
    assert flags.is_enabled(UNSL_UUID, "enable_code_execution") is True
    assert flags.is_enabled(UNSL_UUID, "enable_claude_opus") is True
    assert flags.get_value(UNSL_UUID, "max_episodes_per_day") == 200


def test_tenant_sin_override_cae_al_default(flags: FeatureFlags) -> None:
    other_tenant = uuid4()
    assert flags.is_enabled(other_tenant, "enable_code_execution") is False
    assert flags.get_value(other_tenant, "max_episodes_per_day") == 50


def test_override_parcial_completa_con_default(flags: FeatureFlags) -> None:
    """El tenant bbbbb sólo declara enable_code_execution.
    Los demás valores vienen del default."""
    b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    assert flags.is_enabled(b, "enable_code_execution") is True
    # Estos no están en el override → default
    assert flags.is_enabled(b, "enable_claude_opus") is False
    assert flags.get_value(b, "max_episodes_per_day") == 50


# ── Feature no declarada ───────────────────────────────────────────────


def test_feature_no_declarada_levanta_error(flags: FeatureFlags) -> None:
    with pytest.raises(FeatureNotDeclaredError, match="enable_quantum_mode"):
        flags.is_enabled(UNSL_UUID, "enable_quantum_mode")


# ── Tipado ─────────────────────────────────────────────────────────────


def test_is_enabled_sobre_valor_no_booleano_falla(flags: FeatureFlags) -> None:
    """is_enabled debe ser estricto: si el valor no es bool, error claro."""
    with pytest.raises(TypeError, match="no es booleana"):
        flags.is_enabled(UNSL_UUID, "max_episodes_per_day")


def test_valores_de_distintos_tipos_se_parsean_bien(flags: FeatureFlags) -> None:
    other = uuid4()
    assert flags.get_value(other, "enable_code_execution") is False  # bool
    assert flags.get_value(other, "max_episodes_per_day") == 50  # int
    assert flags.get_value(other, "welcome_message") == "Bienvenido por default"  # string


# ── get_all_for_tenant ─────────────────────────────────────────────────


def test_get_all_devuelve_merge_default_con_override(flags: FeatureFlags) -> None:
    all_flags = flags.get_all_for_tenant(UNSL_UUID)
    assert all_flags["enable_code_execution"] is True  # del override
    assert all_flags["max_episodes_per_day"] == 200  # del override
    assert all_flags["welcome_message"] == "Bienvenido por default"  # del default


def test_get_all_para_tenant_sin_overrides(flags: FeatureFlags) -> None:
    other = uuid4()
    all_flags = flags.get_all_for_tenant(other)
    assert all_flags == {
        "enable_code_execution": False,
        "enable_claude_opus": False,
        "max_episodes_per_day": 50,
        "welcome_message": "Bienvenido por default",
    }


# ── Archivo ausente ────────────────────────────────────────────────────


def test_archivo_ausente_no_crashea_pero_todas_las_features_fallan(tmp_path: Path) -> None:
    flags = FeatureFlags(tmp_path / "no-existe.yaml", reload_interval_seconds=0)
    # Cualquier feature → no declarada
    with pytest.raises(FeatureNotDeclaredError):
        flags.is_enabled(UNSL_UUID, "enable_code_execution")


# ── Reload ─────────────────────────────────────────────────────────────


def test_cambio_en_archivo_se_recarga(flags_file: Path) -> None:
    flags = FeatureFlags(flags_file, reload_interval_seconds=0)
    assert flags.get_value(UNSL_UUID, "max_episodes_per_day") == 200

    # Modificar el archivo
    flags_file.write_text(
        SAMPLE_CONFIG.replace("max_episodes_per_day: 200", "max_episodes_per_day: 500")
    )
    # Con reload_interval_seconds=0, la próxima consulta recarga
    assert flags.get_value(UNSL_UUID, "max_episodes_per_day") == 500
