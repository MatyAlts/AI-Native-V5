"""Exportación académica anonymizada para investigadores.

Produce un dataset del piloto con granularidad suficiente para análisis
empírico (inter-rater Kappa, correlaciones entre coherencias, detección
de patrones de apropiación) sin exponer identidades.

Estrategia de anonimización:
  - student_pseudonym se reemplaza por hash determinista con salt de
    investigación. Dos investigadores con el mismo salt pueden
    cross-referenciar; sin el salt, no se puede re-identificar.
  - Contenido textual (prompts, respuestas) se incluye pero opcional.
    Por default se excluye para minimizar superficie de riesgo.
  - comision_id se preserva (necesaria para agrupar cohorts).
  - tenant_id se reemplaza por alias corto ("UNSL_2026_P2") para
    facilitar publicación sin exponer UUIDs.

El resultado es un dict serializable a JSON o Parquet. En el pipeline
real (F7), un worker corre periódicamente y sube el dataset a un
bucket de solo-lectura para investigadores acreditados.

Uso:
    exporter = AcademicExporter(data_source, salt="pilot_unsl_2026")
    dataset = await exporter.export_cohort(
        comision_id=UUID("..."),
        include_prompts=False,
        period_days=90,
    )
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class EpisodeRecord:
    """Episodio anonimizado para investigación."""

    episode_alias: str  # hash corto estable
    student_alias: str  # hash del student_pseudonym + salt
    comision_id: UUID
    opened_at: str  # ISO
    closed_at: str | None
    duration_seconds: float | None
    total_events: int
    classifier_config_hash: str

    # Etiqueta N4 + 5 coherencias (lo que importa para el análisis)
    appropriation: str | None = None
    ct_summary: float | None = None
    ccd_mean: float | None = None
    ccd_orphan_ratio: float | None = None
    cii_stability: float | None = None
    cii_evolution: float | None = None

    # Métricas del episodio
    prompt_count: int = 0
    code_execution_count: int = 0
    annotation_count: int = 0
    reflection_count: int = 0

    # Opcionalmente, texto de prompts/respuestas (si include_prompts=True)
    prompts: list[dict] = field(default_factory=list)

    # ADR-035: reflexiones metacognitivas post-cierre. Por default los 3 campos
    # textuales (`que_aprendiste`, `dificultad_encontrada`, `que_haria_distinto`)
    # se reemplazan por "[redacted]". `prompt_version` y `tiempo_completado_ms`
    # se preservan siempre — son metadata no identificable. Solo con flag
    # explicito `include_reflections=True` los textos viajan integros y la
    # exportacion emite audit log structlog `reflections_exported_with_consent`.
    reflections: list[dict] = field(default_factory=list)


@dataclass
class CohortDataset:
    """Dataset exportado de una cohorte."""

    cohort_alias: str  # ej "UNSL_2026_P2_CA"
    exported_at: str
    period: dict[str, str]  # {"from": iso, "to": iso}
    schema_version: str
    salt_hash: str  # hash del salt usado (para reproducibilidad entre exports)
    total_episodes: int
    total_students: int
    episodes: list[EpisodeRecord] = field(default_factory=list)
    distribution_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_alias": self.cohort_alias,
            "exported_at": self.exported_at,
            "period": self.period,
            "schema_version": self.schema_version,
            "salt_hash": self.salt_hash,
            "total_episodes": self.total_episodes,
            "total_students": self.total_students,
            "distribution_summary": self.distribution_summary,
            "episodes": [
                {
                    "episode_alias": e.episode_alias,
                    "student_alias": e.student_alias,
                    "comision_id": str(e.comision_id),
                    "opened_at": e.opened_at,
                    "closed_at": e.closed_at,
                    "duration_seconds": e.duration_seconds,
                    "total_events": e.total_events,
                    "classifier_config_hash": e.classifier_config_hash,
                    "appropriation": e.appropriation,
                    "coherences": {
                        "ct_summary": e.ct_summary,
                        "ccd_mean": e.ccd_mean,
                        "ccd_orphan_ratio": e.ccd_orphan_ratio,
                        "cii_stability": e.cii_stability,
                        "cii_evolution": e.cii_evolution,
                    },
                    "event_counts": {
                        "prompts": e.prompt_count,
                        "code_executions": e.code_execution_count,
                        "annotations": e.annotation_count,
                        "reflections": e.reflection_count,
                    },
                    "prompts": e.prompts,
                    "reflections": e.reflections,
                }
                for e in self.episodes
            ],
        }


class _CohortDataSource:
    """Interface mínima. En producción lo implementa un adaptador sobre SQLA."""

    async def list_episodes_in_comision(self, comision_id: UUID, since: datetime) -> list[dict]:
        raise NotImplementedError

    async def list_events_for_episode(self, episode_id: UUID) -> list[dict]:
        raise NotImplementedError

    async def get_current_classification(self, episode_id: UUID) -> dict | None:
        raise NotImplementedError


class AcademicExporter:
    """Exporta un dataset académico anonimizado de una cohorte."""

    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        data_source: _CohortDataSource,
        salt: str,
        cohort_alias: str = "UNSL_PILOT",
    ) -> None:
        if not salt or len(salt) < 16:
            raise ValueError("salt debe tener al menos 16 chars para anonimización robusta")
        self.data_source = data_source
        self.salt = salt
        self.salt_hash = hashlib.sha256(salt.encode()).hexdigest()[:16]
        self.cohort_alias = cohort_alias

    def _pseudonymize(self, uuid: UUID, prefix: str = "") -> str:
        """Hash determinista: mismo UUID + mismo salt → mismo alias."""
        h = hashlib.sha256((self.salt + str(uuid)).encode()).hexdigest()
        return f"{prefix}{h[:12]}" if prefix else h[:12]

    async def export_cohort(
        self,
        comision_id: UUID,
        period_days: int = 90,
        include_prompts: bool = False,
        include_reflections: bool = False,
    ) -> CohortDataset:
        """Exporta la cohorte.

        Args:
            comision_id: comisión a exportar
            period_days: ventana de episodios cerrados
            include_prompts: si True, incluye texto de prompts/respuestas
              (INCREMENTA EL RIESGO DE RE-IDENTIFICACIÓN). Default False.
            include_reflections: ADR-035. Si True, los 3 campos textuales de
              `reflexion_completada` (que_aprendiste / dificultad_encontrada /
              que_haria_distinto) viajan integros en el dataset Y la exportacion
              emite audit log structlog `reflections_exported_with_consent`.
              Default False — los campos se reemplazan por "[redacted]" pero
              prompt_version y tiempo_completado_ms se preservan (metadata
              no identificable). El estudiante puede haber escrito info
              identificable en texto libre, asi que el opt-in requiere
              consentimiento explicito documentado.
        """
        now = datetime.now(UTC)
        since = now - timedelta(days=period_days)

        episodes_raw = await self.data_source.list_episodes_in_comision(comision_id, since)

        records: list[EpisodeRecord] = []
        students_seen: set[str] = set()
        distribution: dict[str, int] = {
            "delegacion_pasiva": 0,
            "apropiacion_superficial": 0,
            "apropiacion_reflexiva": 0,
            "sin_clasificar": 0,
        }

        for ep in episodes_raw:
            ep_id = UUID(ep["id"]) if isinstance(ep["id"], str) else ep["id"]
            student_pseudo = (
                UUID(ep["student_pseudonym"])
                if isinstance(ep["student_pseudonym"], str)
                else ep["student_pseudonym"]
            )

            # Contar eventos por tipo + recolectar prompts si corresponde
            events = await self.data_source.list_events_for_episode(ep_id)
            prompt_count = 0
            code_execution_count = 0
            annotation_count = 0
            reflection_count = 0
            prompt_records: list[dict] = []
            reflection_records: list[dict] = []

            opened_at = None
            closed_at = None

            for ev in events:
                et = ev["event_type"]
                if et == "prompt_enviado":
                    prompt_count += 1
                    if include_prompts:
                        prompt_records.append(
                            {
                                "seq": ev["seq"],
                                "ts": ev["ts"],
                                "content": ev.get("payload", {}).get("content", ""),
                                "prompt_kind": ev.get("payload", {}).get("prompt_kind"),
                            }
                        )
                elif et == "codigo_ejecutado":
                    code_execution_count += 1
                elif et == "anotacion_creada":
                    annotation_count += 1
                elif et == "reflexion_completada":
                    # ADR-035: side-channel post-cierre. Metadata siempre, textos
                    # solo con consent explicito (`include_reflections=True`).
                    reflection_count += 1
                    payload = ev.get("payload") or {}
                    reflection_records.append(
                        {
                            "seq": ev["seq"],
                            "ts": ev["ts"],
                            "prompt_version": payload.get("prompt_version"),
                            "tiempo_completado_ms": payload.get("tiempo_completado_ms"),
                            "que_aprendiste": (
                                payload.get("que_aprendiste", "")
                                if include_reflections
                                else "[redacted]"
                            ),
                            "dificultad_encontrada": (
                                payload.get("dificultad_encontrada", "")
                                if include_reflections
                                else "[redacted]"
                            ),
                            "que_haria_distinto": (
                                payload.get("que_haria_distinto", "")
                                if include_reflections
                                else "[redacted]"
                            ),
                        }
                    )
                elif et == "episodio_abierto":
                    opened_at = ev["ts"]
                elif et == "episodio_cerrado":
                    closed_at = ev["ts"]

            # Duración del episodio
            duration = None
            if opened_at and closed_at:
                from datetime import datetime as dt

                try:
                    o = dt.fromisoformat(opened_at.replace("Z", "+00:00"))
                    c = dt.fromisoformat(closed_at.replace("Z", "+00:00"))
                    duration = (c - o).total_seconds()
                except ValueError:
                    pass

            # Clasificación
            classification = await self.data_source.get_current_classification(ep_id)

            student_alias = self._pseudonymize(student_pseudo, prefix="s_")
            students_seen.add(student_alias)

            appropriation: str | None = None
            if classification:
                appropriation = classification.get("appropiation") or classification.get(
                    "appropriation"
                )
            key = appropriation if appropriation else "sin_clasificar"
            distribution[key] = distribution.get(key, 0) + 1

            record = EpisodeRecord(
                episode_alias=self._pseudonymize(ep_id, prefix="e_"),
                student_alias=student_alias,
                comision_id=comision_id,
                opened_at=opened_at or "",
                closed_at=closed_at,
                duration_seconds=duration,
                total_events=len(events),
                classifier_config_hash=(classification or {}).get("classifier_config_hash", ""),
                appropriation=appropriation,
                ct_summary=(classification or {}).get("ct_summary"),
                ccd_mean=(classification or {}).get("ccd_mean"),
                ccd_orphan_ratio=(classification or {}).get("ccd_orphan_ratio"),
                cii_stability=(classification or {}).get("cii_stability"),
                cii_evolution=(classification or {}).get("cii_evolution"),
                prompt_count=prompt_count,
                code_execution_count=code_execution_count,
                annotation_count=annotation_count,
                reflection_count=reflection_count,
                prompts=prompt_records,
                reflections=reflection_records,
            )
            records.append(record)

        # ADR-035: audit log obligatorio cuando los textos de reflexion viajan
        # integros. structlog (no logging.warning) — queryable en Loki.
        if include_reflections:
            total_reflections = sum(r.reflection_count for r in records)
            try:
                import structlog  # noqa: PLC0415

                structlog.get_logger().info(
                    "reflections_exported_with_consent",
                    cohort_alias=self.cohort_alias,
                    comision_id=str(comision_id),
                    total_episodes=len(records),
                    total_reflections=total_reflections,
                    salt_hash=self.salt_hash,
                )
            except ImportError:
                # Fallback al logger stdlib si structlog no esta disponible
                # (tests que no instalan platform_observability).
                logger.info(
                    "reflections_exported_with_consent cohort=%s comision=%s "
                    "episodes=%d reflections=%d",
                    self.cohort_alias,
                    str(comision_id),
                    len(records),
                    total_reflections,
                )

        return CohortDataset(
            cohort_alias=self.cohort_alias,
            exported_at=now.isoformat().replace("+00:00", "Z"),
            period={
                "from": since.isoformat().replace("+00:00", "Z"),
                "to": now.isoformat().replace("+00:00", "Z"),
            },
            schema_version=self.SCHEMA_VERSION,
            salt_hash=self.salt_hash,
            total_episodes=len(records),
            total_students=len(students_seen),
            episodes=records,
            distribution_summary=distribution,
        )
