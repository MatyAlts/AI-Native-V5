"""Dependencies de FastAPI para auth y tenant context.

En F1 el JWT se valida contra Keycloak. Para tests, se inyecta un User
mock. La validación real con firma de JWT se completa en F3 cuando el
api-gateway toma ese rol.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from platform_observability import verify_gateway_signature
from sqlalchemy.ext.asyncio import AsyncSession

from academic_service.config import settings
from academic_service.db import tenant_session


def _enforce_gateway_signature(
    x_user_id: str | None,
    x_tenant_id: str | None,
    x_user_roles: str | None,
    x_gateway_signature: str | None,
    x_gateway_ts: str | None,
) -> None:
    """Defensa en profundidad: exige firma HMAC del gateway si el flag está ON.

    Con ``require_gateway_signature=False`` (default) es un no-op total — el
    comportamiento runtime no cambia. Con el flag ON, valida que los headers
    de identidad vengan firmados por el gateway (procedencia), sin re-verificar
    el JWT. Firma ausente o inválida => 401.
    """
    if not settings.require_gateway_signature:
        return
    ok = verify_gateway_signature(
        settings.gateway_shared_secret,
        x_user_id or "",
        x_tenant_id or "",
        x_user_roles or "",
        x_gateway_ts,  # type: ignore[arg-type]  # verify maneja None/no-int
        x_gateway_signature or "",
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma del gateway ausente o invalida",
        )


@dataclass(frozen=True)
class User:
    """Usuario autenticado extraído del JWT."""

    id: UUID
    tenant_id: UUID
    email: str
    roles: frozenset[str]
    realm: str
    comisiones_activas: frozenset[UUID] = frozenset()


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),  # solo para tests locales
    x_user_id: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
    x_gateway_signature: str | None = Header(default=None),
    x_gateway_ts: str | None = Header(default=None),
) -> User:
    """Extrae el usuario del header Authorization (JWT Keycloak).

    En F1/F2 (antes de que api-gateway tome el rol de validar JWTs)
    aceptamos headers X-* para facilitar pruebas end-to-end locales.
    En F3, el api-gateway valida el JWT y agrega estos headers; los
    servicios downstream solo los leen, confiando en la validación
    del gateway.
    """
    # Defensa en profundidad (default OFF): si el flag está ON, exigir que el
    # gateway haya firmado los headers de identidad ANTES de confiar en ellos.
    _enforce_gateway_signature(
        x_user_id, x_tenant_id, x_user_roles, x_gateway_signature, x_gateway_ts
    )
    # Path de desarrollo/test: headers X-* inyectados por el api-gateway
    # o por el cliente de tests
    if x_user_id and x_tenant_id and x_user_email:
        return User(
            id=UUID(x_user_id),
            tenant_id=UUID(x_tenant_id),
            email=x_user_email,
            roles=frozenset((x_user_roles or "").split(",")) if x_user_roles else frozenset(),
            realm=x_tenant_id,  # por simplicidad
        )

    # DEFERRED F3: validar firma JWT contra Keycloak y extraer claims acá.
    # Bloqueante hasta que el api-gateway tome rol de validador (ADR auth/F3).
    # Mientras tanto el path X-* arriba cubre dev/test y prod via gateway.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Placeholder: en F3 esto valida firma del JWT
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="JWT validation pending F3 api-gateway integration",
    )


async def _tenant_db(user: User = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    """Sesión DB con tenant del user activo seteado en RLS.

    NO se usa directo desde las rutas: se consume via `get_db`, que la pide con
    `scope="function"`. Ver el docstring de `get_db` — ahí está el porqué.
    """
    async with tenant_session(user.tenant_id) as session:
        yield session


async def get_db(
    session: AsyncSession = Depends(_tenant_db, scope="function"),
) -> AsyncSession:
    """Sesión DB del request. El commit pasa ANTES de que salga la respuesta.

    Hasta el 2026-08-28 esto era, directamente::

        async def get_db(user=Depends(get_current_user)):
            async with tenant_session(user.tenant_id) as session:
                yield session

    y ahí estaba el bug. `tenant_session` tiene el `await session.commit()` en
    el teardown del generador, y FastAPI corre el teardown de una dependencia
    con `yield` en el `AsyncExitStack` de la REQUEST, que se cierra **después**
    de emitir la respuesta. Se ve literal en el fuente de la versión instalada
    (`fastapi/routing.py::request_response`, FastAPI 0.139.2)::

        async with AsyncExitStack() as request_stack:       # teardown "request"
            async with AsyncExitStack() as function_stack:  # teardown "function"
                response = await f(request)
            # cierra function_stack
            await response(scope, receive, send)            # SALE LA RESPUESTA
        # cierra request_stack  <- el commit corría ACÁ

    Y ningún handler de ejercicios/TPs commitea por su cuenta —los únicos
    `commit()` explícitos del servicio están en `routes/instrumentos.py` y
    `routes/student_profiles.py`— así que el 100% de las escrituras dependía de
    ese commit tardío. Un cliente que escribía y leía enseguida podía no ver lo
    que acababa de escribir:

        POST ejercicio         -> 201
        POST TP                -> 201
        POST /{tp}/ejercicios  -> 201
        POST /{tp}/publish     -> 422 "Una TP no se puede publicar vacia"

    (smoke E2E, misma corrida, mismo commit). No es flaky: es el orden de
    operaciones. `web-teacher/.../TareasPracticasView.tsx:1352-1362` hace esa
    misma secuencia contra un docente real.

    **El fix.** La sesión pasa a pedirse con `scope="function"`, que es
    exactamente para esto — la doc de `Depends` lo dice así: «end the dependency
    after the *path operation function* ends, but **before** the response is
    sent back to the client». El teardown se muda al `function_stack`, que cierra
    una línea ANTES de `await response(...)`.

    Se hace acá y no en los 95 `Depends(get_db)` de las rutas a propósito: el
    scope se declara en el sitio de llamada, así que ponerlo en cada ruta lo
    volvería un detalle que alguien puede olvidar en la ruta 96. Acá es
    imposible equivocarse: `get_db` ya no es un generador —no tiene teardown
    propio— y todo el que lo pida hereda el orden correcto sin escribir nada.

    **Cambia el manejo de errores, y es deliberado.** Si el commit falla, ahora
    la excepción sale antes de emitir la respuesta y el cliente recibe un 500.
    Antes recibía el `201` con el id de una fila que no existía, y la excepción
    se perdía en el log del servidor. Está cubierto por
    `tests/unit/test_commit_antes_de_la_respuesta.py`, que verifica el orden
    contra `http.response.start` (no con un `sleep`).
    """
    return session


def require_role(*allowed_roles: str):
    """Dependency factory que exige al menos uno de los roles."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if not user.roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los roles: {', '.join(allowed_roles)}",
            )
        return user

    return checker
