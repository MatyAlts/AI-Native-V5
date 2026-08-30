"""La lista de providers del codigo y la de la base tienen que coincidir.

El 2026-05-04 la migracion `20260504_0002_add_byok_keys` creo el check
`ck_byok_provider` con cuatro proveedores. Despues se agrego `openrouter` al
codigo y el constraint nunca se actualizo: el codigo decia que si y la base
decia que no.

Lo que hace peligroso a ese desfasaje es que NO rompe nada visible. El
ai-gateway siembra la key desde la variable de entorno en cada arranque, la
base la rechaza con `CheckViolationError`, se loguea el traceback y el
servicio sigue andando. OpenRouter quedo configurado, con pinta de funcionar,
y sin una sola key guardada.

Estuvo asi CUATRO MESES. Se descubrio el 2026-08-28 leyendo logs de
produccion por un motivo completamente distinto.

Este test lee las dos listas de sus fuentes y las compara. Es barato y cierra
la clase entera: cualquier proveedor que se agregue al codigo sin su migracion
—o al reves— se ve acá y no en produccion cuatro meses despues.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ai_gateway.services.byok import PROVIDERS_VALIDOS

# Las migraciones de `byok_keys` viven en academic-service: la tabla esta en
# `academic_main`, no en una base propia del ai-gateway.
MIGRACIONES = Path(__file__).resolve().parents[3] / "academic-service" / "alembic" / "versions"


def _providers_del_constraint_vigente() -> set[str]:
    """Los providers del ULTIMO `ck_byok_provider` que se crea en las migraciones.

    Se ordena por nombre de archivo porque las migraciones llevan la fecha
    adelante (`20260504_...`, `20260830_...`), asi que el orden alfabetico es
    el cronologico. La ultima que toca el constraint es la que manda.
    """
    encontrados: list[set[str]] = []
    for archivo in sorted(MIGRACIONES.glob("*.py")):
        texto = archivo.read_text()
        if "ck_byok_provider" not in texto:
            continue
        # Se buscan los `provider IN (...)` del upgrade. El downgrade tambien
        # tiene uno (el viejo), y por eso importa quedarse con el ultimo
        # bloque de `upgrade`.
        upgrade = texto.split("def downgrade")[0]
        for m in re.finditer(r"provider IN \(([^)]*)\)", upgrade):
            crudo = m.group(1)
            encontrados.append({p.strip().strip("'\"") for p in crudo.split(",") if p.strip()})
        # Las migraciones que usan una constante (f-string) no matchean arriba:
        # se resuelve leyendo la constante del propio archivo.
        for m in re.finditer(r"PROVIDERS_NUEVOS\s*=\s*\"([^\"]+)\"", upgrade):
            encontrados.append({p.strip().strip("'\"") for p in m.group(1).split(",")})
    if not encontrados:
        pytest.fail(f"no se encontro ningun `ck_byok_provider` en {MIGRACIONES}")
    return encontrados[-1]


def test_providers_sincronizados_con_la_migracion() -> None:
    """Si esto se pone rojo: agregaste un provider al codigo y falta la migracion.

    (O al reves.) Las dos listas tienen que moverse juntas — si no, la base
    rechaza la key en silencio y el proveedor queda inutilizable.
    """
    del_codigo = set(PROVIDERS_VALIDOS)
    de_la_base = _providers_del_constraint_vigente()

    solo_codigo = del_codigo - de_la_base
    solo_base = de_la_base - del_codigo

    assert not solo_codigo, (
        f"el codigo acepta {sorted(solo_codigo)} y la base NO: falta la migracion que "
        "actualiza `ck_byok_provider`. Sin ella la key se rechaza en cada arranque "
        "con CheckViolationError y el proveedor queda inutilizable (paso con "
        "'openrouter' y estuvo cuatro meses asi)."
    )
    assert not solo_base, (
        f"la base acepta {sorted(solo_base)} y el codigo NO: `crear_key` los va a "
        "rechazar con ValueError antes de llegar a la base."
    )


def test_openrouter_esta_en_las_dos_listas() -> None:
    """La regresion concreta que origino este archivo."""
    assert "openrouter" in PROVIDERS_VALIDOS
    assert "openrouter" in _providers_del_constraint_vigente()


def test_la_lectura_de_la_migracion_encuentra_algo() -> None:
    """Guarda del propio test.

    Si alguien renombra el constraint o cambia la forma del `provider IN (...)`,
    el parser podria devolver un set vacio y los tests de arriba pasarian por
    vacuidad — comparando nada contra nada.
    """
    de_la_base = _providers_del_constraint_vigente()
    assert len(de_la_base) >= 4, f"el parser leyo de menos: {de_la_base}"
    assert "gemini" in de_la_base
