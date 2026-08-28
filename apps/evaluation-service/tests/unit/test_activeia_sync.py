"""Tests del sincronizador de rubricas (tareas 2.11 y 2.12).

Lo que mas importa que este bien: **que una rubrica desactualizada se detecte**.
Una rubrica equivocada no da una nota floja, corrige otra cosa — un TP de
listas corregido con la rubrica de condicionales produce un numero plausible y
sin sentido, y ese numero termina en el legajo de una persona.

Y que el simulador sea imposible de confundir con lo real: si el mock deja de
marcar lo que devuelve, la UI diria "sincronizado" sobre rubricas que no
existen del otro lado.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from evaluation_service.models.activeia import ActiveIARubricaEjercicio
from evaluation_service.services.activeia_client import (
    ActiveIAClient,
    ActiveIAClientMock,
    ActiveIAError,
)
from evaluation_service.services.activeia_sync import (
    EstadoEjercicio,
    EstadoSync,
    _payload_ejercicio,
    _payload_tp,
    _test_cases_para_activeia,
    estado_de_sincronizacion,
    hash_de_lo_enviado,
    rubrica_hash,
    sincronizar_tp,
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EJ1 = UUID("11111111-1111-1111-1111-111111111111")
# LA FORMA REAL DEL BANCO, verificada contra Postgres el 2026-08-18: las 54
# rubricas cargadas son objetos `{"criterios": [...]}`, ninguna es una lista.
# El fixture anterior era una lista con la clave `criterio` — una forma que no
# existe ni en la base ni en el contrato pedido, y con ella un bug de doble
# anidado producia accidentalmente lo correcto. Tres revisiones seguidas
# encontraron bugs por fixtures que no coincidian con el dato real.
RUBRICA = {
    "criterios": [
        {
            "nombre": "Output exacto",
            "descripcion": "Imprime el literal sin variaciones",
            "puntaje_max": 1.0,
        }
    ]
}

# Los tres tipos que hay en el banco. En los de assert `code` es una ASERCION
# y `expected` es null.
TC_STDIN = {
    "id": "t1",
    "name": "caso publico",
    "type": "stdin_stdout",
    "code": "5\n3",
    "expected": "8",
    "is_public": True,
}
TC_OCULTO = {
    "id": "t2",
    "name": "caso oculto",
    "type": "stdin_stdout",
    "code": "0\n0",
    "expected": "0",
    "is_public": False,
}
TC_ASSERT = {
    "id": "t3",
    "name": "suma positivos",
    "type": "pytest_assert",
    "code": "assert suma(2, 3) == 5",
    "expected": None,
    "is_public": True,
}


def _fila_ejercicio(ej_id: UUID = EJ1, rubrica: object = RUBRICA) -> tuple:
    return (ej_id, "Ejercicio 1", "Enunciado", rubrica, [TC_STDIN], 0.5, 1)


def _res_ejercicios(filas: list[tuple]) -> MagicMock:
    return MagicMock(all=MagicMock(return_value=filas))


def _res_vinculos(vinculos: list[ActiveIARubricaEjercicio]) -> MagicMock:
    return MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=vinculos)))
    )


TP_ID = UUID("33333333-3333-3333-3333-333333333333")
MATERIA_ID = UUID("44444444-4444-4444-4444-444444444444")


def _res_tp() -> MagicMock:
    """Determinista: el hash cubre el header del TP, asi que un uuid al azar
    haria que dos llamadas dieran hashes distintos."""
    return MagicMock(first=MagicMock(return_value=(TP_ID, "TP 2", MATERIA_ID)))


def _tp_dict() -> dict:
    return {"id": TP_ID, "titulo": "TP 2", "materia_id": MATERIA_ID}


def _ej_dict(fila: tuple) -> dict:
    """La fila tal como la arma `_ejercicios_de_tp`."""
    return {
        "ejercicio_id": fila[0],
        "titulo": fila[1],
        "enunciado_md": fila[2],
        "rubrica": fila[3],
        "test_cases": fila[4],
        "peso_en_tp": fila[5],
        "orden": fila[6],
    }


def _db(filas: list[tuple], vinculos: list[ActiveIARubricaEjercicio]) -> MagicMock:
    """Sesion para `estado_de_sincronizacion`: ejercicios y vinculos."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=[_res_tp(), _res_ejercicios(filas), _res_vinculos(vinculos)])
    return db


