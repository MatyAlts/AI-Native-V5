"""Ejecuta el derecho al olvido de un alumno del piloto (incidente I06).

POR QUE EXISTE ESTE SCRIPT
--------------------------

El runbook I06 decia, textual:

    report = anonymize_student(student_pseudonym=UUID("..."),
                               data_source=academic_data_source)

**`academic_data_source` no existe en ningun lado del repo.** El protocolo
`_DataSource` de `platform_ops.privacy` solo lo implementan archivos de test.
O sea que el unico procedimiento documentado para cumplir un compromiso del
consentimiento firmado no era ejecutable: quien lo intentara se comia un
`NameError` — y en el mejor caso, si armaba una fuente a mano sin los metodos
de la correccion asistida, `_olvidar_correccion_asistida` caia en su guard de
`hasattr` y devolvia un informe EXITOSO con todo en cero, indistinguible del de
un alumno que efectivamente no tenia correcciones. El codigo del alumno, los
PDF con su nombre y la salida real de su programa seguian en la base.

Este script arma la fuente de verdad y la cablea al adaptador de la correccion
asistida (`OlvidoCorreccionAdapter`), que hasta ahora solo se instanciaba en
tests.

QUE BORRA Y QUE NO
------------------

Todo lo que MUTA vive en `academic_main` y lo cubre este script:

  - `episodes.student_pseudonym`      -> se ROTA (el CTR queda intacto: su hash
                                        incluye el pseudonimo y tocarlo romperia
                                        la cadena criptografica)
  - `entrega_artefactos`              -> se BORRA (es el codigo que escribio)
  - `entregas.artefacto_sha256`       -> se BORRA
  - `correcciones_ia.tests_snapshot`  -> se VACIA (lleva la salida real de su
                                        programa, hasta 2000 chars por caso)
  - `correcciones_ia.desglose`        -> se VACIA (la devolucion sobre su trabajo)
  - `correcciones_ia.artefacto_sha256`-> se VACIA
  - el PDF de devolucion              -> se BORRA del storage

Lo que NO hace, y el informe lo dice en vez de callarlo:

  - **No cuenta eventos del CTR ni clasificaciones.** Viven en `ctr_store` y
    `classifier_db`, otras bases. `anonymize_student` solo los CUENTA para el
    informe (pasos 3 y 4, de lectura), asi que no tocarlos no deja nada sin
    borrar — pero los contadores salen en cero y eso hay que leerlo como "no
    medido", no como "no habia".
  - **No borra la copia que quedo en Active-IA.** Ellos todavia no exponen
    borrado por alumno (pedido 3.6). El informe imprime los
    `external_entrega_id` con los que se puede encontrar y borrar a mano desde
    su panel. Mientras eso siga asi, el olvido de este sistema es INCOMPLETO y
    el script lo dice con todas las letras.

USO
---

    ACADEMIC_DB_URL=postgresql+asyncpg://... \\
        uv run python scripts/olvidar-alumno.py <student_pseudonym> <tenant_id>

    # Ver que haria, sin escribir nada:
    ... uv run python scripts/olvidar-alumno.py <pseudonym> <tenant_id> --dry-run

Verificar identidad del solicitante ANTES de correrlo (firma + DNI contra el
consentimiento archivado). El script no lo puede hacer por vos.
"""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "apps", "evaluation-service", "src")
)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "platform-ops", "src"))

from evaluation_service.services.olvido import OlvidoCorreccionAdapter
from platform_ops.privacy import anonymize_student


