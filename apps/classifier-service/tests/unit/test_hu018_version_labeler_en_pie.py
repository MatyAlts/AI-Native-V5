"""Aceptacion HU-018, version del labeler en el pie (orquestador, antes de
construir; el constructor no la modifica). Juani (22/11): "vos terminas todo".

Hallazgo F04 de HU-014: el pie del alumno decia "labeler: 1.2.0" con el
labeler en 1.3.0. El valor estaba escrito a mano en el componente compartido.

C05  La version que muestra `AuditFooter` es la de `LABELER_VERSION`.
"""

from __future__ import annotations

import re
from pathlib import Path

from classifier_service.services.event_labeler import LABELER_VERSION

RAIZ = Path(__file__).resolve().parents[4]
PIE = RAIZ / "packages" / "ui" / "src" / "components" / "AuditFooter.tsx"


def test_c05_el_pie_muestra_la_version_vigente_del_labeler() -> None:
    texto = PIE.read_text(encoding="utf-8")
    versiones = set(re.findall(r'LABELER_VERSION\s*=\s*"([0-9.]+)"', texto))
    assert versiones == {LABELER_VERSION}, (
        f"AuditFooter declara {versiones or 'ninguna'} y el labeler vigente es {LABELER_VERSION}"
    )
