#!/usr/bin/env python
"""Selector de corpus para la validacion intercoder kappa >= 0,70 (Protocolos A + B).

Implementa la especificacion del paquete de coordinacion
`paquete-coordinacion-intercoder-2026-05-20.md` seccion 2 (sub-secciones 2.1-2.5).

Estado: ESQUELETO con `--dry-run` FUNCIONAL end-to-end sobre datos SINTETICOS.
El path contra DB real (`load_events_from_db` / `load_episodes_from_db`) esta
STUBBEADO con un guard explicito porque depende de:
  - Acceso a las 4 bases del piloto (ACADEMIC_DB_URL / CTR_STORE_URL / CLASSIFIER_DB_URL).
  - Accion A1 cerrada (re-clasificacion de las 106 historicas con LABELER_VERSION 1.2.0)
    para que el corpus NO mezcle versiones del labeler.

La logica de estratificacion + escritura de fichas YAML / ground-truth CSV / metadata.json
es COMPARTIDA entre el path dry-run y el path real: cablear la DB es el unico trabajo restante.

Reusa la FUNCION PURA real `event_labeler.label_event` para calcular el
`nivel_funcion_pura` (ground-truth del Protocolo A) sobre los eventos sinteticos:
asi el dry-run ejercita el path de etiquetado real y la estratificacion es honesta.

Salida stdout: SOLO ASCII (cp1252 en Windows rompe con unicode — gotcha documentado
en el CLAUDE.md del repo, ej. check-rls.py). Usar [OK] / [WARN] / [FAIL].

Uso (ejemplos):
    python scripts/select-intercoder-corpus.py --mode internal-calibration --dry-run
    python scripts/select-intercoder-corpus.py --mode full --dry-run --include-consent-records
    python scripts/select-intercoder-corpus.py --mode protocol-a   # path real (stub -> SystemExit)
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Carga de la funcion pura real `label_event` SIN arrastrar el import chain
# pesado de classifier_service.services.__init__ (que importa pipeline.py ->
# platform_observability, dependencias de runtime/DB que un script de seleccion
# no necesita). Cargamos event_labeler.py por path y lo registramos en
# sys.modules antes de exec_module (necesario por `from __future__ import
# annotations` + @dataclass: dataclasses resuelve los tipos contra
# sys.modules[cls.__module__]).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LABELER_PATH = (
    _REPO_ROOT
    / "apps"
    / "classifier-service"
    / "src"
    / "classifier_service"
    / "services"
    / "event_labeler.py"
)


def _load_real_labeler() -> Any:
    """Carga event_labeler.py como modulo aislado y devuelve el modulo."""
    if not _LABELER_PATH.exists():
        print(
            f"[FAIL] No se encontro el event_labeler real en {_LABELER_PATH}.\n"
            "       El script reusa la funcion pura label_event para el ground-truth.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    mod_name = "intercoder_real_event_labeler"
    spec = importlib.util.spec_from_file_location(mod_name, _LABELER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_LABELER = _load_real_labeler()
label_event = _LABELER.label_event
EpisodeContext = _LABELER.EpisodeContext
LABELER_VERSION = _LABELER.LABELER_VERSION


# ===========================================================================
# === DECISIONES METODOLOGICAS PENDIENTES (Cortez + Garis) ==================
# ===========================================================================
# Estas 4 decisiones NO deben quedar enterradas en el codigo: son del autor de
# la tesis (con la co-directora). Cada constante tiene su DEFAULT placeholder
# vigente + descripcion. Cambiarlas es una decision academica, no de ingenieria.
#
# (1) CIRCULARIDAD DE LA ESTRATIFICACION.
#     El Protocolo A estratifica por la etiqueta de la PROPIA funcion pura del
#     sistema (nivel_funcion_pura via label_event). Esto es circular en apariencia:
#     muestreamos por la verdad que despues queremos validar. La mitigacion es el
#     CEGADO -> la etiqueta del sistema viaja SOLO en ground-truth-*.csv (NO en la
#     ficha del etiquetador). Si se quisiera un estrato complementario por TIPO DE
#     EVENTO crudo (sin pasar por la funcion), poner True abajo y agregar la rama.
STRATIFY_BY_RAW_EVENT_TYPE_COMPLEMENT = False  # default: estratificar por label del sistema + cegado.

# (2) CONSENTIMIENTO PROTOCOLO B.
#     El Protocolo B expone el TEXTO COMPLETO de los prompts del estudiante (la
#     categoria de apropiacion depende del discurso). Eso requiere consentimiento
#     informado especifico, separado del consentimiento general del piloto
#     (ver docs/limitaciones-declaradas.md). Default: gateado detras del flag
#     --include-consent-records con WARNING explicito.
CONSENT_PROTOCOL_B_REQUIRED = True  # default: exigir el flag de consentimiento para exponer prompts.

# (3) POLITICA ANTE ESTRATO SUB-POBLADO.
#     Que hacer si un estrato (ej. N1, tipicamente <5% de la poblacion real) tiene
#     MENOS eventos disponibles que el n requerido. Default: tomar todos los
#     disponibles + WARN (no inventar datos). Alternativas a decidir:
#       "reduce_target"  -> bajar el n de TODOS los estratos al minimo comun.
#       "oversample"     -> permitir repeticion (NO recomendado: sesga kappa).
#       "declare_limit"  -> abortar y declarar la limitacion en el reporte.
UNDERPOPULATED_STRATUM_POLICY = "take_all_available"  # take_all_available | reduce_target | oversample | declare_limit

# (4) SELECCION DENTRO DEL ESTRATO.
#     Una vez fijado el estrato, como se eligen los n elementos. Default: aleatorio
#     puro seeded (reproducible). Alternativa "purposive_boundary": incluir
#     deliberadamente casos limite (anotacion a 119s vs 121s, tests a 59s vs 60s
#     post-tutor) que son los que mas tensionan el manual del etiquetador.
WITHIN_STRATUM_SELECTION = "random_seeded"  # random_seeded | purposive_boundary
# ===========================================================================


# ---------------------------------------------------------------------------
# Constantes de dominio (alineadas a manual-etiquetador-N4.md y al labeler real).
# ---------------------------------------------------------------------------
N_LEVELS = ["N1", "N2", "N3", "N4"]
APPROPRIATION_CATEGORIES = [
    "apropiacion_reflexiva",
    "apropiacion_superficial",
    "delegacion_pasiva",
]
CONTEXT_WINDOW_SECONDS = 60.0  # +-60s de contexto preservado por evento (spec 2.2 / manual 1.2).

SCRIPT_VERSION = "1.0.0"
DEFAULT_SEED = 20260520


# ---------------------------------------------------------------------------
# Modelos internos (representacion homogenea para dry-run y path real).
# ---------------------------------------------------------------------------
@dataclass
class SyntheticEvent:
    """Un evento del CTR (sintetico o cargado de DB) en forma homogenea."""

    event_id: str
    event_type: str
    ts: datetime
    seq: int
    payload: dict[str, Any]
    episode_id: str
    # Contexto temporal del episodio para que label_event aplique overrides.
    episode_started_at: datetime | None = None
    last_tutor_respondio_at: datetime | None = None

    def to_context(self) -> Any:
        return EpisodeContext(
            event_ts=self.ts,
            episode_started_at=self.episode_started_at,
            last_tutor_respondio_at=self.last_tutor_respondio_at,
        )

    def nivel_funcion_pura(self) -> str:
        """Ground-truth N1-N4 via la funcion pura REAL del clasificador."""
        return label_event(self.event_type, self.payload, context=self.to_context())


@dataclass
class SyntheticEpisode:
    """Un episodio cerrado (sintetico o de DB) para el Protocolo B."""

    episode_id: str
    duracion_total_min: int
    n_eventos: int
    distribucion_niveles: dict[str, float]
    cadena_eventos: list[dict[str, Any]]
    prompts_estudiante: list[str]
    # Ground-truth: categoria de apropiacion (en dry-run viene del generador;
    # en el path real vendria de classifier_db.classifications).
    categoria_ground_truth: str
    features: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# YAML manual (sin depender de PyYAML para no agregar dependencia obligatoria;
# PyYAML esta disponible pero el output es controlado y simple, asi el script
# corre aunque el entorno no lo tenga).
# ---------------------------------------------------------------------------
def _yaml_scalar(value: Any) -> str:
    """Serializa un escalar a YAML de forma segura y deterministica."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    s = str(value)
    # Quote si tiene caracteres que rompen YAML plano o si esta vacio.
    needs_quote = (
        s == ""
        or s != s.strip()
        or any(c in s for c in ':#{}[],&*!|>\'"%@`')
        or s in ("null", "true", "false", "~")
        or s.startswith(("- ", "? "))
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


# ---------------------------------------------------------------------------
# Generacion de datos SINTETICOS (dry-run). Deterministica con --seed.
# Se construyen eventos que disparan cada nivel N1-N4 segun las reglas reales
# del manual, para que la estratificacion por label_event sea honesta.
# ---------------------------------------------------------------------------
_NOTE_TEXTS = [
    "estoy leyendo el enunciado y parece que pide ordenar una lista de numeros enteros",
    "no entiendo del todo como iterar sobre el diccionario sin repetir claves",
    "el tutor sugirio usar recursion pero quiero entender por que termina",
    "voy a reescribir esta funcion con mis palabras para ver si la entiendo",
    "creo que el caso base de la recursion esta mal planteado todavia",
    "anotacion rapida de lectura inicial antes de empezar a codear nada",
]
_PROMPT_REFLEXIVA = [
    "por que conviene usar un set en lugar de una lista para buscar duplicados?",
    "que pasa si la entrada esta vacia, como deberia comportarse la funcion?",
    "cual es la diferencia entre iterar con indice y con el iterador directo?",
]
_PROMPT_SUPERFICIAL = [
    "como hago para recorrer la lista y sumar los pares?",
    "podes mostrarme un ejemplo de como usar un for con enumerate?",
    "que sintaxis tiene un diccionario por comprension en python?",
]
_PROMPT_DELEGACION = [
    "no funciona, ayudame a arreglarlo",
    "dame el codigo que resuelve este ejercicio completo",
    "escribime la funcion que ordena la lista",
]


def _mk_event(
    *,
    rng: random.Random,
    counter: dict[str, int],
    episode_id: str,
    episode_started_at: datetime,
    base_ts: datetime,
    seq: int,
    event_type: str,
    payload: dict[str, Any],
    last_tutor_respondio_at: datetime | None,
) -> SyntheticEvent:
    counter["n"] += 1
    return SyntheticEvent(
        event_id=f"ev_{counter['n']:04d}",
        event_type=event_type,
        ts=base_ts,
        seq=seq,
        payload=payload,
        episode_id=episode_id,
        episode_started_at=episode_started_at,
        last_tutor_respondio_at=last_tutor_respondio_at,
    )


def _synthesize_events_for_level(
    target_level: str,
    n: int,
    rng: random.Random,
    counter: dict[str, int],
) -> list[SyntheticEvent]:
    """Genera n eventos cuya etiqueta de la funcion pura es `target_level`.

    Se construyen contextos temporales realistas (episodio + tutor) para que
    label_event aplique los overrides (anotacion N1/N4, tests N3/N4) tal cual
    los aplicaria sobre datos reales. La etiqueta se VERIFICA tras generar.
    """
    out: list[SyntheticEvent] = []
    attempts = 0
    while len(out) < n and attempts < n * 50:
        attempts += 1
        epi = f"ep_dry_{rng.randint(1, 9999):04d}"
        started = datetime(2026, 4, 15, 14, 0, 0, tzinfo=timezone.utc) + timedelta(
            minutes=rng.randint(0, 600)
        )
        ev: SyntheticEvent | None = None

        if target_level == "N1":
            choice = rng.random()
            if choice < 0.5:
                ts = started + timedelta(seconds=rng.uniform(0, 30))
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=1,
                    event_type="lectura_enunciado",
                    payload={"duration_seconds": round(rng.uniform(5, 90), 1)},
                    last_tutor_respondio_at=None,
                )
            else:
                # anotacion dentro de los primeros 120s y sin tutor reciente -> N1
                delta = rng.uniform(1, 118)
                ts = started + timedelta(seconds=delta)
                text = rng.choice(_NOTE_TEXTS)
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=2,
                    event_type="anotacion_creada",
                    payload={"content": text, "words": len(text.split())},
                    last_tutor_respondio_at=None,
                )
        elif target_level == "N2":
            choice = rng.random()
            if choice < 0.6:
                ts = started + timedelta(seconds=rng.uniform(130, 800))
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=5,
                    event_type="edicion_codigo",
                    payload={
                        "snapshot": "def solve(xs):\n    return sorted(xs)",
                        "diff_chars": rng.randint(5, 200),
                        "language": "python",
                        "origin": "student_typed",
                    },
                    last_tutor_respondio_at=None,
                )
            else:
                # anotacion fuera de toda ventana de override -> N2 (fallback)
                ts = started + timedelta(seconds=rng.uniform(200, 900))
                text = rng.choice(_NOTE_TEXTS)
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=6,
                    event_type="anotacion_creada",
                    payload={"content": text, "words": len(text.split())},
                    last_tutor_respondio_at=None,
                )
        elif target_level == "N3":
            choice = rng.random()
            if choice < 0.5:
                ts = started + timedelta(seconds=rng.uniform(150, 700))
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=7,
                    event_type="codigo_ejecutado",
                    payload={
                        "code": "print(solve([3,1,2]))",
                        "stdout": "[1, 2, 3]",
                        "stderr": None,
                        "duration_ms": rng.randint(20, 400),
                        "runtime": "pyodide",
                    },
                    last_tutor_respondio_at=None,
                )
            else:
                # tests con fallos -> N3 siempre
                ts = started + timedelta(seconds=rng.uniform(150, 700))
                failed = rng.randint(1, 4)
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=8,
                    event_type="tests_ejecutados",
                    payload={
                        "test_count_total": failed + rng.randint(0, 3),
                        "test_count_passed": rng.randint(0, 3),
                        "test_count_failed": failed,
                        "tests_publicos": failed + rng.randint(0, 3),
                        "tests_hidden": 0,
                        "ejecucion_ms": rng.randint(50, 800),
                    },
                    last_tutor_respondio_at=None,
                )
        else:  # N4
            choice = rng.random()
            tutor_ts = started + timedelta(seconds=rng.uniform(60, 400))
            if choice < 0.4:
                ts = tutor_ts + timedelta(seconds=rng.uniform(0.5, 5))
                content = rng.choice(_PROMPT_REFLEXIVA + _PROMPT_SUPERFICIAL)
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=10,
                    event_type="prompt_enviado",
                    payload={"content": content, "prompt_kind": "exploracion"},
                    last_tutor_respondio_at=None,
                )
            elif choice < 0.7:
                # anotacion dentro de los 60s post-tutor -> N4 (gana sobre N1)
                ts = tutor_ts + timedelta(seconds=rng.uniform(1, 58))
                text = rng.choice(_NOTE_TEXTS)
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=12,
                    event_type="anotacion_creada",
                    payload={"content": text, "words": len(text.split())},
                    last_tutor_respondio_at=tutor_ts,
                )
            else:
                # edicion copiada del tutor -> N4 por override de origen
                ts = tutor_ts + timedelta(seconds=rng.uniform(1, 30))
                ev = _mk_event(
                    rng=rng, counter=counter, episode_id=epi,
                    episode_started_at=started, base_ts=ts, seq=13,
                    event_type="edicion_codigo",
                    payload={
                        "snapshot": "def solve(xs):\n    return sorted(set(xs))",
                        "diff_chars": rng.randint(10, 120),
                        "language": "python",
                        "origin": "copied_from_tutor",
                    },
                    last_tutor_respondio_at=tutor_ts,
                )

        if ev is None:
            continue
        # VERIFICACION: la funcion pura real debe coincidir con el nivel objetivo.
        if ev.nivel_funcion_pura() == target_level:
            out.append(ev)
    return out


