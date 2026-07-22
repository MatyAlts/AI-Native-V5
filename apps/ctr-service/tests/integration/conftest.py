"""Fixtures para tests de integración.

Skip automático si Docker no está disponible. Los tests de este dir se
ejecutan en CI pero no en sandboxes sin Docker.
"""

from __future__ import annotations

import shutil

import pytest


def _docker_available() -> bool:
    """True si podemos correr contenedores."""
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
    reason="Docker no disponible (tests de integración se corren en CI)",
)
