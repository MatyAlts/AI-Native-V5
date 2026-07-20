"""Dashboard pedagógico agregado para el panel admin (sección "Pedagogía").

Construye, sobre TODOS los episodios de un scope (una materia entera o una
comisión puntual), cinco bloques de análisis a partir de los datos que YA
existen — sin requerir codificación manual de docentes:

  1. Distribución de perfiles de apropiación + subgrupos.
  2. Trayectoria longitudinal por estudiante (reusa la semántica
     `StudentTrajectory` de platform_ops: "mejorando" si el último tercio
     supera al primero). Responde la pregunta central de la tesis.
  3. Matriz estudiante × perfil.
  4. Triangulación perfil vs completitud de ejercicios (proxy honesto: el
     piloto no tiene notas finales cargadas, se declara explícito en la UI).
  5. Señales que respaldan cada perfil: coherencias CT/CCD/CII promedio.

Patrón 3-bases (cross-DB en Python, no SQL join): episodes (ctr_store) para
resolver episode_id → student_pseudonym, classifications (classifier_db) para
las etiquetas + coherencias, entregas (academic_main) para completitud. RLS por
tenant en cada sesión (`set_tenant_rls`).

Acceso: solo roles de administración (superadmin / docente_admin). A diferencia
de los endpoints de cohorte (aislados por membresía de comisión), el panel admin
ve todas las comisiones del tenant.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from analytics_service.db import get_academic_engine, get_classifier_engine, get_ctr_engine
from analytics_service.routes.analytics import get_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics/pedagogia", tags=["pedagogia"])

# Ordinal de apropiación (mayor = mejor). Re-exportado desde platform_ops para
# mantener UNA sola operacionalización en toda la tesis. SOLO las 3 etiquetas del
# continuo superficial↔reflexiva tienen ordinal.
_ORDINAL: dict[str, int] = {
    "delegacion_pasiva": 0,
    "apropiacion_superficial": 1,
    "apropiacion_reflexiva": 2,
}
# Ejes ORTOGONALES al continuo ordinal: son etiquetas oficiales válidas pero NO
# entran en la curva/slope longitudinal ni cuentan como "indeterminado". `autonomo`
# = trabajo sin tutor (color gris en la UI).
_APROPIACION_ORTOGONAL: frozenset[str] = frozenset({"autonomo"})
# Orden canónico de presentación de los perfiles.
_APROPIACION_ORDER = ["apropiacion_reflexiva", "apropiacion_superficial", "delegacion_pasiva"]

_ADMIN_ROLES = frozenset({"superadmin", "docente_admin"})


async def require_admin(x_user_roles: str | None = Header(default=None)) -> None:
    """Exige rol de administración. El panel admin ve TODAS las comisiones del
    tenant, así que no se aísla por membresía de comisión (a diferencia de los
    endpoints de cohorte). El gateway ya valida el JWT; acá solo chequeamos rol."""
    roles = {r.strip() for r in (x_user_roles or "").split(",") if r.strip()}
    if not (roles & _ADMIN_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requiere rol de administración (superadmin o docente_admin).",
        )


# ── Schemas de salida ────────────────────────────────────────────────────


class ComisionScope(BaseModel):
    comision_id: str
    nombre: str
    n_episodios: int
    n_alumnos: int


class MateriaScope(BaseModel):
    materia_id: str
    nombre: str
    codigo: str
    n_episodios: int
    comisiones: list[ComisionScope]


class ScopesOut(BaseModel):
    materias: list[MateriaScope]


class SubgrupoCount(BaseModel):
    key: str
    label: str
    n: int


class DistribucionBlock(BaseModel):
    n_episodios_clasificados: int
    n_indeterminados: int
    por_apropiacion: dict[str, int]
    por_subgrupo: list[SubgrupoCount]


class CurvaPunto(BaseModel):
    posicion: int  # n-ésimo episodio del alumno (1-indexed)
    media_ordinal: float | None  # apropiación promedio (0=deleg, 1=superf, 2=reflex)
    n_alumnos: int


class CurvaApropiacionBlock(BaseModel):
    """Evolución agregada de la cohorte: apropiación media según el orden de
    episodio. Consistente con (no prueba de) un efecto del tutor a lo largo del
    uso. Sin grupo control, la inferencia causal no es posible."""

    puntos: list[CurvaPunto]
    min_alumnos: int  # umbral de corte (posiciones con menos alumnos se omiten)


class CurvaAdversaPunto(BaseModel):
    posicion: int
    media_adversos: float  # intentos adversos promedio por alumno en ese episodio
    n_alumnos: int


class CurvaAdversaBlock(BaseModel):
    """Intentos adversos (tratar de sacarle la respuesta al tutor) promedio por
    alumno según el orden de episodio. Señal de comportamiento INDEPENDIENTE del
    classifier (no hay circularidad). Una curva descendente es consistente con el
    tutor moldeando la conducta hacia un uso legítimo."""

    n_eventos_total: int
    puntos: list[CurvaAdversaPunto]
    min_alumnos: int


class TrayectoriaAlumno(BaseModel):
    student: str
    n_episodios: int
    primera: str | None
    ultima: str | None
    max_alcanzada: str | None
    label: str  # mejorando | estable | empeorando | insuficiente
    serie_ordinal: list[int]


class TrayectoriaBlock(BaseModel):
    n_alumnos: int
    n_con_datos: int
    mejorando: int
    estable: int
    empeorando: int
    insuficiente: int
    net_progression_ratio: float
    alumnos: list[TrayectoriaAlumno]


class MatrizFila(BaseModel):
    student: str
    counts: dict[str, int]
    total: int
    dominante: str | None


class MatrizBlock(BaseModel):
    perfiles: list[str]
    filas: list[MatrizFila]


class TriangulacionPerfil(BaseModel):
    apropiacion: str
    n_alumnos: int
    completitud_promedio: float | None


class TriangulacionBlock(BaseModel):
    sin_notas_finales: bool
    n_alumnos_con_entrega: int
    por_perfil: list[TriangulacionPerfil]


class SenalesPerfil(BaseModel):
    apropiacion: str
    n: int
    ct_promedio: float | None
    ccd_promedio: float | None
    cii_promedio: float | None


class SenalesBlock(BaseModel):
    por_perfil: list[SenalesPerfil]


# Codificaciones mínimas para que un codificador entre a la validación.
# Descarta cuentas de prueba / ruido (ej. 1-2 filas sueltas) que dan κ degenerado.
_MIN_RATINGS_VALIDOS = 5


class KappaPar(BaseModel):
    rater_a: str
    rater_b: str
    n_episodios: int
    kappa: float | None
    interpretacion: str | None
    # Gwet's AC1: robusto a la paradoja de prevalencia (cuando una categoría
    # domina y defla el κ pese a alto acuerdo crudo).
    ac1: float | None
    ac1_interpretacion: str | None
    acuerdo_observado: float | None  # proporción de acuerdo crudo [0,1]


class KappaBlock(BaseModel):
    """Acuerdo inter-codificador (Cohen's κ). Validación empírica del classifier:
    κ máquina–humano mide qué tan cerca está la máquina de los humanos; κ
    humano–humano es el techo (los humanos no concuerdan perfecto entre sí)."""

    disponible: bool
    n_codificadores: int
    n_episodios_codificados: int
    n_gold: int  # episodios de consenso (todos los codificadores válidos coinciden)
    maquina_vs_consenso: KappaPar | None  # κ máquina vs consenso docente (gold)
    pares_humano_humano: list[KappaPar]  # techo: acuerdo entre codificadores


class PedagogiaOut(BaseModel):
    scope_label: str
    comisiones_incluidas: list[str]
    n_episodios_total: int
    distribucion: DistribucionBlock
    curva_apropiacion: CurvaApropiacionBlock
    curva_adversa: CurvaAdversaBlock
    validacion_kappa: KappaBlock
    trayectoria: TrayectoriaBlock
    matriz: MatrizBlock
    triangulacion: TriangulacionBlock
    senales: SenalesBlock


# ── /scopes : árbol materia → comisión para el selector ──────────────────


@router.get("/scopes", response_model=ScopesOut)
async def get_scopes(
    tenant_id: UUID = Depends(get_tenant_id),
    _admin: None = Depends(require_admin),
) -> ScopesOut:
    """Árbol materia → comisiones con conteo de episodios/alumnos por comisión,
    para poblar el selector. Solo lista comisiones que tienen episodios (las
    vacías/de prueba se omiten del default; siguen accesibles por id)."""
    from platform_ops import set_tenant_rls
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    # 1. Conteos por comisión desde ctr_store (episodios + alumnos distintos).
    ctr_maker = async_sessionmaker(get_ctr_engine(), expire_on_commit=False)
    async with ctr_maker() as ctr_s:
        await set_tenant_rls(ctr_s, tenant_id)
        ep_rows = (
            await ctr_s.execute(
                text(
                    "SELECT comision_id, count(*) AS eps, "
                    "count(DISTINCT student_pseudonym) AS alumnos "
                    "FROM episodes WHERE tenant_id = :t GROUP BY comision_id"
                ),
                {"t": str(tenant_id)},
            )
        ).all()
    counts: dict[str, tuple[int, int]] = {
        str(r.comision_id): (int(r.eps), int(r.alumnos)) for r in ep_rows
    }

    # 2. Materias + comisiones desde academic_main.
    acad_maker = async_sessionmaker(get_academic_engine(), expire_on_commit=False)
    async with acad_maker() as acad_s:
        await set_tenant_rls(acad_s, tenant_id)
        rows = (
            await acad_s.execute(
                text(
                    "SELECT m.id AS materia_id, m.nombre AS materia, m.codigo AS codigo, "
                    "c.id AS comision_id, c.nombre AS comision "
                    "FROM comisiones c JOIN materias m ON m.id = c.materia_id "
                    "WHERE c.tenant_id = :t ORDER BY m.nombre, c.nombre"
                ),
                {"t": str(tenant_id)},
            )
        ).all()

    by_materia: dict[str, MateriaScope] = {}
    for r in rows:
        mid = str(r.materia_id)
        if mid not in by_materia:
            by_materia[mid] = MateriaScope(
                materia_id=mid, nombre=r.materia, codigo=r.codigo, n_episodios=0, comisiones=[]
            )
        eps, alumnos = counts.get(str(r.comision_id), (0, 0))
        if eps == 0:
            continue  # comisión sin episodios: fuera del selector
        by_materia[mid].comisiones.append(
            ComisionScope(
                comision_id=str(r.comision_id),
                nombre=r.comision,
                n_episodios=eps,
                n_alumnos=alumnos,
            )
        )
        by_materia[mid].n_episodios += eps

    # Solo materias con al menos una comisión con datos, ordenadas por volumen.
    materias = [m for m in by_materia.values() if m.comisiones]
    materias.sort(key=lambda m: m.n_episodios, reverse=True)
    return ScopesOut(materias=materias)


# ── helpers de agregación ─────────────────────────────────────────────────


def _as_json(value: Any) -> Any:
    """JSONB vía text() crudo puede llegar como str (sin codec) o ya parseado.
    Normaliza a objeto Python; None/'' → None."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return value


def _completitud(ejercicio_estados_raw: Any) -> float | None:
    """Fracción [0,1] de ejercicios completados en una entrega. None si vacía."""
    ejercicio_estados = _as_json(ejercicio_estados_raw)
    if not ejercicio_estados or not isinstance(ejercicio_estados, list):
        return None
    total = len(ejercicio_estados)
    if total == 0:
        return None
    hechos = sum(1 for e in ejercicio_estados if e.get("completado"))
    return hechos / total


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


# ── /  : bundle de los 5 bloques sobre un scope ──────────────────────────


@router.get("", response_model=PedagogiaOut)
async def get_pedagogia(
    comision_id: UUID | None = None,
    materia_id: UUID | None = None,
    tenant_id: UUID = Depends(get_tenant_id),
    _admin: None = Depends(require_admin),
) -> PedagogiaOut:
    """Bundle pedagógico sobre un scope. Pasar `comision_id` (una comisión) o
    `materia_id` (todas las comisiones de la materia = "General")."""
    from itertools import combinations

    from platform_ops import set_tenant_rls
    from platform_ops.kappa_analysis import KappaRating, compute_cohen_kappa
    from platform_ops.longitudinal import ClassificationPoint as _CP
    from platform_ops.longitudinal import StudentTrajectory, summarize_cohort
    from sqlalchemy import bindparam, text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    if not comision_id and not materia_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pasá comision_id o materia_id.",
        )

    acad_maker = async_sessionmaker(get_academic_engine(), expire_on_commit=False)
    ctr_maker = async_sessionmaker(get_ctr_engine(), expire_on_commit=False)
    cls_maker = async_sessionmaker(get_classifier_engine(), expire_on_commit=False)

    # 1. Resolver scope → lista de comision_ids + label.
    async with acad_maker() as acad_s:
        await set_tenant_rls(acad_s, tenant_id)
        if comision_id:
            row = (
                await acad_s.execute(
                    text(
                        "SELECT c.nombre AS comision, m.nombre AS materia "
                        "FROM comisiones c JOIN materias m ON m.id = c.materia_id "
                        "WHERE c.id = :c AND c.tenant_id = :t"
                    ),
                    {"c": str(comision_id), "t": str(tenant_id)},
                )
            ).first()
            comision_ids = [comision_id]
            scope_label = f"{row.materia} · {row.comision}" if row else str(comision_id)
        else:
            crows = (
                await acad_s.execute(
                    text(
                        "SELECT c.id AS cid, m.nombre AS materia FROM comisiones c "
                        "JOIN materias m ON m.id = c.materia_id "
                        "WHERE c.materia_id = :m AND c.tenant_id = :t"
                    ),
                    {"m": str(materia_id), "t": str(tenant_id)},
                )
            ).all()
            comision_ids = [r.cid for r in crows]
            materia_nombre = crows[0].materia if crows else str(materia_id)
            scope_label = f"{materia_nombre} · General"

        if not comision_ids:
            raise HTTPException(status_code=404, detail="Scope sin comisiones.")

        cids = [str(c) for c in comision_ids]

        # 4. Entregas del scope (academic_main) → completitud por alumno.
        ent_stmt = text(
            "SELECT student_pseudonym, ejercicio_estados FROM entregas "
            "WHERE tenant_id = :t AND comision_id IN :cids"
        ).bindparams(bindparam("cids", expanding=True))
        ent_rows = (await acad_s.execute(ent_stmt, {"t": str(tenant_id), "cids": cids})).all()

    # 2. Episodios del scope (ctr_store) → episode_id → student + orden temporal.
    async with ctr_maker() as ctr_s:
        await set_tenant_rls(ctr_s, tenant_id)
        ep_stmt = text(
            "SELECT id, student_pseudonym, opened_at FROM episodes "
            "WHERE tenant_id = :t AND comision_id IN :cids"
        ).bindparams(bindparam("cids", expanding=True))
        ep_rows = (await ctr_s.execute(ep_stmt, {"t": str(tenant_id), "cids": cids})).all()

        ep_to_student: dict[str, str] = {str(r.id): str(r.student_pseudonym) for r in ep_rows}
        n_episodios_total = len(ep_to_student)

        # 2b. Intentos adversos (event_type='intento_adverso_detectado') por episodio.
        # Señal independiente del classifier. Filtrada por los episodios del scope.
        adversos_por_episodio: dict[str, int] = defaultdict(int)
        n_adversos_total = 0
        ep_ids = list(ep_to_student.keys())
        if ep_ids:
            adv_stmt = text(
                "SELECT episode_id, count(*) AS n FROM events "
                "WHERE tenant_id = :t AND event_type = 'intento_adverso_detectado' "
                "AND episode_id IN :eids GROUP BY episode_id"
            ).bindparams(bindparam("eids", expanding=True))
            adv_rows = (await ctr_s.execute(adv_stmt, {"t": str(tenant_id), "eids": ep_ids})).all()
            for r in adv_rows:
                adversos_por_episodio[str(r.episode_id)] = int(r.n)
                n_adversos_total += int(r.n)

    # Orden temporal de los episodios de cada alumno (por opened_at).
    episodios_por_alumno: dict[str, list[str]] = defaultdict(list)
    for r in sorted(ep_rows, key=lambda x: (str(x.student_pseudonym), x.opened_at)):
        episodios_por_alumno[str(r.student_pseudonym)].append(str(r.id))

    # 3. Clasificaciones current + ratings inter-rater del scope (classifier_db).
    async with cls_maker() as cls_s:
        await set_tenant_rls(cls_s, tenant_id)
        cls_stmt = text(
            "SELECT episode_id, appropriation, ct_summary, ccd_mean, "
            "cii_stability, classified_at, features FROM classifications "
            "WHERE tenant_id = :t AND is_current = true "
            "AND comision_id IN :cids "
            "ORDER BY classified_at ASC"
        ).bindparams(bindparam("cids", expanding=True))
        cls_rows = (await cls_s.execute(cls_stmt, {"t": str(tenant_id), "cids": cids})).all()

        # (Las etiquetas humanas para la validación κ se leen GLOBAL —todo el
        # corpus del clasificador, no por scope— en el bloque "Validación: κ".)

    # ── Bloque 1: distribución (+ mapa episodio→ordinal para las curvas) ──
    por_apropiacion: dict[str, int] = defaultdict(int)
    por_subgrupo: dict[str, int] = defaultdict(int)
    subgrupo_labels: dict[str, str] = {}
    appr_por_episodio: dict[str, int] = {}
    n_indeterminados = 0
    for r in cls_rows:
        # Todas las etiquetas (incluido el eje ortogonal `autonomo`) entran a la
        # distribución por apropiación.
        por_apropiacion[r.appropriation] += 1
        if r.appropriation in _ORDINAL:
            # Solo las del continuo alimentan el mapa episodio→ordinal (curvas).
            appr_por_episodio[str(r.episode_id)] = _ORDINAL[r.appropriation]
        elif r.appropriation not in _APROPIACION_ORTOGONAL:
            # `autonomo` NO es indeterminado: es un eje propio sin ordinal. Solo
            # las etiquetas realmente sin perfil cuentan como indeterminadas.
            n_indeterminados += 1
        feats = _as_json(r.features) or {}
        sgd = feats.get("subgrupo") if isinstance(feats, dict) else None
        if isinstance(sgd, dict):
            sg = sgd.get("key")
            if sg and sg != "indeterminado":
                por_subgrupo[sg] += 1
                subgrupo_labels.setdefault(sg, sgd.get("label") or sg)
    distribucion = DistribucionBlock(
        n_episodios_clasificados=len(cls_rows),
        n_indeterminados=n_indeterminados,
        por_apropiacion=dict(por_apropiacion),
        por_subgrupo=sorted(
            (
                SubgrupoCount(key=k, label=subgrupo_labels.get(k, k), n=v)
                for k, v in por_subgrupo.items()
            ),
            key=lambda s: s.n,
            reverse=True,
        ),
    )

    # ── Curvas agregadas de cohorte (por orden de episodio) ─────────────
    MIN_ALUMNOS_CURVA = 3
    ord_acc: dict[int, list[int]] = defaultdict(list)  # posición → ordinales de apropiación
    adv_acc: dict[int, list[int]] = defaultdict(list)  # posición → conteos de adversos
    max_pos = 0
    for _student, eps in episodios_por_alumno.items():
        for idx, ep_id in enumerate(eps, start=1):
            max_pos = max(max_pos, idx)
            if ep_id in appr_por_episodio:
                ord_acc[idx].append(appr_por_episodio[ep_id])
            # cada episodio del alumno cuenta para adversos (0 si no hubo)
            adv_acc[idx].append(adversos_por_episodio.get(ep_id, 0))

    curva_apropiacion = CurvaApropiacionBlock(
        min_alumnos=MIN_ALUMNOS_CURVA,
        puntos=[
            CurvaPunto(
                posicion=p,
                media_ordinal=round(sum(ord_acc[p]) / len(ord_acc[p]), 3),
                n_alumnos=len(ord_acc[p]),
            )
            for p in range(1, max_pos + 1)
            if len(ord_acc.get(p, [])) >= MIN_ALUMNOS_CURVA
        ],
    )
    curva_adversa = CurvaAdversaBlock(
        n_eventos_total=n_adversos_total,
        min_alumnos=MIN_ALUMNOS_CURVA,
        puntos=[
            CurvaAdversaPunto(
                posicion=p,
                media_adversos=round(sum(adv_acc[p]) / len(adv_acc[p]), 3),
                n_alumnos=len(adv_acc[p]),
            )
            for p in range(1, max_pos + 1)
            if len(adv_acc.get(p, [])) >= MIN_ALUMNOS_CURVA
        ],
    )

    # ── Bloques 2/3/5: agrupar puntos por estudiante ────────────────────
    points_by_student: dict[str, list[_CP]] = defaultdict(list)
    coher_by_appr: dict[str, dict[str, list[float]]] = {
        a: {"ct": [], "ccd": [], "cii": []} for a in _ORDINAL
    }
    for r in cls_rows:
        student = ep_to_student.get(str(r.episode_id))
        if student is None:
            continue
        appr = r.appropriation
        if appr in _ORDINAL:
            points_by_student[student].append(
                _CP(
                    episode_id=UUID(str(r.episode_id)),
                    classified_at=r.classified_at,
                    appropriation=appr,
                    ct_summary=r.ct_summary,
                    ccd_mean=r.ccd_mean,
                    cii_stability=r.cii_stability,
                )
            )
            if r.ct_summary is not None:
                coher_by_appr[appr]["ct"].append(r.ct_summary)
            if r.ccd_mean is not None:
                coher_by_appr[appr]["ccd"].append(r.ccd_mean)
            if r.cii_stability is not None:
                coher_by_appr[appr]["cii"].append(r.cii_stability)

    trajectories: list[StudentTrajectory] = []
    for student, pts in points_by_student.items():
        pts.sort(key=lambda p: p.classified_at)
        trajectories.append(StudentTrajectory(student_pseudonym=student, points=pts))

    # Bloque 2: trayectoria (reusa summarize_cohort para los conteos).
    summary = summarize_cohort(comision_ids[0], trajectories)
    alumnos_out: list[TrayectoriaAlumno] = []
    for t in trajectories:
        alumnos_out.append(
            TrayectoriaAlumno(
                student=t.student_pseudonym[:8],
                n_episodios=t.n_episodes,
                primera=t.first_classification,
                ultima=t.last_classification,
                max_alcanzada=t.max_appropriation_reached(),
                label=t.progression_label(),
                serie_ordinal=[_ORDINAL[p.appropriation] for p in t.points],
            )
        )
    # Orden: mejorando primero, después por mayor nivel final, después N episodios.
    _label_rank = {"mejorando": 0, "estable": 1, "empeorando": 2, "insuficiente": 3}
    alumnos_out.sort(
        key=lambda a: (
            _label_rank.get(a.label, 9),
            -(_ORDINAL.get(a.ultima or "", -1)),
            -a.n_episodios,
        )
    )
    trayectoria = TrayectoriaBlock(
        n_alumnos=summary.n_students,
        n_con_datos=summary.n_students_with_enough_data,
        mejorando=summary.mejorando,
        estable=summary.estable,
        empeorando=summary.empeorando,
        insuficiente=summary.insuficiente,
        net_progression_ratio=round(summary.net_progression_ratio, 3),
        alumnos=alumnos_out,
    )

    # Bloque 3: matriz estudiante × perfil.
    filas: list[MatrizFila] = []
    for t in trajectories:
        counts: dict[str, int] = defaultdict(int)
        for p in t.points:
            counts[p.appropriation] += 1
        dominante = max(counts, key=lambda k: counts[k]) if counts else None
        filas.append(
            MatrizFila(
                student=t.student_pseudonym[:8],
                counts=dict(counts),
                total=t.n_episodes,
                dominante=dominante,
            )
        )
    filas.sort(key=lambda f: (-(_ORDINAL.get(f.dominante or "", -1)), -f.total))
    matriz = MatrizBlock(perfiles=_APROPIACION_ORDER, filas=filas)

    # ── Bloque 4: triangulación perfil vs completitud ───────────────────
    # completitud por alumno = promedio de sus entregas.
    comp_by_student: dict[str, list[float]] = defaultdict(list)
    for r in ent_rows:
        c = _completitud(r.ejercicio_estados)
        if c is not None:
            comp_by_student[str(r.student_pseudonym)].append(c)
    # perfil dominante por alumno (de la matriz).
    dominante_by_student = {f.student: f.dominante for f in filas}
    # mapear student corto → completitud (los pseudónimos en filas son [:8]).
    comp_short: dict[str, float] = {}
    for student, comps in comp_by_student.items():
        comp_short[student[:8]] = sum(comps) / len(comps)
    tri_acc: dict[str, list[float]] = defaultdict(list)
    n_con_entrega = 0
    for student_short, dominante in dominante_by_student.items():
        if dominante and student_short in comp_short:
            tri_acc[dominante].append(comp_short[student_short])
            n_con_entrega += 1
    triangulacion = TriangulacionBlock(
        sin_notas_finales=True,  # piloto sin notas cargadas — proxy=completitud
        n_alumnos_con_entrega=n_con_entrega,
        por_perfil=[
            TriangulacionPerfil(
                apropiacion=a,
                n_alumnos=len(tri_acc.get(a, [])),
                completitud_promedio=(round(_mean(tri_acc[a]), 3) if tri_acc.get(a) else None),
            )
            for a in _APROPIACION_ORDER
        ],
    )

    # ── Bloque 5: señales (coherencias por perfil) ──────────────────────
    senales = SenalesBlock(
        por_perfil=[
            SenalesPerfil(
                apropiacion=a,
                n=len(coher_by_appr[a]["ct"]),
                ct_promedio=(
                    round(m, 3) if (m := _mean(coher_by_appr[a]["ct"])) is not None else None
                ),
                ccd_promedio=(
                    round(m, 3) if (m := _mean(coher_by_appr[a]["ccd"])) is not None else None
                ),
                cii_promedio=(
                    round(m, 3) if (m := _mean(coher_by_appr[a]["cii"])) is not None else None
                ),
            )
            for a in _APROPIACION_ORDER
        ]
    )

    # ── Validación: Cohen's κ — máquina vs CONSENSO docente + techo humano ──
    # GLOBAL (todo el corpus del clasificador, NO el scope de comisión): se valida
    # el MODELO, no una comisión. Gold/consenso = episodios donde los codificadores
    # válidos coinciden. Se reporta máquina-vs-consenso (número robusto) y el techo
    # humano-humano. Codificadores con < _MIN_RATINGS_VALIDOS se descartan (ruido).
    async with cls_maker() as kappa_s:
        await set_tenant_rls(kappa_s, tenant_id)
        rat_g = (
            await kappa_s.execute(
                text(
                    "SELECT episode_id, rater_id, label FROM interrater_ratings "
                    "WHERE tenant_id = :t AND protocol = 'ejes'"
                ),
                {"t": str(tenant_id)},
            )
        ).all()
        coded_eps = {str(ep) for ep, _r, _l in rat_g}
        machine_g: dict[str, str] = {}
        if coded_eps:
            mg_rows = (
                await kappa_s.execute(
                    text(
                        "SELECT episode_id, appropriation FROM classifications "
                        "WHERE tenant_id = :t AND is_current = true AND episode_id IN :eps"
                    ).bindparams(bindparam("eps", expanding=True)),
                    {"t": str(tenant_id), "eps": list(coded_eps)},
                )
            ).all()
            machine_g = {str(e): a for e, a in mg_rows}

    by_rater: dict[str, dict[str, str]] = defaultdict(dict)
    for ep, rater, label in rat_g:
        by_rater[str(rater)][str(ep)] = label

    def _kappa_par(
        a_label: str, b_label: str, a_map: dict[str, str], b_map: dict[str, str]
    ) -> KappaPar:
        common = sorted(set(a_map) & set(b_map))
        base = {"rater_a": a_label, "rater_b": b_label, "n_episodios": len(common)}
        if not common:
            return KappaPar(
                **base,
                kappa=None,
                interpretacion=None,
                ac1=None,
                ac1_interpretacion=None,
                acuerdo_observado=None,
            )
        ratings = [KappaRating(episode_id=e, rater_a=a_map[e], rater_b=b_map[e]) for e in common]
        cats = sorted({r.rater_a for r in ratings} | {r.rater_b for r in ratings})
        try:
            res = compute_cohen_kappa(ratings, categories=cats)
            return KappaPar(
                **base,
                kappa=round(res.kappa, 3),
                interpretacion=res.interpretation,
                ac1=round(res.ac1, 3),
                ac1_interpretacion=res.ac1_interpretation,
                acuerdo_observado=round(res.observed_agreement, 3),
            )
        except Exception:
            return KappaPar(
                **base,
                kappa=None,
                interpretacion=None,
                ac1=None,
                ac1_interpretacion=None,
                acuerdo_observado=None,
            )

    # Codificadores con masa suficiente (descarta cuentas de prueba / ruido).
    raters_validos = sorted(r for r in by_rater if len(by_rater[r]) >= _MIN_RATINGS_VALIDOS)

    # Consenso ("gold"): episodio codificado por >=2 codificadores válidos que
    # coinciden todos. Es el ground-truth robusto contra el que se mide la máquina.
    consenso: dict[str, str] = {}
    for ep in coded_eps:
        votos = [by_rater[r][ep] for r in raters_validos if ep in by_rater[r]]
        if len(votos) >= 2 and len(set(votos)) == 1:
            consenso[ep] = votos[0]

    maquina_vs_consenso = (
        _kappa_par("máquina", "consenso docente", machine_g, consenso) if consenso else None
    )
    hh = [
        _kappa_par(ra[:8], rb[:8], by_rater[ra], by_rater[rb])
        for ra, rb in combinations(raters_validos, 2)
    ]
    validacion_kappa = KappaBlock(
        disponible=len(rat_g) > 0,
        n_codificadores=len(raters_validos),
        n_episodios_codificados=len(coded_eps),
        n_gold=len(consenso),
        maquina_vs_consenso=maquina_vs_consenso,
        pares_humano_humano=hh,
    )

    logger.info(
        "pedagogia_computed tenant=%s scope=%s comisiones=%d episodios=%d clasificados=%d alumnos=%d",
        tenant_id,
        scope_label,
        len(comision_ids),
        n_episodios_total,
        len(cls_rows),
        summary.n_students,
    )

    return PedagogiaOut(
        scope_label=scope_label,
        comisiones_incluidas=[str(c) for c in comision_ids],
        n_episodios_total=n_episodios_total,
        distribucion=distribucion,
        curva_apropiacion=curva_apropiacion,
        curva_adversa=curva_adversa,
        validacion_kappa=validacion_kappa,
        trayectoria=trayectoria,
        matriz=matriz,
        triangulacion=triangulacion,
        senales=senales,
    )