def synthesize_events(rng: random.Random, per_level: dict[str, int]) -> list[SyntheticEvent]:
    """Genera el universo sintetico de eventos por nivel (mas que el target para
    poder estratificar/muestrear y simular estratos sub/sobre-poblados)."""
    counter = {"n": 0}
    universe: list[SyntheticEvent] = []
    for level in N_LEVELS:
        # Generamos un universo mas grande que el requerido (x4) para simular
        # disponibilidad real y ejercitar el muestreo dentro del estrato.
        want_universe = max(per_level.get(level, 0) * 4, per_level.get(level, 0))
        universe.extend(_synthesize_events_for_level(level, want_universe, rng, counter))
    return universe


def _build_synthetic_episode(
    rng: random.Random, idx: int, category: str
) -> SyntheticEpisode:
    """Construye un episodio cerrado sintetico con prompts coherentes con la categoria."""
    if category == "apropiacion_reflexiva":
        prompts = rng.sample(_PROMPT_REFLEXIVA, k=rng.randint(2, 3)) + rng.sample(
            _NOTE_TEXTS, k=1
        )
        dist = {"N1": 0.12, "N2": 0.40, "N3": 0.24, "N4": 0.24}
    elif category == "apropiacion_superficial":
        prompts = rng.sample(_PROMPT_SUPERFICIAL, k=rng.randint(2, 3))
        dist = {"N1": 0.10, "N2": 0.30, "N3": 0.30, "N4": 0.30}
    else:  # delegacion_pasiva
        prompts = rng.sample(_PROMPT_DELEGACION, k=rng.randint(2, 3))
        dist = {"N1": 0.05, "N2": 0.15, "N3": 0.20, "N4": 0.60}

    n_eventos = rng.randint(20, 110)
    started = datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc) + timedelta(
        minutes=rng.randint(0, 600)
    )
    dur_min = rng.randint(15, 75)
    cadena = [
        {"seq": 1, "ts": started.isoformat().replace("+00:00", "Z"), "event_type": "episodio_abierto"},
        {
            "seq": 2,
            "ts": (started + timedelta(seconds=20)).isoformat().replace("+00:00", "Z"),
            "event_type": "lectura_enunciado",
        },
        {
            "seq": n_eventos,
            "ts": (started + timedelta(minutes=dur_min)).isoformat().replace("+00:00", "Z"),
            "event_type": "episodio_cerrado",
        },
    ]
    return SyntheticEpisode(
        episode_id=f"ep_{idx:03d}",
        duracion_total_min=dur_min,
        n_eventos=n_eventos,
        distribucion_niveles=dist,
        cadena_eventos=cadena,
        prompts_estudiante=prompts,
        categoria_ground_truth=category,
        features={"branch": category, "source": "synthetic-dry-run"},
    )


