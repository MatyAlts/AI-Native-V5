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
que esta misma change (v1.9.0) vino a corregir para OTRA regla de plataforma
("Afirmar como son las reglas de la plataforma", en "Lo que NO hace el
tutor") — cometido sobre si mismo.

QUE PRUEBA ESTE ARCHIVO
-------------------------
Que el bloque de cita (`> `) al principio de `v1.9.0/system.md` declara a que
version apunta `config.py` de verdad, y que lo que declara COINCIDE con
`Settings().default_prompt_version` leido en runtime — no con lo que alguien
escribio a mano y pudo quedar desactualizado.

Esta change deja v1.9.0 DESACTIVADA a proposito (la revision coautoral de Ana
Garis sigue abierta). El test tiene que fallar si alguien vuelve a
desincronizar el header del estado real, en cualquier direccion: que diga
"activa" sin estarlo, o que diga una version de config.py que no es la real.
"""

from __future__ import annotations

import re
from pathlib import Path

from tutor_service.config import Settings

VERSION = "v1.9.0"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _prompt(version: str) -> str:
    ruta = _repo_root() / "ai-native-prompts/prompts/tutor" / version / "system.md"
    return ruta.read_text(encoding="utf-8")


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


class TestElHeaderDeclaraAQueVersionApuntaConfigPyYEsVerdad:
    def test_el_header_declara_una_version_concreta(self) -> None:
        header = _header(VERSION)
        match = re.search(r"config\.py sigue apuntando a (v\d+\.\d+\.\d+)", header)
        assert match is not None, (
            "el header no declara explicitamente a que version apunta "
            "config.py con la frase 'config.py sigue apuntando a vX.Y.Z'; "
            "sin eso no hay nada que verificar contra el config real."
        )

    def test_lo_que_el_header_afirma_coincide_con_lo_que_config_py_hace(self) -> None:
        """El corazon del fix. Verificado por mutacion: si el header dijera
        v1.9.0 en vez de v1.8.0, esto se cae."""
        header = _header(VERSION)
        match = re.search(r"config\.py sigue apuntando a (v\d+\.\d+\.\d+)", header)
        assert match is not None, "ver test anterior"
        afirmado = match.group(1)
        real = Settings().default_prompt_version
        assert afirmado == real, (
            f"el header de {VERSION} afirma que config.py apunta a "
            f"{afirmado!r}, pero Settings().default_prompt_version es "
            f"{real!r}. El header le miente al modelo sobre su propio "
            "estado de activacion."
        )


class TestElHeaderNoSeDeclaraActivoSiNoLoEsta:
    def test_no_dice_estado_activo_mientras_config_py_apunte_a_otra_version(
        self,
    ) -> None:
        header = _header(VERSION).lower()
        real = Settings().default_prompt_version
        if real != VERSION:
            assert "estado: **activo**" not in header
            assert "estado: **activa**" not in header

    def test_declara_explicitamente_que_no_esta_activa(self) -> None:
        header = _header(VERSION).lower()
        assert "en revision" in header
        assert "no activ" in header  # cubre "no activo" y "no activa"


class TestLaRevisionCoautoralQuedaExplicita:
    """Tarea 4 del change: 'en las notas que la revision esta ABIERTA, y que
    v1.8.0 tambien. No lo dejes implicito.' Lo mismo vale para el header."""

    def test_el_header_dice_que_la_revision_de_ana_garis_esta_abierta(self) -> None:
        header = _header(VERSION).lower()
        assert "ana garis" in header
        assert "abierta" in header

    def test_el_header_no_omite_que_v180_tambien_la_tiene_abierta(self) -> None:
        """La deuda acumulada: v1.8.0 tampoco tiene su revision cerrada, y el
        header tiene que decirlo.

        POR QUE LA ASERCION ESTA ANCLADA ASI
        --------------------------------------
        La version anterior de este test afirmaba `"v1.8.0" in header`, que es
        **trivialmente cierto** en cualquier version derivada de v1.8.0: la
        cadena aparece cuatro veces en el header por motivos ajenos a esto
        ("Derivado de v1.8.0", "config.py sigue apuntando a v1.8.0", "no
        cambian una letra respecto de v1.8.0"). QA lo demostro por mutacion el
        2026-10-01: borro la oracion que afirma que la revision de v1.8.0 sigue
        abierta y el test quedo en verde.

        Es la cuarta asercion floja de esta misma forma en esta change. Las
        otras tres se corrigieron en el archivo hermano; esta vivia aca y no se
        volvio a mirar. Por eso se ancla a la conjuncion que carga el
        significado, no a la version suelta.
        """
        header = _header(VERSION).lower()
        assert "tambien la de v1.8.0" in header


class TestElRestoDelRepoDiceLoMismoQueElHeader:
    """El header no es el unico lugar donde esto se puede desincronizar:
    config.py y el manifest raiz tienen que seguir apuntando a v1.8.0."""

    def test_config_py_sigue_en_v180(self) -> None:
        assert Settings().default_prompt_version == "v1.8.0"

    def test_manifest_raiz_sigue_en_v180(self) -> None:
        manifest = _repo_root() / "ai-native-prompts" / "manifest.yaml"
        texto = manifest.read_text(encoding="utf-8")
        assert "tutor: v1.8.0" in texto, (
            "esta change no activa v1.9.0: el manifest raiz tiene que seguir "
            "apuntando a v1.8.0 hasta que cierre la revision coautoral."
        )
