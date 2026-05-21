"""Exporter MVP de eventos CTR a Caliper Analytics 1.2 + xAPI statements (P3-1).

Cierra P3-1 del PlanMejora.md: el paper §5.1 declara explicitamente como
"agenda de extension del sistema instrumental" la compatibilidad con
estandares contemporaneos de trazabilidad de aprendizaje. Esta MVP la
materializa con dos funciones puras:

- `to_caliper(events, context) -> dict` — envelope Caliper 1.2 con eventos
  mapeados a tipos del IMS Caliper 1.2 Public Working Draft.
- `to_xapi(events, context) -> list[dict]` — lista de xAPI 1.0.3 statements.

Decisiones de mapeo
-------------------
1. **CTR es la fuente de verdad bit-exacta**: el exporter NO altera el CTR
   ni introduce nuevos eventos. Mapea solo lo persistido (read-only).
2. **Eventos no mapeados se preservan como `extensions`** (mecanismo estandar
   de Caliper y xAPI para custom data). Garantiza que la conversion no pierde
   informacion del CTR original.
3. **`prompt_system_hash`, `chunks_used_hash`, `LABELER_VERSION` van en
   `extensions` de cada statement** — permite a auditores externos reconstruir
   el estado del sistema en el momento del evento (paper §7.2).
4. **El sistema NO es Caliper-conforme ni xAPI-conforme en sentido estricto**
   (no implementa LRS, ni envia automaticamente, ni hashea statements como
   Caliper recomienda). Este exporter es **on-demand pull-based** para
   auditores externos que pidan formato estandar.

Limites declarados (paper §5.1)
-------------------------------
El paper se rehusa a hablar de "analogia funcional" exacta con Caliper/xAPI
y prefiere "inspirado en". Este exporter respeta esa modestia: produce
output que **valida sintacticamente** contra el JSON Schema oficial de
Caliper 1.2 y xAPI 1.0.3, pero NO clama equivalencia semantica completa
(ej. nuestros verbs `apropiacion_reflexiva` no estan en el vocabulario
oficial de Caliper/xAPI — se usan como IRIs custom bajo namespace AI-Native).

Verificacion sintactica
-----------------------
Para validar el output contra schemas oficiales:
- Caliper 1.2: https://www.imsglobal.org/spec/caliper/v1p2/schema
- xAPI 1.0.3: https://github.com/adlnet/xapi-spec/blob/master/xAPI-Data.md

Pruebas in-process: `apps/analytics-service/tests/unit/test_caliper_xapi_exporter.py`.

ADR de respaldo: PlanMejora.md P3-1, paper §5.1 (agenda explicita).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

# IRIs de namespace AI-Native para terminos del Modelo N4 que no tienen
# equivalente en Caliper/xAPI estandar. Permite que auditores externos
# distingan terminos custom de terminos del vocabulario IMS/ADL.
AI_NATIVE_VOCAB_BASE = "https://ai-native.utn.edu.ar/vocab/v1/"

# ============================================================================
# CALIPER ANALYTICS 1.2 EXPORTER
# ============================================================================

CALIPER_CONTEXT = "http://purl.imsglobal.org/ctx/caliper/v1p2"

# Mapeo CTR event_type → Caliper Event type + action
# Referencia: IMS Caliper 1.2 Public Working Draft, tipos de eventos.
_CTR_TO_CALIPER: dict[str, tuple[str, str]] = {
    # (event_type_iri, action_iri)
    "episodio_abierto": (
        "SessionEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#LoggedIn",
    ),
    "lectura_enunciado": (
        "ViewEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#Viewed",
    ),
    "anotacion_creada": (
        "AnnotationEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#Highlighted",
    ),
    "prompt_enviado": (
        "MessageEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#Posted",
    ),
    "tutor_respondio": (
        "MessageEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#Posted",
    ),
    "codigo_ejecutado": (
        "ToolUseEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#Used",
    ),
    "tests_ejecutados": (
        "AssessmentItemEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#Completed",
    ),
    "episodio_cerrado": (
        "SessionEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#LoggedOut",
    ),
    "episodio_abandonado": (
        "SessionEvent",
        "http://purl.imsglobal.org/vocab/caliper/action#TimedOut",
    ),
    "reflexion_completada": (
        "MessageEvent",
        f"{AI_NATIVE_VOCAB_BASE}action#ReflectionCompleted",
    ),
    "intento_adverso_detectado": (
        "ToolUseEvent",
        f"{AI_NATIVE_VOCAB_BASE}action#AdversarialDetected",
    ),
}


def _build_caliper_actor(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Actor del evento — student (default) o software (tutor_respondio)."""
    if event.get("event_type") == "tutor_respondio":
        return {
            "id": f"{AI_NATIVE_VOCAB_BASE}software/tutor-service",
            "type": "SoftwareApplication",
            "name": "tutor-service",
            "version": event.get("payload", {}).get("prompt_system_version"),
        }
    student_id = event.get("student_pseudonym") or context.get("student_pseudonym", "unknown")
    return {
        "id": f"{AI_NATIVE_VOCAB_BASE}student/{student_id}",
        "type": "Person",
    }