def synthesize_episodes(
    rng: random.Random, per_category: dict[str, int]
) -> list[SyntheticEpisode]:
    universe: list[SyntheticEpisode] = []
    idx = 1
    for cat in APPROPRIATION_CATEGORIES:
        want_universe = max(per_category.get(cat, 0) * 4, per_category.get(cat, 0))
        for _ in range(want_universe):
            universe.append(_build_synthetic_episode(rng, idx, cat))
            idx += 1
    return universe


# ---------------------------------------------------------------------------
# ESTRATIFICACION (compartida dry-run <-> real).
# ---------------------------------------------------------------------------
@dataclass
class StratumReport:
    name: str
    requested: int
    available: int
    selected: int


def _select_within_stratum(
    items: list[Any], n: int, rng: random.Random
) -> tuple[list[Any], int]:
    """Aplica WITHIN_STRATUM_SELECTION + UNDERPOPULATED_STRATUM_POLICY.

    Devuelve (seleccionados, n_efectivo). No invent datos: si hay menos de n
    disponibles, aplica la politica (default take_all_available)."""
    available = len(items)
    if available <= n:
        if UNDERPOPULATED_STRATUM_POLICY == "declare_limit" and available < n:
            print(
                f"[FAIL] Estrato sub-poblado y politica=declare_limit: "
                f"disponibles={available} < requeridos={n}.",
                file=sys.stderr,
            )
            raise SystemExit(3)
        return list(items), available
    if WITHIN_STRATUM_SELECTION == "purposive_boundary":
        # Placeholder: en datos reales aqui se priorizarian casos limite.
        # Por ahora, mismo muestreo aleatorio seeded (decision pendiente).
        return rng.sample(items, n), n
    return rng.sample(items, n), n


