"""Tests del roundtrip de firma HMAC del gateway (defensa en profundidad)."""

from __future__ import annotations

import time

import pytest
from platform_observability import sign_headers, verify_gateway_signature
from platform_observability.gateway_trust import _canonical_message

SECRET = "test-shared-secret-do-not-use-in-prod"
USER_ID = "b1b1b1b1-0001-0001-0001-000000000001"
TENANT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ROLES = "docente,estudiante"  # mismo formato que inyecta el gateway (sorted, csv)


def test_sign_then_verify_valido() -> None:
    """Una firma recién emitida valida correctamente."""
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, ts)
    assert verify_gateway_signature(SECRET, USER_ID, TENANT_ID, ROLES, ts, sig) is True


def test_firma_es_hexdigest_sha256() -> None:
    """sign_headers devuelve un hexdigest de 64 chars (SHA-256)."""
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, int(time.time()))
    assert len(sig) == 64
    int(sig, 16)  # no lanza => es hex válido


def test_firma_adulterada_falla() -> None:
    """Una firma manipulada (un char distinto) no valida."""
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, ts)
    tampered = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert verify_gateway_signature(SECRET, USER_ID, TENANT_ID, ROLES, ts, tampered) is False


@pytest.mark.parametrize(
    "field",
    ["user_id", "tenant_id", "roles", "ts"],
)
def test_payload_adulterado_falla(field: str) -> None:
    """Cambiar cualquier campo firmado invalida la firma (anti-tampering)."""
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, ts)
    args = {
        "user_id": USER_ID,
        "tenant_id": TENANT_ID,
        "roles": ROLES,
        "ts": ts,
    }
    if field == "ts":
        args[field] = ts - 1  # type: ignore[assignment]
    else:
        args[field] = "forjado-" + str(args[field])
    assert (
        verify_gateway_signature(
            SECRET,
            args["user_id"],  # type: ignore[arg-type]
            args["tenant_id"],  # type: ignore[arg-type]
            args["roles"],  # type: ignore[arg-type]
            args["ts"],  # type: ignore[arg-type]
            sig,
        )
        is False
    )


def test_escalacion_de_roles_falla() -> None:
    """Un atacante que cambia roles a superadmin no puede revalidar la firma.

    Este es el ataque que el fix mitiga: forjar X-User-Roles contra un servicio
    interno expuesto. Sin el secreto, no puede recomputar una firma válida.
    """
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, "estudiante", ts)
    assert (
        verify_gateway_signature(SECRET, USER_ID, TENANT_ID, "superadmin", ts, sig)
        is False
    )


def test_ts_viejo_falla_anti_replay() -> None:
    """Una firma con ts más viejo que max_age_seconds se rechaza (anti-replay)."""
    old_ts = int(time.time()) - 600  # 10 min atrás
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, old_ts)
    assert (
        verify_gateway_signature(
            SECRET, USER_ID, TENANT_ID, ROLES, old_ts, sig, max_age_seconds=300
        )
        is False
    )


def test_ts_dentro_de_ventana_valida() -> None:
    """Una firma con ts reciente (dentro de la ventana) valida."""
    recent_ts = int(time.time()) - 60  # 1 min atrás
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, recent_ts)
    assert (
        verify_gateway_signature(
            SECRET, USER_ID, TENANT_ID, ROLES, recent_ts, sig, max_age_seconds=300
        )
        is True
    )


def test_ts_futuro_lejano_falla() -> None:
    """Un ts demasiado adelantado (más allá del skew tolerado) se rechaza."""
    future_ts = int(time.time()) + 600
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, future_ts)
    assert (
        verify_gateway_signature(
            SECRET, USER_ID, TENANT_ID, ROLES, future_ts, sig, max_age_seconds=300
        )
        is False
    )


def test_secreto_distinto_falla() -> None:
    """Una firma emitida con otro secreto no valida (gateway no autorizado)."""
    ts = int(time.time())
    sig = sign_headers("otro-secreto", USER_ID, TENANT_ID, ROLES, ts)
    assert verify_gateway_signature(SECRET, USER_ID, TENANT_ID, ROLES, ts, sig) is False


def test_firma_vacia_falla() -> None:
    """Firma ausente (string vacío) => False, sin lanzar."""
    ts = int(time.time())
    assert verify_gateway_signature(SECRET, USER_ID, TENANT_ID, ROLES, ts, "") is False


def test_secreto_vacio_falla() -> None:
    """Secreto vacío => False (no se puede verificar sin secreto)."""
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, ts)
    assert verify_gateway_signature("", USER_ID, TENANT_ID, ROLES, ts, sig) is False


def test_ts_no_numerico_falla_sin_lanzar() -> None:
    """ts no convertible a int (ej. header basura) => False, no excepción."""
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, ts)
    assert (
        verify_gateway_signature(SECRET, USER_ID, TENANT_ID, ROLES, "no-soy-int", sig)
        is False
    )


def test_ts_string_numerico_valida() -> None:
    """Los servicios reciben x-gateway-ts como string; verify acepta str numérico."""
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, ts)
    assert (
        verify_gateway_signature(SECRET, USER_ID, TENANT_ID, ROLES, str(ts), sig)
        is True
    )


def test_ts_none_falla_sin_lanzar() -> None:
    """ts None (header ausente) => False, no excepción."""
    ts = int(time.time())
    sig = sign_headers(SECRET, USER_ID, TENANT_ID, ROLES, ts)
    assert (
        verify_gateway_signature(SECRET, USER_ID, TENANT_ID, ROLES, None, sig) is False  # type: ignore[arg-type]
    )


def test_mensaje_canonico_orden_fijo() -> None:
    """El mensaje canónico respeta el orden y separador del contrato."""
    msg = _canonical_message(USER_ID, TENANT_ID, ROLES, 1718000000)
    assert msg == f"{USER_ID}\n{TENANT_ID}\n{ROLES}\n1718000000".encode()
