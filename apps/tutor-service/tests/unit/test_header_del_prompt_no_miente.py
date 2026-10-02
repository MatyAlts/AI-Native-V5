"""El header del prompt no le miente al modelo sobre su propio estado.

EL INCIDENTE (2026-09-30)
--------------------------
El header de una version del prompt decia "config.py sigue apuntando a
v1.8.0" — y el mismo commit que escribio esa linea habia movido
`default_prompt_version` a v1.9.0. Los 21 tests del prompt que existian ese
dia pasaron igual, porque ninguno comparaba lo que el header AFIRMA contra lo
que `config.py` HACE: cada uno verificaba una cosa o la otra, nunca las dos
una contra la otra.

Un prompt que afirma un estado de activacion falso es exactamente el defecto
que la v1.9.0 vino a corregir para OTRA regla de plataforma ("Afirmar como son
las reglas de la plataforma", en "Lo que NO hace el tutor") — cometido sobre si
mismo.

POR QUE ESTE ARCHIVO SE REESCRIBIO (2026-10-02)
-------------------------------------------------
La primera version afirmaba el ESTADO de aquel momento: que v1.9.0 estaba
desactivada, que `config.py` decia exactamente `"v1.8.0"`, que la revision de
Ana Garis estaba abierta. Todo eso era cierto el dia que se escribio, y todo
eso **dejo de ser cierto** cuando Ana aprobo y la version se activo.

Un test anclado a un estado se vuelve un obstaculo el dia que el estado cambia
legitimamente, y entonces alguien lo borra o lo afloja — y con el se va la red.
El defecto del incidente no era "v1.9.0 esta activa": era **que el header
afirmaba una cosa y el repo hacia otra**. Esa es la propiedad, y es la que este
archivo afirma ahora, sin mencionar ninguna version en particular.

Consecuencia practica: al activar cualquier version futura, este archivo falla
hasta que el header diga la verdad. Eso es lo que tiene que pasar — es el unico
momento en que alguien se acuerda de actualizar el header.

LAS TRES PROPIEDADES
----------------------
1. El header declara, con una frase parseable, a que version apunta
   `config.py`. Sin eso no hay nada que verificar.
2. Lo que declara COINCIDE con `Settings().default_prompt_version` leido en
   runtime.
3. El header y el repo no se contradicen sobre la activacion, **en ninguna de
   las dos direcciones**: no dice "activa" si config apunta a otra version, y
   no dice "en revision / no activa" si config apunta a esta.

Mas una cuarta que el `CLAUDE.md` exige como invariante y ningun test fijaba:
el manifest raiz (`ai-native-prompts/manifest.yaml`, que leen los frontends) y
`config.py` (que usa el tutor-service en runtime) apuntan a la MISMA version.
Si solo se cambia uno, los frontends muestran una version y el CTR registra
otra.
"""

from __future__ import annotations

import re
from pathlib import Path

from tutor_service.config import Settings

