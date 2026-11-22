"""Aceptacion HU-011, tramo 1, segunda ronda (orquestador, antes de corregir;
el constructor no la modifica). Sale de la verificacion independiente del
PR #143 (22/11/2026). Juani: "si dale" a la ronda de arreglos.

Contrato que agrega:
  tropiezos_de_episodio(events, language=None)
  trayectoria_alumno: cada episodio puede traer "language" ("python"/"java");
  si viene, manda sobre cualquier heuristica.

N06  Un episodio con language="java" no tiene tropiezos, aunque su stderr
     parezca un error de Python (Java llega al CTR ya traducido).
N07  Un programa Python con "System.out" en un string o comentario no se
     descarta como Java (con language="python" y tambien sin language).
N08  Un error real de Python cuyo mensaje dice "limite de tiempo" o
     "interrumpida" cuenta como tropiezo: lo de la plataforma se reconoce
     solo cuando el mensaje entero es de la plataforma.
C07  La trayectoria ordena por fecha real, no por texto: husos distintos.
"""

from __future__ import annotations

from platform_ops.tropiezos import trayectoria_alumno, tropiezos_de_episodio


def _ejec(seq: int, stderr: str = "", code: str = "x = 1") -> dict:
    return {
        "seq": seq,
        "event_type": "codigo_ejecutado",
        "ts": f"2026-11-22T10:{seq:02d}:00Z",
        "payload": {
            "code": code,
            "stdout": "" if stderr else "ok\n",
            "stderr": stderr,
            "duration_ms": 5,
            "runtime": "pyodide-0.26",
        },
    }


def _ep(eid: str, opened_at: str, events: list[dict], language: str | None = None) -> dict:
    e = {"episode_id": eid, "tarea_practica_id": "TP1", "opened_at": opened_at, "events": events}
    if language is not None:
        e["language"] = language
    return e


VALUE = "ValueError: invalid literal for int() with base 10: 'hola'"


def test_n06_episodio_java_no_tiene_tropiezos() -> None:
    eventos = [_ejec(1, "TypeError: bad operand"), _ejec(2)]
    assert tropiezos_de_episodio(eventos, language="java") == []
    tray = trayectoria_alumno([_ep("e1", "2026-11-01T10:00:00Z", eventos, language="java")])
    assert tray["por_tipo"] == {}


def test_n06_el_mismo_episodio_en_python_si_cuenta() -> None:
    eventos = [_ejec(1, "TypeError: bad operand"), _ejec(2)]
    assert len(tropiezos_de_episodio(eventos, language="python")) == 1


def test_n07_system_out_en_un_string_python_no_es_java() -> None:
    code = 'print("System.out.println no es Python")\nint("hola")'
    eventos = [_ejec(1, VALUE, code=code), _ejec(2, code=code)]
    assert [t["tipo"] for t in tropiezos_de_episodio(eventos, language="python")] == ["ValueError"]
    assert [t["tipo"] for t in tropiezos_de_episodio(eventos)] == ["ValueError"]


def test_n07_public_static_void_main_en_un_comentario_python_no_es_java() -> None:
    code = "# public static void main(String[] args)\nint('hola')"
    eventos = [_ejec(1, VALUE, code=code), _ejec(2, code=code)]
    assert [t["tipo"] for t in tropiezos_de_episodio(eventos)] == ["ValueError"]


def test_n08_error_real_que_menciona_limite_de_tiempo_cuenta() -> None:
    t = tropiezos_de_episodio(
        [_ejec(1, "ValueError: el limite de tiempo debe ser positivo"), _ejec(2)]
    )
    assert [x["tipo"] for x in t] == ["ValueError"]


def test_n08_error_real_que_menciona_interrumpida_cuenta() -> None:
    t = tropiezos_de_episodio([_ejec(1, "RuntimeError: la conexion fue interrumpida"), _ejec(2)])
    assert len(t) == 1


def test_n08_el_mensaje_de_la_plataforma_sigue_sin_contar() -> None:
    plataforma = "Tu programa supero el limite de tiempo y se interrumpio. Suele ser un bucle que nunca termina."
    assert tropiezos_de_episodio([_ejec(1, plataforma), _ejec(2)]) == []


def test_c07_ordena_por_fecha_real_con_husos_distintos() -> None:
    # e_z es 10:00 UTC; e_ar es 09:00 en -03:00, o sea 12:00 UTC: va despues.
    e_ar = _ep("e_ar", "2026-11-02T09:00:00-03:00", [_ejec(1, VALUE), _ejec(2)])
    e_z = _ep("e_z", "2026-11-02T10:00:00Z", [_ejec(1, VALUE), _ejec(2)])
    ap = trayectoria_alumno([e_ar, e_z])["por_tipo"]["ValueError"]["apariciones"]
    assert [a["episode_id"] for a in ap] == ["e_z", "e_ar"]