def _vinculo(rubrica_id: str, hash_guardado: str | None) -> ActiveIARubricaEjercicio:
    v = ActiveIARubricaEjercicio(
        tenant_id=TENANT, ejercicio_id=EJ1, rubrica_id=rubrica_id, external_ref=str(EJ1)
    )
    v.rubrica_hash = hash_guardado
    v.sincronizado_at = None
    return v


class TestHashCanonico:
    def test_el_orden_de_las_claves_no_cambia_el_hash(self) -> None:
        a = rubrica_hash([{"criterio": "x", "puntaje_max": 10}])
        b = rubrica_hash([{"puntaje_max": 10, "criterio": "x"}])
        assert a == b

    def test_las_tildes_no_rompen_el_hash(self) -> None:
        """`ensure_ascii=False` no es cosmetico: sin eso el hash depende de si
        la rubrica tiene tildes, y las nuestras estan en castellano."""
        h = rubrica_hash([{"criterio": "Usa condición y ñandú"}])
        assert len(h) == 64

    def test_un_cambio_en_el_contenido_cambia_el_hash(self) -> None:
        assert rubrica_hash([{"c": 1}]) != rubrica_hash([{"c": 2}])


class TestDeteccionDeDesactualizado:
    async def test_rubrica_editada_despues_de_sincronizar_da_desactualizado(self) -> None:
        """El caso que justifica toda la tarea 2.12."""
        vinculo = _vinculo("42", rubrica_hash([{"criterio": "LA VIEJA"}]))
        db = _db([_fila_ejercicio()], [vinculo])

        estados = await estado_de_sincronizacion(db, TENANT, uuid4())
        assert estados[0].estado is EstadoSync.DESACTUALIZADO

    async def test_rubrica_sin_tocar_da_sincronizado(self) -> None:
        ej = _fila_ejercicio()
        vinculo = _vinculo("42", hash_de_lo_enviado(_ej_dict(ej), _tp_dict()))
        db = _db([ej], [vinculo])

        estados = await estado_de_sincronizacion(db, TENANT, uuid4())
        assert estados[0].estado is EstadoSync.SINCRONIZADO

    async def test_sin_vinculo_da_sin_sincronizar(self) -> None:
        db = _db([_fila_ejercicio()], [])
        estados = await estado_de_sincronizacion(db, TENANT, uuid4())
        assert estados[0].estado is EstadoSync.SIN_SINCRONIZAR

    async def test_ejercicio_sin_rubrica_no_se_reporta_como_fallo_de_sync(self) -> None:
        """ "Sin rubrica" y "sin sincronizar" son cosas distintas: en el primero
        no hay nada contra que corregir, y mezclarlos manda al docente a buscar
        el problema donde no esta."""
        db = _db([_fila_ejercicio(rubrica=None)], [])
        estados = await estado_de_sincronizacion(db, TENANT, uuid4())
        assert estados[0].estado is EstadoSync.SIN_RUBRICA

    async def test_una_rubrica_simulada_se_marca(self) -> None:
        vinculo = _vinculo(
            f"MOCK-{EJ1}", hash_de_lo_enviado(_ej_dict(_fila_ejercicio()), _tp_dict())
        )
        db = _db([_fila_ejercicio()], [vinculo])

        estados = await estado_de_sincronizacion(db, TENANT, uuid4())
        assert estados[0].simulado is True


