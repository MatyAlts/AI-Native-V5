"""Devolver una entrega tiene que REABRIRLE los ejercicios al alumno.

EL BUG (QA 2026-08-31)
----------------------
`return_entrega` hacia una sola cosa: `estado = "returned"`. Del lado del alumno
eso pintaba un cartel

    "Devuelta para revisar. Tu docente devolvio la entrega con observaciones."

y NADA MAS: ni boton de ejercicio ni boton de entregar, porque `ExerciseListView`
gateaba los dos con `estado === "draft"`.

O sea que el boton "Devolver al estudiante" le mostraba al alumno un cartel que
lo invitaba a revisar y le sacaba todas las herramientas para revisar. Un docente
podia pasarse semanas devolviendo TP creyendo que llegaban.

Lo que mas duele: la capacidad ya estaba construida. `MarkEjercicioBody.completado`
acepta `False` desde el 2026-06-19 —"reapertura docente: el docente reabrio el
episodio para que el alumno lo retome"— y nadie la invocaba nunca. La salida de
emergencia estaba hecha y no habia ninguna puerta que llevara a ella.

POR QUE ES UN TEST UNITARIO SOBRE EL HELPER
-------------------------------------------
La propiedad que importa —"al devolver, ningun ejercicio queda completado, y la
lista original no se muta"— es del helper, no de la base. Los tests de
integracion contra Postgres cubren el endpoint entero; estos corren siempre, en
cualquier maquina, sin `EVAL_TEST_DB_URL`. La leccion de agosto es justamente
que un test que no corre no prueba nada.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from evaluation_service.routes.entregas import _reabrir_ejercicios


def _estado(orden: int, *, completado: bool = True, episode: str | None = None) -> dict[str, Any]:
    return {
        "ejercicio_id": str(uuid.uuid4()),
        "orden": orden,
        "episode_id": episode or str(uuid.uuid4()),
        "completado": completado,
        "completed_at": "2026-08-20T14:03:00+00:00" if completado else None,
    }


class TestReabreTodo:
    def test_ningun_ejercicio_queda_completado(self) -> None:
        """El corazon del fix.

        Verificado por reversion: sin `_reabrir_ejercicios`, `return_entrega`
        deja los cinco en True y el alumno recibe la devolucion sin un solo
        boton con el que responderla.
        """
        estados = [_estado(i) for i in range(1, 6)]

        reabiertos = _reabrir_ejercicios(estados)

        assert [e["completado"] for e in reabiertos] == [False] * 5

    def test_limpia_completed_at(self) -> None:
        """Un par que dice dos cosas incompatibles —"no completado, el martes a
        las 14:03"— alguien lo va a leer como fecha de entrega."""
        reabiertos = _reabrir_ejercicios([_estado(1)])

        assert reabiertos[0]["completed_at"] is None

    def test_conserva_el_episode_id_del_intento_anterior(self) -> None:
        """El episodio viejo sigue cerrado, firmado y siendo la evidencia.

        Y en el medio es lo UNICO que permite recuperar el codigo del intento
        anterior: `recuperarArtefactos` cae a `getEpisodeState(episode_id)`
        cuando no hay borrador local. Borrarlo aca dejaria al alumno sin poder
        entregar lo que ya habia escrito.
        """
        ep = str(uuid.uuid4())
        reabiertos = _reabrir_ejercicios([_estado(1, episode=ep)])

        assert reabiertos[0]["episode_id"] == ep

    def test_conserva_ejercicio_id_y_orden(self) -> None:
        """Sin `ejercicio_id` el PATCH siguiente no matchea y appendea un
        estado duplicado — el bug que `_reconciliar_estados` ya documenta."""
        estados = [_estado(1), _estado(2)]
        ids = [e["ejercicio_id"] for e in estados]

        reabiertos = _reabrir_ejercicios(estados)

        assert [e["ejercicio_id"] for e in reabiertos] == ids
        assert [e["orden"] for e in reabiertos] == [1, 2]


class TestNoMutaElValorCargado:
    def test_devuelve_una_copia_profunda(self) -> None:
        """La trampa del JSONB, que en este repo ya mordio dos veces.

        `list()` copia la lista pero COMPARTE los dicts. Si el helper mutara
        esos dicts, SQLAlchemy compararia el valor viejo contra el nuevo, los
        veria iguales (son los mismos objetos, ya mutados) y NO emitiria el
        UPDATE. La columna es JSONB plano sin `MutableList`: nadie avisa. El
        flush pasa limpio, el endpoint devuelve 200 y el cambio no se guardo.

        O sea: el sintoma seria "devolver anda pero no hace nada" — que es
        exactamente el bug que este cambio viene a cerrar, reintroducido por su
        propio fix.
        """
        estados = [_estado(1), _estado(2)]
        antes = copy.deepcopy(estados)

        reabiertos = _reabrir_ejercicios(estados)

        assert estados == antes, "muto la lista original"
        assert reabiertos[0] is not estados[0], "comparte los dicts"


class TestBordes:
    def test_lista_vacia(self) -> None:
        assert _reabrir_ejercicios([]) == []

    def test_none(self) -> None:
        """Una entrega monolitica puede tener `ejercicio_estados` en NULL."""
        assert _reabrir_ejercicios(None) == []

    def test_uno_ya_incompleto_sigue_incompleto(self) -> None:
        """Idempotente: reabrir lo ya abierto no puede romperlo."""
        estados = [_estado(1, completado=True), _estado(2, completado=False)]

        reabiertos = _reabrir_ejercicios(estados)

        assert [e["completado"] for e in reabiertos] == [False, False]

    def test_no_inventa_claves(self) -> None:
        """Un estado guardado por una version vieja puede no tener todas las
        claves. Agregarle campos aca los persistiria como si fueran datos."""
        magro = {"orden": 1, "completado": True}

        reabiertos = _reabrir_ejercicios([magro])

        assert set(reabiertos[0]) == {"orden", "completado", "completed_at"}
