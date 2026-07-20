"""Tests del journal JSONL append-only (ADR-021)."""

from __future__ import annotations

from pathlib import Path

import pytest
from integrity_attestation_service.services.journal import (
    Attestation,
    append_attestation,
    attestation_log_path,
    raw_jsonl_for_date,
    read_attestations_for_date,
)
from pydantic import ValidationError


def _att(
    *,
    episode_id: str = "11111111-2222-3333-4444-555555555555",
    tenant_id: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    ts_attested: str = "2026-04-27T10:30:05Z",
    signature: str = "a" * 128,
) -> Attestation:
    return Attestation(
        episode_id=episode_id,
        tenant_id=tenant_id,
        final_chain_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        total_events=42,
        ts_episode_closed="2026-04-27T10:30:00Z",
        ts_attested=ts_attested,
        signer_pubkey_id="26f7cf0749b5",
        signature=signature,
    )


# ---------------------------------------------------------------------------
# Path computation
# ---------------------------------------------------------------------------


def test_attestation_log_path_formato_yyyy_mm_dd(tmp_path: Path) -> None:
    p = attestation_log_path(tmp_path, "2026-04-27")
    assert p == tmp_path / "attestations-2026-04-27.jsonl"


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------


def test_append_a_archivo_nuevo_lo_crea(tmp_path: Path) -> None:
    att = _att()
    path = append_attestation(tmp_path, att)
    assert path.exists()
    assert path.name == "attestations-2026-04-27.jsonl"


def test_append_a_archivo_existente_preserva_lineas_viejas(tmp_path: Path) -> None:
    att1 = _att(episode_id="11111111-1111-1111-1111-111111111111")
    att2 = _att(episode_id="22222222-2222-2222-2222-222222222222")

    path = append_attestation(tmp_path, att1)
    append_attestation(tmp_path, att2)

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert "11111111" in lines[0]
    assert "22222222" in lines[1]


def test_append_crea_directorio_si_no_existe(tmp_path: Path) -> None:
    nested = tmp_path / "deeply" / "nested" / "logs"
    assert not nested.exists()
    append_attestation(nested, _att())
    assert nested.exists()


def test_append_rota_archivo_por_dia_utc(tmp_path: Path) -> None:
    """Dos attestations en dias UTC distintos → dos archivos distintos."""
    att_dia1 = _att(ts_attested="2026-04-27T23:59:59Z")
    att_dia2 = _att(ts_attested="2026-04-28T00:00:01Z")

    path1 = append_attestation(tmp_path, att_dia1)
    path2 = append_attestation(tmp_path, att_dia2)

    assert path1.name == "attestations-2026-04-27.jsonl"
    assert path2.name == "attestations-2026-04-28.jsonl"
    assert path1 != path2


def test_append_serializa_como_jsonl_una_linea_por_attestation(tmp_path: Path) -> None:
    """Cada attestation debe ser exactamente UNA linea (terminada en \\n).
    Critico para parsing por terceros."""
    att = _att()
    path = append_attestation(tmp_path, att)
    raw = path.read_bytes()
    # Exactamente un newline al final, ninguno en medio del JSON
    assert raw.count(b"\n") == 1
    assert raw.endswith(b"\n")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def test_read_de_archivo_inexistente_devuelve_lista_vacia(tmp_path: Path) -> None:
    assert read_attestations_for_date(tmp_path, "2026-04-27") == []


def test_read_parsea_lineas_a_attestation(tmp_path: Path) -> None:
    att = _att()
    append_attestation(tmp_path, att)

    parsed = read_attestations_for_date(tmp_path, "2026-04-27")
    assert len(parsed) == 1
    assert parsed[0].episode_id == att.episode_id
    assert parsed[0].signature == att.signature


def test_read_ignora_lineas_vacias(tmp_path: Path) -> None:
    """Defensa contra archivos manipulados o newlines extra."""
    att = _att()
    append_attestation(tmp_path, att)

    # Agregamos una linea vacia al final manualmente (simulando \n\n al final)
    path = tmp_path / "attestations-2026-04-27.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write("\n   \n")

    parsed = read_attestations_for_date(tmp_path, "2026-04-27")
    assert len(parsed) == 1


def test_read_falla_con_json_corrupto(tmp_path: Path) -> None:
    """Si alguien edita el JSONL a mano y rompe el formato, fallar fuerte
    al re-leer es preferible a parsear silencioso y perder evidencia."""
    path = tmp_path / "attestations-2026-04-27.jsonl"
    path.write_text("not-valid-json-at-all\n", encoding="utf-8")
    with pytest.raises(ValidationError):  # pydantic v2 envuelve JSONDecodeError
        read_attestations_for_date(tmp_path, "2026-04-27")


# ---------------------------------------------------------------------------
# Raw JSONL (para endpoint GET)
# ---------------------------------------------------------------------------


def test_raw_jsonl_devuelve_none_si_no_existe(tmp_path: Path) -> None:
    assert raw_jsonl_for_date(tmp_path, "2026-04-27") is None


def test_raw_jsonl_devuelve_contenido_bit_exact(tmp_path: Path) -> None:
    """El endpoint sirve lo escrito sin re-serializar — preserva bit-exact
    lo que el verificador externo va a procesar."""
    att = _att()
    path = append_attestation(tmp_path, att)
    raw = raw_jsonl_for_date(tmp_path, "2026-04-27")
    assert raw is not None
    assert raw == path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Concurrencia / idempotencia basica
# ---------------------------------------------------------------------------


def test_appends_secuenciales_no_interleavan(tmp_path: Path) -> None:
    """Single-consumer pero igualmente verificamos que appends rapidos
    no se entremezclen (cada uno termina su \\n antes del proximo)."""
    for i in range(20):
        append_attestation(
            tmp_path,
            _att(episode_id=f"{i:08d}-1111-1111-1111-111111111111"),
        )
    parsed = read_attestations_for_date(tmp_path, "2026-04-27")
    assert len(parsed) == 20
    for i, att in enumerate(parsed):
        assert att.episode_id.startswith(f"{i:08d}")
