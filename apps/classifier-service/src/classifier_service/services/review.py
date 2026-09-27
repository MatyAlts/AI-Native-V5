"""Cola de revisión humana y registro de anulación (B3+B5, design.md D7).

La marca `features['needs_review']` (escrita en `_marcar_para_revision`,
`classify_ep.py`) no la leía nadie — este módulo es el primer lector. Dos
operaciones:

  - `list_review_queue`: episodios `is_current=true` con `needs_review=true`
    y sin revisión posterior (anti-join contra `classification_reviews`).
  - `submit_review`: registra el veredicto humano. Gate 1.4 (decisión del
    usuario, 26/09/2026): REEMPLAZA la etiqueta oficial creando una
    `Classification` nueva y marcando la anterior `is_current=false` — nunca
    un `UPDATE` del valor. Cada llamada apila una fila nueva en
    `classification_reviews`; nunca pisa una revisión anterior.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from classifier_service.models import Classification, ClassificationReview, utc_now_f


class ReviewTargetNotFoundError(Exception):
    """No hay `Classification` `is_current=true` para el episodio a revisar."""


class ReviewConflictError(Exception):
    """Otra revisión ganó la carrera sobre la misma `Classification` vigente.

    `retryable` distingue QUIÉN ganó (hallazgo de QA, 2026-09-27, ronda 5):
    el dato en base queda correcto en cualquier caso, pero el mensaje que
    llega al docente no puede sonar igual si lo pisó un colega o si lo pisó
    el sistema — son dos situaciones distintas y dos acciones distintas.

      - `retryable=True`  → ganó una reclasificación AUTOMÁTICA (la fila
        vigente no tiene `features['revision_humana']`). La decisión de
        ESTE docente sigue siendo válida contra el estado nuevo — el
        sistema no "vio" nada que el docente no haya visto. Se puede
        reintentar sin pedirle que relea nada.
      - `retryable=False` → ganó OTRA revisión humana (la fila vigente SÍ
        tiene `features['revision_humana']`). Hay que leer esa decisión
        antes de insistir — puede que el otro docente haya visto algo
        distinto, y reintentar a ciegas pisaría esa lectura.
    """

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class ReviewQueueItem:
    episode_id: UUID
    comision_id: UUID
    classification_id: int
    appropriation: str
    needs_review_reason: str | None
    estado_juez: str | None


async def list_review_queue(
    session: AsyncSession,
    comision_id: UUID | None = None,
) -> list[ReviewQueueItem]:
    """Episodios retenidos vigentes: `is_current=true`, `needs_review=true`
    en `features`, y sin fila en `classification_reviews` para ese episodio
    (anti-join — una revisión ya registrada lo saca de la cola).

    El filtro por RLS (tenant) lo aplica la sesión, no esta función — mismo
    patrón que `aggregate_by_comision`.
    """
    ya_revisado = (
        select(ClassificationReview.id)
        .where(ClassificationReview.episode_id == Classification.episode_id)
        .correlate(Classification)
        .exists()
    )
    stmt = select(Classification).where(
        Classification.is_current.is_(True),
        Classification.features["needs_review"].astext == "true",
        ~ya_revisado,
    )
    if comision_id is not None:
        stmt = stmt.where(Classification.comision_id == comision_id)
    stmt = stmt.order_by(Classification.classified_at)

    result = await session.execute(stmt)
    items: list[ReviewQueueItem] = []
    for c in result.scalars().all():
        feats = c.features or {}
        regimen = feats.get("regimen_llm") or {}
        items.append(
            ReviewQueueItem(
                episode_id=c.episode_id,
                comision_id=c.comision_id,
                classification_id=c.id,
                appropriation=c.appropriation,
                needs_review_reason=feats.get("needs_review_reason"),
                estado_juez=regimen.get("estado"),
            )
        )
    return items


@dataclass
class ReviewResult:
    review_id: int
    previous_classification_id: int
    new_classification_id: int


def _synthetic_review_config_hash(previous_hash: str, episode_id: UUID, reviewed_at: datetime) -> str:
    """Hash sintético para el `classifier_config_hash` de la Classification
    que resulta de una anulación humana.

    NO representa una configuración del árbol/juez: `compute_classifier_config_hash`
    no se toca ni se llama acá. Existe solo para no violar
    `UniqueConstraint(episode_id, classifier_config_hash)` — la fila humana
    comparte `episode_id` con la(s) fila(s) de máquina de ese episodio, así
    que necesita un hash propio, y distinto en CADA revisión (para que una
    segunda revisión del mismo episodio no colisione con la primera). Se
    deriva de datos ya disponibles (hash anterior + episodio + timestamp de
    la revisión) — reproducible dado el mismo input, sin pretender ser el
    hash de ninguna configuración real del clasificador.

    **Este hash es la causa directa de por qué `persist_classification`
    necesitó un fix (ronda de revisión 2026-09-27).** Que sea SIEMPRE
    distinto al hash de máquina es lo que hace que la fila humana caiga del
    lado "otro hash" del `UPDATE` de reclasificación en `pipeline.py` — sin
    la exclusión explícita por `features['revision_humana']` que ese
    `UPDATE` implementa ahora, cualquier corrida automática posterior
    degradaría la fila humana sin aviso. Quien toque este hash (por ejemplo
    para dejar de incluir el timestamp) tiene que releer
    `persist_classification` en `pipeline.py` y sus tests de
    `tests/integration/test_persist_classification_human_governance_db.py`
    antes de asumir que es un cambio inocuo.
    """
    raw = f"{previous_hash}:human_review:{episode_id}:{reviewed_at.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def submit_review(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    episode_id: UUID,
    reviewer_id: UUID,
    reviewer_role: str,
    verdict: str,
    reason: str,
) -> ReviewResult:
    """Registra la anulación humana. Gate 1.4: REEMPLAZA la etiqueta oficial.

    1. Busca la `Classification` `is_current=true` del episodio.
    2. La marca `is_current=false` (UPDATE real — D7 corregida: el patrón
       vigente de `classifications` no es append-only estricto).
    3. Inserta una `Classification` NUEVA con `appropriation=verdict`,
       copiando las métricas y `features` de la anterior — salvo que quita
       `needs_review`/`needs_review_reason` (ya fue revisado) y NUNCA toca
       `features['regimen_llm']` (gate 1.4: el estado técnico del juez no se
       sobrescribe).
    4. Inserta la fila `ClassificationReview` con las DOS FK (D7.a) y marca
       `features['revision_humana']` (D7.b) en la Classification nueva con
       el id de esa fila.

    Cada llamada es un INSERT de `ClassificationReview` — nunca un UPDATE de
    una revisión existente, así que un segundo POST sobre el mismo episodio
    apila historial en vez de pisarlo.

    **Concurrencia (hallazgo de QA, 2026-09-27, ALTA):** dos revisiones sobre
    el MISMO episodio pueden llegar casi juntas (dos docentes, dos tabs). El
    `UPDATE` del paso 2 usa concurrencia optimista — su `WHERE` exige el `id`
    exacto de la fila leída en el paso 1, no "la que sea vigente ahora". Si
    otra revisión ya la degradó entre el SELECT y el UPDATE, esta función
    levanta `ReviewConflictError` **antes** de insertar nada — no hay
    `ClassificationReview` a medio escribir, no hay `Classification` nueva
    huérfana. La ruta HTTP (`routes/review.py`) traduce esto a
    **409 Conflict** (decisión de contrato: se le pide al docente recargar y
    ver la decisión del otro, en vez de reintentar automáticamente — un
    retry automático aplicaría la revisión de este docente sobre un estado
    que ya no es el que vio cuando decidió, y el motivo que escribió puede
    dejar de tener sentido contra la nueva fila vigente). QUIÉN ganó la
    carrera (otro docente vs. una reclasificación automática) se distingue
    leyendo `features['revision_humana']` en la fila ganadora — ver
    `ReviewConflictError.retryable`.

    **Dependencia invisible: esto asume READ COMMITTED (hallazgo de QA,
    2026-09-27, ronda 5, punto 2).** El engine (`db/__init__.py::get_engine`)
    NO fija `isolation_level` — corre bajo el default de Postgres, que ES
    READ COMMITTED, pero nada en el código lo garantiza si alguien lo
    cambia. La concurrencia optimista de arriba depende de esa semántica
    exacta: cada statement dentro de una transacción toma su propio snapshot
    en el momento en que se emite (no el snapshot del inicio de la
    transacción), así que el `UPDATE` del paso 2 SIEMPRE ve el estado más
    reciente ya comiteado por otra transacción, incluida una fila insertada
    DESPUÉS de que esta transacción empezó. Es ese comportamiento el que
    hace que `rowcount == 0` sea una señal confiable de "alguien se
    adelantó" en el escenario sin contienda de lock (ver
    `tests/integration/test_submit_review_concurrency_db.py::test_segunda_revision_tras_commit_de_la_primera_no_pisa`).

    Bajo **REPEATABLE READ o SERIALIZABLE** el snapshot se toma al INICIO de
    la transacción y no se actualiza statement a statement: el `UPDATE`
    seguiría viendo la fila `previous` como estaba cuando la leyó, y
    dependiendo del nivel, o bien el `UPDATE` fallaría con un error de
    serialización (SERIALIZABLE) o bien -peor- podría no detectar el
    conflicto de la forma en que este código lo espera. **No cambiar
    `isolation_level` en el engine sin releer esta función y su suite de
    concurrencia entera.**

    Raises:
        ReviewTargetNotFoundError: no hay `Classification` vigente para el
            episodio.
        ReviewConflictError: otra revisión ganó la carrera sobre la misma
            fila vigente.
    """
    result = await session.execute(
        select(Classification).where(
            Classification.episode_id == episode_id,
            Classification.is_current.is_(True),
        )
    )
    previous = result.scalar_one_or_none()
    if previous is None:
        raise ReviewTargetNotFoundError(f"Sin clasificación actual para episodio {episode_id}")

    # Concurrencia optimista (hallazgo de QA, 2026-09-27, ALTA): el WHERE
    # incluye el `id` de `previous` — la fila EXACTA que leímos, no
    # "cualquiera que sea vigente ahora". Sin esto, si otra revisión ganó la
    # carrera entre nuestro SELECT y este UPDATE, este UPDATE matchearía la
    # fila NUEVA que dejó esa otra revisión (mismo episode_id, is_current=true)
    # y la degradaría — un lost update: la decisión del otro docente
    # desaparece como gobernante y ninguna fila de `classification_reviews`
    # explica que fue sobrescrita ni por quién. `rowcount == 0` es la señal
    # inequívoca de que eso pasó: NO seguimos adelante como si nada.
    update_result = await session.execute(
        update(Classification)
        .where(
            Classification.id == previous.id,
            Classification.is_current.is_(True),
        )
        .values(is_current=False)
    )
    if update_result.rowcount == 0:
        # ¿Quién ganó la carrera? Releemos la fila vigente actual — si
        # tiene `features['revision_humana']`, ganó OTRO DOCENTE; si no,
        # ganó una reclasificación AUTOMÁTICA (`persist_classification`).
        # Best-effort: es solo para el mensaje, no cambia si se levanta el
        # conflicto (eso ya se decidió arriba, por `rowcount==0`).
        winner_result = await session.execute(
            select(Classification).where(
                Classification.episode_id == episode_id,
                Classification.is_current.is_(True),
            )
        )
        winner = winner_result.scalar_one_or_none()
        winner_is_human = bool(winner is not None and (winner.features or {}).get("revision_humana"))

        if winner_is_human:
            raise ReviewConflictError(
                f"Otro docente ya revisó el episodio {episode_id} mientras se "
                "procesaba tu revisión. Recargá y mirá su decisión antes de "
                "insistir.",
                retryable=False,
            )
        raise ReviewConflictError(
            f"El sistema reclasificó automáticamente el episodio {episode_id} "
            "mientras se procesaba tu revisión. Tu decisión sigue siendo "
            "válida contra el estado nuevo — podés reintentar.",
            retryable=True,
        )

    reviewed_at = utc_now_f()
    new_features = dict(previous.features or {})
    new_features.pop("needs_review", None)
    new_features.pop("needs_review_reason", None)

    new_classification = Classification(
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=previous.comision_id,
        classifier_config_hash=_synthetic_review_config_hash(
            previous.classifier_config_hash, episode_id, reviewed_at
        ),
        appropriation=verdict,
        appropriation_reason=reason,
        ct_summary=previous.ct_summary,
        ccd_mean=previous.ccd_mean,
        ccd_orphan_ratio=previous.ccd_orphan_ratio,
        cii_stability=previous.cii_stability,
        cii_evolution=previous.cii_evolution,
        features=new_features,
        is_current=True,
        classified_at=reviewed_at,
    )
    session.add(new_classification)
    await session.flush()

    review = ClassificationReview(
        tenant_id=tenant_id,
        episode_id=episode_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        previous_classification_id=previous.id,
        new_classification_id=new_classification.id,
        verdict=verdict,
        reason=reason,
        reviewed_at=reviewed_at,
    )
    session.add(review)
    await session.flush()

    new_classification.features = {
        **new_classification.features,
        "revision_humana": {"review_id": review.id},
    }
    await session.flush()

    return ReviewResult(
        review_id=review.id,
        previous_classification_id=previous.id,
        new_classification_id=new_classification.id,
    )
