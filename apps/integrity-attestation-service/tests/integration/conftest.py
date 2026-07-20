"""Fixtures para tests de integracion del integrity-attestation-service.

Mismo patron que `apps/ctr-service/tests/integration/conftest.py`: skip auto
si Docker no esta disponible.
"""

from __future__ import annotations

import shutil

import pytest


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    import subprocess

    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker no disponible (tests de integracion se corren en CI)",
)