class TestElSimuladorEsDistinguible:
    async def test_lo_que_devuelve_va_marcado(self) -> None:
        cli = ActiveIAClientMock("https://x", "u", "p", 1.0)
        resp = await cli.crear_o_actualizar_tp(external_ref=str(EJ1), payload={"ejercicios": []})
        assert resp["simulado"] is True
        assert resp["id"].startswith("MOCK-"), "un id sin prefijo pasaria por real"

    async def test_el_rubrica_id_POR_EJERCICIO_lleva_el_prefijo(self) -> None:
        """El mock devuelve DOS identificadores, y el que se persiste en
        `vinculo.rubrica_id` —el unico que alimenta la deteccion de
        `simulado`— es el de cada ejercicio, no el del TP. Sin el prefijo, la
        UI diria "Sincronizado" en verde sobre rubricas que no existen."""
        cli = ActiveIAClientMock("https://x", "u", "p", 1.0)
        resp = await cli.crear_o_actualizar_tp(
            external_ref="tp-1", payload={"ejercicios": [{"external_ref": str(EJ1)}]}
        )
        assert resp["ejercicios"][0]["rubrica_id"].startswith("MOCK-")
        assert resp["ejercicios"][0]["external_ref"] == str(EJ1)

    async def test_no_hace_ninguna_request(self) -> None:
        """Si el mock llamara a la API de verdad, dejaria de ser un mock."""
        cli = ActiveIAClientMock("https://x", "u", "p", 1.0)
        with patch.object(ActiveIAClient, "request", AsyncMock()) as fake:
            await cli.crear_o_actualizar_tp(external_ref="x", payload={"ejercicios": []})
            await cli.obtener_rubrica("42")
        fake.assert_not_awaited()

    async def test_loguea_cada_llamada_en_warning(self) -> None:
        """Un mock silencioso en produccion es indistinguible de una
        integracion que anda."""
        cli = ActiveIAClientMock("https://x", "u", "p", 1.0)
        with patch("evaluation_service.services.activeia_client.log") as fake_log:
            await cli.crear_o_actualizar_tp(external_ref="x", payload={"ejercicios": []})
        fake_log.warning.assert_called_once()


