"""Tests de las credenciales de Active-IA (Epic 2 de `correccion-activeia`).

Lo que cubren, en orden de importancia:

1. Que el password NO salga por ningun lado — ni en la respuesta, ni en el
   log, ni en el mensaje de error.
2. Que las queries filtren por `user_id` explicito. La RLS de esa tabla es
   solo por tenant, y en produccion todos los docentes comparten tenant: sin
   ese filtro un docente lee la credencial de otro y la RLS no lo frena.
3. Que la validacion sea un login REAL, y que un fallo de credenciales se
   distinga de uno de infraestructura.
"""

from __future__ import annotations

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from evaluation_service.auth.dependencies import User
from evaluation_service.models.activeia import ActiveIACredencial
from evaluation_service.schemas.activeia import CredencialCreate, CredencialEstado
from evaluation_service.services.activeia_client import ActiveIAClient, ActiveIAError
from evaluation_service.services.activeia_credenciales import (
    CredencialNoConfiguradaError,
    cliente_para,
    guardar_credencial,
    obtener_credencial,
    revocar_credencial,
)
from platform_ops.crypto import decrypt

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
KEY_B64 = base64.b64encode(os.urandom(32)).decode()
PASSWORD = "un-password-que-no-debe-aparecer-nunca"


def _db(*resultados: MagicMock) -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=list(resultados))
    return db


def _res(cred: ActiveIACredencial | None) -> MagicMock:
    return MagicMock(scalar_one_or_none=MagicMock(return_value=cred))


class TestNoFiltraElPassword:
    def test_el_schema_de_salida_no_tiene_campo_de_password(self) -> None:
        """Ni el password, ni un fingerprint suyo. Con una API key los ultimos
        caracteres son un identificador util; con un password humano son una
        fuga (por eso NO se reusa `byok_keys`, que los guarda en claro)."""
        campos = set(CredencialEstado.model_fields)
        assert not any("password" in c or "secret" in c for c in campos)
        assert campos == {
            "conectada",
            "modo_simulado",
            "username",
            "created_at",
            "last_login_at",
            "last_login_ok",
        }

    async def test_el_login_fallido_no_devuelve_lo_que_mandamos(self) -> None:
        """El cuerpo de la respuesta de Active-IA NO se propaga: puede traer de
        vuelta las credenciales que le mandamos."""
        cli = ActiveIAClient("https://x", "u", PASSWORD, 1.0)
        resp = MagicMock(status_code=401, text=f'{{"sent": "{PASSWORD}"}}')
        with patch("httpx.AsyncClient") as fake:
            fake.return_value.__aenter__.return_value.post = AsyncMock(return_value=resp)
            with pytest.raises(ActiveIAError) as exc:
                await cli.login()
        assert PASSWORD not in str(exc.value)

    async def test_el_log_del_guardado_no_lleva_credenciales(self) -> None:
        cred_guardada: list[ActiveIACredencial] = []
        db = _db(_res(None))
        db.add = MagicMock(side_effect=cred_guardada.append)

        with (
            patch("evaluation_service.services.activeia_credenciales.settings") as st,
            patch.object(ActiveIAClient, "verificar_credenciales", AsyncMock(return_value=True)),
            patch("evaluation_service.services.activeia_credenciales.log") as fake_log,
        ):
            st.activeia_master_key = KEY_B64
            st.activeia_url = "https://x"
            st.activeia_timeout_seconds = 1.0
            await guardar_credencial(db, TENANT, uuid4(), "docente@utn.edu.ar", PASSWORD)

        kwargs = fake_log.info.call_args.kwargs
        assert PASSWORD not in str(kwargs)
        # Tampoco el username: suele ser el mail institucional del docente.
        assert "docente@utn.edu.ar" not in str(kwargs)


