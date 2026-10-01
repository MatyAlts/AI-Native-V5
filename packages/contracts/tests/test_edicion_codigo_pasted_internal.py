"""`pasted_internal` en el contrato de `edicion_codigo`.

El valor lo emite `web-student` cuando el alumno pega codigo que el mismo
copio DENTRO del editor (portapapeles interno, change
`portapapeles-interno-editor`). Si el contrato no lo acepta, el evento se
rechaza en el borde y la edicion desaparece de la cadena del CTR — se pierde
justo el tramo que explica de donde salio un bloque de codigo.
"""

from __future__ import annotations

import pytest
from platform_contracts.ctr.events import EdicionCodigoPayload
from pydantic import ValidationError


def _payload(origin: str | None) -> EdicionCodigoPayload:
    return EdicionCodigoPayload(
        snapshot="a = 1\na = 1",
        diff_chars=6,
        language="python",
        origin=origin,  # type: ignore[arg-type]
    )


def test_acepta_pasted_internal() -> None:
    assert _payload("pasted_internal").origin == "pasted_internal"


@pytest.mark.parametrize(
    "origin",
    ["student_typed", "copied_from_tutor", "pasted_external", "snippet_expanded", None],
)
def test_los_origenes_que_ya_existian_siguen_aceptados(origin: str | None) -> None:
    """Agregar un valor al Literal no puede sacar ninguno de los de antes.

    Sin este guardian, reescribir el Literal y perder un valor en el camino
    rompe el ingest de un tipo de edicion entero, y se nota recien en
    produccion cuando los eventos empiezan a rebotar.
    """
    assert _payload(origin).origin == origin


def test_sigue_rechazando_un_origen_inventado() -> None:
    """El Literal tiene que seguir siendo cerrado.

    Si se abriera a `str`, un typo del frontend (`pasted_internl`) entraria a
    la cadena firmada y el labeler lo mandaria al fallback N2 sin que nadie se
    entere.
    """
    with pytest.raises(ValidationError):
        _payload("pasted_interno_con_typo")
