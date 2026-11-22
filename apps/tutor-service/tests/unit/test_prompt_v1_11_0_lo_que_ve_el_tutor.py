"""El prompt v1.11.0 del tutor: lo que ve del episodio y lo que no (HU-009).

EL REPORTE (prueba 2 como alumno en produccion, 2026-11-20)
-------------------------------------------------------------
- ej17: "¡Claro que me acuerdo!" sobre un ejercicio anterior, con datos
  inventados. El tutor no recibe nada de otros ejercicios.
- ej4 y ej11: insistio con errores que no habia, con 2 de 2 en Probar.
- ej8: recomendo pegar el "²", con pegar bloqueado.
- ej2: dio la linea exacta de la solucion.
- ej6: no vio que el programa imprimia el resultado escrito a mano.

EL CAMBIO
----------
Una sola seccion nueva, "Lo que ves de este episodio, y lo que no", entre "El
codigo que el estudiante esta escribiendo" y "Usar el material del ejercicio".
Juani levanto para esta historia la regla de prompts intactos; Ana Garis
(coautora) tiene la revision pendiente.

LIMITE CONOCIDO
----------------
Como el resto de los tests de prompt del repo, ancla FRASES: prueba que la regla
esta escrita, no que el modelo la cumpla. Lo que si prueba en serio es la otra
mitad: que todas las demas secciones siguen byte a byte contra v1.10.0.

Lee los archivos por ruta directa (mismo patron que
`test_prompt_v1_10_0_primer_turno_y_sintaxis.py`), asi no depende de que
version este activa.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VERSION = "v1.11.0"
PADRE = "v1.10.0"
NUEVA = "Lo que ves de este episodio"


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


def _encabezados(version: str) -> list[str]:
    return [linea[3:] for linea in _prompt(version).splitlines() if linea.startswith("## ")]


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


def test_la_unica_seccion_nueva_va_antes_del_material_del_ejercicio() -> None:
    nuevos = _encabezados(VERSION)
    viejos = _encabezados(PADRE)
    agregadas = [e for e in nuevos if e not in viejos]
    assert len(agregadas) == 1 and agregadas[0].startswith(NUEVA), agregadas
    assert [e for e in nuevos if not e.startswith(NUEVA)] == viejos, "se perdio o movio una seccion"
    i = nuevos.index(agregadas[0])
    assert nuevos[i - 1].startswith("El codigo que el estudiante esta escribiendo")
    assert nuevos[i + 1].startswith("Usar el material del ejercicio")


class TestLasCincoReglas:
    def test_no_finge_recordar_otros_ejercicios(self) -> None:
        s = _plano(_seccion(VERSION, NUEVA))
        assert "no tenes acceso a otros ejercicios del estudiante" in s
        assert "nunca finjas recordar" in s

    def test_ve_probar_y_no_inventa_errores_si_paso_todo(self) -> None:
        s = _plano(_seccion(VERSION, NUEVA))
        assert "si probar paso todos los casos" in s
        assert "no inventes errores que no estan" in s
        # Y la otra mitad del defecto: entiende "paso la prueba".
        assert "no le preguntes a que se refiere" in s

    def test_de_los_ocultos_solo_sabe_el_nombre(self) -> None:
        s = _plano(_seccion(VERSION, NUEVA))
        assert "de los casos de prueba ocultos solo sabes el nombre" in s

    def test_nunca_sugiere_pegar_y_explica_como_tipear(self) -> None:
        s = _plano(_seccion(VERSION, NUEVA))
        assert "nunca le sugieras pegar" in s
        assert "explicale como escribirlo con el teclado" in s
        # Los atajos concretos, y la confusion que produjo el ej9.
        assert "alt + 0178" in s and "alt + 0176" in s
        assert "\\u00b2" in s and "\\u00b0" in s
        assert '"°" (grado) no es "º" (ordinal)' in s

    def test_no_dicta_la_linea_de_la_solucion(self) -> None:
        s = _plano(_seccion(VERSION, NUEVA))
        assert "no dictes la linea de la solucion" in s
        # Sin pisar la excepcion de v1.4.0: la notacion se sigue respondiendo.
        assert "la notacion se sigue respondiendo directo" in s

    def test_senala_el_resultado_escrito_a_mano(self) -> None:
        s = _plano(_seccion(VERSION, NUEVA))
        assert "si el codigo imprime el resultado escrito a mano, señalalo" in s


SECCIONES_INTACTAS = [
    "Movimientos del metodo",
    "Lo que SI se responde directo",
    "Abrir el lazo",
    "Cerrar el lazo",
    "Principios",
    "Lo que NO hace el tutor",
    "Formato de respuesta",
    "Contexto del TP",
    "El codigo que el estudiante esta escribiendo",
    "Usar el material del ejercicio",
    "Uso del material de catedra",
    "Uso de la rubrica de evaluacion",
    "Temas fuera del scope del tutor",
]


@pytest.mark.parametrize("encabezado", SECCIONES_INTACTAS)
def test_lo_que_no_se_toco_sigue_byte_a_byte(encabezado: str) -> None:
    """El hash del manifest detecta que el prompt cambio; no que cambio solo
    donde se dijo. Esto si: todo lo que no es la seccion nueva queda identico a
    v1.10.0."""
    assert _seccion(VERSION, encabezado) == _seccion(PADRE, encabezado), (
        f"'{encabezado}' cambio respecto de {PADRE} y el bump declara que no"
    )


def test_el_cuerpo_antes_de_los_movimientos_no_cambia() -> None:
    """El parrafo de apertura (despues del header) tampoco se toco."""

    def apertura(version: str) -> str:
        texto = _prompt(version)
        i = texto.index("Sos un tutor socratico de programacion")
        return texto[i : texto.index("## Movimientos del metodo")]

    assert apertura(VERSION) == apertura(PADRE)
