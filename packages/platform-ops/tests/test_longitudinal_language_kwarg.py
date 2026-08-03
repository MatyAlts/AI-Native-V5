"""Contrato del kwarg `language` de `build_trajectories`.

`build_trajectories` promete en su docstring soportar DOS formas de data
source, y la promesa no estaba cubierta por ningun test:

  - los que conocen `language` (el `RealLongitudinalDataSource` de produccion),
  - los que no (los `FakeDataSource` de `test_longitudinal.py`, y cualquier
    implementacion anterior a `multi-language-research-integrity`).

Por eso el reenvio es condicional: `language` solo se pasa si viene seteado.

Esto es lo que mypy esta marcando en CI hoy, y no es un falso positivo del
linter — es que la interfaz declarada quedo desincronizada de todas sus
implementaciones:

    platform_ops/longitudinal.py:191: error: Unexpected keyword argument
      "language" for "list_classifications_grouped_by_student" of "_DataSource"

`_DataSource` declara el metodo SIN `language`, pero `build_trajectories` lo
llama CON `language`, y las dos implementaciones reales lo aceptan. Como
`_DataSource` es una clase comun y no un `Protocol`, mypy exige herencia
nominal: ningun data source real "es" un `_DataSource`, asi que cada llamada
necesita un `# type: ignore[arg-type]` en `analytics.py` — y esos ignore quedan
mal ubicados en la llamada multilinea, lo que produce los otros 4 errores.

Estos tests fijan el comportamiento en runtime para que el arreglo de tipos no
lo cambie sin querer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from platform_ops.longitudinal import build_trajectories

_COMISION = uuid4()
_BASE = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)


def _clasificaciones(n: int) -> list[dict]:
    return [
        {
            "episode_id": str(uuid4()),
            "classified_at": (_BASE + timedelta(hours=i)).isoformat(),
            "appropriation": "apropiacion_reflexiva",
        }
        for i in range(n)
    ]


@dataclass
class DataSourceQueConoceLanguage:
    """Como el `RealLongitudinalDataSource` de produccion."""

    grouped: dict[str, list[dict]] = field(default_factory=dict)
    language_recibido: str | None = None
    veces_llamado: int = 0

    async def list_classifications_grouped_by_student(
        self, comision_id: UUID, language: str | None = None
    ) -> dict[str, list[dict]]:
        self.veces_llamado += 1
        self.language_recibido = language
        return self.grouped


@dataclass
class DataSourceLegacy:
    """Como los `FakeDataSource` de `test_longitudinal.py`: no conoce el kwarg."""

    grouped: dict[str, list[dict]] = field(default_factory=dict)
    veces_llamado: int = 0

    async def list_classifications_grouped_by_student(
        self, comision_id: UUID
    ) -> dict[str, list[dict]]:
        self.veces_llamado += 1
        return self.grouped


@pytest.mark.asyncio
async def test_el_language_llega_al_data_source_que_lo_conoce() -> None:
    ds = DataSourceQueConoceLanguage(grouped={"s_1": _clasificaciones(3)})

    trayectorias = await build_trajectories(ds, _COMISION, language="java")

    assert ds.language_recibido == "java", "el filtro tiene que llegar al data source"
    assert len(trayectorias) == 1
    assert trayectorias[0].n_episodes == 3


@pytest.mark.asyncio
async def test_sin_language_no_se_reenvia_el_kwarg() -> None:
    """La razon de que el reenvio sea condicional y no `language=language`.

    Si se pasara siempre, un data source legacy explotaria con TypeError en
    cada llamada sin filtro — que es el 100% del uso anterior a
    `multi-language-research-integrity`.
    """
    ds = DataSourceLegacy(grouped={"s_1": _clasificaciones(3)})

    trayectorias = await build_trajectories(ds, _COMISION)

    assert ds.veces_llamado == 1
    assert len(trayectorias) == 1


@pytest.mark.asyncio
async def test_el_data_source_moderno_sin_filtro_recibe_none() -> None:
    """Sin filtro, el data source moderno no debe ver un `language` inventado."""
    ds = DataSourceQueConoceLanguage(grouped={"s_1": _clasificaciones(3)})

    await build_trajectories(ds, _COMISION)

    assert ds.language_recibido is None


@pytest.mark.asyncio
async def test_un_data_source_legacy_con_filtro_falla_fuerte() -> None:
    """Caracterizacion del limite: legacy + filtro NO esta soportado.

    Esta es la combinacion que la firma de `_DataSource` deberia describir y no
    describe. Queda fijada como TypeError explicito y no como comportamiento
    accidental: si alguien decide soportarla (por ejemplo ignorando el filtro en
    silencio), que sea una decision con este test enfrente — porque devolver la
    cohorte SIN filtrar cuando el caller pidio un lenguaje es peor que fallar:
    mete episodios de otro lenguaje en un analisis de la tesis sin avisar.
    """
    ds = DataSourceLegacy(grouped={"s_1": _clasificaciones(3)})

    with pytest.raises(TypeError, match="language"):
        await build_trajectories(ds, _COMISION, language="java")