class TestCifrado:
    async def test_el_password_se_guarda_cifrado_y_vuelve_igual(self) -> None:
        guardadas: list[ActiveIACredencial] = []
        db = _db(_res(None))
        db.add = MagicMock(side_effect=guardadas.append)

        with (
            patch("evaluation_service.services.activeia_credenciales.settings") as st,
            patch.object(ActiveIAClient, "verificar_credenciales", AsyncMock(return_value=True)),
        ):
            st.activeia_master_key = KEY_B64
            st.activeia_url = "https://x"
            st.activeia_timeout_seconds = 1.0
            await guardar_credencial(db, TENANT, uuid4(), "u", PASSWORD)

        blob = guardadas[0].encrypted_password
        assert PASSWORD.encode() not in blob, "el password quedo legible en la columna"
        assert decrypt(blob, base64.b64decode(KEY_B64)).decode() == PASSWORD

    async def test_sin_master_key_lo_dice_en_vez_de_fallar_adentro(self) -> None:
        with patch("evaluation_service.services.activeia_credenciales.settings") as st:
            st.activeia_master_key = ""
            with pytest.raises(ActiveIAError) as exc:
                await guardar_credencial(_db(), TENANT, uuid4(), "u", PASSWORD)
        assert "ACTIVEIA_MASTER_KEY" in str(exc.value)


class TestAislamientoPorUsuario:
    async def test_la_query_filtra_por_user_id(self) -> None:
        """La RLS es solo por tenant (design D6). Sin este filtro un docente
        leeria la credencial de otro del mismo tenant.

        Se inspecciona el WHERE y NO `str(stmt)` entero: `str()` de un
        `select(Modelo)` incluye la lista de columnas del SELECT, y `user_id`
        es una columna de la tabla — o sea que `"user_id" in str(stmt)` es
        cierto aunque el WHERE no lo mencione. La version anterior de este
        test pasaba con y sin el filtro, que es lo mismo que no tenerlo.
        """
        db = _db(_res(None))
        await obtener_credencial(db, TENANT, uuid4())

        where = str(db.execute.call_args.args[0].whereclause)
        assert "activeia_credenciales.user_id" in where, f"el WHERE no filtra por usuario: {where}"
        assert "activeia_credenciales.tenant_id" in where
        assert "revoked_at IS NULL" in where

    async def test_revocar_sin_credencial_no_explota(self) -> None:
        assert await revocar_credencial(_db(_res(None)), TENANT, uuid4()) is False

    async def test_cliente_para_sin_credencial_dice_que_falta_conectar(self) -> None:
        with pytest.raises(CredencialNoConfiguradaError):
            await cliente_para(_db(_res(None)), TENANT, uuid4())


class TestValidacionDeCuenta:
    async def test_valida_con_login_real_no_listando_rubricas(self) -> None:
        """Validar listando rubricas hace que 'no me pude loguear' y 'esta
        materia no tiene rubricas' se vean iguales — ya confundio a un tutor
        en produccion."""
        db = _db(_res(None))
        with (
            patch("evaluation_service.services.activeia_credenciales.settings") as st,
            patch.object(ActiveIAClient, "verificar_credenciales", AsyncMock()) as fake_login,
            patch.object(ActiveIAClient, "rubricas_de_materia", AsyncMock()) as fake_rub,
        ):
            st.activeia_master_key = KEY_B64
            st.activeia_url = "https://x"
            st.activeia_timeout_seconds = 1.0
            await guardar_credencial(db, TENANT, uuid4(), "u", PASSWORD)

        fake_login.assert_awaited_once()
        fake_rub.assert_not_awaited()

    async def test_credenciales_malas_no_son_fallo_de_infraestructura(self) -> None:
        """Un password equivocado NO puede reintentarse ni reportarse como
        'el servicio no anda'."""
        cli = ActiveIAClient("https://x", "u", "mala", 1.0)
        with patch("httpx.AsyncClient") as fake:
            fake.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=MagicMock(status_code=401, text="{}")
            )
            with pytest.raises(ActiveIAError) as exc:
                await cli.login()
        assert exc.value.es_infraestructura is False

    async def test_timeout_si_es_infraestructura(self) -> None:
        import httpx

        cli = ActiveIAClient("https://x", "u", "p", 1.0)
        with patch("httpx.AsyncClient") as fake:
            fake.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectTimeout("timeout")
            )
            with pytest.raises(ActiveIAError) as exc:
                await cli.login()
        assert exc.value.es_infraestructura is True


