"""Verificador de integridad del CTR como job batch.

Recorre episodios cerrados y recomputa su cadena de hashes. Cualquier
episodio cuya cadena no pueda validarse se marca `integrity_compromised=true`
y se emite un evento `ctr.integrity.violation` con los detalles.

Diseñado para correrse como Kubernetes CronJob cada N horas, o como
comando manual on-demand por el equipo de seguridad.

Uso:
    python -m ctr_service.workers.integrity_checker [--limit N] [--since-hours H]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update

from ctr_service.db.session import get_engine, get_session_factory
from ctr_service.metrics import ctr_episodes_integrity_compromised_total
from ctr_service.models import Episode, Event
from ctr_service.models.base import GENESIS_HASH
from ctr_service.services.hashing import compute_chain_hash, compute_self_hash

logger = logging.getLogger(__name__)


@dataclass
class VerificationReport:
    episodes_scanned: int
    episodes_valid: int
    episodes_corrupted: int
    new_compromised: list[UUID]  # los que detectamos ahora
    already_compromised: list[UUID]  # ya marcados antes
    duration_seconds: float

    def summary(self) -> str:
        lines = [
            f"Episodios escaneados: {self.episodes_scanned}",
            f"  Íntegros: {self.episodes_valid}",
            f"  Corruptos: {self.episodes_corrupted}",
            f"    Recién detectados: {len(self.new_compromised)}",
            f"    Ya marcados: {len(self.already_compromised)}",
            f"Duración: {self.duration_seconds:.2f}s",
        ]
        if self.new_compromised:
            lines.append("")
            lines.append("IDs recién marcados como comprometidos:")
            for eid in self.new_compromised[:20]:
                lines.append(f"  - {eid}")
            if len(self.new_compromised) > 20:
                lines.append(f"  ... y {len(self.new_compromised) - 20} más")
        return "\n".join(lines)


class IntegrityChecker:
    """Recorre episodios y verifica la cadena de cada uno."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def run(
        self,
        limit: int | None = None,
        since: datetime | None = None,
    ) -> VerificationReport:
        """Escanea episodios cerrados y verifica cadenas.

        Args:
            limit: max episodios a chequear (None = todos).
            since: solo episodios cerrados después de este timestamp.
        """
        start = datetime.now(UTC)
        new_compromised: list[UUID] = []
        already_compromised: list[UUID] = []
        valid = 0
        scanned = 0

        async with self.session_factory() as session:
            stmt = select(Episode).where(Episode.estado.in_(["closed", "integrity_compromised"]))
            if since:
                stmt = stmt.where(Episode.closed_at >= since)
            stmt = stmt.order_by(Episode.closed_at.desc())
            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            episodes = list(result.scalars().all())

        for ep in episodes:
            scanned += 1
            if ep.integrity_compromised:
                already_compromised.append(ep.id)
                continue

            is_valid = await self._verify_episode(ep)
            if is_valid:
                valid += 1
            else:
                logger.warning("integrity_violation episode_id=%s", ep.id)
                new_compromised.append(ep.id)
                await self._mark_compromised(ep.id, ep.tenant_id)

        duration = (datetime.now(UTC) - start).total_seconds()
        return VerificationReport(
            episodes_scanned=scanned,
            episodes_valid=valid,
            episodes_corrupted=len(new_compromised) + len(already_compromised),
            new_compromised=new_compromised,
            already_compromised=already_compromised,
            duration_seconds=duration,
        )

    async def _verify_episode(self, episode: Episode) -> bool:
        """Verifica la cadena criptográfica de un solo episodio.

        Returns True si toda la cadena es consistente, False si algún
        evento se manipuló o tiene hashes incorrectos.
        """
        async with self.session_factory() as session:
            # Setear tenant para RLS antes de leer
            from sqlalchemy import text

            await session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(episode.tenant_id)},
            )

            result = await session.execute(
                select(Event).where(Event.episode_id == episode.id).order_by(Event.seq)
            )
            events = list(result.scalars().all())

        if not events:
            # Episodio sin eventos: tratamos como íntegro (no se emitió nada)
            return True

        prev_chain = GENESIS_HASH
        for ev in events:
            event_dict = {
                "event_uuid": str(ev.event_uuid),
                "episode_id": str(ev.episode_id),
                "tenant_id": str(ev.tenant_id),
                "seq": ev.seq,
                "event_type": ev.event_type,
                "ts": ev.ts.isoformat().replace("+00:00", "Z"),
                "payload": ev.payload,
                "prompt_system_hash": ev.prompt_system_hash,
                "prompt_system_version": ev.prompt_system_version,
                "classifier_config_hash": ev.classifier_config_hash,
            }
            computed_self = compute_self_hash(event_dict)
            if computed_self != ev.self_hash:
                return False

            computed_chain = compute_chain_hash(ev.self_hash, prev_chain)
            if computed_chain != ev.chain_hash:
                return False
            prev_chain = ev.chain_hash

        return True

    async def _mark_compromised(self, episode_id: UUID, tenant_id: UUID) -> None:
        """Marca el episodio como comprometido + persiste.

        Emite la métrica `ctr_episodes_integrity_compromised_total{tenant_id}`
        con label tenant — episode_id NO entra como label (cardinalidad).
        Target estricto del piloto: 0. Cualquier incremento dispara I01 del
        runbook (`docs/pilot/runbook.md`).
        """
        async with self.session_factory() as session:
            from sqlalchemy import text

            await session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            await session.execute(
                update(Episode)
                .where(Episode.id == episode_id)
                .values(
                    integrity_compromised=True,
                    estado="integrity_compromised",
                )
            )
            await session.commit()

        ctr_episodes_integrity_compromised_total.add(
            1, {"tenant_id": str(tenant_id)}
        )


# ── CLI entry ───────────────────────────────────────────────────────────


async def run_cli(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    engine = get_engine()
    session_factory = get_session_factory()
    checker = IntegrityChecker(session_factory)

    since: datetime | None = None
    if args.since_hours is not None:
        since = datetime.now(UTC) - timedelta(hours=args.since_hours)

    try:
        report = await checker.run(limit=args.limit, since=since)
        print(report.summary())

        # Exit code:
        #   0 = todo íntegro
        #   1 = violaciones detectadas (CronJob las marca como alerta)
        #   2 = ya había violaciones pre-existentes (informativo, no alerta)
        if report.new_compromised:
            return 1
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verificador de integridad del CTR")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de episodios a verificar (None=todos)",
    )
    parser.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="Solo episodios cerrados en las últimas N horas (default: 24)",
    )
    args = parser.parse_args()
    exit_code = asyncio.run(run_cli(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