# La version que este archivo audita: la ultima que existe en disco. No se
# hardcodea a proposito — al agregar una v1.10.0, el test la audita sola.
_RE_VERSION = re.compile(r"^v\d+\.\d+\.\d+$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _dir_prompts() -> Path:
    return _repo_root() / "ai-native-prompts" / "prompts" / "tutor"


def _ultima_version() -> str:
    versiones = sorted(
        (p.name for p in _dir_prompts().iterdir() if _RE_VERSION.match(p.name)),
        key=lambda v: [int(n) for n in v.lstrip("v").split(".")],
    )
    assert versiones, f"no encontre ninguna version bajo {_dir_prompts()}"
    return versiones[-1]


VERSION = _ultima_version()


def _prompt(version: str) -> str:
    return (_dir_prompts() / version / "system.md").read_text(encoding="utf-8")


def _header(version: str) -> str:
    """El bloque de cita (lineas que arrancan con `>`) al inicio del prompt."""
    lineas: list[str] = []
    empezo = False
    for linea in _prompt(version).splitlines():
        if linea.startswith(">"):
            lineas.append(linea)
            empezo = True
        elif empezo:
            break
    return "\n".join(lineas)


def _version_que_el_header_declara(header: str) -> str | None:
    """La version que el header dice que `config.py` usa, o None si no lo dice.

    Acepta las dos formas en que el header puede redactarlo —"sigue apuntando
    a" cuando la version NO esta activa, y "apunta a" cuando SI lo esta— porque
    la propiedad que importa es que declare UNA version verificable, no con que
    verbo la redacta.
    """
    m = re.search(r"config\.py (?:sigue )?apunta(?:ndo)? a (v\d+\.\d+\.\d+)", header)
    return m.group(1) if m else None


def test_la_version_auditada_se_detecto() -> None:
    """Guarda contra el modo de falla mas tonto de este archivo.

    Si el glob de `_ultima_version` se rompe, `VERSION` queda en algo que no
    existe, `_prompt` revienta y el error se lee como un bug del prompt en vez
    de como un bug de este test.
    """
    assert (_dir_prompts() / VERSION / "system.md").exists(), (
        f"la version detectada ({VERSION}) no tiene system.md: la deteccion automatica se rompio"
    )


class TestElHeaderDeclaraAQueVersionApuntaConfigPyYEsVerdad:
    def test_el_header_declara_una_version_concreta(self) -> None:
        declarada = _version_que_el_header_declara(_header(VERSION))
        assert declarada is not None, (
            f"el header de {VERSION} no declara a que version apunta "
            "config.py con una frase parseable ('config.py apunta a vX.Y.Z' o "
            "'config.py sigue apuntando a vX.Y.Z'); sin eso no hay nada que "
            "verificar contra el config real."
        )

    def test_lo_que_el_header_afirma_coincide_con_lo_que_config_py_hace(self) -> None:
        """El corazon del fix, y lo unico que reproduce el incidente."""
        declarada = _version_que_el_header_declara(_header(VERSION))
        assert declarada is not None, "ver test anterior"
        real = Settings().default_prompt_version
        assert declarada == real, (
            f"el header de {VERSION} afirma que config.py apunta a "
            f"{declarada!r}, pero Settings().default_prompt_version es "
            f"{real!r}. El header le miente al modelo sobre su propio estado "
            "de activacion."
        )


class TestElHeaderNoSeContradiceSobreLaActivacion:
    """Las dos direcciones, y las dos importan.

    La version anterior de este archivo solo cubria una —no decir "activa" sin
    estarlo— porque era la del incidente. La direccion opuesta —seguir diciendo
    "en revision" despues de activarse— es el mismo defecto con el signo
    cambiado, y es la que iba a aparecer el dia que Ana aprobara. Aparecio el
    2026-10-02.
    """

    def test_no_dice_activa_si_config_apunta_a_otra_version(self) -> None:
        header = _header(VERSION).lower()
        if Settings().default_prompt_version != VERSION:
            assert "estado: **activo**" not in header
            assert "estado: **activa**" not in header

    def test_no_dice_que_esta_en_revision_si_config_apunta_a_esta(self) -> None:
        header = _header(VERSION).lower()
        if Settings().default_prompt_version == VERSION:
            assert "en revision" not in header, (
                f"config.py apunta a {VERSION} —esta corriendo— y el header "
                "sigue diciendo 'en revision'. Le miente al modelo en la "
                "direccion opuesta a la del incidente del 2026-09-30."
            )
            assert "no activ" not in header


class TestLaRevisionCoautoralNoQuedaImplicita:
    """El header dice en que estado esta la revision coautoral, cualquiera sea.

    NO se afirma CUAL es el estado: si Ana aprobo o no es un hecho que vive
    afuera del repo y este test no tiene forma de verificarlo. Lo que se afirma
    es que el header lo DIGA — porque la deuda de revision acumulada
    (v1.6.0 a v1.9.0 esperaron juntas) se volvio invisible justamente por no
    estar escrita en el unico archivo que todos leen.
    """

    def test_el_header_nombra_a_la_coautora_y_el_estado_de_su_revision(self) -> None:
        header = _header(VERSION).lower()
        assert "ana garis" in header, (
            "el header no nombra la revision coautoral. Con el gate abierto o "
            "cerrado, el estado se escribe: es lo que lo volvio invisible "
            "cuando cuatro versiones la esperaron juntas."
        )
        estados = ("aprob", "abierta", "pendiente", "cerrada")
        assert any(e in header for e in estados), (
            f"el header nombra a la coautora pero no dice en que estado esta "
            f"su revision (ninguno de {estados} aparece)."
        )


class TestElManifestRaizYConfigPyNoSeDesincronizan:
    """Invariante del `CLAUDE.md`, y hasta hoy sin test que lo fijara.

    El manifest raiz lo parsea `PromptLoader.active_configs()` y lo consumen
    los frontends y dashboards; `config.py` es lo que el tutor-service usa de
    verdad en runtime. El `CLAUDE.md` lo dice textual: *"Si solo se cambia uno,
    frontends ven una version y el CTR registra otra"*.

    El test que existia afirmaba `"tutor: v1.8.0" in texto`, o sea el estado de
    ese dia. Este afirma el acuerdo, que es lo que no puede romperse nunca.
    """

    def test_el_manifest_raiz_apunta_a_la_misma_version_que_config_py(self) -> None:
        manifest = _repo_root() / "ai-native-prompts" / "manifest.yaml"
        texto = manifest.read_text(encoding="utf-8")
        real = Settings().default_prompt_version

        # Se busca la clave `tutor:` indentada dentro del bloque `active:`, no
        # una subcadena suelta: la version aparece decenas de veces en los
        # comentarios del changelog de ese archivo.
        declaradas = re.findall(r"^\s+tutor:\s*(v\d+\.\d+\.\d+)\s*$", texto, re.M)
        assert declaradas, "no encontre ninguna clave `tutor: vX.Y.Z` en el manifest raiz"
        assert all(d == real for d in declaradas), (
            f"el manifest raiz declara {declaradas} y config.py usa {real!r}. "
            "Los frontends van a mostrar una version y el CTR va a registrar "
            "otra."
        )


# POR QUE NO HAY UN TEST SOBRE TODAS LAS VERSIONES EN DISCO
# -----------------------------------------------------------
# Se escribio uno y se saco el mismo dia (2026-10-02). Encontro algo real —
# v1.5.0, v1.6.0 y v1.7.0 siguen diciendo "Estado: **activo**" despues de ser
# reemplazadas— y despues quedo claro que el hallazgo no es un defecto:
#
#   1. Editarlas romperia su `sha256` sellado, y ahi salta
#      `test_manifests_de_prompts_parsean.py`. Dos tests de este repo se
#      contradirian, lo que ya dice que la edicion es el error y no el arreglo.
#      El `CLAUDE.md` guarda esas versiones a proposito: "v1.4.0 y anteriores
#      siguen en disco para reproducibilidad historica del piloto".
#
#   2. Y sobre todo: **el modelo recibe UN solo prompt**, el que `config.py`
#      apunta. Un header viejo en un archivo que ya nadie carga no le miente a
#      nadie — es un documento fechado, y decia la verdad cuando se escribio.
#
# La mentira que importa es la del archivo que el modelo SI recibe, y eso lo
# cubren las clases de arriba. Queda anotado para que el proximo que tenga la
# misma idea no gaste la tarde: la idea es razonable y la respuesta es que no.
