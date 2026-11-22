"""Imprime la trayectoria de tropiezos de un alumno y la serie del juez (HU-011).

MODO SOMBRA: lee archivos JSON locales y escribe texto por pantalla. No lee
bases de datos, no usa la red y no guarda nada.

Uso:

    uv run python scripts/trayectoria-sombra.py episodios.json [clasificaciones.json]

`episodios.json`: lista de episodios de UN alumno,
    [{"episode_id", "tarea_practica_id", "opened_at", "events": [...],
      "language": "python" | "java"}]
    donde `events` son los eventos CTR del episodio (`seq`, `event_type`,
    `payload`). `language` es opcional: si viene, manda (un episodio Java no
    tiene tropiezos); si no, se usa la heuristica de Java del modulo.

`clasificaciones.json` (opcional):
    [{"episode_id", "opened_at", "features": {"regimen_llm": {...}}}]

La salida es ASCII a proposito (consola cp1252 de Windows, ver CLAUDE.md).
Que mide y que no: `docs/research/indicio-aprendizaje.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from platform_ops.tropiezos import serie_juez, trayectoria_alumno

_RESOLUCION = {"solo": "solo", "con_tutor": "con tutor", "sin_resolver": "SIN RESOLVER"}
_TENDENCIA = {"mejora": "MEJORA", "sin_cambio": "sin cambio", "sin_datos": "sin datos (1 episodio)"}


def _leer(path: str) -> list[dict[str, Any]]:
    datos = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(datos, list):
        raise SystemExit(f"[FAIL] {path}: se esperaba una lista JSON")
    return datos


def _ascii(x: object) -> str:
    return str(x).encode("ascii", "replace").decode("ascii")


def _fecha(opened_at: object) -> str:
    return _ascii(opened_at)[:10] if opened_at else "?"


def imprimir_lenguajes(episodios: list[dict[str, Any]]) -> None:
    conteo: dict[str, int] = {}
    for ep in episodios:
        lenguaje = ep.get("language")
        clave = lenguaje if isinstance(lenguaje, str) and lenguaje else "sin dato"
        conteo[clave] = conteo.get(clave, 0) + 1
    partes = ", ".join(f"{_ascii(k)} {v}" for k, v in sorted(conteo.items()))
    print(f"EPISODIOS: {len(episodios)} (lenguaje: {partes})")
    if conteo.get("java"):
        print("  Los episodios Java no aportan tropiezos.")
    print()


def imprimir_trayectoria(tray: dict[str, Any]) -> None:
    print(f"TROPIEZOS (version {tray['version']}, modo sombra)")
    if not tray["por_tipo"]:
        print("  Sin errores de Python en los episodios.")
        return
    for tipo in sorted(tray["por_tipo"]):
        entrada = tray["por_tipo"][tipo]
        print()
        print(
            f"{tipo}  ->  tendencia: {_TENDENCIA.get(entrada['tendencia'], entrada['tendencia'])}"
        )
        for a in entrada["apariciones"]:
            if a["mismo_tp"] is None:
                tp_rel = "primera vez"
            else:
                tp_rel = "mismo TP" if a["mismo_tp"] else "otro TP"
            seq = f"seq {a['seq_inicio']}" + (
                f"-{a['seq_fin']}" if a["seq_fin"] is not None else ""
            )
            print(
                f"  {_fecha(a['opened_at'])}  TP {_ascii(a['tarea_practica_id'])} ({tp_rel})"
                f"  intentos {a['intentos']}  {_RESOLUCION.get(a['resolucion'], a['resolucion'])}"
                f"  [ep {_ascii(a['episode_id'])}, {seq}]"
            )


def imprimir_serie(serie: list[dict[str, str]], fechas: dict[str, str]) -> None:
    print()
    print("SERIE DEL JUEZ (solo episodios donde decidio)")
    if not serie:
        print("  Sin veredictos del juez.")
        return
    print(
        f"  {'fecha':<10}  {'episodio':<12}  {'D1 verb.':<12}  {'D2 verif.':<12}  {'D3 just.':<12}  D4 autonomia"
    )
    for s in serie:
        print(
            f"  {fechas.get(s['episode_id'], '?'):<10}  {_ascii(s['episode_id'])[:12]:<12}"
            f"  {s['d1']:<12}  {s['d2']:<12}  {s['d3']:<12}  {s['d4']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("episodios", help="JSON con los episodios de un alumno")
    parser.add_argument(
        "clasificaciones", nargs="?", help="JSON con las clasificaciones (opcional)"
    )
    args = parser.parse_args(argv)

    episodios = _leer(args.episodios)
    imprimir_lenguajes(episodios)
    imprimir_trayectoria(trayectoria_alumno(episodios))
    if args.clasificaciones:
        clasif = _leer(args.clasificaciones)
        fechas = {str(c.get("episode_id")): _fecha(c.get("opened_at")) for c in clasif}
        imprimir_serie(serie_juez(clasif), fechas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
