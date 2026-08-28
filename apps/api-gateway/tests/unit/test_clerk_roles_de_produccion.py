"""El gateway le da los DOS roles a TODO usuario logueado con Clerk.

Esta es la premisa sobre la que descansan todos los guards de autorizacion del
repo, y hasta hoy no la fijaba ningun test. La constante vive sola en
`config.py`::

    clerk_base_roles: str = "estudiante,docente"

y `ClerkJWTValidator` se la entrega tal cual a cualquiera que presente un token
valido. Despues `JWTMiddleware` **pisa autoritativamente** el header entrante con
`",".join(sorted(principal.roles))`, asi que lo que los servicios internos leen
en `X-User-Roles` es literalmente `"docente,estudiante"` para el alumno de primer
ano y para el titular de catedra por igual.

## Por que hace falta fijarlo

Ya mordio dos veces. Un guard que preguntaba `if user.roles & DOCENTE_ROLES`
habria devuelto 403 a todos los alumnos del piloto —que en `usuarios_comision`
no existen, viven en `inscripciones`— y no lo agarro ningun test, porque los ~40
que existian armaban al alumno con `X-User-Roles: "estudiante"` a secas, una
identidad que produccion NUNCA emite. El write-up completo esta en
`apps/evaluation-service/tests/unit/test_scope_con_roles_de_produccion.py`.

La consecuencia dura, y la regla que sale de aca: **un test de autorizacion con
un usuario de UN solo rol no prueba nada en este deploy.**

## Que fija exactamente

Que la premisa siga siendo cierta. Si manana alguien deja
`clerk_base_roles = "estudiante"` porque "el docente ya se distingue por otro
lado", cada guard del repo cambia de significado en silencio y ningun test de
autorizacion lo nota: los tests que discriminan por rol se pondrian VERDES
—empezarian a funcionar como sus autores creian— mientras el piloto se rompe.
El unico lugar donde eso se puede ver es aca.

No fija que la eleccion sea buena: fija que sigue vigente. Si se cambia a
proposito, este test es la lista de lo que hay que revisar.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
import pytest
from api_gateway.config import settings
from api_gateway.services.jwt_validator import (
    ClerkJWTValidator,
    JWTValidatorConfig,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://clerk.test.local"
TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture(scope="module")
def par_rsa() -> dict[str, Any]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return {
        "private_pem": key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode(),
        "public_pem": key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode(),
    }


class _CacheFalsa:
    def __init__(self, public_pem: str) -> None:
        self._pem = public_pem

    async def get_key(self, kid: str):
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        return load_pem_public_key(self._pem.encode())


def _token(private_pem: str, *, sub: str, email: str) -> str:
    ahora = int(time.time())
    return jwt.encode(
        {"sub": sub, "email": email, "iss": ISSUER, "iat": ahora, "exp": ahora + 300},
        private_pem,
        algorithm="RS256",
        headers={"kid": "k1"},
    )


def _validator(par_rsa: dict[str, Any], *, admin_emails: frozenset[str] = frozenset()):
    """Se construye con los MISMOS `base_roles` que arma `main.py`.

    `main.py` hace `frozenset(r.strip() for r in settings.clerk_base_roles.split(","))`.
    Si el test hardcodeara el frozenset, la mutacion de la constante sobreviviria
    — que es justo lo que este archivo existe para impedir.
    """
    return ClerkJWTValidator(
        config=JWTValidatorConfig(
            issuer=ISSUER, audience="", jwks_uri=f"{ISSUER}/.well-known/jwks.json"
        ),
        fixed_tenant_id=TENANT,
        base_roles=frozenset(
            r.strip() for r in settings.clerk_base_roles.split(",") if r.strip()
        ),
        admin_emails=admin_emails,
        jwks_cache=_CacheFalsa(par_rsa["public_pem"]),
    )


class TestTodoUsuarioLogueadoTraeLosDosRoles:
    async def test_el_alumno_tambien_llega_con_docente(self, par_rsa: dict[str, Any]) -> None:
        """La mitad contraintuitiva: el alumno trae `docente` encima."""
        principal = await _validator(par_rsa).validate(
            _token(par_rsa["private_pem"], sub="user_alumno", email="alumna@utn.edu.ar")
        )

        assert principal.roles == frozenset({"estudiante", "docente"}), principal.roles

    async def test_el_docente_tambien_llega_con_estudiante(
        self, par_rsa: dict[str, Any]
    ) -> None:
        """Y la otra mitad: por eso `"estudiante" in roles` tampoco identifica a nadie."""
        principal = await _validator(par_rsa).validate(
            _token(par_rsa["private_pem"], sub="user_docente", email="titular@utn.edu.ar")
        )

        assert principal.roles == frozenset({"estudiante", "docente"}), principal.roles

    async def test_dos_usuarios_DISTINTOS_traen_los_mismos_roles(
        self, par_rsa: dict[str, Any]
    ) -> None:
        """La propiedad, dicha entera: el rol no distingue a nadie de nadie.

        Lo unico que difiere entre estos dos principals es el `user_id`. Por eso
        los guards del repo preguntan por PROPIEDAD (`student_pseudonym ==
        user.id`) o por MEMBRESIA (`usuarios_comision`), no por rol.
        """
        v = _validator(par_rsa)
        alumno = await v.validate(
            _token(par_rsa["private_pem"], sub="user_a", email="a@utn.edu.ar")
        )
        docente = await v.validate(
            _token(par_rsa["private_pem"], sub="user_b", email="b@utn.edu.ar")
        )

        assert alumno.roles == docente.roles
        assert alumno.user_id != docente.user_id

    async def test_el_default_de_la_constante_sigue_siendo_los_dos(self) -> None:
        """El valor literal, para que la mutacion no se pueda esconder.

        Los tests de arriba leen `settings.clerk_base_roles`, asi que un cambio
        del default los mueve a los dos lados a la vez. Este assert es el ancla.
        """
        assert settings.clerk_base_roles == "estudiante,docente"


class TestElAllowlistDeAdminsEsLoUnicoQueDiferencia:
    async def test_un_email_del_allowlist_suma_oversight(
        self, par_rsa: dict[str, Any]
    ) -> None:
        """`admin_emails` es el UNICO camino a `superadmin`/`docente_admin`.

        Importa porque `_OVERSIGHT` (evaluation-service) y varios guards
        bypassean el scope de comision con esos dos roles: quien esta en esta
        lista opera cross-comision en todo el sistema.
        """
        principal = await _validator(
            par_rsa, admin_emails=frozenset({"coordinacion@utn.edu.ar"})
        ).validate(
            _token(par_rsa["private_pem"], sub="user_admin", email="Coordinacion@UTN.edu.ar")
        )

        assert principal.roles == frozenset(
            {"estudiante", "docente", "superadmin", "docente_admin"}
        ), principal.roles

    async def test_fuera_del_allowlist_NO_hay_oversight(
        self, par_rsa: dict[str, Any]
    ) -> None:
        """Sin esto el test de arriba pasaria aunque el allowlist se ignorara."""
        principal = await _validator(
            par_rsa, admin_emails=frozenset({"coordinacion@utn.edu.ar"})
        ).validate(
            _token(par_rsa["private_pem"], sub="user_x", email="otro@utn.edu.ar")
        )

        assert not (principal.roles & {"superadmin", "docente_admin"}), principal.roles


class TestLaIdentidadQueSiDistingue:
    async def test_el_user_id_es_deterministico_por_sub_de_clerk(
        self, par_rsa: dict[str, Any]
    ) -> None:
        """Es lo unico sobre lo que un guard puede apoyarse.

        `X-User-Id` sale de un UUIDv5 sobre el `sub` de Clerk: mismo usuario,
        mismo UUID entre sesiones y deploys. El token puede mentir sobre los
        roles; sobre esto no.
        """
        v = _validator(par_rsa)
        uno = await v.validate(
            _token(par_rsa["private_pem"], sub="user_estable", email="a@utn.edu.ar")
        )
        otro = await v.validate(
            _token(par_rsa["private_pem"], sub="user_estable", email="a@utn.edu.ar")
        )

        assert uno.user_id == otro.user_id
        uuid.UUID(uno.user_id)  # y es un UUID de verdad, no el `sub` crudo
        assert uno.user_id != "user_estable"
