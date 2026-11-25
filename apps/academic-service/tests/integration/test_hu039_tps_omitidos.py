"""Aceptacion HU-039 (orquestador, antes de construir; el constructor no la
modifica). Hallazgo de la recorrida como docente del 25/11: al aplicar una
plantilla, los TPs cuyo `codigo` ya existe en la comision destino se saltean
(correcto: no se pisa nada) pero la respuesta no lo dice; solo queda en el
audit log, y el docente no entiende por que una unidad quedo sin TPs.

Contrato:
  - `AplicacionPlantillaOut.tps_omitidos: list[str]` (codigos salteados, por
    defecto lista vacia).
  - `PlantillaCampusService.aplicar` devuelve `tps_omitidos` en el resultado
    (el mismo valor que ya va al audit log).

C14  La respuesta de aplicar informa los TPs que no se crearon.
"""

from __future__ import annotations

from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[2]


def test_c14_el_esquema_lleva_tps_omitidos() -> None:
    from academic_service.schemas.plantilla_campus import AplicacionPlantillaOut

    out = AplicacionPlantillaOut(
        unidades_creadas=3,
        unidades_omitidas=[],
        tps_creados=1,
        bienvenida_aplicada=True,
        tps_omitidos=["TP-01", "TP-02"],
    )
    assert out.tps_omitidos == ["TP-01", "TP-02"]
    sin = AplicacionPlantillaOut(
        unidades_creadas=0, unidades_omitidas=[], tps_creados=0, bienvenida_aplicada=False
    )
    assert sin.tps_omitidos == []


def test_c14_el_servicio_devuelve_tps_omitidos() -> None:
    fuente = (
        RAIZ_SERVICIO / "src/academic_service/services/plantilla_campus_service.py"
    ).read_text(encoding="utf-8")
    inicio = fuente.index("resultado = {")
    fin = fuente.index("}", inicio)
    assert '"tps_omitidos"' in fuente[inicio:fin], (
        "el resultado de aplicar no devuelve tps_omitidos"
    )
