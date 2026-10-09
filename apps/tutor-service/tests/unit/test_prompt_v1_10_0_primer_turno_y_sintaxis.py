"""El prompt v1.10.0 del tutor: el primer turno y la respuesta directa acotada.

EL REPORTE (QA sobre produccion, 2026-10-08)
----------------------------------------------
#17 — El tutor abre con "¿En que ejercicio estas trabajando?" aunque el
enunciado SI le llega en el system message (`tutor_core.py`,
`_build_ejercicio_context`). v1.9.0 decia que lo recibe, pero no tenia
ninguna regla para el primer turno: ante un "hola" sin contenido, el modelo
caia en la pregunta de apertura generica.

#18 — Con un estudiante que recien empieza, el tutor explico `int()` y
`float()` con su uso completo en vez de guiar. Dos reglas de v1.9.0 tiraban en
direcciones opuestas: "si pregunta por la sintaxis o por un hecho del lenguaje,
respondele directo" (que incluia "el uso de algo de la biblioteca estandar") y
"dale el piso". El modelo resolvia el empate dando el uso entero.

LOS DOS CAMBIOS
----------------
1. Regla de primer turno en "Contexto del TP": ante un saludo o una apertura
   sin contenido, nombrar el ejercicio por su titulo y preguntar por donde
   quiere empezar o que entendio. Nunca preguntar en que ejercicio esta cuando
   el contexto lo trae. El fallback (la consulta fallo) queda como estaba.
2. "Lo que SI se responde directo" se acota a la pregunta por la forma precisa
   de algo que el estudiante YA sabe que necesita. Cuando no sabe que
   herramienta necesita: el piso en una oracion, una pregunta sobre su caso, y
   NO el uso completo que resuelve el ejercicio. La regla de desempate de
   "Abrir el lazo" sigue diciendo "dale el piso", y aclara que el piso es el
   concepto, no el uso.

LIMITE CONOCIDO
----------------
Como el resto de los tests de prompt de este repo, este archivo ancla FRASES:
prueba que la regla esta escrita, no que el modelo la cumpla. No hay eval con
LLM real. Lo que si prueba en serio es la otra mitad: que las secciones que no
se tocaron siguen byte a byte contra v1.9.0.

Lee el archivo de v1.10.0 por ruta directa (mismo patron que
`test_prompt_v1_9_0_calidad_de_pregunta.py`), asi no depende de que version
este activa.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VERSION = "v1.10.0"
PADRE = "v1.9.0"


def _ruta(version: str) -> Path:
    raiz = Path(__file__).resolve().parents[4]
    return raiz / "ai-native-prompts/prompts/tutor" / version / "system.md"


def _prompt(version: str) -> str:
    ruta = _ruta(version)
    if not ruta.exists():
        pytest.fail(f"el prompt {version} no existe en {ruta}")
    return ruta.read_text(encoding="utf-8")


def _plano(texto: str) -> str:
    """Colapsa espacios y saltos y pasa a minusculas: un reflow no rompe nada."""
    return re.sub(r"\s+", " ", texto).lower()


def _seccion(version: str, encabezado: str) -> str:
    """Texto de la seccion `## encabezado...` (match por prefijo), sin el titulo."""
    dentro = False
    bloque: list[str] = []
    encontrada = False
    for linea in _prompt(version).splitlines():
        if linea.startswith(f"## {encabezado}"):
            dentro = True
            encontrada = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            bloque.append(linea)
    if not encontrada:
        pytest.fail(f"la seccion '## {encabezado}' no existe en {version}")
    return "\n".join(bloque)


def test_el_titulo_se_autodeclara() -> None:
    primera = _prompt(VERSION).splitlines()[0]
    assert f"({VERSION})" in primera, f"el titulo no se autodeclara: {primera!r}"


class TestPrimerTurno:
    """#17: el tutor no pregunta lo que ya tiene en el contexto."""

    def test_hay_una_regla_para_el_primer_turno(self) -> None:
        contexto = _plano(_seccion(VERSION, "Contexto del TP"))
        assert "primer turno" in contexto, (
            "'Contexto del TP' no tiene regla de primer turno: ante un 'hola' el "
            "modelo vuelve a la pregunta de apertura generica"
        )

    def test_ante_un_saludo_nombra_el_ejercicio_por_su_titulo(self) -> None:
        contexto = _plano(_seccion(VERSION, "Contexto del TP"))
        assert "saluda" in contexto
        assert "nombra el ejercicio por su titulo" in contexto

    def test_pregunta_por_donde_empezar_o_que_entendio(self) -> None:
        contexto = _plano(_seccion(VERSION, "Contexto del TP"))
        assert "por donde quiere empezar" in contexto
        assert "que entendio" in contexto

    def test_prohibe_preguntar_en_que_ejercicio_esta_si_el_contexto_lo_trae(self) -> None:
        contexto = _plano(_seccion(VERSION, "Contexto del TP"))
        assert "nunca le preguntes en que ejercicio esta trabajando" in contexto

    def test_conserva_el_fallback_cuando_la_consulta_falla(self) -> None:
        """La otra mitad: sin enunciado, preguntar por el problema sigue siendo
        lo correcto. Un fix que lo borre deja al tutor sin salida en ese caso."""
        contexto = _plano(_seccion(VERSION, "Contexto del TP"))
        assert "si la consulta al servicio academico falla" in contexto
        assert "preguntale al estudiante por el problema concreto" in contexto
        assert "no le pidas que te pegue el enunciado" in contexto


