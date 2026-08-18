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

import contextlib
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
    # Lo que agrega la correccion asistida (Epic 5 de `correccion-activeia`):
    # el codigo que el alumno entrego, y lo que se mando a un servicio externo.
    # Cuentan aparte de los episodios porque la garantia es distinta: el CTR se
    # disocia rotando el pseudonimo, esto se BORRA.
    artefactos_borrados: int = 0
    correcciones_rotadas: int = 0
    pdfs_borrados: int = 0
    # PDF que no se pudieron borrar del storage. Un olvido incompleto que se
    # reporta como completo es peor que uno que falla: el dato sigue ahi y
    # nadie lo sabe.
    pdfs_con_error: list[str] = field(default_factory=list)
    # Si se pidio el borrado del lado de Active-IA, y si contesto. `None` =
    # no se intento (la integracion no expone el endpoint todavia).
    borrado_externo_ok: bool | None = None
    performed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


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

    # ── Correccion asistida ────────────────────────────────────────────
    #
    # Estos tres son OPCIONALES: un `data_source` que no los implemente
    # (los tests viejos, o un servicio que no tenga correcciones) deja el
    # informe en cero en vez de romper. Pero si los implementa a medias, el
    # informe lo dice — un olvido parcial reportado como completo es peor
    # que uno que falla.

    async def list_correcciones_by_student(self, pseudonym: UUID) -> list[dict]:
        """Las correcciones del alumno, con su `pdf_storage_key`."""
        raise NotImplementedError

    async def delete_artefactos_by_student(self, pseudonym: UUID) -> int:
        """Borra el codigo entregado. Devuelve cuantas filas borro.

        Se BORRA y no se rota: el artefacto ES el dato personal (el codigo que
        escribio esa persona), no una referencia a el. Rotar el pseudonimo lo
        dejaria igual de legible.
        """
        raise NotImplementedError

    async def update_correcciones_pseudonym(self, original: UUID, new: UUID) -> int:
        """Rota el pseudonimo en las correcciones."""
        raise NotImplementedError

    async def delete_pdf(self, storage_key: str) -> bool:
        """Borra un PDF del storage. `True` si quedo borrado."""
        raise NotImplementedError

    async def borrar_en_activeia(self, pseudonym: UUID) -> bool:
        """Pide el borrado del alumno del lado de Active-IA.

        Depende del pedido 3.6 de `activeia-cambios-pedidos.md`. Mientras el
        endpoint no exista, el adaptador puede no implementarlo y el informe
        queda con `borrado_externo_ok=None` — que significa "no se intento",
        no "salio bien".
        """
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

    # 5. La correccion asistida. Va DESPUES de lo anterior y en su propio
    #    bloque: si el `data_source` no la implementa, el resto del olvido ya
    #    ocurrio y el informe lo dice con ceros, en vez de perderse entero.
    extra = await _olvidar_correccion_asistida(student_pseudonym, new_pseudonym, data_source)

    return AnonymizationReport(
        original_pseudonym=student_pseudonym,
        new_pseudonym=new_pseudonym,
        episodes_updated=updated,
        classifications_preserved=len(classifications),
        events_untouched=len(events),
        performed_at=datetime.now(UTC),
        **extra,
    )


async def _olvidar_correccion_asistida(
    original: UUID, nuevo: UUID, data_source: _DataSource
) -> dict:
    """Borra el artefacto y los PDF, y rota el pseudonimo en las correcciones.

    **El artefacto y el PDF se BORRAN; el pseudonimo se rota.** No es
    inconsistencia: el artefacto es el codigo que escribio esa persona y el
    PDF lleva su nombre y la devolucion sobre su trabajo — son el dato
    personal, no una referencia a el, y rotar un identificador los dejaria
    igual de legibles. La fila de la correccion, en cambio, se conserva
    disociada: que hubo una correccion es parte de la trazabilidad del
    piloto, quien fue no.

    Un PDF que no se puede borrar se REPORTA, no se traga. Un olvido
    incompleto que se informa como completo es peor que uno que falla.
    """
    out: dict = {
        "artefactos_borrados": 0,
        "correcciones_rotadas": 0,
        "pdfs_borrados": 0,
        "pdfs_con_error": [],
        "borrado_externo_ok": None,
    }

    # `AttributeError` ademas de `NotImplementedError`: los `data_source` de
    # este modulo son duck-typed (los tests usan un fake que no hereda de
    # `_DataSource`), asi que "no implementa esto" llega de las dos formas.
    # Tratar solo una hacia que un adaptador sin correcciones reventara el
    # olvido ENTERO en vez de completar la parte que si sabe hacer.
    try:
        correcciones = await data_source.list_correcciones_by_student(original)
    except (NotImplementedError, AttributeError):
        return out

    for c in correcciones:
        key = c.get("pdf_storage_key")
        if not key:
            continue
        try:
            ok = await data_source.delete_pdf(str(key))
        except (NotImplementedError, AttributeError):
            ok = False
        except Exception:
            ok = False
        if ok:
            out["pdfs_borrados"] += 1
        else:
            out["pdfs_con_error"].append(str(key))

    with contextlib.suppress(NotImplementedError, AttributeError):
        out["artefactos_borrados"] = await data_source.delete_artefactos_by_student(original)

    with contextlib.suppress(NotImplementedError, AttributeError):
        out["correcciones_rotadas"] = await data_source.update_correcciones_pseudonym(
            original, nuevo
        )

    # El borrado del otro lado depende de un endpoint que Active-IA todavia no
    # expone. `None` significa "no se intento" y NO "salio bien": el informe
    # tiene que poder distinguirlos, porque de eso depende si el olvido esta
    # completo o si queda una copia afuera.
    try:
        out["borrado_externo_ok"] = await data_source.borrar_en_activeia(original)
    except (NotImplementedError, AttributeError):
        out["borrado_externo_ok"] = None

    return out
