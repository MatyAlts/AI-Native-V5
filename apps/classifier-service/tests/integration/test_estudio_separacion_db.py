"""Separación del estudio respecto de las etiquetas oficiales y del piloto
(tarea 8.4, design D1, spec estudio-codificacion "Separación...").

Se siembran filas del piloto (`classifications`, `classification_reviews`,
`interrater_ratings`) bajo el tenant del estudio, se fotografían junto con las
respuestas de los endpoints del piloto, se corre el flujo completo del estudio
(muestra, enunciados, codebook, etiquetas de dos codificadores, cierre,
exportaciones) y se vuelve a fotografiar: nada puede cambiar.
"""

from __future__ import annotations

from uuid import uuid4

TABLAS_PILOTO = ("classifications", "classification_reviews", "interrater_ratings")


async def _foto(e) -> dict[str, list[str]]:
    return {
        t: [
            f["fila"]
            for f in await e.sql(f"SELECT row_to_json(x)::text AS fila FROM {t} x ORDER BY id")
        ]
        for t in TABLAS_PILOTO
    }


async def test_flujo_completo_no_toca_tablas_ni_endpoints_del_piloto(
    estudio_http, etiqueta_reflexiva
) -> None:
    e = estudio_http
    comision, materia = uuid4(), uuid4()
    episodios = [e.ctr.agregar() for _ in range(2)]
    for i, ep in enumerate(episodios):
        await e.sql(
            "INSERT INTO classifications (tenant_id, episode_id, comision_id, classifier_config_hash, "
            "appropriation, appropriation_reason, features, is_current) VALUES (:t, :ep, :c, :h, "
            "'apropiacion_reflexiva', 'maquina', CAST(:f AS jsonb), true)",
            {
                "t": e.tenant_id,
                "ep": ep,
                "c": comision,
                "h": f"hash-{i}",
                "f": '{"subgrupo": {"key": "colaborador_reflexivo"}}',
            },
            commit=True,
        )
    await e.sql(
        "INSERT INTO classification_reviews (tenant_id, episode_id, reviewer_id, reviewer_role, "
        "previous_classification_id, verdict, reason) SELECT :t, episode_id, gen_random_uuid(), 'docente', id, "
        "'apropiacion_superficial', 'revision' FROM classifications ORDER BY id LIMIT 1",
        {"t": e.tenant_id},
        commit=True,
    )
    docente = {
        "X-User-Id": str(uuid4()),
        "X-Tenant-Id": str(e.tenant_id),
        "X-User-Email": "docente@utn.test",
        "X-User-Roles": "docente",
    }
    rating = {
        "episode_id": str(episodios[0]),
        "comision_id": str(comision),
        "materia_id": str(materia),
        "label": "apropiacion_reflexiva",
    }
    assert (
        await e.client.post("/api/v1/interrater/ratings", json=rating, headers=docente)
    ).status_code == 204

    async def piloto() -> tuple:
        sample = await e.client.get(
            f"/api/v1/interrater/sample?comision_id={comision}", headers=docente
        )
        progreso = await e.client.get(
            f"/api/v1/interrater/my-progress?materia_id={materia}", headers=docente
        )
        rating_r = await e.client.post("/api/v1/interrater/ratings", json=rating, headers=docente)
        return (
            (sample.status_code, sample.json()),
            (progreso.status_code, progreso.json()),
            rating_r.status_code,
        )

    antes_endpoints = await piloto()
    antes = await _foto(e)
    assert len(antes["classifications"]) == 2 and len(antes["interrater_ratings"]) == 1

    # Flujo completo del estudio sobre los MISMOS episodios.
    assert (await e.cargar_muestra(episodios)).status_code == 200
    assert (await e.cargar_enunciados(e.requeridos(episodios))).status_code == 200
    await e.revisar_todos()
    await e.codebook()
    for persona in (e.c1, e.c2):
        for item in await e.items(persona):
            r = await e.pedir(
                "PUT", f"/items/{item['item_id']}/mi-etiqueta", persona, json=etiqueta_reflexiva
            )
            assert r.status_code == 200, r.text
        assert (await e.pedir("POST", "/mi-codificacion/cerrar", persona)).status_code == 200
    for contenido in ("etiquetas", "entrenamiento", "historial"):
        for formato in ("csv", "json"):
            r = await e.pedir(
                "GET",
                "/exportacion",
                e.investigador,
                params={"contenido": contenido, "formato": formato},
            )
            assert r.status_code == 200, r.text
    assert len(await e.sql("SELECT id FROM estudio_etiqueta")) == 4

    assert await _foto(e) == antes
    assert await piloto() == antes_endpoints
