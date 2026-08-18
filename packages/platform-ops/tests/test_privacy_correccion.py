"""El derecho al olvido sobre la correccion asistida (tarea 5.8).

Lo que distingue esta parte del resto del olvido: **el artefacto y el PDF se
BORRAN, el pseudonimo se rota.** No es inconsistencia. El artefacto es el
codigo que escribio esa persona y el PDF lleva su nombre y la devolucion sobre
su trabajo — son el dato personal, no una referencia a el, y rotar un
identificador los dejaria igual de legibles. La fila de la correccion se
conserva disociada: que hubo una correccion es parte de la trazabilidad del
piloto; quien fue, no.
"""

from __future__ import annotations

from uuid import UUID

from platform_ops.privacy import anonymize_student

ALUMNO = UUID("11111111-1111-1111-1111-111111111111")


class FuenteConCorrecciones:
    """Un `data_source` que implementa TODO lo de correcciones."""

    def __init__(self, *, pdfs: list[str] | None = None, pdf_falla: set[str] | None = None):
        self.pdfs = pdfs if pdfs is not None else ["k1.pdf", "k2.pdf"]
        self.pdf_falla = pdf_falla or set()
        self.borrados: list[str] = []
        self.artefactos_borrados_de: UUID | None = None
        self.rotacion: tuple[UUID, UUID] | None = None
        self.borrado_externo_de: UUID | None = None

    async def list_episodes_by_student(self, pseudonym: UUID) -> list[dict]:
        return []

    async def list_events_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        return []

    async def list_classifications_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        return []

    async def update_episodes_pseudonym(self, original: UUID, new: UUID) -> int:
        return 0

    async def list_correcciones_by_student(self, pseudonym: UUID) -> list[dict]:
        return [{"pdf_storage_key": k} for k in self.pdfs]

    async def delete_pdf(self, storage_key: str) -> bool:
        if storage_key in self.pdf_falla:
            return False
        self.borrados.append(storage_key)
        return True

    async def delete_artefactos_by_student(self, pseudonym: UUID) -> int:
        self.artefactos_borrados_de = pseudonym
        return 3

    async def update_correcciones_pseudonym(self, original: UUID, new: UUID) -> int:
        self.rotacion = (original, new)
        return 2

    async def borrar_en_activeia(self, pseudonym: UUID) -> bool:
        self.borrado_externo_de = pseudonym
        return True


class FuenteVieja:
    """Un `data_source` de antes de este epic: no sabe de correcciones."""

    async def list_episodes_by_student(self, pseudonym: UUID) -> list[dict]:
        return []

    async def list_events_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        return []

    async def list_classifications_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        return []

    async def update_episodes_pseudonym(self, original: UUID, new: UUID) -> int:
        return 7


class TestOlvidoCompleto:
    async def test_borra_el_pdf_y_el_artefacto_y_rota_la_correccion(self) -> None:
        fuente = FuenteConCorrecciones()
        r = await anonymize_student(ALUMNO, fuente)

        assert r.pdfs_borrados == 2
        assert sorted(fuente.borrados) == ["k1.pdf", "k2.pdf"]
        assert r.artefactos_borrados == 3
        assert fuente.artefactos_borrados_de == ALUMNO
        assert r.correcciones_rotadas == 2

    async def test_la_correccion_se_rota_al_pseudonimo_NUEVO(self) -> None:
        """La fila queda, disociada: que hubo una correccion es trazabilidad
        del piloto, quien fue no."""
        fuente = FuenteConCorrecciones()
        r = await anonymize_student(ALUMNO, fuente)

        assert fuente.rotacion == (ALUMNO, r.new_pseudonym)
        assert r.new_pseudonym != ALUMNO

    async def test_pide_el_borrado_del_lado_de_active_ia(self) -> None:
        """El codigo salio del perimetro: borrarlo aca y dejarlo alla no es un
        olvido."""
        fuente = FuenteConCorrecciones()
        r = await anonymize_student(ALUMNO, fuente)

        assert fuente.borrado_externo_de == ALUMNO
        assert r.borrado_externo_ok is True


class TestUnOlvidoParcialSeReporta:
    async def test_un_pdf_que_no_se_puede_borrar_queda_listado(self) -> None:
        """Un olvido incompleto informado como completo es peor que uno que
        falla: el dato sigue ahi y nadie lo sabe."""
        fuente = FuenteConCorrecciones(pdf_falla={"k2.pdf"})
        r = await anonymize_student(ALUMNO, fuente)

        assert r.pdfs_borrados == 1
        assert r.pdfs_con_error == ["k2.pdf"]

    async def test_sin_endpoint_externo_el_informe_dice_None_y_no_True(self) -> None:
        """`None` significa "no se intento". Colapsarlo en `False` haria que el
        informe no distinga "Active-IA dijo que no" de "ni siquiera se le
        pregunto" — y de eso depende si queda una copia afuera.

        Se usa una subclase que levanta `NotImplementedError`, que es lo que
        hace el adaptador real mientras el endpoint no exista.
        """

        class SinBorradoExterno(FuenteConCorrecciones):
            async def borrar_en_activeia(self, pseudonym: UUID) -> bool:
                raise NotImplementedError("Active-IA no expone borrado por alumno")

        r = await anonymize_student(ALUMNO, SinBorradoExterno())
        assert r.borrado_externo_ok is None
        # Y el resto del olvido SI ocurrio: no se aborta por lo que falta.
        assert r.pdfs_borrados == 2
        assert r.artefactos_borrados == 3


class TestCompatibilidad:
    async def test_una_fuente_sin_correcciones_no_rompe_el_olvido(self) -> None:
        """Un adaptador viejo (o un servicio sin correcciones) tiene que
        completar la parte que SI sabe hacer, no reventar entero."""
        r = await anonymize_student(ALUMNO, FuenteVieja())

        assert r.episodes_updated == 7  # lo de siempre sigue funcionando
        assert r.artefactos_borrados == 0
        assert r.pdfs_borrados == 0
        assert r.borrado_externo_ok is None

    async def test_una_correccion_sin_pdf_no_cuenta_como_borrado(self) -> None:
        fuente = FuenteConCorrecciones(pdfs=[])
        r = await anonymize_student(ALUMNO, fuente)
        assert r.pdfs_borrados == 0
        assert r.pdfs_con_error == []
