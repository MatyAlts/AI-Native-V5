#!/usr/bin/env python3
"""Validación read-only de la nueva medición de apropiación (Fase 1 de B1).

Compara, episodio por episodio, la **etiqueta actual** del clasificador en
producción (importando la lógica REAL de classifier-service, sin reimplementar)
contra el **subgrupo nuevo** (4 dimensiones / 7 subgrupos) definido en
`docs/NUEVA-MEDICION-SUBGRUPOS.md`.

NO toca nada vivo: solo lee. Dos fuentes de datos:
  --self-test   episodios canónicos sintéticos (incluye el autónomo que el motor
                viejo invierte). No necesita DB ni prod. Es el default.
  --db          lee episodios cerrados reales de ctr_store (SELECT, read-only).
                DSN desde --dsn o env CTR_STORE_URL.

Uso:
    uv run python scripts/validate_subgrupos.py --self-test
    uv run python scripts/validate_subgrupos.py --db --limit 25
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ── Bootstrap: importar la lógica REAL del classifier (sin reimplementar) ──
_SRC = Path(__file__).resolve().parent.parent / "apps" / "classifier-service" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from classifier_service.services.ccd import compute_ccd  # noqa: E402
from classifier_service.services.cii import compute_cii  # noqa: E402
from classifier_service.services.ct import ct_features  # noqa: E402
from classifier_service.services.tree import classify  # noqa: E402

# ── Constantes (🔧 calibrables — ver docs/NUEVA-MEDICION-SUBGRUPOS.md) ──
PROMPT_SCALE = 6
EXEC_SCALE = 8
FOCUS_SCALE = 3
MIN_EVENTS = 4
DEP_SOLICITA = 2          # prompts solicitud_directa para marcar delegación
DEP_EXP = 0.4
REFLEX_EXP = 0.4
TRABADO_MIN_EJEC = 2      # ejecuciones mínimas para "peleó" (trabado real vs abandonó temprano)
EDIT_MIN = 10             # ediciones para "escribió bastante" (separa desenganchado de escribe-sin-validar)

_REFLECTIVE_KINDS = {
    "exploracion",
    "aclaracion_enunciado",
    "comparativa",
    "epistemologica",
    "validacion",
}
# Mismos exclusiones que pipeline.py::_EXCLUDED_FROM_FEATURES
_EXCLUDED = frozenset({"reflexion_completada", "tp_entregada", "tp_calificada"})


@dataclass
class Subgrupo:
    key: str
    label: str
    accion_docente: str
    eje: str  # roll-up a los 3 ejes (opción A)


INDETERMINADO = Subgrupo("indeterminado", "Indeterminado 🔒", "No concluir — episodio muy corto", "sin_clasificar")
AUTONOMO_COMPETENTE = Subgrupo("autonomo_competente", "Autónomo competente ⭐", "Darle más desafío", "reflexiva")
AUTONOMO_TRABADO = Subgrupo("autonomo_trabado", "Autónomo trabado 🆘", "Ofrecer scaffolding — NO delegó", "superficial")
DESENGANCHADO = Subgrupo("desenganchado", "Desenganchado 💤", "Re-enganchar", "superficial")
ESCRIBE_SIN_VALIDAR = Subgrupo("escribe_sin_validar", "Escribió sin validar 📝", "Fomentar el hábito de ejecutar y probar el código", "superficial")
DEPENDIENTE = Subgrupo("dependiente_delegador", "Dependiente / delegador ⚠️", "Intervenir (copió de la IA)", "delegacion_pasiva")
COLABORADOR_REFLEXIVO = Subgrupo("colaborador_reflexivo", "Colaborador reflexivo ✅", "Va bien", "reflexiva")
COLABORADOR_FUNCIONAL = Subgrupo("colaborador_funcional", "Colaborador funcional", "Empujar a profundizar/probar", "superficial")


# ── Helpers sobre la serie de eventos ──
def _kind(e: dict) -> str:
    return (e.get("payload") or {}).get("prompt_kind") or ""


def _count(events: list[dict], et: str) -> int:
    return sum(1 for e in events if e["event_type"] == et)


def _significativos(events: list[dict]) -> list[dict]:
    return [e for e in events if e["event_type"] not in _EXCLUDED]


# ── Las 4 dimensiones (cada una en [0,1]) ──
def dim_autonomia(events: list[dict]) -> tuple[float, float]:
    """Devuelve (autonomia, paste_ratio). 1.0 = autónomo puro.

    Ajustado a los datos REALES de prod (2026-06-10): el `origin` de
    `edicion_codigo` es `student_typed` / `pasted_external` — NO existe
    `copied_from_tutor`. La señal de "código no propio" es `pasted_external`.
    """
    prompts = _count(events, "prompt_enviado")
    ediciones = [e for e in events if e["event_type"] == "edicion_codigo"]
    pegadas = sum(1 for e in ediciones if (e.get("payload") or {}).get("origin") == "pasted_external")
    paste_ratio = pegadas / len(ediciones) if ediciones else 0.0
    comp_prompts = 1.0 - min(1.0, prompts / PROMPT_SCALE)
    return 0.5 * comp_prompts + 0.5 * (1.0 - paste_ratio), paste_ratio


def dim_experimentacion(events: list[dict]) -> float:
    ex = _count(events, "codigo_ejecutado") + _count(events, "tests_ejecutados")
    return min(1.0, ex / EXEC_SCALE)


def dim_persistencia(events: list[dict]) -> float:
    """Ajustado a prod (2026-06-10): no hay tests_ejecutados. Un "fallo" es un
    codigo_ejecutado con stderr no vacío; persistencia = recuperación tras error."""
    sorted_ev = sorted(events, key=lambda e: e["seq"])
    fallos = 0
    recup = 0
    for i, e in enumerate(sorted_ev):
        p = e.get("payload") or {}
        if e["event_type"] == "codigo_ejecutado" and (p.get("stderr") or "") != "":
            fallos += 1
            if any(ev["event_type"] in ("edicion_codigo", "codigo_ejecutado") for ev in sorted_ev[i + 1:]):
                recup += 1
    if fallos == 0:
        return 1.0  # no se trabó (no hubo error de ejecución)
    return recup / fallos


def dim_foco(events: list[dict]) -> float:
    # prod (2026-06-10): existen DOS anti-trampa — copia_intentada Y pega_intentada.
    distr = (
        _count(events, "pestana_perdida")
        + _count(events, "copia_intentada")
        + _count(events, "pega_intentada")
    )
    return 1.0 / (1.0 + distr / FOCUS_SCALE)


def _resolvio(events: list[dict]) -> bool:
    """Refinado (2026-06-10): la ÚLTIMA ejecución del episodio terminó limpia.
    No hay tests_ejecutados/tp_entregada en el CTR real — la señal es
    codigo_ejecutado con stdout no vacío y stderr vacío en la última corrida.
    'Terminó funcionando' es mejor proxy de 'lo logró' que 'alguna vez le anduvo'."""
    ejec = [e for e in sorted(events, key=lambda e: e["seq"]) if e["event_type"] == "codigo_ejecutado"]
    if not ejec:
        return False
    p = ejec[-1].get("payload") or {}
    return (p.get("stdout") or "") != "" and (p.get("stderr") or "") == ""


def _verbaliza(events: list[dict]) -> bool:
    if _count(events, "anotacion_creada") > 0:
        return True
    return any(e["event_type"] == "prompt_enviado" and _kind(e) in _REFLECTIVE_KINDS for e in events)


# ── El árbol de 7 subgrupos ──
def subgrupo(events: list[dict]) -> Subgrupo:
    sig = _significativos(events)
    if len(sig) < MIN_EVENTS:
        return INDETERMINADO

    prompts = _count(events, "prompt_enviado")
    ejec = _count(events, "codigo_ejecutado")
    ediciones = _count(events, "edicion_codigo")
    exp = dim_experimentacion(events)
    sol_directa = sum(
        1 for e in events
        if e["event_type"] == "prompt_enviado" and _kind(e) == "solicitud_directa"
    )

    # "Trabajó poco": pocas ediciones Y casi sin ejecutar. Editar mucho YA es trabajo.
    poco_trabajo = ediciones < EDIT_MIN and ejec < TRABADO_MIN_EJEC

    if prompts == 0:
        # FIX inversión: sin prompts, delegar es imposible → rama autónoma.
        if poco_trabajo:
            return DESENGANCHADO          # trabajó poco en general → re-enganchar
        if _resolvio(events):
            return AUTONOMO_COMPETENTE
        if ejec >= TRABADO_MIN_EJEC:
            return AUTONOMO_TRABADO       # peleó ejecutando, no logró → scaffolding
        return ESCRIBE_SIN_VALIDAR        # escribió bastante pero casi no ejecutó/probó

    # prompts > 0 → usó el tutor. La delegación se chequea ANTES que "poco trabajo":
    # el delegador labura poco JUSTAMENTE porque copia — pero usó el tutor, no está desenganchado.
    if sol_directa >= DEP_SOLICITA and exp < DEP_EXP:
        return DEPENDIENTE                # delegación real: pidió código directo + poca acción propia
    if poco_trabajo:
        return DESENGANCHADO
    if exp >= REFLEX_EXP:
        return COLABORADOR_REFLEXIVO
    return COLABORADOR_FUNCIONAL


def dimensiones(events: list[dict]) -> dict[str, float]:
    auto, _ = dim_autonomia(events)
    return {
        "autonomia": round(auto, 2),
        "experimentacion": round(dim_experimentacion(events), 2),
        "persistencia": round(dim_persistencia(events), 2),
        "foco": round(dim_foco(events), 2),
    }


# ── Etiqueta ACTUAL: reproduce el pipeline real (pipeline.py:72-92) ──
def etiqueta_actual(events: list[dict]) -> str:
    classifier_events = [e for e in events if e.get("event_type") not in _EXCLUDED]
    ct = ct_features(classifier_events)
    ccd = compute_ccd(classifier_events)
    cii = compute_cii(classifier_events)
    return classify(ct=ct, ccd=ccd, cii=cii).appropriation


# ── Casos canónicos sintéticos para --self-test ──
_BASE = datetime.fromisoformat("2026-06-09T22:00:00+00:00")


def _ev(seq: int, et: str, off_s: int, **payload: Any) -> dict:
    return {
        "seq": seq,
        "event_type": et,
        "ts": (_BASE + timedelta(seconds=off_s)).isoformat().replace("+00:00", "Z"),
        "payload": payload,
    }


def _casos() -> list[tuple[str, list[dict]]]:
    casos: list[tuple[str, list[dict]]] = []

    # 1. AUTÓNOMO COMPETENTE — programó solo, sin tutor, última ejecución limpia.
    #    El motor viejo lo INVIERTE a delegacion_pasiva (orphan 1.0).
    seq = 0
    ev = []
    ev.append(_ev(seq, "lectura_enunciado", 0)); seq += 1
    for k in range(6):
        ev.append(_ev(seq, "edicion_codigo", 30 + k * 40, origin="student_typed")); seq += 1
        ev.append(_ev(seq, "codigo_ejecutado", 50 + k * 40, stdout="42\n", stderr="")); seq += 1
    casos.append(("autónomo (solo, corrió ok)", ev))

    # 2. DEPENDIENTE / DELEGADOR — varios prompts solicitud_directa, poca acción propia.
    seq = 0
    ev = []
    ev.append(_ev(seq, "lectura_enunciado", 0)); seq += 1
    for k in range(5):
        ev.append(_ev(seq, "prompt_enviado", 20 + k * 30, prompt_kind="solicitud_directa", content="dame el codigo")); seq += 1
        ev.append(_ev(seq, "edicion_codigo", 35 + k * 30, origin="pasted_external")); seq += 1
    ev.append(_ev(seq, "codigo_ejecutado", 200, stdout="", stderr="NameError"))
    casos.append(("delegador (pide código directo)", ev))

    # 3. COLABORADOR REFLEXIVO — usa el tutor para explorar + experimenta y le corre.
    seq = 0
    ev = []
    ev.append(_ev(seq, "lectura_enunciado", 0)); seq += 1
    for k in range(4):
        ev.append(_ev(seq, "prompt_enviado", 20 + k * 60, prompt_kind="exploracion", content="que pasa si itero distinto el bucle")); seq += 1
        ev.append(_ev(seq, "codigo_ejecutado", 50 + k * 60, stdout="ok\n", stderr="")); seq += 1
    casos.append(("colaborador reflexivo", ev))

    # 4. DESENGANCHADO — casi nada de actividad, perdió la pestaña.
    seq = 0
    ev = []
    ev.append(_ev(seq, "lectura_enunciado", 0)); seq += 1
    ev.append(_ev(seq, "prompt_enviado", 30, prompt_kind="aclaracion_enunciado", content="que hay que hacer")); seq += 1
    ev.append(_ev(seq, "pestana_perdida", 60)); seq += 1
    ev.append(_ev(seq, "edicion_codigo", 90, origin="student_typed"))
    casos.append(("desenganchado", ev))

    return casos


# ── Carga desde DB real (read-only) — para la corrida contra prod ──
def cargar_desde_db(dsn: str, limit: int) -> list[tuple[str, list[dict]]]:
    try:
        import asyncpg  # noqa
        import asyncio
    except ImportError:
        sys.exit("asyncpg no disponible — corré con `uv run` o usá --self-test")

    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    async def _run() -> list[tuple[str, list[dict]]]:
        conn = await asyncpg.connect(dsn)
        # asyncpg devuelve jsonb como str por default; decodificar a dict.
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )
        try:
            eps = await conn.fetch(
                "SELECT id, student_pseudonym FROM episodes "
                "WHERE estado = 'closed' ORDER BY closed_at DESC LIMIT $1",
                limit,
            )
            out: list[tuple[str, list[dict]]] = []
            for ep in eps:
                rows = await conn.fetch(
                    "SELECT seq, event_type, ts, payload FROM events "
                    "WHERE episode_id = $1 ORDER BY seq",
                    ep["id"],
                )
                events = [
                    {"seq": r["seq"], "event_type": r["event_type"],
                     "ts": r["ts"].isoformat().replace("+00:00", "Z"), "payload": r["payload"]}
                    for r in rows
                ]
                label = str(ep["student_pseudonym"])[:8] + " / " + str(ep["id"])[:8]
                out.append((label, events))
            return out
        finally:
            await conn.close()

    return asyncio.run(_run())


# ── Reporte ──
def imprimir_tabla(episodios: list[tuple[str, list[dict]]]) -> None:
    header = f"{'episodio':28} | {'ACTUAL':24} | {'SUBGRUPO NUEVO':26} | {'eje':12} | autn exp pers foco | Δ"
    print(header)
    print("-" * len(header))
    cambios = 0
    salieron_de_delegacion = 0
    for nombre, events in episodios:
        actual = etiqueta_actual(events)
        sg = subgrupo(events)
        d = dimensiones(events)
        cambio = "←CAMBIA" if _eje_actual_difiere(actual, sg.eje) else ""
        if cambio:
            cambios += 1
        if actual == "delegacion_pasiva" and sg.eje != "delegacion_pasiva":
            salieron_de_delegacion += 1
            cambio = "←SALE DE DELEGACIÓN"
        print(
            f"{nombre[:28]:28} | {actual:24} | {sg.label:26} | {sg.eje:12} | "
            f"{d['autonomia']:.2f} {d['experimentacion']:.2f} {d['persistencia']:.2f} {d['foco']:.2f} | {cambio}"
        )
    print("-" * len(header))
    print(f"Total: {len(episodios)} episodios · {cambios} cambian de eje · {salieron_de_delegacion} salen de delegación mal asignada")


def _eje_actual_difiere(actual: str, eje_nuevo: str) -> bool:
    # Normalizar: el motor viejo usa "apropiacion_reflexiva"/"apropiacion_superficial"/
    # "delegacion_pasiva"; el eje nuevo usa "reflexiva"/"superficial"/"delegacion_pasiva".
    if eje_nuevo == "sin_clasificar":
        return False
    return actual.replace("apropiacion_", "") != eje_nuevo


def main() -> None:
    ap = argparse.ArgumentParser(description="Validación read-only de la nueva medición de apropiación")
    ap.add_argument("--self-test", action="store_true", help="usa episodios canónicos sintéticos (default)")
    ap.add_argument("--db", action="store_true", help="lee episodios reales de ctr_store (read-only)")
    ap.add_argument("--dsn", default=os.environ.get("CTR_STORE_URL", ""), help="DSN de ctr_store")
    ap.add_argument("--limit", type=int, default=25, help="máximo de episodios a leer en modo --db")
    args = ap.parse_args()

    if args.db:
        if not args.dsn:
            sys.exit("Falta DSN: pasá --dsn o seteá CTR_STORE_URL")
        episodios = cargar_desde_db(args.dsn, args.limit)
        print(f"# Modo DB — {len(episodios)} episodios cerrados de ctr_store\n")
    else:
        episodios = _casos()
        print("# Modo self-test — episodios canónicos sintéticos\n")

    imprimir_tabla(episodios)


if __name__ == "__main__":
    main()
