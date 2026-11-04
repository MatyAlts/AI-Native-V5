"""Inmutabilidad del estudio en la BASE (tarea 2.2, design D2).

SQL directo, sin pasar por endpoints: la referencia del paper tiene que estar
protegida aunque un endpoint futuro se equivoque. Cada caso prohibido espera
el error del trigger; cada caso permitido (el control) prueba que el trigger no
bloquea de más.

Todo corre dentro de la transacción de `db_session` (rollback al final). Cada
operación que debe fallar va en un SAVEPOINT para que la transacción siga viva.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

MARCA = "estudio_inmutable"

EVIDENCIA = {
    "episode_id": "gen_random_uuid()",
    "seq_tope": "seq_tope + 1",
    "chain_hash_tope": "repeat('b', 64)",
    "events_count_carga": "events_count_carga + 1",
    "last_chain_hash_carga": "repeat('c', 64)",
    "estado_carga": "'open'",
    "problema_id": "gen_random_uuid()",
    "ejercicio_id": "gen_random_uuid()",
}


async def _rechaza(session, sql: str, params: dict | None = None) -> None:
    with pytest.raises(DBAPIError, match=MARCA):
        async with session.begin_nested():
            await session.execute(text(sql), params or {})


async def _estudio(session, tenant_id):
    estudio_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO estudio_codificacion (id, tenant_id, clave, titulo, traza_version, "
            "created_by) VALUES (:id, :t, :c, 'Estudio', 'traza_v1', :u)"
        ),
        {"id": estudio_id, "t": tenant_id, "c": f"e-{estudio_id.hex[:8]}", "u": uuid4()},
    )
    return estudio_id


async def _version(session, tenant_id, estudio_id):
    version_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO codebook_version (id, tenant_id, estudio_id, etiqueta, estado, "
            "contenido_md, created_by) VALUES (:id, :t, :e, :et, 'borrador', '# v', :u)"
        ),
        {"id": version_id, "t": tenant_id, "e": estudio_id, "et": version_id.hex[:8], "u": uuid4()},
    )
    return version_id


async def _congelar(session, version_id) -> None:
    await session.execute(
        text(
            "UPDATE codebook_version SET estado = 'congelada', contenido_sha256 = repeat('f', 64), "
            "congelada_at = now(), congelada_por = gen_random_uuid() WHERE id = :v"
        ),
        {"v": version_id},
    )


_INSERT_ANCLA = (
    "INSERT INTO estudio_ancla (item_id, tenant_id, estudio_id, codebook_version_id, episode_id, "
    "seq_tope, chain_hash_tope, events_count_carga, last_chain_hash_carga, estado_carga, "
    "problema_id, ejercicio_id, uso, orden, respuesta_esperada) VALUES (:i, :t, :e, :v, "
    "gen_random_uuid(), 3, repeat('a', 64), 4, repeat('a', 64), 'closed', gen_random_uuid(), "
    "NULL, 'ejemplo', 1, '{}'::jsonb)"
)


async def _ancla(session, tenant_id, estudio_id, version_id):
    item_id = uuid4()
    await session.execute(
        text(_INSERT_ANCLA), {"i": item_id, "t": tenant_id, "e": estudio_id, "v": version_id}
    )
    return item_id


async def _item(session, tenant_id, estudio_id):
    item_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO estudio_muestra (item_id, tenant_id, estudio_id, episode_id, seq_tope, "
            "chain_hash_tope, events_count_carga, last_chain_hash_carga, estado_carga, "
            "problema_id, ejercicio_id) VALUES (:i, :t, :e, gen_random_uuid(), 7, repeat('a', 64), "
            "8, repeat('a', 64), 'closed', gen_random_uuid(), NULL)"
        ),
        {"i": item_id, "t": tenant_id, "e": estudio_id},
    )
    return item_id


async def _membresia(session, tenant_id, estudio_id):
    membresia_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO estudio_membresia (id, tenant_id, estudio_id, email, rol, alias, "
            "semilla, created_by) VALUES (:id, :t, :e, :email, 'codificador', 'C1', 1, :u)"
        ),
        {
            "id": membresia_id,
            "t": tenant_id,
            "e": estudio_id,
            "email": f"{membresia_id.hex[:6]}@ejemplo.org",
            "u": uuid4(),
        },
    )
    return membresia_id


async def _enunciado(session, tenant_id, estudio_id, *, revisado: bool):
    enunciado_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO estudio_enunciado (id, tenant_id, estudio_id, fuente, fuente_id, "
            "archivo_sha256, cargado_por, contenido_original_md, sha256_original, "
            "contenido_mostrado_md, sha256_mostrado, revisado_por, revisado_at) VALUES "
            "(:id, :t, :e, 'tp', gen_random_uuid(), repeat('d', 64), gen_random_uuid(), "
            "'Consigna', repeat('e', 64), "
            "CASE WHEN :rev THEN 'Consigna' END, CASE WHEN :rev THEN repeat('e', 64) END, "
            "CASE WHEN :rev THEN gen_random_uuid() END, CASE WHEN :rev THEN now() END)"
        ),
        {"id": enunciado_id, "t": tenant_id, "e": estudio_id, "rev": revisado},
    )
    return enunciado_id


# ── codebook_version ──────────────────────────────────────────────────────


async def test_borrador_se_edita_y_se_congela(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    version_id = await _version(session, tenant_id, estudio_id)
    await session.execute(
        text("UPDATE codebook_version SET contenido_md = '# otro' WHERE id = :v"),
        {"v": version_id},
    )
    await _congelar(session, version_id)
    estado = (
        await session.execute(
            text("SELECT estado FROM codebook_version WHERE id = :v"), {"v": version_id}
        )
    ).scalar_one()
    assert estado == "congelada"


async def test_version_congelada_rechaza_update_y_delete(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    version_id = await _version(session, tenant_id, estudio_id)
    await _congelar(session, version_id)
    await _rechaza(
        session,
        "UPDATE codebook_version SET contenido_md = '# otro' WHERE id = :v",
        {"v": version_id},
    )
    await _rechaza(
        session, "UPDATE codebook_version SET estado = 'borrador' WHERE id = :v", {"v": version_id}
    )
    await _rechaza(session, "DELETE FROM codebook_version WHERE id = :v", {"v": version_id})


# ── estudio_ancla ─────────────────────────────────────────────────────────


async def test_ancla_de_borrador_se_agrega_edita_y_borra(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    version_id = await _version(session, tenant_id, estudio_id)
    item_id = await _ancla(session, tenant_id, estudio_id, version_id)
    await session.execute(
        text("UPDATE estudio_ancla SET explicacion_md = 'porque' WHERE item_id = :i"),
        {"i": item_id},
    )
    await session.execute(text("DELETE FROM estudio_ancla WHERE item_id = :i"), {"i": item_id})
    n = (
        await session.execute(
            text("SELECT count(*) FROM estudio_ancla WHERE item_id = :i"), {"i": item_id}
        )
    ).scalar_one()
    assert n == 0


async def test_ancla_de_version_congelada_rechaza_insert_update_y_delete(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    version_id = await _version(session, tenant_id, estudio_id)
    item_id = await _ancla(session, tenant_id, estudio_id, version_id)
    await _congelar(session, version_id)
    await _rechaza(
        session, _INSERT_ANCLA, {"i": uuid4(), "t": tenant_id, "e": estudio_id, "v": version_id}
    )
    await _rechaza(
        session,
        "UPDATE estudio_ancla SET explicacion_md = 'otra' WHERE item_id = :i",
        {"i": item_id},
    )
    await _rechaza(session, "DELETE FROM estudio_ancla WHERE item_id = :i", {"i": item_id})


async def test_ancla_no_se_mueve_a_una_version_congelada(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    borrador = await _version(session, tenant_id, estudio_id)
    congelada = await _version(session, tenant_id, estudio_id)
    await _congelar(session, congelada)
    item_id = await _ancla(session, tenant_id, estudio_id, borrador)
    await _rechaza(
        session,
        "UPDATE estudio_ancla SET codebook_version_id = :v WHERE item_id = :i",
        {"v": congelada, "i": item_id},
    )


# ── historial y entrenamiento: append-only ────────────────────────────────


async def test_historial_de_etiquetas_es_append_only(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    membresia_id = await _membresia(session, tenant_id, estudio_id)
    item_id = await _item(session, tenant_id, estudio_id)
    version_id = await _version(session, tenant_id, estudio_id)
    etiqueta_id = (
        await session.execute(
            text(
                "INSERT INTO estudio_etiqueta (tenant_id, membresia_id, muestra_item_id, "
                "codebook_version_id, traza_version) VALUES (:t, :m, :i, :v, 'traza_v1') "
                "RETURNING id"
            ),
            {"t": tenant_id, "m": membresia_id, "i": item_id, "v": version_id},
        )
    ).scalar_one()
    historial_id = (
        await session.execute(
            text(
                "INSERT INTO estudio_etiqueta_historial (tenant_id, etiqueta_id, membresia_id, "
                "muestra_item_id, snapshot) VALUES (:t, :e, :m, :i, '{}'::jsonb) RETURNING id"
            ),
            {"t": tenant_id, "e": etiqueta_id, "m": membresia_id, "i": item_id},
        )
    ).scalar_one()
    await _rechaza(
        session,
        "UPDATE estudio_etiqueta_historial SET snapshot = '{\"x\": 1}'::jsonb WHERE id = :h",
        {"h": historial_id},
    )
    await _rechaza(
        session, "DELETE FROM estudio_etiqueta_historial WHERE id = :h", {"h": historial_id}
    )


async def test_respuestas_de_entrenamiento_son_append_only(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    membresia_id = await _membresia(session, tenant_id, estudio_id)
    version_id = await _version(session, tenant_id, estudio_id)
    ancla_id = await _ancla(session, tenant_id, estudio_id, version_id)
    respuesta_id = (
        await session.execute(
            text(
                "INSERT INTO entrenamiento_respuesta (tenant_id, membresia_id, ancla_id, "
                "codebook_version_id, traza_version) VALUES (:t, :m, :a, :v, 'traza_v1') "
                "RETURNING id"
            ),
            {"t": tenant_id, "m": membresia_id, "a": ancla_id, "v": version_id},
        )
    ).scalar_one()
    await _rechaza(
        session,
        "UPDATE entrenamiento_respuesta SET regimen = 'otro' WHERE id = :r",
        {"r": respuesta_id},
    )
    await _rechaza(
        session, "DELETE FROM entrenamiento_respuesta WHERE id = :r", {"r": respuesta_id}
    )


# ── evidencia fija ────────────────────────────────────────────────────────


@pytest.mark.parametrize("columna", sorted(EVIDENCIA))
async def test_evidencia_fija_de_la_muestra_no_se_actualiza(db_session, columna: str) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    item_id = await _item(session, tenant_id, estudio_id)
    await _rechaza(
        session,
        f"UPDATE estudio_muestra SET {columna} = {EVIDENCIA[columna]} WHERE item_id = :i",
        {"i": item_id},
    )


@pytest.mark.parametrize("columna", sorted(EVIDENCIA))
async def test_evidencia_fija_del_ancla_no_se_actualiza_ni_en_borrador(
    db_session, columna: str
) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    version_id = await _version(session, tenant_id, estudio_id)
    item_id = await _ancla(session, tenant_id, estudio_id, version_id)
    await _rechaza(
        session,
        f"UPDATE estudio_ancla SET {columna} = {EVIDENCIA[columna]} WHERE item_id = :i",
        {"i": item_id},
    )


async def test_muestra_sin_etiquetas_se_puede_reemplazar(db_session) -> None:
    """Design D6: el reemplazo de la muestra (sin etiquetas) borra e inserta.
    El trigger de evidencia fija no tiene que bloquear el DELETE."""
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    item_id = await _item(session, tenant_id, estudio_id)
    await session.execute(text("DELETE FROM estudio_muestra WHERE item_id = :i"), {"i": item_id})
    n = (
        await session.execute(
            text("SELECT count(*) FROM estudio_muestra WHERE item_id = :i"), {"i": item_id}
        )
    ).scalar_one()
    assert n == 0


# ── enunciados ────────────────────────────────────────────────────────────


async def test_enunciado_sin_revisar_admite_reemplazo_y_revision(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    enunciado_id = await _enunciado(session, tenant_id, estudio_id, revisado=False)
    await session.execute(
        text(
            "UPDATE estudio_enunciado SET contenido_original_md = 'Consigna corregida', "
            "sha256_original = repeat('9', 64) WHERE id = :e"
        ),
        {"e": enunciado_id},
    )
    await session.execute(
        text(
            "UPDATE estudio_enunciado SET contenido_mostrado_md = contenido_original_md, "
            "sha256_mostrado = sha256_original, revisado_por = gen_random_uuid(), "
            "revisado_at = now() WHERE id = :e"
        ),
        {"e": enunciado_id},
    )
    revisado = (
        await session.execute(
            text("SELECT revisado_at IS NOT NULL FROM estudio_enunciado WHERE id = :e"),
            {"e": enunciado_id},
        )
    ).scalar_one()
    assert revisado is True


async def test_enunciado_revisado_rechaza_update_y_delete(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    enunciado_id = await _enunciado(session, tenant_id, estudio_id, revisado=True)
    await _rechaza(
        session,
        "UPDATE estudio_enunciado SET contenido_mostrado_md = 'otra' WHERE id = :e",
        {"e": enunciado_id},
    )
    await _rechaza(
        session,
        "UPDATE estudio_enunciado SET contenido_original_md = 'otra' WHERE id = :e",
        {"e": enunciado_id},
    )
    await _rechaza(
        session,
        "UPDATE estudio_enunciado SET revisado_at = NULL WHERE id = :e",
        {"e": enunciado_id},
    )
    await _rechaza(session, "DELETE FROM estudio_enunciado WHERE id = :e", {"e": enunciado_id})


# ── TRUNCATE (verify-1, F5) ───────────────────────────────────────────────
# Los triggers de fila no se disparan con TRUNCATE y RLS no lo filtra: sin un
# trigger de sentencia, el dueño de las tablas vaciaba el historial de TODOS los
# tenants. Cada tabla que D2 declara inmutable tiene su `BEFORE TRUNCATE`.
# Se trunca con CASCADE (si no, una FK entrante lo rechaza antes que el trigger)
# y se exige el nombre de LA tabla pedida en el mensaje: Postgres dispara primero
# los triggers de las tablas nombradas, así que una tabla sin trigger propio
# fallaría con el nombre de otra tabla de la cascada y el test lo detecta.

TABLAS_INMUTABLES = (
    "codebook_version",
    "estudio_ancla",
    "estudio_etiqueta_historial",
    "entrenamiento_respuesta",
    "estudio_muestra",
    "estudio_enunciado",
)


@pytest.mark.parametrize("tabla", TABLAS_INMUTABLES)
async def test_truncate_de_tabla_inmutable_se_rechaza(db_session, tabla: str) -> None:
    session, _ = db_session
    with pytest.raises(DBAPIError, match=f"{MARCA}: TRUNCATE de {tabla} rechazado"):
        async with session.begin_nested():
            await session.execute(text(f"TRUNCATE {tabla} CASCADE"))


async def test_truncate_en_cascada_desde_el_estudio_se_rechaza(db_session) -> None:
    session, _ = db_session
    await _rechaza(session, "TRUNCATE estudio_codificacion CASCADE")


async def test_truncate_no_borra_el_historial(db_session) -> None:
    session, tenant_id = db_session
    estudio_id = await _estudio(session, tenant_id)
    membresia_id = await _membresia(session, tenant_id, estudio_id)
    item_id = await _item(session, tenant_id, estudio_id)
    version_id = await _version(session, tenant_id, estudio_id)
    etiqueta_id = (
        await session.execute(
            text(
                "INSERT INTO estudio_etiqueta (tenant_id, membresia_id, muestra_item_id, "
                "codebook_version_id, traza_version) VALUES (:t, :m, :i, :v, 'traza_v1') "
                "RETURNING id"
            ),
            {"t": tenant_id, "m": membresia_id, "i": item_id, "v": version_id},
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO estudio_etiqueta_historial (tenant_id, etiqueta_id, membresia_id, "
            "muestra_item_id, snapshot) VALUES (:t, :e, :m, :i, '{}'::jsonb)"
        ),
        {"t": tenant_id, "e": etiqueta_id, "m": membresia_id, "i": item_id},
    )
    await _rechaza(session, "TRUNCATE estudio_etiqueta_historial")
    n = (
        await session.execute(
            text("SELECT count(*) FROM estudio_etiqueta_historial WHERE etiqueta_id = :e"),
            {"e": etiqueta_id},
        )
    ).scalar_one()
    assert n == 1
