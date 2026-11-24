"""Genera `esperados.json` corriendo cada caso con PSeInt oficial (HU-030, C11).

El árbitro de la paridad es PSeInt oficial, no nuestro intérprete: este script
se corre a mano, una vez, cuando se agregan o cambian casos, y el resultado se
commitea. Las pruebas de `paridad.test.ts` solo leen `esperados.json`.

Uso:
    python3 generar_esperados.py RUTA/AL/BINARIO/pseint

Versión usada para generar el archivo commiteado: PSeInt 20250314, Linux 64
bits (`pseint-l64-20250314.tgz` de SourceForge), perfil por defecto (sin
`--profile`).

Reglas de traducción de la salida de PSeInt:
- Se corre con `--nouser --fortest --rawerrors`: sin mensajes de estado y con
  los errores en formato fijo (`=== Line N: SynError C` / `ExeError C`).
- PSeInt lee los `.psc` en latin-1 y escribe en latin-1: se convierte ida y
  vuelta, así que los casos y el JSON quedan en UTF-8.
- Cada `Leer` escribe el indicador `> ` antes de esperar el dato. Es eco de la
  consola, no salida del algoritmo, y se quita (igual que el preludio de Python
  quita el texto de `input()`): se borra todo `> ` repetido al principio de una
  línea. Ningún caso escribe `> ` por su cuenta al principio de una línea.
- Un error de sintaxis no ejecuta nada: `tipo = "error_sintaxis"`, `linea` es la
  del primer error y `salida` queda vacía.
- Un error de ejecución corta el algoritmo: `tipo = "error_ejecucion"`, `linea`
  es la del error y `salida` es lo escrito antes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CASOS = AQUI / "casos"
SALIDA = AQUI / "esperados.json"

ERROR = re.compile(r"^=== Line (\d+): (SynError|ExeError) (\d+)\s*$")
INDICADOR_LEER = re.compile(r"(?m)^(?:> )+")


def correr(binario: str, caso: Path) -> dict[str, object]:
    entrada_path = caso.with_suffix(".entrada")
    entrada = entrada_path.read_text(encoding="utf-8") if entrada_path.exists() else ""
    with tempfile.TemporaryDirectory() as tmp:
        fuente = Path(tmp) / "caso.psc"
        fuente.write_bytes(caso.read_text(encoding="utf-8").encode("latin-1"))
        proc = subprocess.run(  # noqa: S603 - binario que elige quien regenera, a mano
            [binario, str(fuente), "--nouser", "--fortest", "--rawerrors"],
            input=entrada.encode("latin-1"),
            capture_output=True,
            timeout=20,
            check=False,
        )
    texto = INDICADOR_LEER.sub("", proc.stdout.decode("latin-1"))
    lineas = texto.splitlines(keepends=True)
    for i, linea in enumerate(lineas):
        m = ERROR.match(linea)
        if m:
            sintaxis = m.group(2) == "SynError"
            previa = "" if sintaxis else "".join(lineas[:i])
            return {
                "tipo": "error_sintaxis" if sintaxis else "error_ejecucion",
                "linea": int(m.group(1)),
                "codigo_pseint": int(m.group(3)),
                "salida": previa,
            }
    return {"tipo": "ok", "linea": None, "codigo_pseint": None, "salida": texto}


def main() -> None:
    binario = sys.argv[1]
    esperados = {caso.stem: correr(binario, caso) for caso in sorted(CASOS.glob("*.psc"))}
    SALIDA.write_text(json.dumps(esperados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(esperados)} casos -> {SALIDA.name}")


if __name__ == "__main__":
    main()
