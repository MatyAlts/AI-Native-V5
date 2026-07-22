"""Tests de privacy: export de datos + anonimización.

Usa un `FakeDataSource` en memoria para verificar la lógica sin DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from platform_ops.privacy import (
    anonymize_student,
    export_student_data,
)


@dataclass
class FakeDataSource:
    episodes: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    classifications: list[dict] = field(default_factory=list)
    materials: list[dict] = field(default_factory=list)
    pseudonym_updates: list[tuple[UUID, UUID]] = field(default_factory=list)

    async def list_episodes_by_student(self, pseudonym: UUID) -> list[dict]:
        return [e for e in self.episodes if UUID(e["student_pseudonym"]) == pseudonym]

    async def list_events_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        ids_set = {str(i) for i in episode_ids}
        return [e for e in self.events if str(e["episode_id"]) in ids_set]

    async def list_classifications_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        ids_set = {str(i) for i in episode_ids}
        return [c for c in self.classifications if str(c["episode_id"]) in ids_set]

    async def list_materials_by_uploader(self, user_id: UUID) -> list[dict]:
        return [m for m in self.materials if UUID(m["uploaded_by"]) == user_id]

    async def update_episodes_pseudonym(self, original: UUID, new: UUID) -> int:
        self.pseudonym_updates.append((original, new))
        count = 0
        for ep in self.episodes:
            if UUID(ep["student_pseudonym"]) == original:
                ep["student_pseudonym"] = str(new)
                count += 1
        return count


def _sample_student_data():
    student = uuid4()
    episode1_id = uuid4()
    episode2_id = uuid4()
    ds = FakeDataSource(
        episodes=[
            {
                "id": str(episode1_id),
                "student_pseudonym": str(student),
                "comision_id": str(uuid4()),
                "estado": "closed",
            },
            {
                "id": str(episode2_id),
                "student_pseudonym": str(student),
                "comision_id": str(uuid4()),
                "estado": "closed",
            },
        ],
        events=[
            {"episode_id": str(episode1_id), "seq": 0, "event_type": "episodio_abierto"},
            {"episode_id": str(episode1_id), "seq": 1, "event_type": "prompt_enviado"},
            {"episode_id": str(episode2_id), "seq": 0, "event_type": "episodio_abierto"},
        ],
        classifications=[
            {"episode_id": str(episode1_id), "appropriation": "apropiacion_reflexiva"},
        ],
    )
    return ds, student, [episode1_id, episode2_id]


# ── Export ────────────────────────────────────────────────────────────


async def test_export_incluye_todos_los_episodios() -> None:
    ds, student, _ = _sample_student_data()
    export = await export_student_data(student, ds)
    assert len(export.episodes) == 2
    assert export.student_pseudonym == student


async def test_export_embebe_eventos_en_cada_episodio() -> None:
    ds, student, _ = _sample_student_data()
    export = await export_student_data(student, ds)
    # episode1 tiene 2 eventos, episode2 tiene 1
    ep1 = next(e for e in export.episodes if len(e.get("events", [])) == 2)
    ep2 = next(e for e in export.episodes if len(e.get("events", [])) == 1)
    assert ep1["events"][0]["event_type"] == "episodio_abierto"
    assert ep2["events"][0]["event_type"] == "episodio_abierto"


async def test_export_incluye_clasificaciones_asociadas() -> None:
    ds, student, _ = _sample_student_data()
    export = await export_student_data(student, ds)
    assert len(export.classifications) == 1
    assert export.classifications[0]["appropriation"] == "apropiacion_reflexiva"


async def test_export_firma_hash_reproducible() -> None:
    """El signature_hash debe ser determinista dado el mismo contenido."""
    ds, student, _ = _sample_student_data()
    export = await export_student_data(student, ds)
    # Recomputar debe dar el mismo hash (sin modificar nada)
    original_hash = export.signature_hash
    assert export.compute_signature() == original_hash
    assert len(original_hash) == 64


async def test_export_de_estudiante_sin_datos_devuelve_estructura_vacia() -> None:
    ds = FakeDataSource()
    export = await export_student_data(uuid4(), ds)
    assert export.episodes == []
    assert export.classifications == []
    assert export.signature_hash != ""  # firma sobre lista vacía sigue siendo válida


# ── Anonimización ────────────────────────────────────────────────────


async def test_anonymize_rota_pseudonymo_en_episodios() -> None:
    ds, student, _ = _sample_student_data()
    original_events_count = len(ds.events)

    report = await anonymize_student(student, ds)

    assert report.original_pseudonym == student
    assert report.new_pseudonym != student
    assert report.episodes_updated == 2  # los 2 episodios
    assert report.events_untouched == original_events_count  # cadena intacta

    # Episodios ya apuntan al nuevo pseudónimo
    for ep in ds.episodes:
        assert UUID(ep["student_pseudonym"]) == report.new_pseudonym


async def test_anonymize_preserva_cadena_ctr() -> None:
    """CRÍTICO: los eventos CTR persistidos no se tocan, porque cambiar
    el student_pseudonym en un evento rompería su self_hash y con eso
    la cadena criptográfica."""
    ds, student, _ = _sample_student_data()
    original_events = [dict(e) for e in ds.events]

    await anonymize_student(student, ds)

    # Eventos idénticos al snapshot anterior
    assert ds.events == original_events


async def test_anonymize_sin_episodios_no_hace_nada_malo() -> None:
    ds = FakeDataSource()
    unknown_student = uuid4()

    report = await anonymize_student(unknown_student, ds)

    assert report.episodes_updated == 0
    assert report.events_untouched == 0
    assert report.new_pseudonym != unknown_student


async def test_dos_anonymizes_producen_pseudonymos_distintos() -> None:
    ds = FakeDataSource()
    student = uuid4()

    r1 = await anonymize_student(student, ds)
    r2 = await anonymize_student(student, ds)

    assert r1.new_pseudonym != r2.new_pseudonym  # UUIDs random siempre únicos