def stratify_events(
    events: list[SyntheticEvent], per_level: dict[str, int], rng: random.Random
) -> tuple[list[SyntheticEvent], list[StratumReport]]:
    """Estratifica eventos por nivel_funcion_pura (decision metodologica 1)."""
    by_level: dict[str, list[SyntheticEvent]] = {lv: [] for lv in N_LEVELS}
    for ev in events:
        lv = ev.nivel_funcion_pura()
        if lv in by_level:
            by_level[lv].append(ev)

    selected: list[SyntheticEvent] = []
    reports: list[StratumReport] = []
    for lv in N_LEVELS:
        want = per_level.get(lv, 0)
        # Orden determinista antes de muestrear (reproducibilidad).
        pool = sorted(by_level[lv], key=lambda e: e.event_id)
        chosen, eff = _select_within_stratum(pool, want, rng)
        selected.extend(chosen)
        reports.append(
            StratumReport(name=lv, requested=want, available=len(pool), selected=len(chosen))
        )
        if eff < want:
            print(
                f"[WARN] Estrato {lv}: disponibles={len(pool)} < requeridos={want}. "
                f"Politica={UNDERPOPULATED_STRATUM_POLICY} -> seleccionados {len(chosen)}.",
                file=sys.stderr,
            )
    return selected, reports


