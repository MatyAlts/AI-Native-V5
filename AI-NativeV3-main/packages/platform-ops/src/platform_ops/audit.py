"""Auditoría de accesos sospechosos.

Analiza eventos de acceso (logins, requests al api-gateway) buscando
patrones anómalos que requieran revisión:

  1. **Brute force de login**: N logins fallidos en ventana de K minutos
  2. **Acceso cross-tenant**: principal intentando tenant != su home
  3. **Token anómalo**: muchos 401s consecutivos del mismo user_id
  4. **Exfil potencial**: tasa alta de GETs sobre endpoints sensibles
     (ej /api/v1/classifications/aggregated)

Los eventos se evalúan contra reglas y se generan `SuspiciousAccess`
findings. En F7 el resultado se exporta a SIEM; en F6 lo guardamos como
registros locales para revisión manual del docente_admin.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AccessEvent:
    """Evento de acceso crudo (proveniente de logs del api-gateway)."""

    ts: datetime
    principal_id: str  # sub del JWT o IP si anonymous
    tenant_id: str | None  # tenant del JWT (None en logins fallidos)
    action: str  # "login_success" | "login_failed" | "api_request"
    path: str
    status_code: int
    ip: str | None = None
    user_agent: str | None = None
    error_reason: str | None = None


@dataclass
class SuspiciousAccess:
    """Hallazgo de patrón sospechoso."""

    rule_id: str
    severity: Severity
    principal_id: str
    tenant_id: str | None
    summary: str
    event_count: int
    first_seen: datetime
    last_seen: datetime
    sample_events: list[AccessEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "summary": self.summary,
            "event_count": self.event_count,
            "first_seen": self.first_seen.isoformat().replace("+00:00", "Z"),
            "last_seen": self.last_seen.isoformat().replace("+00:00", "Z"),
        }


# ── Reglas ────────────────────────────────────────────────────────────


@dataclass
class BruteForceRule:
    """Detecta N logins fallidos del mismo principal en una ventana de
    tiempo."""

    threshold: int = 5
    window: timedelta = timedelta(minutes=5)
    rule_id: str = "brute_force_login"

    def evaluate(self, events: Iterable[AccessEvent]) -> list[SuspiciousAccess]:
        # Group by principal
        failed_by_principal: dict[str, list[AccessEvent]] = defaultdict(list)
        for ev in events:
            if ev.action == "login_failed":
                failed_by_principal[ev.principal_id].append(ev)

        findings: list[SuspiciousAccess] = []
        for principal, evs in failed_by_principal.items():
            evs_sorted = sorted(evs, key=lambda e: e.ts)
            # Sliding window sobre los timestamps
            window_events: deque[AccessEvent] = deque()
            for ev in evs_sorted:
                window_events.append(ev)
                # Drop eventos fuera de la ventana
                while window_events and (ev.ts - window_events[0].ts) > self.window:
                    window_events.popleft()
                if len(window_events) >= self.threshold:
                    findings.append(
                        SuspiciousAccess(
                            rule_id=self.rule_id,
                            severity=Severity.HIGH,
                            principal_id=principal,
                            tenant_id=None,
                            summary=(
                                f"{len(window_events)} logins fallidos en {self.window.total_seconds() / 60:.0f} min"
                            ),
                            event_count=len(window_events),
                            first_seen=window_events[0].ts,
                            last_seen=window_events[-1].ts,
                            sample_events=list(window_events)[:5],
                        )
                    )
                    break  # un finding por principal es suficiente
        return findings


@dataclass
class CrossTenantAccessRule:
    """Detecta requests con tenant_id header != al tenant del JWT.

    Este es un evento gravísimo: indica intento de escalada.
    Implementado como auditoría porque el gateway YA rechaza estos
    requests (JWT validator), pero querés saberlo igual.
    """

    rule_id: str = "cross_tenant_access_attempt"

    def evaluate(self, events: Iterable[AccessEvent]) -> list[SuspiciousAccess]:
        findings: list[SuspiciousAccess] = []
        for ev in events:
            if (
                ev.action == "api_request"
                and ev.status_code in (401, 403)
                and ev.error_reason
                and "tenant" in ev.error_reason.lower()
            ):
                findings.append(
                    SuspiciousAccess(
                        rule_id=self.rule_id,
                        severity=Severity.CRITICAL,
                        principal_id=ev.principal_id,
                        tenant_id=ev.tenant_id,
                        summary=f"Intento cross-tenant: {ev.error_reason}",
                        event_count=1,
                        first_seen=ev.ts,
                        last_seen=ev.ts,
                        sample_events=[ev],
                    )
                )
        return findings


@dataclass
class RepeatedAuthFailuresRule:
    """Muchos 401 del mismo principal → token podrido o atacante con
    refresh token robado."""

    threshold: int = 10
    window: timedelta = timedelta(minutes=10)
    rule_id: str = "repeated_auth_failures"

    def evaluate(self, events: Iterable[AccessEvent]) -> list[SuspiciousAccess]:
        failures_by_principal: dict[str, list[AccessEvent]] = defaultdict(list)
        for ev in events:
            if ev.action == "api_request" and ev.status_code == 401:
                failures_by_principal[ev.principal_id].append(ev)

        findings: list[SuspiciousAccess] = []
        for principal, evs in failures_by_principal.items():
            evs_sorted = sorted(evs, key=lambda e: e.ts)
            window_events: deque[AccessEvent] = deque()
            for ev in evs_sorted:
                window_events.append(ev)
                while window_events and (ev.ts - window_events[0].ts) > self.window:
                    window_events.popleft()
                if len(window_events) >= self.threshold:
                    findings.append(
                        SuspiciousAccess(
                            rule_id=self.rule_id,
                            severity=Severity.MEDIUM,
                            principal_id=principal,
                            tenant_id=evs_sorted[0].tenant_id,
                            summary=(
                                f"{len(window_events)} errores 401 en {self.window.total_seconds() / 60:.0f} min"
                            ),
                            event_count=len(window_events),
                            first_seen=window_events[0].ts,
                            last_seen=window_events[-1].ts,
                        )
                    )
                    break
        return findings


# ── Engine ────────────────────────────────────────────────────────────


@dataclass
class AuditEngine:
    """Corre todas las reglas contra un batch de eventos."""

    rules: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.rules:
            self.rules = [
                BruteForceRule(),
                CrossTenantAccessRule(),
                RepeatedAuthFailuresRule(),
            ]

    def evaluate(self, events: Iterable[AccessEvent]) -> list[SuspiciousAccess]:
        events_list = list(events)
        findings: list[SuspiciousAccess] = []
        for rule in self.rules:
            findings.extend(rule.evaluate(events_list))
        # Ordenar por severidad (critical primero) y luego por last_seen
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }
        findings.sort(key=lambda f: (severity_order[f.severity], -f.last_seen.timestamp()))
        return findings