class TestSincronizar:
    async def test_apagado_el_flag_no_sincroniza(self) -> None:
        with patch("evaluation_service.services.activeia_sync.settings") as st:
            st.activeia_sync_rubricas_enabled = False
            with pytest.raises(ActiveIAError):
                await sincronizar_tp(MagicMock(), MagicMock(), TENANT, uuid4())

    async def test_pega_a_la_url_del_contrato(self) -> None:
        """El path es parte del contrato. Sin esto, volver al
        `/rubricas/external/{ref}` de la version anterior —que es EL hallazgo
        que esta ronda vino a cerrar— pasaria desapercibido."""
        cli = ActiveIAClient("https://x", "u", "p", 1.0)
        cli._token = "t"
        with patch.object(
            ActiveIAClient, "request", AsyncMock(return_value=MagicMock(status_code=200))
        ) as fake:
            fake.return_value.json = MagicMock(return_value={})
            await cli.crear_o_actualizar_tp(external_ref="abc", payload={})
        metodo, path = fake.await_args.args
        assert metodo == "PUT"
        assert path == "/trabajos-practicos/by-ref/abc"

    async def test_empuja_UN_solo_tp_con_los_ejercicios_anidados(self) -> None:
        """El contrato pide el TP entero, no N rubricas sueltas: sin el TP que
        los agrupe, los ejercicios quedan huerfanos del otro lado."""
        ej2 = uuid4()
        filas = [_fila_ejercicio(), (ej2, "Ejercicio 2", "E", RUBRICA, [], 0.5, 2)]
        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _res_tp(),
                _res_ejercicios(filas),
                _res_vinculos([]),
                _res_tp(),
                _res_ejercicios(filas),
                _res_vinculos([]),
            ]
        )
        cliente = MagicMock()
        cliente.crear_o_actualizar_tp = AsyncMock(
            return_value={
                "id": "TP-1",
                "ejercicios": [
                    {"external_ref": str(EJ1), "rubrica_id": "r1"},
                    {"external_ref": str(ej2), "rubrica_id": "r2"},
                ],
            }
        )

        with patch("evaluation_service.services.activeia_sync.settings") as st:
            st.activeia_sync_rubricas_enabled = True
            await sincronizar_tp(db, cliente, TENANT, uuid4())

        assert cliente.crear_o_actualizar_tp.await_count == 1, "mando mas de un request"
        payload = cliente.crear_o_actualizar_tp.await_args.kwargs["payload"]
        assert len(payload["ejercicios"]) == 2
        assert payload["materia_external_ref"]

    async def test_un_ejercicio_sin_id_en_la_respuesta_no_se_marca_sincronizado(self) -> None:
        """Sin `rubrica_id` no se puede corregir ese ejercicio, y marcarlo
        sincronizado seria mentir."""
        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _res_tp(),
                _res_ejercicios([_fila_ejercicio()]),
                _res_vinculos([]),
                _res_tp(),
                _res_ejercicios([_fila_ejercicio()]),
                _res_vinculos([]),
            ]
        )
        cliente = MagicMock()
        cliente.crear_o_actualizar_tp = AsyncMock(return_value={"id": "TP-1", "ejercicios": []})

        with patch("evaluation_service.services.activeia_sync.settings") as st:
            st.activeia_sync_rubricas_enabled = True
            estados = await sincronizar_tp(db, cliente, TENANT, uuid4())

        db.add.assert_not_called()
        assert estados[0].estado is EstadoSync.SIN_SINCRONIZAR

    async def test_empareja_por_external_ref_y_no_por_orden(self) -> None:
        """Emparejar por orden seria adivinar: si Active-IA devuelve los
        ejercicios en otro orden, cada uno quedaria con la rubrica del otro."""
        ej2 = uuid4()
        filas = [_fila_ejercicio(), (ej2, "Ejercicio 2", "E", RUBRICA, [], 0.5, 2)]
        guardados: list = []
        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock(side_effect=guardados.append)
        db.execute = AsyncMock(
            side_effect=[
                _res_tp(),
                _res_ejercicios(filas),
                _res_vinculos([]),
                _res_tp(),
                _res_ejercicios(filas),
                _res_vinculos([]),
            ]
        )
        cliente = MagicMock()
        # A PROPOSITO al reves del orden local.
        cliente.crear_o_actualizar_tp = AsyncMock(
            return_value={
                "ejercicios": [
                    {"external_ref": str(ej2), "rubrica_id": "LA-DEL-2"},
                    {"external_ref": str(EJ1), "rubrica_id": "LA-DEL-1"},
                ]
            }
        )

        with patch("evaluation_service.services.activeia_sync.settings") as st:
            st.activeia_sync_rubricas_enabled = True
            await sincronizar_tp(db, cliente, TENANT, uuid4())

        por_ej = {v.ejercicio_id: v.rubrica_id for v in guardados}
        assert por_ej[EJ1] == "LA-DEL-1"
        assert por_ej[ej2] == "LA-DEL-2"

    async def test_no_manda_ejercicios_sin_rubrica(self) -> None:
        """Una rubrica vacia del otro lado corregiria contra nada y devolveria
        un numero igual."""
        filas = [_fila_ejercicio(), (uuid4(), "Sin rubrica", "E", None, [], 0.5, 2)]
        db = MagicMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _res_tp(),
                _res_ejercicios(filas),
                _res_vinculos([]),
                _res_tp(),
                _res_ejercicios(filas),
                _res_vinculos([]),
            ]
        )
        cliente = MagicMock()
        cliente.crear_o_actualizar_tp = AsyncMock(return_value={"ejercicios": []})

        with patch("evaluation_service.services.activeia_sync.settings") as st:
            st.activeia_sync_rubricas_enabled = True
            await sincronizar_tp(db, cliente, TENANT, uuid4())

        payload = cliente.crear_o_actualizar_tp.await_args.kwargs["payload"]
        assert len(payload["ejercicios"]) == 1

    async def test_ningun_ejercicio_con_rubrica_no_contacta_a_activeia(self) -> None:
        filas = [_fila_ejercicio(rubrica=None)]
        db = MagicMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(side_effect=[_res_tp(), _res_ejercicios(filas), _res_vinculos([])])
        cliente = MagicMock()
        cliente.crear_o_actualizar_tp = AsyncMock()

        with patch("evaluation_service.services.activeia_sync.settings") as st:
            st.activeia_sync_rubricas_enabled = True
            with pytest.raises(ActiveIAError):
                await sincronizar_tp(db, cliente, TENANT, uuid4())
        cliente.crear_o_actualizar_tp.assert_not_awaited()