def stratify_episodes(
    episodes: list[SyntheticEpisode], per_category: dict[str, int], rng: random.Random
) -> tuple[list[SyntheticEpisode], list[StratumReport]]:
    by_cat: dict[str, list[SyntheticEpisode]] = {c: [] for c in APPROPRIATION_CATEGORIES}
    for ep in episodes:
        if ep.categoria_ground_truth in by_cat:
            by_cat[ep.categoria_ground_truth].append(ep)

    selected: list[SyntheticEpisode] = []
    reports: list[StratumReport] = []
    for cat in APPROPRIATION_CATEGORIES:
        want = per_category.get(cat, 0)
        pool = sorted(by_cat[cat], key=lambda e: e.episode_id)
        chosen, eff = _select_within_stratum(pool, want, rng)
        selected.extend(chosen)
        reports.append(
            StratumReport(name=cat, requested=want, available=len(pool), selected=len(chosen))
        )
        if eff < want:
            print(
                f"[WARN] Categoria {cat}: disponibles={len(pool)} < requeridos={want}. "
                f"Politica={UNDERPOPULATED_STRATUM_POLICY} -> seleccionados {len(chosen)}.",
                file=sys.stderr,
            )
    return selected, reports


# ---------------------------------------------------------------------------
# Escritores de output (compartidos dry-run <-> real).
# ---------------------------------------------------------------------------
def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_protocol_a_fiches(
    events: list[SyntheticEvent], out_dir: Path, truncate_chars: int
) -> int:
    """Escribe una ficha YAML por evento (formato manual 1.5). Campo del
    etiquetador VACIO (`nivel_propuesto_por_etiquetador: ___`)."""
    pa_dir = out_dir / "protocol-a"
    pa_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, ev in enumerate(sorted(events, key=lambda e: e.event_id), start=1):
        eid = f"ev_{i:03d}"
        raw_content = ev.payload.get("content")
        content_line = ""
        if raw_content is not None:
            truncated = str(raw_content)[:truncate_chars]
            content_line = f"  content: {_yaml_scalar(truncated)}\n"

        delta_open = None
        if ev.episode_started_at is not None:
            delta_open = round((ev.ts - ev.episode_started_at).total_seconds(), 1)
        delta_tutor = None
        last_tutor = None
        if ev.last_tutor_respondio_at is not None:
            last_tutor = _iso_z(ev.last_tutor_respondio_at)
            delta_tutor = round((ev.ts - ev.last_tutor_respondio_at).total_seconds(), 1)

        ficha = (
            f"event_id: {eid}\n"
            f"event_type: {_yaml_scalar(ev.event_type)}\n"
            f"event_ts: {_yaml_scalar(_iso_z(ev.ts))}\n"
            f"seq: {ev.seq}\n"
            f"payload:\n"
            f"{content_line}"
            f"context:\n"
            f"  episodio_abierto_ts: {_yaml_scalar(_iso_z(ev.episode_started_at) if ev.episode_started_at else None)}\n"
            f"  delta_desde_apertura_s: {_yaml_scalar(delta_open)}\n"
            f"  ultimo_tutor_respondio_ts: {_yaml_scalar(last_tutor)}\n"
            f"  delta_desde_ultimo_tutor_s: {_yaml_scalar(delta_tutor)}\n"
            f"nivel_propuesto_por_etiquetador: ___\n"
            f"nota_libre: ___\n"
        )
        (pa_dir / f"{eid}.yaml").write_text(ficha, encoding="utf-8")
        written += 1
    return written


