"""Tests de auditoría de accesos sospechosos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from platform_ops.audit import (
    AccessEvent,
    AuditEngine,
    BruteForceRule,
    CrossTenantAccessRule,
    RepeatedAuthFailuresRule,
    Severity,
)


def _ev(
    ts_offset_sec: int,
    principal: str = "user-alice",
    action: str = "login_failed",
    status: int = 401,
    path: str = "/auth/login",
    tenant_id: str | None = None,
    error_reason: str | None = None,
) -> AccessEvent:
    base = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
    return AccessEvent(
        ts=base + timedelta(seconds=ts_offset_sec),
        principal_id=principal,
        tenant_id=tenant_id,
        action=action,
        path=path,
        status_code=status,
        error_reason=error_reason,
    )


# ── Brute force ───────────────────────────────────────────────────────


def test_brute_force_5_fallos_en_ventana_detecta() -> None:
    rule = BruteForceRule(threshold=5, window=timedelta(minutes=5))
    events = [_ev(i * 10) for i in range(5)]  # 5 fallos en 50 seg

    findings = rule.evaluate(events)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "brute_force_login"
    assert f.severity == Severity.HIGH
    assert f.principal_id == "user-alice"
    assert f.event_count == 5


def test_brute_force_fallos_dispersos_no_dispara() -> None:
    """5 fallos espaciados por 10 min no deben disparar si la ventana es 5 min."""
    rule = BruteForceRule(threshold=5, window=timedelta(minutes=5))
    events = [_ev(i * 600) for i in range(5)]  # 10 min entre cada uno

    findings = rule.evaluate(events)
    assert len(findings) == 0


def test_brute_force_separa_por_principal() -> None:
    rule = BruteForceRule(threshold=3, window=timedelta(minutes=5))
    events = [
        _ev(0, principal="alice"),
        _ev(10, principal="alice"),
        _ev(20, principal="alice"),  # 3 fallos de alice → detect
        _ev(0, principal="bob"),
        _ev(10, principal="bob"),  # solo 2 de bob → no detect
    ]

    findings = rule.evaluate(events)
    assert len(findings) == 1
    assert findings[0].principal_id == "alice"


def test_brute_force_con_mix_login_exitoso_solo_cuenta_fallidos() -> None:
    rule = BruteForceRule(threshold=3, window=timedelta(minutes=5))
    events = [
        _ev(0, action="login_failed"),
        _ev(10, action="login_success"),  # no cuenta
        _ev(20, action="login_failed"),
        _ev(30, action="login_failed"),
    ]
    findings = rule.evaluate(events)
    # 3 fallidos → detecta
    assert len(findings) == 1
    assert findings[0].event_count == 3


# ── Cross-tenant ──────────────────────────────────────────────────────


def test_cross_tenant_attempt_se_detecta() -> None:
    rule = CrossTenantAccessRule()
    events = [
        _ev(
            0,
            principal="attacker",
            action="api_request",
            status=403,
            path="/api/v1/classifications/abc",
            tenant_id="tenant-victim",
            error_reason="tenant mismatch: JWT tenant=X but header tenant=Y",
        ),
    ]
    findings = rule.evaluate(events)
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL
    assert findings[0].rule_id == "cross_tenant_access_attempt"


def test_cross_tenant_requests_normales_no_disparan() -> None:
    rule = CrossTenantAccessRule()
    events = [
        _ev(0, action="api_request", status=200, path="/api/v1/episodes"),
        _ev(10, action="api_request", status=404, path="/api/v1/x"),
        _ev(20, action="api_request", status=500, path="/api/v1/y"),
    ]
    findings = rule.evaluate(events)
    assert findings == []


# ── Repeated auth failures ────────────────────────────────────────────


def test_repeated_401s_disparan() -> None:
    rule = RepeatedAuthFailuresRule(threshold=10, window=timedelta(minutes=10))
    events = [
        _ev(i * 30, action="api_request", status=401) for i in range(10)
    ]  # 10 401s en 300 seg
    findings = rule.evaluate(events)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].event_count == 10


def test_9_401s_no_disparan() -> None:
    rule = RepeatedAuthFailuresRule(threshold=10, window=timedelta(minutes=10))
    events = [_ev(i * 30, action="api_request", status=401) for i in range(9)]
    findings = rule.evaluate(events)
    assert findings == []


# ── AuditEngine ────────────────────────────────────────────────────────


def test_engine_corre_todas_las_reglas() -> None:
    engine = AuditEngine()
    events = [
        # 5 fallos rápidos
        *[_ev(i * 10, action="login_failed") for i in range(5)],
        # 1 cross-tenant
        _ev(
            100,
            principal="another",
            action="api_request",
            status=403,
            error_reason="tenant mismatch",
        ),
    ]
    findings = engine.evaluate(events)
    # Al menos el brute force y el cross-tenant
    rule_ids = {f.rule_id for f in findings}
    assert "brute_force_login" in rule_ids
    assert "cross_tenant_access_attempt" in rule_ids


def test_engine_ordena_por_severidad() -> None:
    engine = AuditEngine()
    events = [
        *[_ev(i * 10, action="login_failed") for i in range(5)],  # HIGH
        _ev(
            100,
            principal="another",
            action="api_request",
            status=403,
            error_reason="tenant mismatch",
        ),  # CRITICAL
    ]
    findings = engine.evaluate(events)
    # CRITICAL aparece primero
    assert findings[0].severity == Severity.CRITICAL
    assert findings[1].severity == Severity.HIGH


def test_finding_serializable() -> None:
    rule = BruteForceRule(threshold=3, window=timedelta(minutes=5))
    events = [_ev(i * 10) for i in range(3)]
    findings = rule.evaluate(events)

    import json

    serialized = json.dumps(findings[0].to_dict())
    parsed = json.loads(serialized)
    assert parsed["severity"] == "high"
    assert parsed["principal_id"] == "user-alice"
    assert "first_seen" in parsed