class FuenteAcademica:
    """La fuente de verdad de `anonymize_student` sobre `academic_main`.

    Delega en `OlvidoCorreccionAdapter` todo lo de la correccion asistida: ese
    adaptador ya sabe la asimetria (el artefacto y el PDF se BORRAN, la fila de
    la correccion se ROTA) y no tiene sentido reimplementarla acá.
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._correccion = OlvidoCorreccionAdapter(db, tenant_id)

    # ── Episodios (lo unico que este script rota fuera de la correccion) ──

    async def list_episodes_by_student(self, pseudonym: UUID) -> list[dict]:
        rows = await self._db.execute(
            text("SELECT id FROM episodes WHERE tenant_id = :t AND student_pseudonym = :p"),
            {"t": str(self._tenant_id), "p": str(pseudonym)},
        )
        return [{"id": r[0]} for r in rows.all()]

    async def update_episodes_pseudonym(self, original: UUID, new: UUID) -> int:
        res = await self._db.execute(
            text(
                "UPDATE episodes SET student_pseudonym = :n "
                "WHERE tenant_id = :t AND student_pseudonym = :o"
            ),
            {"n": str(new), "t": str(self._tenant_id), "o": str(original)},
        )
        return int(getattr(res, "rowcount", 0) or 0)

    # ── Solo se CUENTAN para el informe (pasos 3 y 4, de lectura) ─────────
    #
    # Viven en `ctr_store` y `classifier_db`. No tocarlos es correcto —el CTR
    # es append-only por diseño— pero los contadores salen en cero, y eso se
    # lee como "no medido" y no como "no habia". El script lo aclara al final.

    async def list_events_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        return []

    async def list_classifications_by_episodes(self, episode_ids: list[UUID]) -> list[dict]:
        return []

    async def list_materials_by_uploader(self, user_id: UUID) -> list[dict]:
        return []

    # ── Correccion asistida: delega en el adaptador del evaluation-service ─

    async def list_correcciones_by_student(self, pseudonym: UUID) -> list[dict]:
        return await self._correccion.list_correcciones_by_student(pseudonym)

    async def delete_artefactos_by_student(self, pseudonym: UUID) -> int:
        return await self._correccion.delete_artefactos_by_student(pseudonym)

    async def update_correcciones_pseudonym(self, original: UUID, new: UUID) -> int:
        return await self._correccion.update_correcciones_pseudonym(original, new)

    async def delete_pdf(self, storage_key: str) -> bool:
        return await self._correccion.delete_pdf(storage_key)

    async def borrar_en_activeia(self, pseudonym: UUID) -> bool:
        return await self._correccion.borrar_en_activeia(pseudonym)


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if len(args) != 2:
        print(__doc__)
        return 2

    pseudonym, tenant_id = UUID(args[0]), UUID(args[1])
    dsn = os.environ.get("ACADEMIC_DB_URL")
    if not dsn:
        print("ERROR: falta ACADEMIC_DB_URL", file=sys.stderr)
        return 3

    engine = create_async_engine(dsn)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)}
        )
        fuente = FuenteAcademica(db, tenant_id)
        report = await anonymize_student(pseudonym, fuente)

        if dry_run:
            await db.rollback()
            print("\n[DRY-RUN] nada se escribio.\n")
        else:
            await db.commit()
    await engine.dispose()

    print("=" * 68)
    print(f"OLVIDO DE {pseudonym}")
    print("=" * 68)
    print(f"  pseudonimo nuevo        : {report.new_pseudonym}")
    print(f"  episodios rotados       : {report.episodes_updated}")
    print(f"  artefactos borrados     : {report.artefactos_borrados}")
    print(f"  PDF borrados            : {report.pdfs_borrados}")
    print(f"  correcciones disociadas : {report.correcciones_rotadas}")
    print(f"  ejecutado               : {report.performed_at.isoformat()}")

    if report.pdfs_con_error:
        print("\n  [!] PDF que NO se pudieron borrar (siguen en el storage):")
        for k in report.pdfs_con_error:
            print(f"        {k}")

    print("\n  Lo que este script NO cubre:")
    print("    - eventos del CTR y clasificaciones: viven en otras bases y")
    print("      `anonymize_student` solo los CUENTA. Los ceros de arriba son")
    print("      'no medido', no 'no habia'. El CTR queda intacto a proposito:")
    print("      su hash incluye el pseudonimo y tocarlo rompe la cadena.")
    if report.borrado_externo_ok is None:
        print("    - la copia en Active-IA: NO se intento (no exponen borrado")
        print("      por alumno todavia). Hay que borrarla a mano desde su panel.")
        if report.ids_externos_a_borrar:
            print("      Buscar por estos id de entrega:")
            for i in report.ids_externos_a_borrar:
                print(f"        {i}")
        else:
            print("      (este alumno no tiene entregas subidas alla)")

    incompleto = bool(report.pdfs_con_error) or report.borrado_externo_ok is None
    print("\n  ESTADO: " + ("INCOMPLETO — leer arriba" if incompleto else "completo"))
    print("=" * 68)
    return 1 if incompleto and not dry_run else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