class TestLaRespuestaDirectaSeAcota:
    """#18: la respuesta directa es para quien ya eligio la herramienta."""

    def test_la_respuesta_directa_queda_acotada_a_la_forma_de_lo_que_ya_sabe_que_necesita(
        self,
    ) -> None:
        directo = _plano(_seccion(VERSION, "Lo que SI se responde directo"))
        assert "respondele directo" in directo
        assert "sin devolverle la pregunta" in directo
        assert "ya sabe que necesita" in directo, (
            "la respuesta directa no quedo acotada a quien ya sabe que herramienta necesita"
        )

    def test_la_formulacion_amplia_de_v1_9_0_no_sobrevive(self) -> None:
        """Lo que produjo #18, verificado contra el padre para que no sea un
        negativo que pasa solo: la frase tiene que estar en v1.9.0."""
        vieja = "si el estudiante pregunta por la sintaxis o por un hecho del lenguaje"
        assert vieja in _plano(_prompt(PADRE)), "el ancla del padre se movio"
        assert vieja not in _plano(_prompt(VERSION))

        viejo_bullet = "el nombre o el uso de algo de la biblioteca estandar"
        assert viejo_bullet in _plano(_prompt(PADRE)), "el ancla del padre se movio"
        assert viejo_bullet not in _plano(_prompt(VERSION))

    def test_cuando_no_sabe_que_herramienta_necesita_no_es_notacion(self) -> None:
        directo = _plano(_seccion(VERSION, "Lo que SI se responde directo"))
        assert "no sabe que herramienta necesita" in directo
        assert "no es una consulta de notacion" in directo

    def test_da_el_piso_en_una_oracion_y_cierra_con_una_pregunta_sobre_su_caso(self) -> None:
        directo = _plano(_seccion(VERSION, "Lo que SI se responde directo"))
        assert "en una oracion" in directo
        assert "pregunta sobre su caso" in directo

    def test_no_muestra_el_uso_completo_que_resuelve_el_ejercicio(self) -> None:
        directo = _plano(_seccion(VERSION, "Lo que SI se responde directo"))
        assert "no le muestres el uso completo" in directo

    def test_sigue_dando_ejemplos_de_lo_que_si_entra(self) -> None:
        """La excepcion de v1.4.0 no se pierde: preguntar como se escribe un for
        se sigue respondiendo directo."""
        directo = _plano(_seccion(VERSION, "Lo que SI se responde directo"))
        assert "¿como se escribe un for?" in directo


class TestLaReglaDeDesempateSigueCoherente:
    def test_abrir_el_lazo_sigue_diciendo_dale_el_piso(self) -> None:
        abrir = _plano(_seccion(VERSION, "Abrir el lazo"))
        assert "regla de desempate" in abrir
        assert "dale el piso" in abrir

    def test_el_piso_es_el_concepto_no_el_uso(self) -> None:
        abrir = _plano(_seccion(VERSION, "Abrir el lazo"))
        assert "el piso es el concepto, no el uso" in abrir


SECCIONES_INTACTAS = [
    "Movimientos del metodo",
    "Cerrar el lazo",
    "Principios",
    "Lo que NO hace el tutor",
    "Formato de respuesta",
    "El codigo que el estudiante esta escribiendo",
    "Usar el material del ejercicio",
    "Uso del material de catedra",
    "Uso de la rubrica de evaluacion",
    "Temas fuera del scope del tutor",
]


@pytest.mark.parametrize("encabezado", SECCIONES_INTACTAS)
def test_lo_que_no_se_toco_sigue_byte_a_byte(encabezado: str) -> None:
    """El hash del manifest detecta que el prompt cambio; no que cambio solo
    donde se dijo. Esto si: el metodo, los principios, los guardrails y el tono
    (voseo) quedan identicos a v1.9.0."""
    assert _seccion(VERSION, encabezado) == _seccion(PADRE, encabezado), (
        f"'{encabezado}' cambio respecto de {PADRE} y el bump declara que no"
    )
