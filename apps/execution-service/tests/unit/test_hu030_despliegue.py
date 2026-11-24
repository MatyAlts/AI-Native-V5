"""Aceptacion HU-030 (orquestador, antes de construir; el constructor no la
modifica). Criterios acordados con Juani el 24/11/2026.

C13  Tres ejercicios de prueba (secuencial con Leer, arreglos, funciones)
     listos para cargar en "Prog 1 · Pruebas", con casos que la solucion de
     referencia pasa en el interprete (eso lo verifica `ejercicios.test.ts`).
C14  GitHub construye y publica la imagen del sandbox; los scripts de
     verificacion y la guia de deploy incluyen `PSEINT_IMAGE`.
N04  Los prompts del tutor quedan intactos byte a byte.
K01  `CLAUDE.md` del codigo nombra PSeInt y la lista de lenguajes de navegador.
K02  `docs/EASYPANEL-DEPLOY.md` explica `PSEINT_IMAGE` y que pasa si falta.
K03  ADR nuevo con el interprete propio y el perfil.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]

# Huella de `ai-native-prompts/prompts/tutor/` en `main` (3f97d4a), 23 archivos.
HUELLA_PROMPTS_TUTOR = "cbc856dc08142a6c65895e8cbd52424b15a6d546f7b7bd0ee596fe72c131acbe"


def _leer(rel: str) -> str:
    p = RAIZ / rel
    assert p.exists(), f"falta {rel}"
    return p.read_text(encoding="utf-8")


def test_n04_prompts_del_tutor_intactos() -> None:
    base = RAIZ / "ai-native-prompts" / "prompts" / "tutor"
    h = hashlib.sha256()
    for p in sorted(base.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(base)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    assert h.hexdigest() == HUELLA_PROMPTS_TUTOR


def test_c14_dockerfile_del_sandbox() -> None:
    df = _leer("infrastructure/pseint-sandbox.Dockerfile")
    lineas_from = [ln for ln in df.splitlines() if ln.strip().upper().startswith("FROM ")]
    assert lineas_from, "el Dockerfile no tiene FROM"
    final = lineas_from[-1]
    assert "node" in final.lower()
    assert "@sha256:" in final, "la base de la imagen final va por digest (control C1)"
    assert "/opt/pseint/run.js" in df
    assert "USER" in df, "la imagen no corre como root"


def test_c14_workflow_que_publica_la_imagen() -> None:
    wf = _leer(".github/workflows/pseint-sandbox.yml")
    assert "infrastructure/pseint-sandbox.Dockerfile" in wf
    assert "ghcr.io" in wf
    assert "packages/pseint/**" in wf, "se reconstruye cuando cambia el interprete"
    assert "packages: write" in wf


def test_c14_scripts_de_verificacion_y_arranque() -> None:
    assert "PSEINT_IMAGE" in _leer("scripts/verificar-despliegue-ejecucion.sh")
    assert "PSEINT_IMAGE" in _leer("scripts/dev-start-all.sh")


def test_k02_guia_de_deploy() -> None:
    guia = _leer("docs/EASYPANEL-DEPLOY.md")
    assert "PSEINT_IMAGE" in guia
    assert "lenguaje_no_disponible" in guia or "sin ejecutar" in guia.lower()


def test_k01_claude_md_del_codigo() -> None:
    claude = _leer("CLAUDE.md")
    assert "PSeInt" in claude
    assert "LENGUAJES_DE_NAVEGADOR" in claude


def test_k03_adr_del_interprete() -> None:
    adrs = sorted((RAIZ / "docs" / "adr").glob("*pseint*.md"))
    assert adrs, "falta el ADR de PSeInt en docs/adr"
    texto = adrs[0].read_text(encoding="utf-8")
    assert "perfil" in texto.lower()
    assert "20250314" in texto, "el ADR nombra la version de PSeInt usada como arbitro"


def test_c12_perfil_documentado() -> None:
    perfil = _leer("packages/pseint/PERFIL.md")
    for regla in ("20250314", "arreglos", "Leer"):
        assert regla in perfil, regla


def test_c13_tres_ejercicios_de_prueba() -> None:
    carpeta = RAIZ / "scripts" / "data" / "pseint-prueba"
    archivos = sorted(carpeta.glob("*.json"))
    assert len(archivos) == 3, [a.name for a in archivos]
    temas = set()
    for a in archivos:
        ej = json.loads(a.read_text(encoding="utf-8"))
        assert ej["language"] == "pseint"
        assert ej["solucion_referencia"].strip()
        casos = ej["test_cases"]
        assert len(casos) >= 3
        assert all(c["type"] == "stdin_stdout" for c in casos)
        assert any(c["is_public"] for c in casos) and any(not c["is_public"] for c in casos)
        temas.add(ej["tema"])
    assert temas == {"secuencial", "arreglos", "funciones"}