class TestPayload:
    def test_lleva_enunciado_y_test_cases_ademas_de_la_rubrica(self) -> None:
        """Sin la consigna, el motor evalua los criterios contra un codigo que
        no sabe que tenia que hacer."""
        p = _payload_ejercicio(
            {
                "ejercicio_id": EJ1,
                "orden": 1,
                "titulo": "T",
                "enunciado_md": "consigna",
                "rubrica": RUBRICA,
                "test_cases": [TC_STDIN],
                "peso_en_tp": 0.5,
            }
        )
        assert p["enunciado_md"] == "consigna"
        assert p["test_cases"]
        assert p["rubrica"] == RUBRICA
        assert p["external_ref"] == str(EJ1)
        # `peso`, no `peso_en_tp`: asi lo pide el contrato.
        assert p["peso"] == 0.5

    def test_el_tp_va_con_los_ejercicios_anidados(self) -> None:
        tp = {"id": uuid4(), "titulo": "TP 2", "materia_id": uuid4()}
        ejs = [
            {
                "ejercicio_id": EJ1,
                "orden": 1,
                "titulo": "T",
                "enunciado_md": "c",
                "rubrica": RUBRICA,
                "test_cases": [],
                "peso_en_tp": 1.0,
            }
        ]
        p = _payload_tp(tp, ejs)
        assert p["external_ref"] == str(tp["id"])
        assert p["materia_external_ref"] == str(tp["materia_id"])
        assert len(p["ejercicios"]) == 1


class TestTestCases:
    def test_traduce_las_claves_al_vocabulario_pedido(self) -> None:
        """Si mandamos `is_public`, el otro lado lo lee como ausente y trata
        un caso OCULTO como publico."""
        out = _test_cases_para_activeia([TC_STDIN])
        assert out[0]["nombre"] == "caso publico"
        assert out[0]["entrada"] == "5\n3"
        assert out[0]["salida_esperada"] == "8"
        assert out[0]["es_publico"] is True

    def test_el_tipo_viaja(self) -> None:
        """Sin `tipo`, del otro lado no hay forma de detectar que un caso de
        assert esta mal formado."""
        assert _test_cases_para_activeia([TC_ASSERT])[0]["tipo"] == "pytest_assert"
        assert _test_cases_para_activeia([TC_STDIN])[0]["tipo"] == "stdin_stdout"

    def test_un_assert_no_se_manda_como_entrada(self) -> None:
        """`assert suma(2,3)==5` en el campo `entrada` con salida vacia hacia
        que el motor evaluara "el programa funciona" contra eso, y produjera
        un numero plausible y sin sentido."""
        out = _test_cases_para_activeia([TC_ASSERT])[0]
        assert "entrada" not in out
        assert out["asercion"] == "assert suma(2, 3) == 5"

    def test_a_un_caso_oculto_no_se_le_manda_la_salida_esperada(self) -> None:
        """El motor sigue sabiendo que existe y como se llama —que es lo que
        aporta al enunciado— pero no puede citar en el PDF del alumno lo que
        nunca recibio. Depender de que un tercero respete un parrafo es mas
        debil: de este motor ya esta medido que no honra las reglas declaradas
        en su propia rubrica."""
        out = _test_cases_para_activeia([TC_OCULTO])[0]
        assert out["es_publico"] is False
        assert out["nombre"] == "caso oculto"
        assert "salida_esperada" not in out, "la salida esperada de un caso oculto salio"
        # La ENTRADA tampoco (2026-08-20). El documento de integracion declara
        # que de un caso oculto mandamos "el id, el nombre y el tipo": mandar
        # ademas la entrada era mas de lo dicho, y del lado inseguro. Con la
        # entrada a la vista en el PDF —"probamos con 3 estudiantes y cupo 2"—
        # la regla que el caso codifica queda dicha para toda la cohorte.
        assert "entrada" not in out, "la entrada de un caso oculto salio"
        # Lo que si viaja, para que el motor sepa que el caso existe:
        assert out["id"] and out["nombre"] and out["tipo"]

    def test_un_assert_oculto_tampoco_manda_la_asercion(self) -> None:
        oculto_assert = {**TC_ASSERT, "is_public": False}
        out = _test_cases_para_activeia([oculto_assert])[0]
        assert "asercion" not in out

    def test_un_caso_oculto_nunca_se_vuelve_publico(self) -> None:
        """El `is not False` y no un `or True`."""
        assert _test_cases_para_activeia([{"is_public": False}])[0]["es_publico"] is False

    def test_sin_la_clave_se_considera_publico(self) -> None:
        assert _test_cases_para_activeia([{"id": "t"}])[0]["es_publico"] is True

    def test_tolera_basura(self) -> None:
        assert _test_cases_para_activeia(None) == []
        assert _test_cases_para_activeia(["no soy un dict"]) == []


