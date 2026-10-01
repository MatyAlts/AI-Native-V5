"""Todo `manifest.yaml` de un prompt tiene que ser YAML valido y declarar el
hash real de su `system.md`.

POR QUE EXISTE ESTE ARCHIVO
-----------------------------
El 2026-10-01, el `manifest.yaml` de la version v1.9.0 del tutor se commiteo
siendo **YAML invalido**. Un `": "` dentro de un escalar plano -en una nota
redactada en prosa, del tipo "los alumnos dijeron la misma cosa de cuatro
formas: le preguntan al tutor..."- rompe el parseo. Habia seis lugares asi.

Nada lo detecto:

- los tests del prompt leen el manifest con una expresion regular para sacar el
  sha256, asi que nunca lo parsean;
- la revision de QA tambien lo leyo con `rg`, por el mismo motivo;
- CI no tiene ningun paso que valide los YAML del repo de prompts;
- y la version no estaba activa, asi que el `PromptLoader` nunca la abrio.

La consecuencia, si se hubiera activado: el governance-service parsea este
archivo al cargar el prompt, el parseo revienta, y
`POST /api/v1/episodes` del tutor-service devuelve 500 — es decir, **ningun
estudiante puede abrir un episodio**. Un fallo total del nucleo de la
plataforma, por una prosa con dos puntos.

Este archivo cubre TODAS las versiones en disco, no la ultima: el modo de falla
no tiene nada de particular a v1.9.0 y la proxima version va a redactar sus
notas en prosa igual que esta.
"""

import hashlib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
PROMPTS_TUTOR = REPO_ROOT / "ai-native-prompts" / "prompts" / "tutor"


def _versiones_con_manifest() -> list[Path]:
    if not PROMPTS_TUTOR.exists():
        return []
    return sorted(p for p in PROMPTS_TUTOR.glob("*/manifest.yaml"))


MANIFESTS = _versiones_con_manifest()
IDS = [m.parent.name for m in MANIFESTS]


def test_hay_manifests_para_revisar() -> None:
    """Guarda contra el modo de falla mas tonto de este archivo.

    Si el glob se rompe (se mueve el directorio, cambia la profundidad de
    `parents[4]`), `MANIFESTS` queda vacio, los tests parametrizados no corren
    NINGUNA vez, y la suite queda en verde sin haber mirado un solo archivo.
    """
    assert MANIFESTS, f"no encontre ningun manifest bajo {PROMPTS_TUTOR}"
    assert len(MANIFESTS) >= 5, (
        f"solo encontre {len(MANIFESTS)} manifests; el repo tiene mas versiones "
        "con manifest propio, asi que el glob esta matcheando de menos"
    )


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_el_manifest_es_yaml_valido(manifest: Path) -> None:
    """Lo que el governance-service hace al cargar el prompt."""
    try:
        datos = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        pytest.fail(
            f"{manifest.parent.name}/manifest.yaml no es YAML valido: {e}\n\n"
            "La causa mas probable es un ': ' dentro de una nota en prosa sin "
            "comillas. Reformulala con ' - ', que es el separador que el resto "
            "de las notas ya usa."
        )
    assert isinstance(datos, dict), "el manifest no es un mapeo"


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_el_manifest_declara_el_hash_real_de_system_md(manifest: Path) -> None:
    """El governance-service verifica esto fail-loud: si no coincide, no carga.

    Se recalcula sobre los bytes del archivo, no sobre el texto decodificado —
    es la misma operacion que hace el servicio.
    """
    datos = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    declarado = datos["files"]["system.md"]

    system_md = manifest.parent / "system.md"
    assert system_md.exists(), f"falta {system_md}"
    real = hashlib.sha256(system_md.read_bytes()).hexdigest()

    assert declarado == real, (
        f"{manifest.parent.name}: el manifest declara {declarado[:16]}... y el "
        f"archivo es {real[:16]}.... Se modifico `system.md` sin re-firmar el "
        "manifest, y el governance-service va a fallar al cargar esta version."
    )


@pytest.mark.parametrize("manifest", MANIFESTS, ids=IDS)
def test_el_manifest_declara_su_propia_version(manifest: Path) -> None:
    """`version` tiene que coincidir con el directorio que lo contiene.

    Una version que se declara distinta de donde vive es la clase de desfasaje
    que despues se lee como un dato y no como un error.
    """
    datos = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert datos["version"] == manifest.parent.name, (
        f"vive en {manifest.parent.name}/ y se declara {datos['version']}"
    )
