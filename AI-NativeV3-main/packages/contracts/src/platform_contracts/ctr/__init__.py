"""Eventos del CTR."""

from platform_contracts.ctr.events import (
    AnotacionCreada,
    CodigoEjecutado,
    CTRBaseEvent,
    EdicionCodigo,
    EpisodioAbandonado,
    EpisodioAbierto,
    EpisodioCerrado,
    IntentoAdversoDetectado,
    LecturaEnunciado,
    PromptEnviado,
    ReflexionCompletada,
    TestsEjecutados,
    TutorRespondio,
)
from platform_contracts.ctr.hashing import (
    GENESIS_HASH,
    compute_chain_hash,
    compute_self_hash,
    verify_chain_integrity,
)

__all__ = [
    "GENESIS_HASH",
    "AnotacionCreada",
    "CTRBaseEvent",
    "CodigoEjecutado",
    "EdicionCodigo",
    "EpisodioAbandonado",
    "EpisodioAbierto",
    "EpisodioCerrado",
    "IntentoAdversoDetectado",
    "LecturaEnunciado",
    "PromptEnviado",
    "ReflexionCompletada",
    "TestsEjecutados",
    "TutorRespondio",
    "compute_chain_hash",
    "compute_self_hash",
    "verify_chain_integrity",
]
