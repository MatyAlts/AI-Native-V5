"""`init_seq_counter` no puede BAJAR el contador de seq.

El heal de sesion que este PR agrega convirtio a `init_seq_counter` de dos
callers explicitos —abrir el episodio y un `POST /resume` del usuario— a OCHO
callers implicitos y concurrentes: los siete `emit_*` mas `send_message`, todos
via `_emitir_con_heal`. Ninguno garantiza nada, y el chequeo
`existing is not None` de `resume_episode` es un check-then-act con dos `await`
de red en el medio.

Con un SET incondicional eso produce la carrera que sigue, con la sesion vencida
por TTL y `events_count = N`:

    A: POST /message          -> get()=None -> arranca resume
    B: POST /edicion_codigo   -> get()=None -> arranca resume
    B: set(state); init(N)                      [contador = N]
    B: next_seq -> INCR -> N+1 -> publica seq=N
    A: set(state); init(N)          <- REGRESION del contador a N
    A: next_seq -> INCR -> N+1 -> publica seq=N   <- DUPLICADO

Dos eventos distintos con el mismo seq. El worker persiste uno; el otro no
matchea `expected_seq`, va a la DLQ y marca el episodio `integrity_compromised`
— o sea, el bug que este PR viene a cerrar, reintroducido por su propio heal.

Y no es un borde: el frontend emite `edicion_codigo` con debounce mientras el
alumno charla con el tutor, asi que dos requests concurrentes sobre el mismo
episodio son la norma.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest_asyncio
from tutor_service.services.session import SessionManager


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[SessionManager]:
    r = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield SessionManager(r)
    await r.aclose()


async def test_no_pisa_hacia_abajo_un_contador_ya_avanzado(sessions: SessionManager) -> None:
    """El corazon del fix: la reserva concurrente gana.

    Verificado por reversion: con el `SET` incondicional de antes, el contador
    vuelve a 5, el proximo `INCR` devuelve 6 y `next_seq` entrega 5 — un seq YA
    USADO por el evento que reservo en el medio.
    """
    ep = uuid.uuid4()
    await sessions.init_seq_counter(ep, 5)

    # Alguien reserva mientras el otro resume esta en vuelo.
    await sessions.redis.incr(sessions._seq_key(ep))  # contador = 6

    # El resume que llega tarde pide inicializar en 5 otra vez.
    await sessions.init_seq_counter(ep, 5)

    valor = int(await sessions.redis.get(sessions._seq_key(ep)))
    assert valor == 6, f"el contador se pisó hacia abajo: quedó en {valor}, no en 6"


async def test_dos_resume_concurrentes_no_producen_el_mismo_seq(
    sessions: SessionManager,
) -> None:
    """La carrera del docstring del modulo, entera y en orden.

    Es la asercion que importa: los dos seq entregados tienen que ser DISTINTOS.
    """
    ep = uuid.uuid4()
    N = 5

    # B llega primero, inicializa y reserva.
    await sessions.init_seq_counter(ep, N)
    seq_b = int(await sessions.redis.incr(sessions._seq_key(ep))) - 1

    # A viene atras y re-inicializa con el MISMO events_count que leyo antes.
    await sessions.init_seq_counter(ep, N)
    seq_a = int(await sessions.redis.incr(sessions._seq_key(ep))) - 1

    assert seq_b == N
    assert seq_a != seq_b, f"dos eventos nacieron con el mismo seq ({seq_a})"
    assert seq_a == N + 1, "la secuencia tiene que quedar contigua"


async def test_si_el_contador_esta_AUSENTE_lo_inicializa(sessions: SessionManager) -> None:
    """El caso normal no puede romperse: sin key, el resume tiene que sembrarla.

    Sin esto, `INCR` sobre una key ausente arranca en 0 y entrega `seq=0` sobre
    un episodio con historia — el rechazo permanente que
    `test_contador_perdido_arranca_en_cero_y_la_cadena_lo_rechaza` caracteriza.
    """
    ep = uuid.uuid4()
    await sessions.init_seq_counter(ep, 42)

    assert int(await sessions.redis.get(sessions._seq_key(ep))) == 42


async def test_si_el_contador_esta_ATRASADO_lo_adelanta(sessions: SessionManager) -> None:
    """Un contador por DEBAJO del `events_count` si se corrige.

    Es lo que hace el heal util: la cadena avanzo y el contador quedo atras.
    """
    ep = uuid.uuid4()
    await sessions.init_seq_counter(ep, 2)
    await sessions.init_seq_counter(ep, 9)

    assert int(await sessions.redis.get(sessions._seq_key(ep))) == 9


async def test_refresca_el_TTL_aunque_no_escriba(sessions: SessionManager) -> None:
    """La sesion que acaba de reanudarse necesita que el contador la acompañe.

    Si el CAS decide no escribir, el TTL igual se renueva: dejarlo vencer
    antes que la sesion devuelve el contador a cero y la cadena lo rechaza.
    """
    ep = uuid.uuid4()
    await sessions.init_seq_counter(ep, 5)
    await sessions.redis.incr(sessions._seq_key(ep))
    await sessions.redis.expire(sessions._seq_key(ep), 10)

    await sessions.init_seq_counter(ep, 5)

    assert int(await sessions.redis.ttl(sessions._seq_key(ep))) > 10
