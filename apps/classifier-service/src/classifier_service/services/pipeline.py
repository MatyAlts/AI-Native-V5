"""Pipeline: episodio cerrado → features → árbol → clasificación persistida.

El worker de classifier-service escucha eventos `episodio_cerrado`, carga
todos los eventos del episodio desde el ctr-service, calcula las 3
coherencias, aplica el árbol N4, y persiste la clasificación como fila
append-only en `classifications`. Normalmente entra con `is_current=true`
(marcando la anterior, si existía, como `is_current=false`) — EXCEPTO si
una anulación humana gobierna ese episodio (B3+B5,
`services/review.py::submit_review`), en cuyo caso la fila de máquina se
registra con `is_current=false`: la anulación humana gobierna hasta que
otro humano la cambie. Ver el docstring de `persist_classification` y el
de `Classification.is_current` en `models/__init__.py`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from classifier_service.metrics import (
    classifier_ccd_orphan_ratio,
    classifier_cii_evolution_slope,
    classifier_classifications_total,
)
from classifier_service.models import Classification
from classifier_service.services.ccd import compute_ccd
from classifier_service.services.cii import compute_cii
from classifier_service.services.ct import ct_features
from classifier_service.services.subgrupo import compute_subgrupo
from classifier_service.services.tree import (
    DEFAULT_REFERENCE_PROFILE,
    ClassificationResult,
    classify,
)

logger = logging.getLogger(__name__)


def compute_classifier_config_hash(
    reference_profile: dict[str, Any], tree_version: str = "v4.0.0"
) -> str:
    """Hash determinista del config del classifier.

    Este hash acompaña cada clasificación (classifier_config_hash) y es lo
    que permite reproducir EXACTAMENTE el mismo resultado en el futuro.
    Si cambia el reference_profile o la versión del árbol, cambia el hash
    y toda reclasificación insert nueva fila append-only (ADR-010).
    """
    canonical = json.dumps(
        {"tree_version": tree_version, "profile": reference_profile},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# ADR-035: eventos side-channel que el CTR persiste pero el classifier IGNORA.
# Mantenerlos fuera del feature extraction es lo que preserva reproducibilidad
# bit-a-bit del `classifier_config_hash` cuando se introducen senales nuevas
# (reflexion metacognitiva, attestation requests, etc.) post-cierre del episodio.
# Cada entrada de este set debe estar respaldada por un ADR.
_EXCLUDED_FROM_FEATURES = frozenset(
    {
        "reflexion_completada",  # ADR-035
        "tp_entregada",  # tp-entregas-correccion: meta-evento de entrega formal
        "tp_calificada",  # tp-entregas-correccion: meta-evento de calificacion docente
        "pestana_perdida",  # side-channel integridad de foco — NO cognitivo
        "pestana_recuperada",  # side-channel integridad de foco — NO cognitivo
        "episodio_reabierto",  # reapertura docente (2026-06-19): meta-evento de gobernanza
    }
)

# Roll-up del eje del subgrupo a la etiqueta oficial (4 categorias del schema: 3 del continuo + autonomo ortogonal).
# REEMPLAZO 2026-06-11 (tree_version v3.0.0): el subgrupo pasa a decidir la etiqueta.
# Indeterminado (episodios muy cortos, sin señal) -> superficial (default acordado).
_EJE_TO_APPROPRIATION = {
    "reflexiva": "apropiacion_reflexiva",
    "superficial": "apropiacion_superficial",
    "delegacion_pasiva": "delegacion_pasiva",
    # Eje autonomo (v4.0.0): todo el brazo sin-tutor (prompts == 0). Se persiste
    # como su propio valor de `appropriation` — no se colapsa en reflexiva/superficial
    # porque no hubo conversacion con el tutor que permita juzgar la apropiacion.
    "autonomo": "autonomo",
    "sin_clasificar": "apropiacion_superficial",
}


def classify_episode_from_events(
    events: list[dict],
    reference_profile: dict[str, Any] | None = None,
) -> ClassificationResult:
    """Clasifica un episodio dado su lista de eventos.

    Esta función es pura y determinista: mismos eventos + mismo profile =
    misma clasificación.

    Eventos en `_EXCLUDED_FROM_FEATURES` se filtran ANTES del feature
    extraction (ADR-035) — son side-channel del CTR que NO afectan
    reproducibilidad.
    """
    profile = reference_profile or DEFAULT_REFERENCE_PROFILE
    classifier_events = [e for e in events if e.get("event_type") not in _EXCLUDED_FROM_FEATURES]
    ct = ct_features(classifier_events)
    ccd = compute_ccd(classifier_events)
    cii = compute_cii(classifier_events)
    result = classify(ct=ct, ccd=ccd, cii=cii, reference_profile=profile)
    # REEMPLAZO OFICIAL (2026-06-11, tree_version v3.0.0): la etiqueta oficial
    # `appropriation` pasa a derivarse del SUBGRUPO (roll-up al eje), corrigiendo la
    # inversion del arbol viejo (autonomos sin tutor caian en delegacion_pasiva). Las
    # 5 metricas (ct/ccd/cii) se siguen calculando y persistiendo para auditoria, pero
    # ya NO deciden la etiqueta. El subgrupo + 4 dimensiones se calculan sobre los
    # eventos ORIGINALES (para que el foco cuente pestana/copia/pega) y van en features.
    sg = compute_subgrupo(events)
    result.features["subgrupo"] = sg
    result.appropriation = _EJE_TO_APPROPRIATION[sg["eje"]]
    result.reason = (
        f"Subgrupo {sg['key']} ({sg['label']}) -> eje {sg['eje']}. {sg['accion_docente']}."
    )
    return result


async def persist_classification(
    session: AsyncSession,
    tenant_id: UUID,
    episode_id: UUID,
    comision_id: UUID,
    result: ClassificationResult,
    classifier_config_hash: str,
) -> Classification:
    """Persiste append-only (ADR-010).

    Idempotencia: si ya existe UNA FILA CUALQUIERA (vigente o no) con este
    `(episode_id, classifier_config_hash)`, la devuelve tal cual (no-op, sin
    insertar ni tocar su `is_current`). Si no existe ninguna con ese hash
    (reclasificación real con config nueva), degrada las vigentes que
    correspondan e inserta la nueva.

    Esto cierra la deuda QA "POST /classify_episode/{id} no es idempotente":
    el `UniqueConstraint(episode_id, classifier_config_hash)` haría fallar
    un re-POST con duplicate-key 500 — ahora se devuelve la existente.

    **Gobernanza humana (extensión post-B3+B5, ronda de revisión 2026-09-27):**
    `is_current=true` dejó de significar "la última clasificación que
    corrió" y pasa a significar **"la que gobierna"**. Una fila de
    procedencia humana (`features['revision_humana']`, ver
    `services/review.py::submit_review`) SIEMPRE tiene un
    `classifier_config_hash` sintético distinto del de máquina — así que el
    `UPDATE` de reclasificación, si no la excluyera explícitamente,
    la degradaría en la primera corrida automática posterior (bug real,
    confirmado: "el humano manda hasta la próxima corrida", que vacía el
    propósito de la anulación). Regla: **la anulación humana gobierna hasta
    que otro humano la cambie**. La reclasificación automática posterior a
    una anulación SE REGISTRA (es información: el juez y el docente pueden
    discrepar sistemáticamente en ese episodio) pero entra con
    `is_current=false` — nunca gobierna por sí sola.

    Y por eso la idempotencia se amplió a "cualquier fila con ese hash, no
    solo la vigente": tras una anulación humana, el hash de MÁQUINA de un
    episodio queda "usado" en una fila no-vigente (la que la anulación
    reemplazó). Si una corrida automática posterior vuelve a computar ESE
    MISMO hash (config sin cambios — el caso normal, ya que el hash no
    avanza solo porque hubo una revisión), el `INSERT` chocaría con el
    `UniqueConstraint` aunque esa fila no sea la vigente. La idempotencia
    de arriba (chequeo por hash sin filtrar `is_current`) resuelve las dos
    cosas con el mismo SELECT.
    """
    # SELECT previo: ¿ya existe UNA FILA (current o no) con este hash para
    # este episodio? Si sí → idempotencia: no tocamos nada y la devolvemos
    # tal cual. Antes de la gobernanza humana esto solo miraba `is_current`,
    # pero una anulación humana deja el hash de máquina "usado" en una fila
    # no-vigente — sin ampliar el chequeo, la siguiente corrida automática
    # con el mismo hash intentaría un INSERT que choca con el
    # UniqueConstraint(episode_id, classifier_config_hash).
    existing_same_hash = await session.execute(
        select(Classification).where(
            Classification.episode_id == episode_id,
            Classification.classifier_config_hash == classifier_config_hash,
        )
    )
    current_row = existing_same_hash.scalar_one_or_none()
    if current_row is not None:
        logger.debug(
            "Idempotent re-classify: classification ya existe "
            "(episode_id=%s, classifier_config_hash=%s, is_current=%s)",
            episode_id,
            classifier_config_hash,
            current_row.is_current,
        )
        return current_row

    # Reclasificación con hash nuevo: degradar las vigentes — EXCEPTO una de
    # procedencia humana. `~features.has_key("revision_humana")` es la
    # exclusión que gate 1.4 pide ("la anulación humana gobierna hasta que
    # otro humano la cambie"); la comparación de hash es la defensa original
    # (caso de carrera puntual) y ahora también es redundante-pero-inocua
    # con el SELECT de arriba (que ya garantiza que ninguna fila vigente
    # comparte este hash exacto).
    await session.execute(
        update(Classification)
        .where(
            Classification.episode_id == episode_id,
            Classification.is_current.is_(True),
            Classification.classifier_config_hash != classifier_config_hash,
            ~Classification.features.has_key("revision_humana"),
        )
        .values(is_current=False)
    )

    # ¿Sigue habiendo una fila vigente? Solo puede ser una humana — el
    # UPDATE de arriba degradó cualquier otra. Si la hay, la nueva fila de
    # máquina se registra pero NO gobierna (is_current=false).
    still_current = await session.execute(
        select(Classification.id).where(
            Classification.episode_id == episode_id,
            Classification.is_current.is_(True),
        )
    )
    new_row_governs = still_current.scalar_one_or_none() is None

    new_classification = Classification(
        tenant_id=tenant_id,
        episode_id=episode_id,
        comision_id=comision_id,
        classifier_config_hash=classifier_config_hash,
        appropriation=result.appropriation,
        appropriation_reason=result.reason,
        ct_summary=result.ct_summary,
        ccd_mean=result.ccd_mean,
        ccd_orphan_ratio=result.ccd_orphan_ratio,
        cii_stability=result.cii_stability,
        cii_evolution=result.cii_evolution,
        features=result.features,
        is_current=new_row_governs,
    )
    session.add(new_classification)
    await session.flush()

    # Métricas: emisión post-flush para que el conteo refleje persistencias
    # exitosas. `tenant_id` y `cohort` son labels permitidas; `episode_id`
    # NO se incluye (cardinalidad). `template_id` como label queda DEFERRED:
    # requiere lookup cross-service Episode → TareaPractica.template_id
    # (academic-service vía HTTP o cache) que no está disponible en este
    # scope sin un join extra.
    cohort_label = str(comision_id)
    classifier_classifications_total.add(
        1,
        {
            "tenant_id": str(tenant_id),
            "appropriation": result.appropriation,
            "classifier_config_hash": classifier_config_hash,
            "cohort": cohort_label,
        },
    )
    if result.ccd_orphan_ratio is not None:
        # UpDownCounter — aproximación al gauge per-cohort. Cada clasificación
        # contribuye con su valor; el panel del dashboard 5 muestra avg() por
        # cohorte, lo cual es equivalente al promedio de los emisores.
        classifier_ccd_orphan_ratio.add(float(result.ccd_orphan_ratio), {"cohort": cohort_label})
    if result.cii_evolution is not None:
        classifier_cii_evolution_slope.record(float(result.cii_evolution))

    return new_classification