class TestHashCubreTodoLoEnviado:
    def _ej(self, **over) -> dict:
        base = {
            "ejercicio_id": EJ1,
            "orden": 1,
            "titulo": "T",
            "enunciado_md": "consigna",
            "rubrica": RUBRICA,
            "test_cases": [],
            "peso_en_tp": 0.5,
        }
        base.update(over)
        return base

    def test_cambiar_el_enunciado_cambia_el_hash(self) -> None:
        """El bug que esto cierra: el hash cubria solo la rubrica, asi que
        editar la consigna dejaba el ejercicio en verde "Sincronizado" para
        siempre mientras Active-IA seguia con el enunciado viejo."""
        assert hash_de_lo_enviado(self._ej()) != hash_de_lo_enviado(
            self._ej(enunciado_md="OTRA consigna")
        )

    def test_agregar_un_test_case_cambia_el_hash(self) -> None:
        assert hash_de_lo_enviado(self._ej()) != hash_de_lo_enviado(
            self._ej(test_cases=[{"id": "t9", "name": "nuevo"}])
        )

    def test_cambiar_el_peso_cambia_el_hash(self) -> None:
        assert hash_de_lo_enviado(self._ej()) != hash_de_lo_enviado(self._ej(peso_en_tp=0.9))

    def test_cambiar_la_rubrica_cambia_el_hash(self) -> None:
        assert hash_de_lo_enviado(self._ej()) != hash_de_lo_enviado(
            self._ej(rubrica=[{"criterio": "otro"}])
        )

    def test_no_cambia_si_no_cambio_nada(self) -> None:
        assert hash_de_lo_enviado(self._ej()) == hash_de_lo_enviado(self._ej())


class TestModoSimulado:
    def test_mira_el_dato_y_no_solo_el_flag(self) -> None:
        """Un vinculo `MOCK-` persiste a que se apague el simulador. Mirando
        solo el flag, apagarlo hacia desaparecer el banner grande y dejaba
        solo el "(simulada)" chiquito de la columna — sobre rubricas que
        siguen sin existir del otro lado."""
        from evaluation_service.routes.activeia import _hay_simulacion

        simulado = EstadoEjercicio(
            ejercicio_id=EJ1, titulo="T", estado=EstadoSync.SINCRONIZADO, simulado=True
        )
        real = EstadoEjercicio(
            ejercicio_id=EJ1, titulo="T", estado=EstadoSync.SINCRONIZADO, simulado=False
        )
        with patch("evaluation_service.routes.activeia.settings") as st:
            st.activeia_mock_escritura = False
            assert _hay_simulacion([simulado]) is True, "el flag apagado tapo el dato"
            assert _hay_simulacion([real]) is False
            st.activeia_mock_escritura = True
            assert _hay_simulacion([real]) is True


class TestHashGolden:
    def test_golden(self) -> None:
        """Hash congelado. `CLAUDE.md` marca `ensure_ascii=False` como
        load-bearing y las otras dos formulas canonicas del repo tienen su
        golden; esta no lo tenia. El valor incluye tildes y enie a proposito:
        con `ensure_ascii=True` el hash cambia y este test lo caza.
        """
        entrada = {"criterios": [{"nombre": "Usa condición y ñandú", "puntaje_max": 1}]}
        assert (
            rubrica_hash(entrada)
            == "50cd47a356106edc809cd0f83b2f57042835be50610361e325c0f5621ef8c78e"
        )