class TestSchemas:
    def test_el_create_exige_los_dos_campos(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CredencialCreate(username="", password="x")


class TestPropiedadesDeclaradasDelEpic:
    """Cuatro propiedades que el spec declara y que no tenian ningun test:
    sobrevivian a su mutacion, o sea que nada las defendia de una edicion."""

    async def test_reconectar_revoca_la_credencial_anterior(self) -> None:
        """Scenario del spec: "only one active credential per teacher". El
        UNIQUE es parcial sobre las vigentes, asi que si no se revoca la
        anterior el insert explota."""
        anterior = ActiveIACredencial(
            tenant_id=TENANT, user_id=uuid4(), username="vieja", encrypted_password=b"x"
        )
        anterior.revoked_at = None
        db = _db(_res(anterior))

        with (
            patch("evaluation_service.services.activeia_credenciales.settings") as st,
            patch.object(ActiveIAClient, "verificar_credenciales", AsyncMock(return_value=True)),
        ):
            st.activeia_master_key = KEY_B64
            st.activeia_url = "https://x"
            st.activeia_timeout_seconds = 1.0
            await guardar_credencial(db, TENANT, uuid4(), "nueva", PASSWORD)

        assert anterior.revoked_at is not None, "quedarian dos credenciales vigentes"

    def test_el_gate_de_rol_no_deja_pasar_a_un_estudiante(self) -> None:
        """Disparar una correccion manda codigo de un alumno a un servicio
        externo y gasta cuota que se paga. Es una accion docente."""
        from evaluation_service.auth.dependencies import require_correccion_ia
        from fastapi import HTTPException

        alumno = User(
            id=uuid4(),
            tenant_id=TENANT,
            email="a@utn.edu.ar",
            roles=frozenset({"estudiante"}),
            realm="utn",
        )
        with pytest.raises(HTTPException) as exc:
            require_correccion_ia(alumno)
        assert exc.value.status_code == 403

    def test_el_gate_de_rol_deja_pasar_a_un_docente(self) -> None:
        """Control positivo: el 403 de arriba tiene que ser por el rol, no
        porque el gate rechace a todos."""
        from evaluation_service.auth.dependencies import require_correccion_ia

        docente = User(
            id=uuid4(),
            tenant_id=TENANT,
            email="d@utn.edu.ar",
            roles=frozenset({"docente"}),
            realm="utn",
        )
        assert require_correccion_ia(docente) is docente

    def test_una_master_key_de_largo_invalido_no_da_500(self) -> None:
        """`CryptoError` NO hereda de `ActiveIAError`, asi que el `except` de
        la ruta no lo agarraba y salia 500. Y el orden importa: validar
        DESPUES del login real haria loguearse contra Active-IA para descubrir
        recien ahi que no se va a poder cifrar."""
        import base64 as b64

        from evaluation_service.services.activeia_credenciales import _master_key

        corta = b64.b64encode(b"8bytes!!").decode()
        with patch("evaluation_service.services.activeia_credenciales.settings") as st:
            st.activeia_master_key = corta
            with pytest.raises(ActiveIAError) as exc:
                _master_key()
        assert "32 bytes" in str(exc.value)


class TestKillSwitch:
    """El kill switch falla CERRADO: apagado, no se contacta a Active-IA."""

    def test_apagado_conectar_da_503(self) -> None:
        from evaluation_service.routes.activeia import _assert_habilitado
        from fastapi import HTTPException

        with patch("evaluation_service.routes.activeia.settings") as st:
            st.activeia_enabled = False
            with pytest.raises(HTTPException) as exc:
                _assert_habilitado()
        assert exc.value.status_code == 503

    def test_prendido_no_frena(self) -> None:
        from evaluation_service.routes.activeia import _assert_habilitado

        with patch("evaluation_service.routes.activeia.settings") as st:
            st.activeia_enabled = True
            _assert_habilitado()
