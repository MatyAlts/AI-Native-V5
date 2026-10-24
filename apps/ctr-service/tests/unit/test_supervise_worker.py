"""Tests de `ctr-supervise-worker.sh`: un worker caído vuelve, sin solaparse.

El script corre el worker en FOREGROUND dentro de un loop: el siguiente
lanzamiento ocurre recién cuando el anterior terminó, así que nunca hay dos
procesos de la misma partición (single-writer, ADR-010). Acá el "worker" es un
script falso que registra start/end y sale con rc=1; `sleep` se reemplaza por un
falso en PATH para no esperar y poder leer los delays.
"""

# ruff: noqa: S603

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ctr-supervise-worker.sh"

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="requiere sh (POSIX)")


def _posix(p: Path) -> str:
    return p.as_posix()


@pytest.fixture
def entorno(tmp_path: Path) -> dict[str, object]:
    """Worker falso + sleep falso; devuelve rutas y el env base."""
    log = tmp_path / "worker.log"
    sleeps = tmp_path / "sleeps.log"
    worker = tmp_path / "fake-worker"
    worker.write_text(
        f'#!/bin/sh\necho "start $*" >> "{_posix(log)}"\necho "end" >> "{_posix(log)}"\nexit 1\n',
        newline="\n",
    )
    worker.chmod(0o755)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_sleep = bindir / "sleep"
    fake_sleep.write_text(
        f'#!/bin/sh\necho "$1" >> "{_posix(sleeps)}"\n',
        newline="\n",
    )
    fake_sleep.chmod(0o755)
    env = {
        **os.environ,
        "CTR_VENV_PY": _posix(worker),
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
    }
    return {"log": log, "sleeps": sleeps, "env": env}


def _correr(entorno: dict[str, object], partition: str = "3", **extra: str) -> str:
    env = {**entorno["env"], **extra}  # type: ignore[dict-item]
    r = subprocess.run(
        ["sh", _posix(SCRIPT), partition],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return r.stdout + r.stderr


def test_script_pasa_sintaxis_posix() -> None:
    r = subprocess.run(["sh", "-n", _posix(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_relanza_el_worker_que_muere_y_loguea_particion_y_rc(entorno: dict[str, object]) -> None:
    salida = _correr(entorno, CTR_SUPERVISE_MAX_RESTARTS="3")

    lineas = Path(str(entorno["log"])).read_text().splitlines()
    assert [ln for ln in lineas if ln.startswith("start")] == [
        "start -m ctr_service.workers.partition_worker --partition 3"
    ] * 3
    salidas = [ln for ln in salida.splitlines() if "salio" in ln]
    assert len(salidas) >= 2  # la última puede ser el corte por MAX_RESTARTS
    for ln in salidas:
        assert "partition=3" in ln
        assert "rc=1" in ln


def test_nunca_hay_dos_workers_de_la_misma_particion_a_la_vez(
    entorno: dict[str, object],
) -> None:
    _correr(entorno, CTR_SUPERVISE_MAX_RESTARTS="4")

    marcas = [ln.split()[0] for ln in Path(str(entorno["log"])).read_text().splitlines()]
    assert marcas == ["start", "end"] * 4  # start/end alternados: sin solapamiento


def test_la_particion_viene_del_argumento(entorno: dict[str, object]) -> None:
    _correr(entorno, partition="6", CTR_SUPERVISE_MAX_RESTARTS="1")

    assert "--partition 6" in Path(str(entorno["log"])).read_text()


def test_el_backoff_crece_y_respeta_el_tope(entorno: dict[str, object]) -> None:
    _correr(entorno, CTR_SUPERVISE_MAX_RESTARTS="7", CTR_SUPERVISE_BACKOFF_MAX="10")

    delays = Path(str(entorno["sleeps"])).read_text().split()
    assert delays == ["1", "2", "4", "8", "10", "10"]


def test_el_backoff_se_resetea_si_el_worker_vivio_lo_suficiente(
    entorno: dict[str, object],
) -> None:
    """RESET_AFTER=0: toda corrida cuenta como 'vivió bastante' => delay vuelve a 1."""
    _correr(entorno, CTR_SUPERVISE_MAX_RESTARTS="4", CTR_SUPERVISE_RESET_AFTER="0")

    delays = Path(str(entorno["sleeps"])).read_text().split()
    assert delays == ["1", "1", "1"]