def write_ground_truth_a(events: list[SyntheticEvent], out_dir: Path) -> Path:
    """CSV (event_id, nivel_funcion_pura). NO entregar a etiquetadores."""
    path = out_dir / "ground-truth-protocol-a.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["# NO ENTREGAR A ETIQUETADORES - ground truth del sistema"])
        w.writerow(["event_id", "nivel_funcion_pura"])
        for i, ev in enumerate(sorted(events, key=lambda e: e.event_id), start=1):
            w.writerow([f"ev_{i:03d}", ev.nivel_funcion_pura()])
    return path


def write_protocol_b_dossiers(
    episodes: list[SyntheticEpisode], out_dir: Path, expose_prompts: bool
) -> int:
    """Escribe un dossier YAML por episodio (formato manual 2.4). Campo del
    etiquetador VACIO (`categoria_propuesta_por_etiquetador: ___`)."""
    pb_dir = out_dir / "protocol-b"
    pb_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, ep in enumerate(sorted(episodes, key=lambda e: e.episode_id), start=1):
        eid = f"ep_{i:03d}"
        dist_lines = "".join(
            f"  {lv}: {ep.distribucion_niveles.get(lv, 0.0)}\n" for lv in N_LEVELS
        )
        cadena_lines = "".join(
            "  - { "
            + f"seq: {e['seq']}, ts: {_yaml_scalar(e['ts'])}, event_type: {_yaml_scalar(e['event_type'])}"
            + " }\n"
            for e in ep.cadena_eventos
        )
        if expose_prompts:
            prompt_lines = "".join(f"  - {_yaml_scalar(p)}\n" for p in ep.prompts_estudiante)
        else:
            prompt_lines = (
                "  # [GATEADO] prompts completos requieren --include-consent-records\n"
                "  # (decision metodologica 2: consentimiento informado especifico Protocolo B)\n"
            )
        dossier = (
            f"episode_id: {eid}\n"
            f"duracion_total_min: {ep.duracion_total_min}\n"
            f"n_eventos: {ep.n_eventos}\n"
            f"distribucion_niveles:\n"
            f"{dist_lines}"
            f"cadena_eventos:\n"
            f"{cadena_lines}"
            f"prompts_estudiante:\n"
            f"{prompt_lines}"
            f"categoria_propuesta_por_etiquetador: ___\n"
            f"nota_libre: ___\n"
        )
        (pb_dir / f"{eid}.yaml").write_text(dossier, encoding="utf-8")
        written += 1
    return written


def write_ground_truth_b(episodes: list[SyntheticEpisode], out_dir: Path) -> Path:
    path = out_dir / "ground-truth-protocol-b.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["# NO ENTREGAR A ETIQUETADORES - ground truth del sistema"])
        w.writerow(["episode_id", "categoria_apropiacion"])
        for i, ep in enumerate(sorted(episodes, key=lambda e: e.episode_id), start=1):
            w.writerow([f"ep_{i:03d}", ep.categoria_ground_truth])
    return path


