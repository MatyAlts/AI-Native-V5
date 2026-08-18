"""Schemas de la integración con Active-IA.

Nota deliberada: NO existe un schema de salida que incluya el password, ni
cifrado, ni sus últimos caracteres. Con una API key un fingerprint es un
identificador útil; con un password humano es una fuga.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CredencialCreate(BaseModel):
    """Body para conectar la cuenta de Active-IA del docente."""

    username: str = Field(min_length=1, max_length=255)
    # `SecretStr` y no `str`: su `repr` es `**********`, así que la contraseña
    # no aparece si el modelo entra en un traceback, en un log estructurado o
    # en el `repr` de la request. Es defensa en profundidad — lo que cierra el
    # agujero del 422 es el handler de `RequestValidationError` en `main.py`.
    password: SecretStr = Field(min_length=1, max_length=255)


class CredencialEstado(BaseModel):
    """Lo único que se puede saber de la cuenta conectada desde afuera."""

    conectada: bool
    # El simulador de escritura esta puesto en este entorno. Viaja acá porque
    # la vista tiene que poder avisarlo ANTES de que el docente elija un TP —
    # si no, el formulario para conectar la cuenta se ve sin ninguna
    # advertencia de que nada de lo que haga va a llegar a Active-IA.
    modo_simulado: bool = False
    username: str | None = None
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    last_login_ok: bool | None = None


class EjercicioSyncOut(BaseModel):
    """Estado de sincronización de UN ejercicio."""

    ejercicio_id: UUID
    titulo: str
    # sincronizado | desactualizado | sin_sincronizar | sin_rubrica
    estado: str
    rubrica_id: str | None = None
    sincronizado_at: datetime | None = None
    # El vínculo salió del simulador: esa rúbrica NO existe en Active-IA.
    simulado: bool = False


class SincronizacionOut(BaseModel):
    """Estado de la TP entera.

    `modo_simulado` va arriba de todo y no por ejercicio: si el simulador está
    puesto, nada de lo que diga esta respuesta llegó a Active-IA, y eso hay
    que decirlo una vez y fuerte, no repartido en una columna.
    """

    ejercicios: list[EjercicioSyncOut] = Field(default_factory=list)
    modo_simulado: bool = False


# ── Epic 3: el disparo por ejercicio ─────────────────────────────────────


class CorreccionIABody(BaseModel):
    """Body del disparo.

    `confirmado=False` (el default) devuelve un PREVIEW: qué ejercicio, con
    qué rúbrica y qué tests, sin ejecutar, sin contactar a Active-IA y sin
    consumir cuota. Es el default porque la operación cuesta plata y tiempo de
    cómputo, y porque el docente tiene que poder ver con qué rúbrica se va a
    corregir ANTES de que se corrija.
    """

    # Obligatorio: cada corrección se paga, así que qué ejercicio se corrige
    # tiene que ser una decisión explícita y no el default de un campo omitido.
    ejercicio_orden: int = Field(ge=1, le=1000)
    confirmado: bool = False


class CorreccionPreviewOut(BaseModel):
    """Lo que se ve antes de gastar."""

    orden: int
    ejercicio_titulo: str
    rubrica_id: str
    rubrica_estado: str
    rubrica_simulada: bool
    n_test_cases: int
    codigo_bytes: int
    ya_corregido: bool
    cuota_restante: int


class CorreccionIAOut(BaseModel):
    """Una corrección. `nota_100` es None mientras no haya terminado bien.

    NO se serializa `nota_100` para un estado que no sea `done`: la base lo
    impide con un CHECK, y el schema lo repite para que un cliente no pueda
    leer una nota de una corrección fallida ni por accidente.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entrega_id: UUID
    orden: int
    estado: str
    rubrica_id: str
    nota_100: Decimal | None = None
    desglose: list[dict[str, Any]] = Field(default_factory=list)
    tests_snapshot: dict[str, Any] = Field(default_factory=dict)
    artefacto_sha256: str
    error_code: str | None = None
    error_detail: str | None = None
    # Separa "el servicio no pudo" de "el servicio dijo que no". La UI pinta
    # ámbar y "puede que reintentar sirva" para el primero, rojo para el
    # segundo. Confundirlos ya costó dos días de reintentos inútiles.
    es_infraestructura: bool = False
    external_correccion_id: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class CorreccionIAListOut(BaseModel):
    correcciones: list[CorreccionIAOut] = Field(default_factory=list)
