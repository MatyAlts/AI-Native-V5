#!/usr/bin/env python
"""Banco de medicion del costo criptografico de la bitacora (Tabla IV del paper).

Mide las filas de COMPUTO de la Tabla IV importando las funciones REALES de la
realizacion — no copias ni reimplementaciones:

    fila  1  sobrecosto de sellado por evento (self_hash + chain_hash)
    fila  2  throughput de sellado (reciproco de la fila 1)
    fila  3  tamano canonico del evento, por tipo
    fila  8  verificacion de un episodio
    fila  9  verificacion de una traza larga
    fila 10  firma Ed25519 de la atestacion de cierre
    fila 11  verificacion de firma Ed25519 (la operacion del auditor)

Las filas 3 a 7 de ALMACENAMIENTO no salen de aca: son consultas de solo lectura
sobre el almacen y viven en `scripts/volumen-almacen.sql`.

Uso:
    uv run python scripts/bench-tabla-iv.py
    uv run python scripts/bench-tabla-iv.py --repeticiones 5000 --traza 100000

Que NO mide, y conviene no confundir
------------------------------------
Mide el costo del SELLADO, que es lo que la arquitectura agrega sobre una
escritura comun. El camino completo de captura (XADD a Redis -> consumer ->
INSERT en Postgres, serializado por episodio) esta dominado por la base de
datos y por la red, no por el hash: el numero de la fila 2 es el techo del
sellado, no el throughput sostenible del sistema.

Reporta ademas el entorno de medicion, incluida la version de la biblioteca
criptografica, que es la variable dominante de las filas 10 y 11: la misma
maquina con otra version de `cryptography`/OpenSSL da numeros distintos.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from ctr_service.services.hashing import (
    GENESIS_HASH,
    canonicalize,
    compute_chain_hash,
    compute_self_hash,
    verify_chain_integrity,
)
from integrity_attestation_service.services.signing import (
    compute_canonical_buffer,
    sign_buffer,
    verify_buffer,
)

# Hashes de configuracion de ejemplo: cualquier valor hex de 64 sirve, lo que
# importa es la LONGITUD, porque es lo que pesa en la serializacion canonica.
_H64 = "a" * 64

# Payloads representativos de los tipos de evento que dominan el almacen. Las
# longitudes de texto salen de lo que el piloto produce de verdad: el snapshot
# de codigo es el campo que domina el tamano (ver fila 5 de la Tabla IV).
_CODIGO = (
    "def resolver(n):\n    total = 0\n    for i in range(n):\n        total += i\n    return total\n"
    * 6
)
_PAYLOADS: dict[str, dict] = {
    "episodio_abierto": {"tarea_practica_id": str(uuid4()), "lenguaje": "python"},
    "prompt_enviado": {
        "content": "No entiendo por que me da error en la linea 4, ya probe cambiando el rango",
        "prompt_kind": "duda_conceptual",
        "chunks_used_hash": _H64,
    },
    "tutor_respondio": {
        "content": (
            "Antes de mirar la linea 4, contame que esperas que valga `total` "
            "despues de la primera vuelta del bucle. Si lo escribis a mano para "
            "n=3, que numeros van pasando por ahi?"
        ),
        "tokens_input": 1840,
        "tokens_output": 96,
        "provider": "mistral",
        "chunks_used_hash": _H64,
    },
    "edicion_codigo": {"snapshot": _CODIGO, "origin": "student_typed"},
    "codigo_ejecutado": {"code": _CODIGO, "exit_code": 0, "duration_ms": 412},
    "episodio_cerrado": {"duration_seconds": 1523.4, "reason": "student_closed"},
}


def construir_evento(seq: int, event_type: str, episode_id: str, tenant_id: str) -> dict:
    """Evento con la forma canonica que persiste el ctr-service.

    Misma estructura que `_build_event_canonical` de los seeds: son los campos
    que entran a `canonicalize()` y por lo tanto al `self_hash`.
    """
    ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=seq * 7)
    return {
        "event_uuid": str(uuid4()),
        "episode_id": episode_id,
        "tenant_id": tenant_id,
        "seq": seq,
        "event_type": event_type,
        "ts": ts.isoformat().replace("+00:00", "Z"),
        "payload": _PAYLOADS[event_type],
        "prompt_system_hash": _H64,
        "prompt_system_version": "tutor/v1.3.0",
        "classifier_config_hash": _H64,
    }


def _mezcla(n: int, episode_id: str, tenant_id: str) -> list[dict]:
    """Traza con la mezcla de tipos que produce un episodio real.

    La proporcion sigue la distribucion del almacen del piloto, donde
    `edicion_codigo` domina por lejos. Importa para el tamano canonico
    promedio: medir solo sobre el evento mas chico subestimaria la fila 3.
    """
    # 14 : 2 : 1 : 1 — proporcion aproximada del almacen del piloto, donde
    # `edicion_codigo` es el 72 % de los eventos y `prompt_enviado` el 1,8 %.
    tipos = (
        ["edicion_codigo"] * 14
        + ["codigo_ejecutado"] * 2
        + ["prompt_enviado"]
        + ["tutor_respondio"]
    )
    eventos = [construir_evento(0, "episodio_abierto", episode_id, tenant_id)]
    for i in range(1, n):
        eventos.append(construir_evento(i, tipos[i % len(tipos)], episode_id, tenant_id))
    return eventos


def _sellar(eventos: list[dict]) -> list[tuple[dict, str, str]]:
    """Sella una traza completa y devuelve el formato que espera el verificador."""
    sellados: list[tuple[dict, str, str]] = []
    prev = GENESIS_HASH
    for ev in eventos:
        sh = compute_self_hash(ev)
        ch = compute_chain_hash(sh, prev)
        sellados.append((ev, sh, ch))
        prev = ch
    return sellados


def _fmt(us: float) -> str:
    return f"{us / 1000:.4f} ms" if us >= 1000 else f"{us:.2f} us"


def medir_sellado(repeticiones: int) -> dict:
    """Filas 1 y 2: costo de sellar un evento (self_hash + chain_hash)."""
    episode_id, tenant_id = str(uuid4()), str(uuid4())
    eventos = [
        construir_evento(i, t, episode_id, tenant_id)
        for i, t in enumerate(list(_PAYLOADS) * (repeticiones // len(_PAYLOADS) + 1))
    ][:repeticiones]

    prev = GENESIS_HASH
    muestras: list[float] = []
    for ev in eventos:
        t0 = time.perf_counter()
        sh = compute_self_hash(ev)
        ch = compute_chain_hash(sh, prev)
        muestras.append((time.perf_counter() - t0) * 1e6)
        prev = ch

    media = statistics.mean(muestras)
    return {
        "n": repeticiones,
        "media_us": media,
        "mediana_us": statistics.median(muestras),
        "p95_us": sorted(muestras)[int(len(muestras) * 0.95)],
        "throughput": 1e6 / media,
    }


def medir_tamano() -> dict:
    """Fila 3: tamano canonico del evento, por tipo y promedio ponderado."""
    episode_id, tenant_id = str(uuid4()), str(uuid4())
    por_tipo = {
        t: len(canonicalize(construir_evento(1, t, episode_id, tenant_id))) for t in _PAYLOADS
    }
    traza = _mezcla(500, episode_id, tenant_id)
    promedio = statistics.mean(len(canonicalize(ev)) for ev in traza)
    return {"por_tipo": por_tipo, "promedio_mezcla": promedio}


def medir_verificacion(n_episodio: int, n_traza: int) -> dict:
    """Filas 8 y 9: verificacion de cadena, en un episodio y en una traza larga.

    Se reportan las DOS: el paper debe declarar cual usa como "episodio tipico"
    y con que n, porque el costo por evento es plano y el total escala lineal.
    """
    out = {}
    for etiqueta, n in (("episodio", n_episodio), ("traza", n_traza)):
        sellados = _sellar(_mezcla(n, str(uuid4()), str(uuid4())))
        t0 = time.perf_counter()
        ok, primera_mala = verify_chain_integrity(sellados)
        dt = (time.perf_counter() - t0) * 1e6
        assert ok and primera_mala is None, "la cadena recien sellada debe verificar"
        out[etiqueta] = {"n": n, "total_us": dt, "por_evento_us": dt / n}
    return out


def medir_ed25519(repeticiones: int) -> dict:
    """Filas 10 y 11: firma y verificacion de la atestacion de cierre."""
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    buffer = compute_canonical_buffer(
        episode_id=uuid4(),
        tenant_id=uuid4(),
        final_chain_hash="b" * 64,
        total_events=208,
        ts_episode_closed="2026-06-01T12:30:00Z",
    )

    t0 = time.perf_counter()
    for _ in range(repeticiones):
        firma = sign_buffer(sk, buffer)
    firmar_us = (time.perf_counter() - t0) * 1e6 / repeticiones

    t0 = time.perf_counter()
    for _ in range(repeticiones):
        verify_buffer(pk, buffer, firma)
    verificar_us = (time.perf_counter() - t0) * 1e6 / repeticiones

    assert verify_buffer(pk, buffer, firma), "la firma recien producida debe verificar"
    return {
        "n": repeticiones,
        "firmar_us": firmar_us,
        "firmar_ops": 1e6 / firmar_us,
        "verificar_us": verificar_us,
        "verificar_ops": 1e6 / verificar_us,
        "buffer_bytes": len(buffer),
    }


def entorno() -> dict:
    """Condicion de medicion. Va al pie de la Tabla IV.

    La version de `cryptography`/OpenSSL es la variable dominante de las filas
    10 y 11: sin declararla, esas dos celdas no son reproducibles ni siquiera
    en la misma maquina despues de actualizar dependencias.
    """
    import cryptography
    from cryptography.hazmat.backends.openssl.backend import backend

    return {
        "python": sys.version.split()[0],
        "cryptography": cryptography.__version__,
        "openssl": backend.openssl_version_text(),
        "plataforma": f"{platform.machine()} · {platform.system()} {platform.release()}",
        "cpus": os.cpu_count(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--repeticiones", type=int, default=5000, help="muestras de sellado y de Ed25519"
    )
    ap.add_argument("--episodio", type=int, default=208, help="eventos del episodio de la fila 8")
    ap.add_argument("--traza", type=int, default=100_000, help="eventos de la traza de la fila 9")
    ap.add_argument("--json", action="store_true", help="salida cruda para procesar")
    args = ap.parse_args()

    env = entorno()
    sellado = medir_sellado(args.repeticiones)
    tam = medir_tamano()
    verif = medir_verificacion(args.episodio, args.traza)
    ed = medir_ed25519(args.repeticiones)

    if args.json:
        print(
            json.dumps(
                {
                    "entorno": env,
                    "sellado": sellado,
                    "tamano": tam,
                    "verificacion": verif,
                    "ed25519": ed,
                },
                indent=2,
                default=str,
            )
        )
        return 0

    print("\nCONDICION DE MEDICION")
    print(f"  Python {env['python']} · cryptography {env['cryptography']}")
    print(f"  {env['openssl']}")
    print(f"  {env['plataforma']} · {env['cpus']} nucleos")

    print("\nTABLA IV — filas de computo")
    print(
        f"  1  sellado por evento .......... {_fmt(sellado['media_us'])}"
        f"   (mediana {_fmt(sellado['mediana_us'])} · p95 {_fmt(sellado['p95_us'])} · n={sellado['n']})"
    )
    print(f"  2  throughput de sellado ....... {sellado['throughput']:,.0f} eventos/s")
    print(
        f"  3  tamano canonico ............. {tam['promedio_mezcla']:,.0f} B  (promedio sobre mezcla real)"
    )
    for t, b in sorted(tam["por_tipo"].items(), key=lambda kv: -kv[1]):
        print(f"       {t:.<28} {b:>6,} B")
    e, tr = verif["episodio"], verif["traza"]
    print(
        f"  8  verificacion de episodio .... {_fmt(e['total_us'])}"
        f"   (n={e['n']} eventos · {e['por_evento_us']:.2f} us/evento)"
    )
    print(
        f"  9  verificacion de traza ....... {_fmt(tr['total_us'])}"
        f"   (n={tr['n']:,} eventos · {tr['por_evento_us']:.2f} us/evento)"
    )
    print(
        f" 10  firma Ed25519 ............... {ed['firmar_ops']:,.0f} op/s"
        f"   ({_fmt(ed['firmar_us'])} · buffer de {ed['buffer_bytes']} B)"
    )
    print(
        f" 11  verificacion Ed25519 ........ {ed['verificar_ops']:,.0f} op/s   ({_fmt(ed['verificar_us'])})"
    )

    print("\n  El costo por evento de las filas 8 y 9 debe coincidir: es la misma")
    print("  funcion. Si difieren mas alla del ruido, la pendiente publicada")
    print("  tiene que declarar sobre cual de las dos se ajusto.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
