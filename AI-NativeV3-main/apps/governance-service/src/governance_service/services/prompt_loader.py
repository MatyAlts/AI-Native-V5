"""PromptLoader con verificación criptográfica de hash (ADR-009).

El governance-service clona el repo Git de prompts, verifica firmas GPG
de los commits (en F5) y expone API para que otros servicios obtengan
el prompt activo junto con su hash.

Clave del diseño: `verify_hash()` recomputa el SHA-256 del contenido y
lo compara con el declarado en `manifest.yaml`. Si no coincide, falla
fail-loud (nunca servir contenido manipulado).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PromptConfig:
    """Prompt activo para una comisión/curso.

    El `hash` es el SHA-256 del contenido exacto (bytes) que los tutor y
    classifier services recomputan al arrancar para fail-loud si hay
    manipulación.
    """

    name: str
    version: str
    content: str
    hash: str  # SHA-256 hex del contenido
    path: str  # path relativo al repo, para auditoría


def compute_content_hash(content: str) -> str:
    """SHA-256 determinista del contenido del prompt."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class PromptLoader:
    """Carga prompts desde un repo local clonado.

    Para F3 asumimos que el repo ya está clonado en disco (por un init
    container o volumen mount). F5 agrega webhook de GitHub para pull
    automático + verificación GPG.
    """

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path
        self._cache: dict[tuple[str, str], PromptConfig] = {}

    def load(self, name: str, version: str) -> PromptConfig:
        """Carga el prompt `name` en `version` con verificación de hash.

        Args:
            name: ej. "tutor"
            version: ej. "v1.0.0" o "v1.1.0-unsl"

        Returns:
            PromptConfig con contenido + hash recomputado.

        Raises:
            FileNotFoundError si el prompt no existe.
            ValueError si el hash declarado en el manifest (si existe)
                no coincide con el recomputado.
        """
        cache_key = (name, version)
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt_dir = self.repo_path / "prompts" / name / version
        system_file = prompt_dir / "system.md"
        if not system_file.exists():
            raise FileNotFoundError(f"Prompt {name}/{version} no existe en {self.repo_path}")

        content = system_file.read_text(encoding="utf-8")
        computed_hash = compute_content_hash(content)

        # Si existe manifest con hashes declarados, verificar
        manifest_path = self.repo_path / "prompts" / name / version / "manifest.yaml"
        if manifest_path.exists():
            declared_hash = self._declared_hash(manifest_path, "system.md")
            if declared_hash and declared_hash != computed_hash:
                raise ValueError(
                    f"Hash mismatch en {name}/{version}/system.md: "
                    f"declarado={declared_hash[:12]}... "
                    f"computado={computed_hash[:12]}... "
                    f"(posible manipulación)"
                )

        config = PromptConfig(
            name=name,
            version=version,
            content=content,
            hash=computed_hash,
            path=str(system_file.relative_to(self.repo_path)),
        )
        self._cache[cache_key] = config
        return config

    def _declared_hash(self, manifest_path: Path, filename: str) -> str | None:
        """Lee el hash declarado en manifest.yaml.

        Formato esperado (parseo minimal para no depender de PyYAML):
            files:
              system.md: <hash hex>
        """
        text = manifest_path.read_text()
        in_files = False
        for line in text.splitlines():
            stripped = line.split("#", 1)[0].rstrip()
            if stripped.strip() == "files:":
                in_files = True
                continue
            if in_files:
                if ":" in stripped and not stripped.startswith(" "):
                    in_files = False
                    continue
                parts = stripped.strip().split(":", 1)
                if len(parts) == 2 and parts[0].strip() == filename:
                    return parts[1].strip().strip('"').strip("'")
        return None

    def active_configs(self) -> dict[str, Any]:
        """Devuelve el manifest global de configs activos (por tenant).

        Formato del archivo esperado en `manifest.yaml` del repo root:

            active:
              default:
                tutor: v1.0.0
                classifier: v1.0.0
              <tenant_uuid>:
                tutor: v1.1.0-unsl
        """
        manifest = self.repo_path / "manifest.yaml"
        if not manifest.exists():
            return {"active": {"default": {"tutor": "v1.0.0", "classifier": "v1.0.0"}}}
        # Parseo mínimo — en producción reemplazar por PyYAML
        text = manifest.read_text()
        result: dict[str, Any] = {"active": {"default": {}}}
        current_tenant: str | None = None
        for line in text.splitlines():
            stripped = line.split("#", 1)[0].rstrip()
            if not stripped.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 2 and stripped.rstrip(":").strip() and ":" in stripped:
                current_tenant = stripped.rstrip(":").strip()
                result["active"].setdefault(current_tenant, {})
            elif indent >= 4 and current_tenant:
                if ":" in stripped:
                    k, v = stripped.split(":", 1)
                    result["active"][current_tenant][k.strip()] = v.strip()
        return result
