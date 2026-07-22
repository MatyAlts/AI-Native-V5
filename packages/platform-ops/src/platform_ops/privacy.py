"""Privacy controls — export de datos y right to be forgotten.

Dos funciones principales según GDPR / Ley 25.326 (Argentina):

  1. `export_student_data(student_pseudonym)` — recolecta TODOS los datos
     asociados a un estudiante específico y devuelve un JSON firmado.
     Incluye: eventos CTR, clasificaciones N4, episodios, materiales
     subidos por el estudiante (si aplica).

  2. `anonymize_student(student_pseudonym)` — deja los datos en forma
     agregada pero DESVINCULADOS del estudiante. Reemplaza el
     `student_pseudonym` por un nuevo UUID aleatorio (rotación de
     pseudónimo). Los eventos CTR quedan en la cadena (no se pueden
     borrar sin romper la integridad criptográfica) pero ya no son
     identificables con el estudiante original.

El "right to be forgotten" estricto (DELETE completo) NO es compatible
con la append-only del CTR. En su lugar ofrecemos disociación, que es
lo que permite la regulación cuando hay interés legítimo en preservar
el registro auditable de una interacción (art. 17.3.e GDPR).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass
class ExportedData:
    """Paquete exportable de datos de un estudiante."""

    export_id: UUID
    student_pseudonym: UUID
    exported_at: datetime
    episodes: list[dict[str, Any]] = field(default_factory=list)
    classifications: list[dict[str, Any]] = field(default_factory=list)
    materials_uploaded: list[dict[str, Any]] = field(default_factory=list)
    signature_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_id": str(self.export_id),
            "student_pseudonym": str(self.student_pseudonym),
            "exported_at": self.exported_at.isoformat().replace("+00:00", "Z"),
            "episodes": self.episodes,
            "classifications": self.classifications,
            "materials_uploaded": self.materials_uploaded,
            "signature_hash": self.signature_hash,
        }

    def compute_signature(self) -> str:
        """Hash SHA-256 del contenido (sin el signature) para verificar integridad."""
        body = {k: v for k, v in self.to_dict().items() if k != "signature_hash"}
        canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class AnonymizationReport:
    original_pseudonym: UUID
    new_pseudonym: UUID
    episodes_updated: int
    classifications_preserved: int
    events_untouched: int  # cadena CTR inmutable
    performed_at: datetime


# ── Interfaces mínimas para testeo sin DB ──────────────────────────────


class _DataSource:
    """Contract mínimo. En prod lo implementa un adaptador que toca SQLA."""

    async def list_episodes_by_student(self, pseudonym: UUID) -> list[dict]:
        raise NotImplementedError

    async def list_events_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        raise NotImplementedError

    async def list_classifications_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        raise NotImplementedError

    async def list_materials_by_uploader(self, user_id: UUID) -> list[dict]:
        raise NotImplementedError

    async def update_episodes_pseudonym(self, original: UUID, new: UUID) -> int:
        """Actualiza el pseudónimo en los episodios y devuelve cuántos cambió."""
        raise NotImplementedError


# ── Export ────────────────────────────────────────────────────────────


async def export_student_data(
    student_pseudonym: UUID,
    data_source: _DataSource,
    include_materials: bool = False,
    uploader_id: UUID | None = None,
) -> ExportedData:
    """Exporta todos los datos asociados al student_pseudonym."""
    export = ExportedData(
        export_id=uuid4(),
        student_pseudonym=student_pseudonym,
        exported_at=datetime.now(UTC),
    )

    # 1. Episodios del estudiante
    episodes = await data_source.list_episodes_by_student(student_pseudonym)
    export.episodes = episodes

    if episodes:
        episode_ids = [UUID(e["id"]) if isinstance(e["id"], str) else e["id"] for e in episodes]

        # 2. Clasificaciones de esos episodios
        classifications = await data_source.list_classifications_by_episodes(episode_ids)
        export.classifications = classifications

        # 3. Eventos CTR (los embeddemos dentro del episodio correspondiente)
        events = await data_source.list_events_by_episodes(episode_ids)
        events_by_episode: dict[str, list[dict]] = {}
        for ev in events:
            ep_id = str(ev["episode_id"])
            events_by_episode.setdefault(ep_id, []).append(ev)
        for ep in export.episodes:
            ep["events"] = events_by_episode.get(str(ep["id"]), [])

    # 4. Materiales (solo si el estudiante es uploader — caso raro)
    if include_materials and uploader_id:
        export.materials_uploaded = await data_source.list_materials_by_uploader(uploader_id)

    # 5. Firma
    export.signature_hash = export.compute_signature()
    return export


# ── Anonimización ─────────────────────────────────────────────────────


async def anonymize_student(
    student_pseudonym: UUID,
    data_source: _DataSource,
) -> AnonymizationReport:
    """Rota el pseudónimo del estudiante para disociar datos preservados.

    Propiedad clave: los eventos CTR ya persistidos NO se tocan. Su hash
    canónico incluye el student_pseudonym del payload, por lo que
    cambiar ese campo rompería la cadena criptográfica. En su lugar
    rotamos el pseudónimo SOLO en los objetos derivados que permiten
    UPDATE (`episodes.student_pseudonym`).

    El CTR queda sin modificar pero los eventos dejan de ser vinculables
    externamente al estudiante: sin la fila del episodio (que ahora tiene
    un nuevo pseudónimo), no hay forma de ir del estudiante original a
    los eventos.

    Alternativa más estricta (futuro): tombstone rows que marcan el
    episodio como 'olvidado' + redacción de payloads sensibles en DB (no
    en el hash, que queda inmutable como evidencia de que *algo* ocurrió).
    """
    new_pseudonym = uuid4()

    # 1. Contar episodios asociados
    episodes = await data_source.list_episodes_by_student(student_pseudonym)
    episode_ids = [UUID(e["id"]) if isinstance(e["id"], str) else e["id"] for e in episodes]

    # 2. Actualizar el pseudónimo en esos episodios
    updated = await data_source.update_episodes_pseudonym(
        original=student_pseudonym, new=new_pseudonym
    )

    # 3. Las clasificaciones ya apuntan por episode_id; no necesitan cambio.
    classifications = await data_source.list_classifications_by_episodes(episode_ids)

    # 4. Los eventos CTR quedan sin tocar
    events = await data_source.list_events_by_episodes(episode_ids)

    return AnonymizationReport(
        original_pseudonym=student_pseudonym,
        new_pseudonym=new_pseudonym,
        episodes_updated=updated,
        classifications_preserved=len(classifications),
        events_untouched=len(events),
        performed_at=datetime.now(UTC),
    )