def write_metadata(
    out_dir: Path,
    *,
    mode: str,
    seed: int,
    args: argparse.Namespace,
    event_reports: list[StratumReport],
    episode_reports: list[StratumReport],
    dry_run: bool,
) -> Path:
    path = out_dir / "metadata.json"
    now = _iso_z(datetime.now(timezone.utc))
    meta = {
        "script": "scripts/select-intercoder-corpus.py",
        "script_version": SCRIPT_VERSION,
        "generated_at": now,
        "mode": mode,
        "seed": seed,
        "dry_run": dry_run,
        "data_source": "synthetic" if dry_run else "pilot_db",
        "labeler_version": LABELER_VERSION,
        # En una corrida real, este hash viene de
        # classifier_service.services.pipeline.compute_classifier_config_hash
        # sobre el profile vigente. En dry-run es placeholder declarado.
        "classifier_config_hash": (
            "PLACEHOLDER_DRY_RUN_no_real_classifier_config_hash"
            if dry_run
            else "TO_BE_FILLED_FROM_REAL_CLASSIFIER"
        ),
        "manual_version_expected": "1.1.0 (post-pre-calibracion); 1.0.0 vigente al generar",
        "params": {
            "n_events": args.n_events,
            "n_episodes": args.n_episodes,
            "truncate_content_chars": args.truncate_content_chars,
            "include_consent_records": bool(args.include_consent_records),
        },
        "open_methodological_decisions": {
            "stratify_by_raw_event_type_complement": STRATIFY_BY_RAW_EVENT_TYPE_COMPLEMENT,
            "consent_protocol_b_required": CONSENT_PROTOCOL_B_REQUIRED,
            "underpopulated_stratum_policy": UNDERPOPULATED_STRATUM_POLICY,
            "within_stratum_selection": WITHIN_STRATUM_SELECTION,
        },
        "protocol_a_strata": [
            {"level": r.name, "requested": r.requested, "available": r.available, "selected": r.selected}
            for r in event_reports
        ],
        "protocol_b_strata": [
            {"category": r.name, "requested": r.requested, "available": r.available, "selected": r.selected}
            for r in episode_reports
        ],
    }
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# PATH REAL (stub con guard).
# ---------------------------------------------------------------------------
def _assert_real_db_preconditions() -> None:
    required = ["ACADEMIC_DB_URL", "CTR_STORE_URL", "CLASSIFIER_DB_URL"]
    missing = [v for v in required if not os.environ.get(v)]
    msg = [
        "[FAIL] El path contra DB real NO esta implementado todavia (esqueleto).",
        "       Requisitos antes de cablear la DB:",
        f"       - Variables de entorno: {', '.join(required)} (faltan: {missing or 'ninguna'}).",
        "       - Accion A1 CERRADA: las 106 classifications historicas re-clasificadas con",
        "         LABELER_VERSION 1.2.0 (sino el corpus mezcla versiones del labeler y el",
        "         kappa intercoder pierde validez). Ver plan-accion.md A1 + scripts/reclassify-legacy-106.py.",
        "",
        "       Mientras tanto, usa --dry-run para ejercitar el formato de salida real",
        "       sobre datos sinteticos (fichas YAML + ground-truth CSV + metadata.json).",
    ]
    raise SystemExit("\n".join(msg))


def load_events_from_db(args: argparse.Namespace) -> list[SyntheticEvent]:
    """STUB: cargaria eventos de ctr_store.events (con su contexto temporal).

    La implementacion real:
      1. SELECT eventos de episodios cerrados del piloto (ctr_store).
      2. Reconstruye EpisodeContext por episodio (episodio_abierto + ultimo tutor_respondio).
      3. Etiqueta con label_event (mismo que dry-run) para estratificar.
    El resto del pipeline (stratify_events + writers) ya esta listo y se reusa tal cual.
    """
    _assert_real_db_preconditions()
    raise NotImplementedError  # inalcanzable: _assert_real_db_preconditions aborta antes.


def load_episodes_from_db(args: argparse.Namespace) -> list[SyntheticEpisode]:
    """STUB: cargaria episodios cerrados + classifications de classifier_db.

    La categoria ground-truth vendria de classifier_db.classifications.appropriation;
    los prompts del estudiante de ctr_store (eventos prompt_enviado del episodio).
    El resto del pipeline (stratify_episodes + writers) se reusa tal cual.
    """
    _assert_real_db_preconditions()
    raise NotImplementedError  # inalcanzable.


# ---------------------------------------------------------------------------
# Orquestacion por modo.
# ---------------------------------------------------------------------------
def _per_level_for_mode(mode: str, n_events: int) -> dict[str, int]:
    if mode == "internal-calibration":
        return {lv: 5 for lv in N_LEVELS}  # 20 eventos (5 por nivel)
    # protocol-a / full: reparto equitativo de n_events entre 4 niveles.
    base = n_events // len(N_LEVELS)
    rem = n_events % len(N_LEVELS)
    per = {lv: base for lv in N_LEVELS}
    for i in range(rem):  # distribuir el resto de forma determinista
        per[N_LEVELS[i]] += 1
    return per


def _per_category_for_mode(mode: str, n_episodes: int) -> dict[str, int]:
    if mode == "internal-calibration":
        # 5 episodios: ~2 reflexiva / 2 superficial / 1 delegacion.
        return {
            "apropiacion_reflexiva": 2,
            "apropiacion_superficial": 2,
            "delegacion_pasiva": 1,
        }
    base = n_episodes // len(APPROPRIATION_CATEGORIES)
    rem = n_episodes % len(APPROPRIATION_CATEGORIES)
    per = {c: base for c in APPROPRIATION_CATEGORIES}
    for i in range(rem):
        per[APPROPRIATION_CATEGORIES[i]] += 1
    return per


