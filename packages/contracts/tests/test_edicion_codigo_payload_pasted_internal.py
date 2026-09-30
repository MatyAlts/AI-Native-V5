"""`pasted_internal` en el Literal de `EdicionCodigoPayload.origin`.

Change `copiar-pegar-interno-en-el-episodio`. El portapapeles interno del
editor (web-student) distingue un pegado copiado DENTRO del episodio
(consigna o editor propio) de uno externo. El backend necesita aceptar ese
valor nuevo o rechaza el evento — ver `CodeEditor.tsx` y el proposal.

NO se agrega a `_EDICION_CODIGO_N4_ORIGINS` del event_labeler (test aparte,
`apps/classifier-service/tests/unit/test_event_labeler.py`): copiar el
nombre de una variable de la consigna no es apropiacion reflexiva.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from platform_contracts.ctr.events import EdicionCodigoPayload


def test_pasted_internal_es_un_origin_valido() -> None:
    payload = EdicionCodigoPayload(
        snapshot="x = 1",
        diff_chars=5,
        language="python",
        origin="pasted_internal",
    )
    assert payload.origin == "pasted_internal"


def test_los_origins_previos_siguen_aceptados() -> None:
    # Triangula contra una implementacion que reemplazara el Literal en vez
    # de extenderlo.
    for origen in ("student_typed", "copied_from_tutor", "pasted_external", "snippet_expanded"):
        payload = EdicionCodigoPayload(
            snapshot="x = 1", diff_chars=1, language="python", origin=origen
        )
        assert payload.origin == origen


def test_un_origin_inventado_sigue_rechazado() -> None:
    # Guardian: el Literal sigue siendo cerrado, no un string libre.
    with pytest.raises(ValidationError):
        EdicionCodigoPayload(
            snapshot="x = 1",
            diff_chars=1,
            language="python",
            origin="pasted_from_the_moon",
        )
