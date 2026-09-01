"""`integrity_compromised` no puede leerse como "el alumno hizo trampa".

EL HALLAZGO (QA 2026-08-31)
---------------------------
`_move_to_dlq` marca `integrity_compromised=True` siempre que un evento no
entra en la cadena. Como registro tecnico es correcto: el hueco existio. Pero
la palabra se lee como una acusacion, y en el piloto es una acusacion sobre una
persona real.

Y hay algo peor que el reporte de QA no dice, y que sale de leer el codigo:
**ninguna de las causas que llegan hasta aca es adulteracion.**

  - La adulteracion la detecta el integrity-checker comparando hashes ya
    persistidos, no el worker de ingesta.
  - `_es_transitorio` ya garantiza que un fallo de infraestructura no llegue a
    la DLQ: Postgres cortado, Redis caido y pool agotado se reintentan sin tope
    y el mensaje queda en la PEL.

Lo que queda, entonces, es SIEMPRE una falla nuestra: un `seq` que no encaja,
un episodio que no existe, un payload mal armado. O sea que el flag se prende
exclusivamente por errores propios y se lee como sospecha sobre el alumno.

`_causa_del_hueco` no cambia el flag —es un invariante documentado (RN-039 /
RN-040) y el hueco realmente ocurrio— pero rotula de que familia es, en la fila
de la DLQ, en el log y en el label de la metrica.

Es una funcion pura y estatica: no necesita worker, Redis ni Postgres.

QUE **NO** ARREGLA ESTO — leer antes de citarlo
-----------------------------------------------
El nombre del archivo puede hacer creer que cierra el hallazgo de la PERDIDA de
eventos. No lo cierra, y conviene que quede escrito porque hay un paper que
depende de esa distincion.

Medido sobre el almacen de produccion el 2026-09-01:

    eventos en dead_letters      10.061   (535 episodios)
    huecos de secuencia               0
    seq duplicados                    0

Diez mil eventos fuera de la cadena y la secuencia perfectamente contigua. La
causa sigue intacta: `_reponer_contador_seq` repone el contador al
`events_count` vigente, asi que el numero del evento perdido lo ocupa uno
posterior y el agujero se cierra sobre si mismo. El Algoritmo 1 devuelve OK.

Corolario incomodo: **la comprobacion de contigüidad de `seq` —la correccion
"obvia"— no habria detectado ninguna de las 10.061.** No hay huecos que
encontrar. Detectar perdida en ingreso exige un contador de emision separado
del de persistencia, o el ancla externa de la atestacion.

Lo que este cambio arregla es otra cosa, real y mas chica: que la fila de la
DLQ diga de que familia es el hueco en vez de dejar que `integrity_compromised`
se lea como una acusacion.
"""

from __future__ import annotations

import pytest
from ctr_service.workers.partition_worker import PartitionWorker

causa = PartitionWorker._causa_del_hueco


class TestElHuecoDeIngesta:
    """El caso tipico y el mas caro de confundir."""

    @pytest.mark.parametrize(
        "error",
        [
            "ValueError: seq inesperado: expected 87, got 85",
            "expected_seq mismatch",
            "El seq esperado era 12",
        ],
    )
    def test_un_seq_que_no_encaja_es_hueco_de_ingesta(self, error: str) -> None:
        """Verificado por reversion: sin el rotulo, la fila de la DLQ dice
        `ValueError: seq inesperado` y el dashboard dice "episodio
        comprometido" — dos formas de no decir de quien fue la culpa.
        """
        assert causa(error) == "hueco_de_ingesta"


class TestElEpisodioAusente:
    @pytest.mark.parametrize(
        "error",
        [
            "Episode not found: 3f2a...",
            "el episodio no existe",
            "NoResultFound: episode",
        ],
    )
    def test_se_rotula_aparte(self, error: str) -> None:
        """Es otra falla nuestra, pero de otra familia: no hubo hueco en una
        cadena, hubo un evento que apunta a una cadena que no esta. Meterlos
        juntos hace que el contador no sirva para decidir que arreglar."""
        assert causa(error) == "episodio_ausente"


class TestElResto:
    @pytest.mark.parametrize(
        "error",
        [
            "json.JSONDecodeError: Expecting value",
            "ValidationError: 3 validation errors for EventIn",
            "",
        ],
    )
    def test_cae_al_rotulo_generico(self, error: str) -> None:
        """Default abierto pero honesto: no inventa una causa que no puede
        deducir del texto, y el nombre igual dice que el problema es el evento,
        no el alumno."""
        assert causa(error) == "evento_no_procesable"


class TestNingunaCausaAcusaAlAlumno:
    def test_los_tres_rotulos_hablan_del_sistema(self) -> None:
        """La propiedad que este cambio viene a fijar.

        Si alguien agrega un cuarto rotulo que nombre al alumno —"sospechoso",
        "adulterado", "tampering"— este test se lo dice. La adulteracion se
        detecta en otro lado; desde el worker de ingesta no se puede afirmar.
        """
        rotulos = {
            causa("seq inesperado"),
            causa("episode not found"),
            causa("lo que sea"),
        }
        prohibidas = ("alumno", "estudiante", "trampa", "adulter", "sospech", "tamper")
        for rotulo in rotulos:
            for palabra in prohibidas:
                assert palabra not in rotulo, f"el rotulo {rotulo!r} acusa a una persona"

    def test_son_estables_y_pocos(self) -> None:
        """Van como label de metrica: la cardinalidad tiene que ser chica y
        conocida. Un rotulo derivado del texto del error explotaria el
        cardinal del dashboard."""
        vistos = {
            causa(e)
            for e in (
                "seq inesperado",
                "expected 5",
                "episode not found",
                "json roto",
                "",
                "x" * 500,
            )
        }
        assert vistos <= {"hueco_de_ingesta", "episodio_ausente", "evento_no_procesable"}


class TestEsRobusta:
    def test_no_le_importan_las_mayusculas(self) -> None:
        assert causa("SEQ INESPERADO") == "hueco_de_ingesta"

    def test_aguanta_un_stack_trace_entero(self) -> None:
        traza = "Traceback (most recent call last):\n  File x\nValueError: seq inesperado 9"
        assert causa(traza) == "hueco_de_ingesta"

    def test_el_seq_gana_sobre_episodio_cuando_estan_los_dos(self) -> None:
        """Un error que menciona los dos es un hueco en la cadena de un
        episodio que si existe. Rotularlo `episodio_ausente` mandaria a buscar
        el problema al lado equivocado."""
        assert causa("seq inesperado en episode 3f2a") == "hueco_de_ingesta"