def run(args: argparse.Namespace) -> int:
    mode = args.mode
    seed = args.seed
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    wants_a = mode in ("protocol-a", "full", "internal-calibration")
    wants_b = mode in ("protocol-b", "full", "internal-calibration")

    per_level = _per_level_for_mode(mode, args.n_events) if wants_a else {}
    per_category = _per_category_for_mode(mode, args.n_episodes) if wants_b else {}

    print("=" * 64)
    print(f"[INFO] select-intercoder-corpus v{SCRIPT_VERSION}")
    print(f"[INFO] mode={mode} seed={seed} dry_run={bool(args.dry_run)}")
    print(f"[INFO] labeler_version={LABELER_VERSION}")
    print(f"[INFO] output_dir={out_dir}")
    print("=" * 64)

    expose_prompts = bool(args.include_consent_records)
    if wants_b and CONSENT_PROTOCOL_B_REQUIRED and not expose_prompts:
        print(
            "[WARN] Protocolo B: los prompts COMPLETOS del estudiante quedan GATEADOS.\n"
            "       El contenido textual requiere consentimiento informado especifico\n"
            "       (decision metodologica 2). Pasa --include-consent-records solo si los\n"
            "       estudiantes del corpus B firmaron consentimiento para texto completo.",
        )
    if wants_b and expose_prompts:
        print(
            "[WARN] --include-consent-records ACTIVO: se exponen prompts COMPLETOS en Protocolo B.\n"
            "       Verifica que TODOS los estudiantes del corpus dieron consentimiento explicito."
        )

    if not args.dry_run:
        # PATH REAL -> stub con guard (aborta con instrucciones claras).
        if wants_a:
            load_events_from_db(args)
        if wants_b:
            load_episodes_from_db(args)
        return 0  # inalcanzable.

    # ---------------- DRY-RUN ----------------
    event_reports: list[StratumReport] = []
    episode_reports: list[StratumReport] = []
    n_fiches = 0
    n_dossiers = 0

    if wants_a:
        universe = synthesize_events(rng, per_level)
        selected, event_reports = stratify_events(universe, per_level, rng)
        n_fiches = write_protocol_a_fiches(selected, out_dir, args.truncate_content_chars)
        gt_a = write_ground_truth_a(selected, out_dir)
        print(f"[OK] Protocolo A: {n_fiches} fichas YAML en {out_dir / 'protocol-a'}")
        print(f"[OK] Ground-truth A: {gt_a}")
        for r in event_reports:
            print(f"     estrato {r.name}: requerido={r.requested} disp={r.available} sel={r.selected}")

    if wants_b:
        universe_ep = synthesize_episodes(rng, per_category)
        selected_ep, episode_reports = stratify_episodes(universe_ep, per_category, rng)
        n_dossiers = write_protocol_b_dossiers(selected_ep, out_dir, expose_prompts)
        gt_b = write_ground_truth_b(selected_ep, out_dir)
        print(f"[OK] Protocolo B: {n_dossiers} dossiers YAML en {out_dir / 'protocol-b'}")
        print(f"[OK] Ground-truth B: {gt_b}")
        for r in episode_reports:
            print(f"     categoria {r.name}: requerido={r.requested} disp={r.available} sel={r.selected}")

    meta_path = write_metadata(
        out_dir,
        mode=mode,
        seed=seed,
        args=args,
        event_reports=event_reports,
        episode_reports=episode_reports,
        dry_run=True,
    )
    print(f"[OK] Metadata: {meta_path}")
    print("=" * 64)
    print(f"[OK] DRY-RUN completado. fichas_A={n_fiches} dossiers_B={n_dossiers}")
    print("=" * 64)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Selector de corpus para validacion intercoder kappa>=0,70 (Protocolos A+B). "
            "Spec: paquete-coordinacion-intercoder-2026-05-20.md seccion 2."
        )
    )
    p.add_argument(
        "--mode",
        choices=["internal-calibration", "protocol-a", "protocol-b", "full"],
        required=True,
    )
    p.add_argument("--n-events", type=int, default=200, help="Total eventos Protocolo A (def 200).")
    p.add_argument("--n-episodes", type=int, default=50, help="Total episodios Protocolo B (def 50).")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Seed reproducible (def {DEFAULT_SEED}).")
    p.add_argument(
        "--output-dir",
        default="docs/research/intercoder-corpus/round-01/",
        help="Directorio de salida.",
    )
    p.add_argument(
        "--truncate-content-chars",
        type=int,
        default=40,
        help="Truncado de payload.content en Protocolo A (privacidad, def 40).",
    )
    p.add_argument(
        "--include-consent-records",
        action="store_true",
        help="Expone prompts COMPLETOS en Protocolo B (requiere consentimiento informado).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Usa datos sinteticos (no DB). Ejercita el formato de salida real.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
