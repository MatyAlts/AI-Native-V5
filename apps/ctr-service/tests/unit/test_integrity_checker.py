"""Tests del integrity checker.

Usa fakes de session_factory que devuelven datos controlados.
No requiere DB real; verifica la lógica pura del verificador.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ctr_service.models.base import GENESIS_HASH
from ctr_service.services.hashing import compute_chain_hash, compute_self_hash
from ctr_service.workers.integrity_checker import IntegrityChecker

# ── Fakes mínimos ──────────────────────────────────────────────────────


@dataclass
class FakeEpisode:
    id: UUID
    tenant_id: UUID
    estado: str
    integrity_compromised: bool = False
    closed_at: datetime | None = None


@dataclass
class FakeEvent:
    event_uuid: UUID
    episode_id: UUID
    tenant_id: UUID
    seq: int
    event_type: str
    ts: datetime
    payload: dict
    self_hash: str
    chain_hash: str
    prompt_system_hash: str = "a" * 64
    prompt_system_version: str = "v1.0.0"
    classifier_config_hash: str = "b" * 64


@dataclass
class FakeSession:
    episodes: list[FakeEpisode] = field(default_factory=list)
    events: list[FakeEvent] = field(default_factory=list)
    updates: list[tuple[UUID, dict]] = field(default_factory=list)

    async def execute(self, stmt, params=None):
        # Parser muy simple del caso: si es update → registrar; si es select → devolver
        text_stmt = str(stmt).lower()
        if "update" in text_stmt:
            return _NoopResult()
        if "set_config" in text_stmt:
            return _NoopResult()
        # Select
        return _SelectResult(self)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _NoopResult:
    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return _Scalars([])


class _SelectResult:
    """Devuelve eventos o episodios del FakeSession según el orden de llamada."""

    _calls = 0

    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def scalars(self):
        # Heurística: primera llamada = episodes, segunda+ = events
        # Para tests usamos fixture que asigna manualmente.
        return _Scalars(
            self.session.episodes
            if not hasattr(self.session, "_selecting_events") or not self.session._selecting_events
            else self.session.events
        )


class _Scalars:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class _FakeSessionFactory:
    """Factory que construye siempre la misma sesión predeterminada."""

    def __init__(self, episodes: list[FakeEpisode], events: list[FakeEvent]) -> None:
        self.episodes = episodes
        self.events = events
        self._call_count = 0

    def __call__(self):
        @asynccontextmanager
        async def ctx():
            self._call_count += 1
            session = FakeSession(episodes=self.episodes, events=self.events)
            # Primera llamada → se buscan episodios; siguientes → eventos
            if self._call_count == 1:
                session._selecting_events = False
            else:
                session._selecting_events = True
            yield session

        return ctx()


# ── Helpers para construir cadenas correctas ───────────────────────────


def _valid_chain_events(episode_id: UUID, tenant_id: UUID, n: int) -> list[FakeEvent]:
    """Construye una cadena criptográficamente consistente de n eventos."""
    events: list[FakeEvent] = []
    prev_chain = GENESIS_HASH
    for i in range(n):
        ts = datetime(2026, 9, 1, 10, i, 0, tzinfo=UTC)
        raw = {
            "event_uuid": str(uuid4()),
            "episode_id": str(episode_id),
            "tenant_id": str(tenant_id),
            "seq": i,
            "event_type": "prompt_enviado" if i > 0 else "episodio_abierto",
            "ts": ts.isoformat().replace("+00:00", "Z"),
            "payload": {"content": f"evento_{i}"},
            "prompt_system_hash": "a" * 64,
            "prompt_system_version": "v1.0.0",
            "classifier_config_hash": "b" * 64,
        }
        self_h = compute_self_hash(raw)
        chain_h = compute_chain_hash(self_h, prev_chain)
        events.append(
            FakeEvent(
                event_uuid=UUID(raw["event_uuid"]),
                episode_id=episode_id,
                tenant_id=tenant_id,
                seq=i,
                event_type=raw["event_type"],
                ts=ts,
                payload=raw["payload"],
                self_hash=self_h,
                chain_hash=chain_h,
            )
        )
        prev_chain = chain_h
    return events


# ── Tests ──────────────────────────────────────────────────────────────


async def test_cadena_valida_se_reporta_integra() -> None:
    tenant = uuid4()
    ep_id = uuid4()
    ep = FakeEpisode(id=ep_id, tenant_id=tenant, estado="closed")
    events = _valid_chain_events(ep_id, tenant, n=3)

    factory = _FakeSessionFactory([ep], events)
    checker = IntegrityChecker(factory)

    report = await checker.run()

    assert report.episodes_scanned == 1
    assert report.episodes_valid == 1
    assert report.episodes_corrupted == 0
    assert report.new_compromised == []


async def test_cadena_manipulada_se_detecta_y_marca() -> None:
    """Si manipulamos el payload de un evento sin actualizar su self_hash,
    el checker lo detecta y marca el episodio como comprometido."""
    tenant = uuid4()
    ep_id = uuid4()
    ep = FakeEpisode(id=ep_id, tenant_id=tenant, estado="closed")
    events = _valid_chain_events(ep_id, tenant, n=3)

    # Manipular payload del segundo evento sin actualizar self_hash
    events[1].payload = {"content": "CONTENIDO_MODIFICADO"}

    factory = _FakeSessionFactory([ep], events)
    checker = IntegrityChecker(factory)

    report = await checker.run()

    assert report.episodes_scanned == 1
    assert report.episodes_valid == 0
    assert len(report.new_compromised) == 1
    assert report.new_compromised[0] == ep_id


async def test_ya_marcados_no_se_re_chequean() -> None:
    """Episodios ya marcados integrity_compromised=True pasan a
    already_compromised sin recomputar la cadena."""
    tenant = uuid4()
    ep = FakeEpisode(
        id=uuid4(),
        tenant_id=tenant,
        estado="integrity_compromised",
        integrity_compromised=True,
    )
    factory = _FakeSessionFactory([ep], [])
    checker = IntegrityChecker(factory)

    report = await checker.run()

    assert report.episodes_scanned == 1
    assert ep.id in report.already_compromised
    assert report.new_compromised == []


async def test_sin_episodios_report_vacio() -> None:
    factory = _FakeSessionFactory([], [])
    checker = IntegrityChecker(factory)
    report = await checker.run()
    assert report.episodes_scanned == 0
    assert report.episodes_valid == 0


async def test_reporte_summary_legible() -> None:
    tenant = uuid4()
    ep = FakeEpisode(id=uuid4(), tenant_id=tenant, estado="closed")
    events = _valid_chain_events(ep.id, tenant, n=2)
    factory = _FakeSessionFactory([ep], events)
    checker = IntegrityChecker(factory)

    report = await checker.run()
    summary = report.summary()
    assert "Episodios escaneados: 1" in summary
    assert "Íntegros: 1" in summary
    assert "Duración:" in summary
