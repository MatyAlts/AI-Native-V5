"""La salida de una corrida tiene que tener techo, y el corte tiene que avisarse.

EL HALLAZGO (a partir del reporte de una alumna de Prog 2, 2026-09-01)
----------------------------------------------------------------------
Nada acotaba la salida. `proc.communicate()` acumula todo lo que el programa
escriba, y el modo de falla mas comun de quien recien arranca —un bucle que
imprime— produce cientos de MB en los 10 segundos de wall-time.

Esa cadena despues viajaba entera:

  - a Redis, con TTL de 600 s, en el MISMO VPS que ya corre al 82,8 % en reposo;
  - de ahi al navegador;
  - y el navegador la metia en el DOM.

Con `execution_max_concurrent_runs = 8`, ocho alumnos con un bucle que imprime
alcanzaban para comprometer el servicio de toda la cohorte.

Y lo tercero es lo que explica el sintoma reportado: **una pestaña renderizando
cientos de MB se cuelga**, y colgada se ve exactamente como "la plataforma se
quedo en un bucle infinito" — aunque el bucle sea del programa del alumno y
nosotros ya lo hayamos matado.

POR QUE LA MARCA NO ES DECORATIVA
---------------------------------
Una salida cortada EN SILENCIO se lee como completa. El alumno buscaria el error
en la logica de su programa —"¿por que no imprime el resto?"— en vez de en la
cantidad que imprime, que es el problema real.
"""

from __future__ import annotations

import pytest
from execution_service.config import settings
from execution_service.services.docker_runner import _acotar, _docker_args

LIMITE = settings.execution_max_output_bytes


class TestCortaCuandoSePasa:
    def test_una_salida_enorme_queda_acotada(self) -> None:
        """El corazon del fix.

        Verificado por reversion: sin `_acotar`, esto devuelve los 5 MB enteros
        y de ahi van a Redis y al navegador.
        """
        cinco_megas = b"x" * (5 * 1024 * 1024)

        salida = _acotar(cinco_megas)

        assert len(salida.encode("utf-8")) < LIMITE + 500, "no se acoto"

    def test_avisa_que_corto(self) -> None:
        """Cortar en silencio es peor que no cortar: el alumno lee la salida
        truncada como si fuera toda la que su programa produjo."""
        salida = _acotar(b"y" * (LIMITE * 3))

        assert "salida cortada" in salida

    def test_el_aviso_nombra_el_bucle(self) -> None:
        """Es la pista que convierte el corte en un diagnostico. Imprimir mas de
        256 KB casi nunca es intencional en un ejercicio de catedra."""
        salida = _acotar(b"z" * (LIMITE * 2))

        assert "bucle" in salida.lower()

    def test_conserva_el_principio_de_la_salida(self) -> None:
        """Lo que el alumno necesita leer esta al principio: los primeros
        `println` son los que dicen por donde iba el programa. Cortar por el
        final —o quedarse con la cola— le sacaria justo eso."""
        crudo = b"PRIMERA LINEA IMPORTANTE\n" + b"ruido\n" * (LIMITE // 3)

        salida = _acotar(crudo)

        assert salida.startswith("PRIMERA LINEA IMPORTANTE")


class TestNoMolestaCuandoNoHaceFalta:
    def test_una_salida_normal_pasa_intacta(self) -> None:
        """El caso de todos los dias no puede cambiar ni un byte."""
        crudo = b"Hola\nEl resultado es 42\n"

        assert _acotar(crudo) == "Hola\nEl resultado es 42\n"

    def test_salida_vacia(self) -> None:
        assert _acotar(b"") == ""

    def test_exactamente_en_el_limite_no_se_toca(self) -> None:
        """El borde: `<=` y no `<`. Con `<` una salida de exactamente el limite
        se marcaria como cortada sin haber perdido nada."""
        crudo = b"a" * LIMITE

        salida = _acotar(crudo)

        assert "salida cortada" not in salida
        assert len(salida) == LIMITE


class TestNoRompeConAcentos:
    def test_un_caracter_multibyte_partido_al_medio_no_explota(self) -> None:
        """El corte es sobre BYTES, asi que partir una "ñ" o una tilde a la
        mitad es lo normal aca, no el borde raro. Sin `errors="replace"` esto
        seria un UnicodeDecodeError y la corrida entera se perderia por un
        acento mal ubicado."""
        # Se arma para que el byte del limite caiga en el medio de un caracter.
        crudo = b"a" * (LIMITE - 1) + "ñ".encode() + b"b" * 100

        salida = _acotar(crudo)  # no tira

        assert "salida cortada" in salida

    @pytest.mark.parametrize("texto", ["áéíóú", "ñandú", "日本語", "🙂"])
    def test_una_salida_corta_con_no_ascii_pasa_intacta(self, texto: str) -> None:
        assert _acotar(texto.encode("utf-8")) == texto


class TestElDaemonTampocoGuardaLaSalida:
    """El techo de `_acotar` no alcanza: el daemon guarda su propia copia.

    `docker run` escribe TODO el stdout del contenedor a
    `/var/lib/docker/containers/<id>/<id>-json.log`, sin techo, en disco, por
    fuera del pipe que este proceso lee. `_acotar` corta lo que SALE de aca —
    a Redis, al navegador, al CTR— y no toca esa copia.

    NO ES HIPOTETICO. El 2026-09-01, sobre la maquina de desarrollo del equipo,
    ese directorio tenia 336 GB en `*-json.log`, con dos archivos sueltos de
    18 GB, y habia llenado un disco de 460 GB al 100 %.

    El detalle que lo hace peligroso: `docker system df` reportaba 26 GB. NO
    cuenta los logs de contenedores. La herramienta que deberia avisar es
    exactamente ciega donde esta el problema — asi que el disco se llena sin
    que ninguna metrica se mueva.

    En el VPS del piloto el que imprime no es un experimento: son alumnos con
    bucles infinitos, hasta 8 en paralelo por el semaforo de concurrencia.
    """

    def test_el_contenedor_corre_SIN_log_driver(self) -> None:
        """Verificado por reversion: sacar el flag deja el log del daemon
        creciendo sin techo, y no hay nada mas en el sistema que lo acote."""
        assert "--log-driver=none" in _docker_args("class Main {}")

    def test_no_perdemos_la_salida_del_alumno(self) -> None:
        """El flag es seguro porque la salida viaja por el PIPE, que es de donde
        la leemos. El log del daemon era una copia que nadie consulta: no hay
        ningun `docker logs` en el camino de lectura de este servicio."""
        assert "-i" in _docker_args("class Main {}")
