"""Las listas de providers de BYOK tienen que moverse juntas.

Hay CUATRO lugares que enumeran los proveedores validos:

  1. `services/byok.py::PROVIDERS_VALIDOS`     — valida en `crear_key`
  2. `routes/byok.py`                          — el `Literal` del endpoint
  3. el check `ck_byok_provider` de `byok_keys` — lo pone una migracion
  4. `web-admin`                               — el `<select>` del panel

Los tres primeros se verifican acá. El cuarto es TypeScript y vive en otro
paquete: lo cubre `apps/web-admin/tests/providersByok.test.ts`.

## Por que existe este archivo

El 2026-05-04 la migracion `20260504_0002_add_byok_keys` creo el check con
cuatro proveedores. Despues se agrego `openrouter` a (1) y (2), y el
constraint quedo con los cuatro originales. Estuvo asi CUATRO MESES.

Y la consecuencia real NO fue "OpenRouter roto" —eso es lo que parecia—:
OpenRouter **funciono todo el tiempo** por el camino del env fallback, que no
necesita ninguna fila en `byok_keys`. Lo que se rompio fue el registro de
COSTO. Cuando se usa la key de entorno, `_ensure_env_fallback_sentinel` crea
una fila centinela (`fingerprint_last4='ENVF'`, `revoked_at=created_at` para
quedar fuera del UNIQUE activo) cuyo unico proposito es servir de FK para
`byok_keys_usage`. Esa fila la rechazaba el constraint, el `except Exception`
de `complete.py:520` se comia el error para no tumbar la respuesta del LLM, y
el uso de OpenRouter quedo sin auditar durante cuatro meses.

**Eso no se puede backfillear.** Para un repo cuya justificacion es la
auditabilidad academica, ese es el daño: no un proveedor caido, un agujero en
el registro de costos.

## Por que el test se escribe ASI y no leyendo un string

La primera version de este archivo parseaba la constante `PROVIDERS_NUEVOS`
del modulo de la migracion. Un verificador la vacio —dejo `upgrade()` en
`pass`— y **los tres tests quedaron verdes**: se estaba comprobando que
existiera un string en un archivo, no que la migracion hiciera algo.

Peor: se demostro un falso verde punta a punta. Una migracion posterior con
la frase "def downgrade" dentro de su docstring se saltea entera (el parser
cortaba por esa cadena), asi que se podia sacar un provider del constraint
con el guardian en verde.

Aca se EJECUTA el `upgrade()` de cada migracion contra un doble de `op` que
registra las llamadas. Eso mide el efecto, no el texto.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest
from ai_gateway.services.byok import PROVIDERS_VALIDOS

RAIZ = Path(__file__).resolve().parents[4]
MIGRACIONES = RAIZ / "apps" / "academic-service" / "alembic" / "versions"
RUTAS_BYOK = RAIZ / "apps" / "ai-gateway" / "src" / "ai_gateway" / "routes" / "byok.py"

CONSTRAINT = "ck_byok_provider"
TABLA = "byok_keys"


class _OpEspia:
    """Doble de `alembic.op` que registra el efecto sobre el constraint.

    Solo implementa lo que las migraciones de este constraint usan. Cualquier
    otra operacion es un no-op: no se esta simulando Alembic, se esta
    observando UNA cosa.
    """

    def __init__(self) -> None:
        self.constraint_actual: set[str] | None = None
        self.borrado = False

    def create_check_constraint(self, nombre: str, tabla: str, condicion: str, **_: Any) -> None:
        if nombre != CONSTRAINT or tabla != TABLA:
            return
        m = re.search(r"provider IN \(([^)]*)\)", str(condicion))
        if not m:
            pytest.fail(f"no se pudo leer la condicion del check: {condicion!r}")
        self.constraint_actual = {p.strip().strip("'\"") for p in m.group(1).split(",")}

    def drop_constraint(self, nombre: str, tabla: str, **_: Any) -> None:
        if nombre == CONSTRAINT and tabla == TABLA:
            self.borrado = True

    def create_table(self, tabla: str, *args: Any, **_: Any) -> None:
        # `20260504_0002` crea la tabla con el CheckConstraint adentro.
        if tabla != TABLA:
            return
        for arg in args:
            cond = getattr(arg, "sqltext", None)
            nombre = getattr(arg, "name", None)
            if nombre != CONSTRAINT or cond is None:
                continue
            m = re.search(r"provider IN \(([^)]*)\)", str(cond))
            if m:
                self.constraint_actual = {p.strip().strip("'\"") for p in m.group(1).split(",")}

    def __getattr__(self, _nombre: str) -> Any:
        return lambda *a, **k: None


def _cargar(archivo: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"_mig_{archivo.stem}", archivo)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _cadena_de_revisiones() -> list[Path]:
    """Las migraciones en orden REAL, siguiendo `down_revision`.

    No por nombre de archivo: `make migrate-new` genera `<rev-hex>_<slug>.py`
    (el default de Alembic, ningun `alembic.ini` define `file_template`), asi
    que el orden alfabetico NO es el cronologico. Un rev id que empiece con
    `0` ordenaria antes que todos los `2026*` y se ignoraria.
    """
    por_rev: dict[str, tuple[Path, Any]] = {}
    for archivo in MIGRACIONES.glob("*.py"):
        modulo = _cargar(archivo)
        rev = getattr(modulo, "revision", None)
        if rev:
            por_rev[str(rev)] = (archivo, modulo)

    hijos: dict[str | None, str] = {}
    for rev, (_, modulo) in por_rev.items():
        down = getattr(modulo, "down_revision", None)
        down = str(down) if down else None
        if down in hijos:
            pytest.fail(f"rama en el arbol de migraciones: {down} tiene dos hijos")
        hijos[down] = rev

    cadena: list[Path] = []
    actual: str | None = None
    while actual in hijos:
        rev = hijos[actual]
        cadena.append(por_rev[rev][0])
        actual = rev
    return cadena


def providers_del_constraint_vigente() -> set[str]:
    """Ejecuta los `upgrade()` en orden y devuelve el constraint resultante."""
    espia = _OpEspia()
    for archivo in _cadena_de_revisiones():
        modulo = _cargar(archivo)
        if not hasattr(modulo, "upgrade"):
            continue
        original = getattr(modulo, "op", None)
        modulo.op = espia  # type: ignore[attr-defined]
        try:
            modulo.upgrade()
        except Exception:
            pass
        finally:
            if original is not None:
                modulo.op = original  # type: ignore[attr-defined]
    if espia.constraint_actual is None:
        pytest.fail(
            f"ningun `upgrade()` de {MIGRACIONES} definio `{CONSTRAINT}`. "
            "O se renombro el constraint, o una migracion dejo de crearlo."
        )
    return espia.constraint_actual


def _providers_del_endpoint() -> set[str]:
    texto = RUTAS_BYOK.read_text(encoding="utf-8")
    m = re.search(r"provider:\s*Literal\[([^\]]*)\]", texto)
    if not m:
        pytest.fail(f"no se encontro el Literal de provider en {RUTAS_BYOK}")
    return {p.strip().strip("'\"") for p in m.group(1).split(",") if p.strip()}


# ── Los tres lugares, comparados de a pares ────────────────────────────────


def test_el_codigo_y_la_base_coinciden() -> None:
    """Si esto se pone rojo: agregaste un provider y falta su migracion.

    (O al reves.) Sin la migracion, la base rechaza la fila centinela del env
    fallback y el uso de ese proveedor queda SIN AUDITAR — en silencio, porque
    `complete.py:520` se come el error para no tumbar la respuesta del LLM.
    """
    del_codigo = set(PROVIDERS_VALIDOS)
    de_la_base = providers_del_constraint_vigente()

    assert not (del_codigo - de_la_base), (
        f"el codigo acepta {sorted(del_codigo - de_la_base)} y la base NO: falta la "
        f"migracion que actualiza `{CONSTRAINT}`. Paso con 'openrouter' y el costo "
        "de ese proveedor quedo sin auditar cuatro meses."
    )
    assert not (de_la_base - del_codigo), (
        f"la base acepta {sorted(de_la_base - del_codigo)} y el codigo NO: "
        "`crear_key` los rechaza con ValueError antes de llegar a la base."
    )


def test_el_endpoint_y_el_servicio_coinciden() -> None:
    """La tercera lista: el `Literal` de `routes/byok.py`.

    `crear_key` documenta que NO valida el provider ("eso lo hace el
    endpoint"), asi que si el Literal se queda corto el proveedor es
    inalcanzable por la API aunque el servicio y la base lo acepten.
    """
    assert _providers_del_endpoint() == set(PROVIDERS_VALIDOS), (
        f"endpoint={sorted(_providers_del_endpoint())} vs servicio={sorted(PROVIDERS_VALIDOS)}"
    )


def test_openrouter_esta_en_los_tres() -> None:
    """La regresion concreta que origino este archivo."""
    assert "openrouter" in PROVIDERS_VALIDOS
    assert "openrouter" in providers_del_constraint_vigente()
    assert "openrouter" in _providers_del_endpoint()


# ── Guardas del propio test ────────────────────────────────────────────────


def test_la_cadena_de_revisiones_es_completa() -> None:
    """Sin esto, un parser que lee de menos deja pasar todo por vacuidad."""
    cadena = _cadena_de_revisiones()
    en_disco = len(list(MIGRACIONES.glob("*.py")))
    assert len(cadena) == en_disco, (
        f"la cadena tiene {len(cadena)} de {en_disco} migraciones: hay una huerfana "
        "o una rama. Las que queden afuera NO se verifican."
    )


def test_el_constraint_se_lee_del_efecto_y_no_del_texto() -> None:
    """El espia tiene que ver el DROP, no solo el CREATE.

    Si una migracion futura solo hiciera `create_check_constraint` sin dropear
    el anterior, la migracion fallaria en Postgres (nombre duplicado) y acá
    pasaria igual. Esta guarda lo hace visible.
    """
    espia = _OpEspia()
    for archivo in _cadena_de_revisiones():
        modulo = _cargar(archivo)
        original = getattr(modulo, "op", None)
        modulo.op = espia  # type: ignore[attr-defined]
        try:
            modulo.upgrade()
        except Exception:
            pass
        finally:
            if original is not None:
                modulo.op = original  # type: ignore[attr-defined]
    assert espia.borrado, (
        "ninguna migracion dropeo el constraint antes de recrearlo — en Postgres "
        "eso falla por nombre duplicado"
    )
