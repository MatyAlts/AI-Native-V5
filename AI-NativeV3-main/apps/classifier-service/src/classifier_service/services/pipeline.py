"""Pipeline: episodio cerrado → features → árbol → clasificación persistida.

El worker de classifier-service escucha eventos `episodio_cerrado`, carga
todos los eventos del episodio desde el ctr-service, calcula las 3
coherencias, aplica el árbol N4, y persiste la clasificación como fila
append-only en `classifications` con `is_current=true` (marcando la
anterior, si existía, como `is_current=false`).
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
from classifier_service.services.tree import (
    DEFAULT_REFERENCE_PROFILE,
    ClassificationResult,
    classify,
)

logger = logging.getLogger(__name__)


def compute_classifier_config_hash(
    reference_profile: dict[str, Any], tree_version: str = "v1.0.0"
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
        "tp_entregada",          # tp-entregas-correccion: meta-evento de entrega formal
        "tp_calificada",         # tp-entregas-correccion: meta-evento de calificacion docente
    }
)


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
    classifier_events = [
        e for e in events if e.get("event_type") not in _EXCLUDED_FROM_FEATURES
    ]
    ct = ct_features(classifier_events)
    ccd = compute_ccd(classifier_events)
    cii = compute_cii(classifier_events)
    return classify(ct=ct, ccd=ccd, cii=cii, reference_profile=profile)


async def persist_classification(
    session: AsyncSession,
    tenant_id: UUID,
    episode_id: UUID,
    comision_id: UUID,
    result: ClassificationResult,
    classifier_config_hash: str,
) -> Classification:
    """Persiste append-only (ADR-010).

    Idempotencia: si ya existe una fila `is_current=true` con el mismo
    `classifier_config_hash` para este `episode_id`, la devuelve tal cual
    (no-op). Si existe `is_current=true` con OTRO hash (reclasificación
    real con config nueva), la marca `is_current=false` e inserta la nueva.

    Esto cierra la deuda QA "POST /classify_episode/{id} no es idempotente":
    el `UniqueConstraint(episode_id, classifier_config_hash)` haría fallar
    un re-POST con duplicate-key 500 — ahora se devuelve la existente.
    """
    # SELECT previo: ¿ya existe una clasificación current con MISMO hash?
    # Si sí → idempotencia: no tocamos nada y devolvemos la fila existente.
    existing_same_hash = await session.execute(
        select(Classification).where(
            Classification.episode_id == episode_id,
            Classification.classifier_config_hash == classifier_config_hash,
            Classification.is_current.is_(True),
        )
    )
    current_row = existing_same_hash.scalar_one_or_none()
    if current_row is not None:
        logger.debug(
            "Idempotent re-classify: classification ya existe "
            "(episode_id=%s, classifier_config_hash=%s)",
            episode_id,
            classifier_config_hash,
        )
        return current_row

    # Reclasificación con config distinta: marcar la vieja como no-current.
    # Filtramos por hash distinto para evitar tocar filas con el mismo hash
    # (defensa adicional al SELECT de arriba — caso de carrera puntual).
    await session.execute(
        update(Classification)
        .where(
            Classification.episode_id == episode_id,
            Classification.is_current.is_(True),
            Classification.classifier_config_hash != classifier_config_hash,
        )
        .values(is_current=False)
    )

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
        is_current=True,
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
        classifier_ccd_orphan_ratio.add(
            float(result.ccd_orphan_ratio), {"cohort": cohort_label}
        )
    if result.cii_evolution is not None:
        classifier_cii_evolution_slope.record(float(result.cii_evolution))

    return new_classification