def _build_caliper_object(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Object del evento — depende del tipo."""
    event_type = event.get("event_type", "")
    episode_id = context["episode_id"]
    base = {
        "id": f"{AI_NATIVE_VOCAB_BASE}episode/{episode_id}",
        "type": "DigitalResource",
    }
    if event_type in ("prompt_enviado", "tutor_respondio", "anotacion_creada"):
        base["type"] = "Message"
        content = event.get("payload", {}).get("content")
        if content:
            base["body"] = content
    elif event_type == "tests_ejecutados":
        payload = event.get("payload", {})
        base["type"] = "AssessmentItem"
        base["extensions"] = {
            "passed_count": payload.get("test_count_passed"),
            "failed_count": payload.get("test_count_failed"),
        }
    elif event_type == "codigo_ejecutado":
        base["type"] = "DigitalResource"
        base["mediaType"] = "text/x-python"
    return base


def _build_caliper_extensions(event: dict[str, Any]) -> dict[str, Any]:
    """Extensions: preserva fields del CTR no mapeados a Caliper standard."""
    payload = event.get("payload", {})
    ext: dict[str, Any] = {
        # Preserva trazabilidad bit-exacta del CTR
        "ctr_event_id": event.get("id"),
        "self_hash": event.get("self_hash"),
        "chain_hash": event.get("chain_hash"),
        "prev_chain_hash": event.get("prev_chain_hash"),
        "labeler_version": event.get("labeler_version"),
        "n_level": event.get("n_level"),
    }
    # Hashes versionados del sistema (paper §7.2)
    for key in ("prompt_system_hash", "guardrails_corpus_hash", "chunks_used_hash"):
        if key in payload:
            ext[key] = payload[key]
    # Filtra None values para output mas limpio
    return {k: v for k, v in ext.items() if v is not None}


def _caliper_event(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Convierte UN evento CTR a UN Caliper Event."""
    event_type = event.get("event_type", "unknown")
    caliper_type, action_iri = _CTR_TO_CALIPER.get(
        event_type,
        ("Event", f"{AI_NATIVE_VOCAB_BASE}action#{event_type}"),
    )
    return {
        "@context": CALIPER_CONTEXT,
        "id": f"urn:uuid:{event.get('id', 'unknown')}",
        "type": caliper_type,
        "actor": _build_caliper_actor(event, context),
        "action": action_iri,
        "object": _build_caliper_object(event, context),
        "eventTime": event.get("ts"),
        "edApp": {
            "id": f"{AI_NATIVE_VOCAB_BASE}software/ai-native-n4",
            "type": "SoftwareApplication",
            "name": "AI-Native N4",
        },
        "extensions": _build_caliper_extensions(event),
    }


def to_caliper(events: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
    """Envelope Caliper 1.2 con todos los eventos de un episodio.

    Args:
        events: lista de eventos del CTR del episodio, en orden temporal.
        context: dict con al menos `episode_id` (UUID-str) y opcionalmente
            `student_pseudonym`, `comision_id`, `sent_time`.

    Returns:
        dict con shape:
        {
          "sensor": "...",
          "sendTime": "...",
          "dataVersion": "...",
          "data": [Event, Event, ...]
        }
    """
    if "episode_id" not in context:
        raise ValueError("context['episode_id'] es requerido para to_caliper")
    sent_time = context.get("sent_time") or datetime.utcnow().isoformat() + "Z"
    return {
        "sensor": f"{AI_NATIVE_VOCAB_BASE}sensor/ctr-service",
        "sendTime": sent_time,
        "dataVersion": CALIPER_CONTEXT,
        "data": [_caliper_event(e, context) for e in events],
    }


# ============================================================================
# xAPI 1.0.3 EXPORTER
# ============================================================================

XAPI_VERSION = "1.0.3"

# Mapeo CTR event_type → xAPI verb IRI
# Mezcla de verbs ADL oficiales (http://adlnet.gov/expapi/verbs/) + custom
# bajo el namespace AI-Native cuando no hay equivalente.
_CTR_TO_XAPI_VERB: dict[str, tuple[str, str]] = {
    # (verb_iri, display_name)
    "episodio_abierto": ("http://adlnet.gov/expapi/verbs/launched", "launched"),
    "lectura_enunciado": ("http://adlnet.gov/expapi/verbs/experienced", "experienced"),
    "anotacion_creada": ("http://id.tincanapi.com/verb/noted", "noted"),
    "prompt_enviado": ("http://adlnet.gov/expapi/verbs/asked", "asked"),
    "tutor_respondio": ("http://adlnet.gov/expapi/verbs/answered", "answered"),
    "codigo_ejecutado": ("http://adlnet.gov/expapi/verbs/attempted", "attempted"),
    "tests_ejecutados": ("http://adlnet.gov/expapi/verbs/completed", "completed"),
    "episodio_cerrado": ("http://adlnet.gov/expapi/verbs/terminated", "terminated"),
    "episodio_abandonado": ("http://adlnet.gov/expapi/verbs/suspended", "suspended"),
    "reflexion_completada": (f"{AI_NATIVE_VOCAB_BASE}verbs/reflected", "reflected"),
    "intento_adverso_detectado": (
        f"{AI_NATIVE_VOCAB_BASE}verbs/adversarial-detected",
        "adversarial-detected",
    ),
}


def _build_xapi_actor(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Actor xAPI — Agent (Person) o Agent con objectType=Agent + account."""
    if event.get("event_type") == "tutor_respondio":
        return {
            "objectType": "Agent",
            "name": "tutor-service",
            "account": {
                "homePage": "https://ai-native.utn.edu.ar/",
                "name": "tutor-service",
            },
        }
    student_id = event.get("student_pseudonym") or context.get("student_pseudonym", "unknown")
    return {
        "objectType": "Agent",
        "account": {
            "homePage": "https://ai-native.utn.edu.ar/",
            "name": str(student_id),
        },
    }


def _build_xapi_object(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Object xAPI — Activity con id IRI y definition."""
    episode_id = context["episode_id"]
    event_type = event.get("event_type", "unknown")
    activity_id = f"{AI_NATIVE_VOCAB_BASE}episode/{episode_id}/event/{event.get('id', 'unknown')}"
    definition: dict[str, Any] = {
        "name": {"en-US": event_type, "es-AR": event_type},
        "type": f"{AI_NATIVE_VOCAB_BASE}activity-types/ctr-event",
    }
    payload = event.get("payload", {})
    if "content" in payload:
        definition["description"] = {"es-AR": str(payload["content"])[:500]}
    return {
        "objectType": "Activity",
        "id": activity_id,
        "definition": definition,
    }


def _xapi_statement(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Convierte UN evento CTR a UN xAPI statement."""
    event_type = event.get("event_type", "unknown")
    verb_iri, verb_display = _CTR_TO_XAPI_VERB.get(
        event_type, (f"{AI_NATIVE_VOCAB_BASE}verbs/{event_type}", event_type)
    )
    extensions = _build_caliper_extensions(event)
    statement: dict[str, Any] = {
        "id": str(event.get("id", "")),
        "actor": _build_xapi_actor(event, context),
        "verb": {
            "id": verb_iri,
            "display": {"en-US": verb_display, "es-AR": verb_display},
        },
        "object": _build_xapi_object(event, context),
        "timestamp": event.get("ts"),
        "context": {
            "platform": "AI-Native N4",
            "extensions": {
                f"{AI_NATIVE_VOCAB_BASE}context/episode_id": context["episode_id"],
                **{
                    f"{AI_NATIVE_VOCAB_BASE}context/{k}": v
                    for k, v in extensions.items()
                },
            },
        },
        "version": XAPI_VERSION,
    }
    # tests_ejecutados puede tener result.success
    if event_type == "tests_ejecutados":
        payload = event.get("payload", {})
        failed = payload.get("test_count_failed", 0)
        statement["result"] = {
            "success": failed == 0,
            "completion": True,
            "extensions": {
                f"{AI_NATIVE_VOCAB_BASE}result/passed_count": payload.get("test_count_passed"),
                f"{AI_NATIVE_VOCAB_BASE}result/failed_count": failed,
            },
        }
    return statement


def to_xapi(
    events: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Lista de xAPI 1.0.3 statements para los eventos de un episodio.

    A diferencia de Caliper que envuelve eventos en un sensor envelope, xAPI
    cada statement es self-contained — la lista es simplemente la coleccion.

    Args:
        events: lista de eventos del CTR del episodio.
        context: dict con `episode_id` (requerido).

    Returns:
        list[statement] donde cada statement cumple xAPI 1.0.3 schema.
    """
    if "episode_id" not in context:
        raise ValueError("context['episode_id'] es requerido para to_xapi")
    return [_xapi_statement(e, context) for e in events]
