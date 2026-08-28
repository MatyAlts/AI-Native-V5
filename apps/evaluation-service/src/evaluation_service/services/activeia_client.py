"""Cliente HTTP de Active-IA.

El contrato de acá NO está inventado: sale de leer el cliente que ya opera
contra la API en vivo (`Skill-Moodle/codigo/mcp/moodle/active_ia.py` y su
`references/active-ia.md`, verificado contra producción el 2026-08-17).

Endpoints que existen hoy:

    POST /auth/login                            {username, password} -> access_token
    GET  /comisiones/
    GET  /rubricas/?materia_id=N                listado (anda con rol tutor)
    GET  /rubricas/{id}                         403 con rol tutor
    POST /entregas/                             multipart: archivo + metadatos
    POST /correcciones/entregas/{id}/corregir   dispara Gemini (async)
    GET  /correcciones/entregas/{id}            poll del resultado
    GET  /entregas/?comision_id=&estado=
    GET  /documentos/correcciones/{id}/pdf

Tres cosas medidas contra producción que este cliente respeta:

1. **Timeout de 90s, no 30.** `GET /pendientes/moodle` tardó 25, 40 y 24
   segundos en tres corridas. Con 30 fallaba una de cada tres.
2. **`GET /entregas/{id}` está roto del lado del server** (500). Para saber si
   una entrega ya se corrigió se usa `GET /correcciones/entregas/{id}`: 200 =
   corregida, 404 = todavía no.
3. **El 409 de `POST /entregas/` keyea por `(comision_id, rubrica_id,
   alumno_nombre)`.** Sin comparar `rubrica_id` se retomaba la entrega de OTRO
   TP del mismo alumno y se adjuntaba la devolución de otra unidad. El
   `rubrica_id` en el match no es opcional.

Cliente efímero por request y token en memoria con re-login ante 401, mismo
patrón que el cliente de Moodle.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class ActiveIAError(Exception):
    """Fallo hablando con Active-IA.

    `es_infraestructura` separa "el servicio no pudo responder" (timeout,
    5xx, Gemini saturado) de "el servicio respondió que no" (credenciales
    inválidas, rúbrica inexistente). La distinción no es cosmética: un fallo
    de infraestructura NUNCA puede convertirse en una nota, y en cambio sí
    puede reintentarse.
    """

    def __init__(self, mensaje: str, *, es_infraestructura: bool = False) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.es_infraestructura = es_infraestructura


def _detalle(e: BaseException) -> str:
    """Mensaje de error que no queda vacío.

    `f"...: {e}"` sobre una excepción de httpx sin args produce "algo falló: "
    y nada. El tipo siempre dice algo.
    """
    txt = str(e).strip()
    return f"{type(e).__name__}: {txt}" if txt else type(e).__name__


class ActiveIAClient:
    """Un cliente por request. NO compartir entre usuarios: el token es de
    la cuenta logueada y los ids que devuelve la API salen de ella."""

    def __init__(self, base_url: str, username: str, password: str, timeout: float) -> None:
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._token: str | None = None

    async def login(self) -> None:
        """`POST /auth/login`. Un fallo acá es de credenciales, no de red —
        salvo que el error sea de transporte, que sí es infraestructura."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                resp = await http.post(
                    f"{self._base}/auth/login",
                    json={"username": self._username, "password": self._password},
                )
        except httpx.HTTPError as e:
            raise ActiveIAError(
                f"No se pudo contactar a Active-IA: {_detalle(e)}", es_infraestructura=True
            ) from e

        if resp.status_code != 200:
            # El cuerpo NO se propaga: puede traer de vuelta lo que mandamos.
            raise ActiveIAError("Usuario o contraseña de Active-IA inválidos")

        token = resp.json().get("access_token")
        if not token:
            raise ActiveIAError(
                "Active-IA aceptó el login pero no devolvió token", es_infraestructura=True
            )
        self._token = token

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Request autenticado, con re-login ante un 401.

        `follow_redirects=True` porque la API redirige `/entregas` a
        `/entregas/`, y httpx por default no sigue el redirect — en un POST
        además perdería el body.
        """
        if self._token is None:
            await self.login()

        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as http:
                resp = await http.request(method, url, headers=self._auth_headers(), **kwargs)
                if resp.status_code == 401:
                    self._token = None
                    await self.login()
                    resp = await http.request(method, url, headers=self._auth_headers(), **kwargs)
        except httpx.HTTPError as e:
            raise ActiveIAError(
                f"Active-IA no respondió ({method} {path}): {_detalle(e)}",
                es_infraestructura=True,
            ) from e
        return resp

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    # ── Operaciones ───────────────────────────────────────────────────────

    async def verificar_credenciales(self) -> bool:
        """Valida la cuenta haciendo un login REAL.

        Se valida con el login y no listando rúbricas: si la cuenta no tiene
        rúbricas cargadas, el listado devuelve `[]` — y "no me pude loguear" y
        "esta materia no tiene rúbricas" se verían exactamente iguales. Eso ya
        confundió a un tutor en producción.
        """
        await self.login()
        return True

    async def rubricas_de_materia(self, materia_id: int | str) -> list[dict[str, Any]]:
        """`GET /rubricas/?materia_id=N`.

        Propaga el error en vez de devolver `[]`: el cliente de la skill se
        tragaba cualquier fallo y devolvía lista vacía, con lo cual "no hay
        rúbricas" tapaba un fallo de autenticación.
        """
        resp = await self.request(
            "GET", "/rubricas/", params={"materia_id": materia_id, "per_page": 100}
        )
        if resp.status_code != 200:
            raise ActiveIAError(
                f"GET /rubricas/ devolvió {resp.status_code}",
                es_infraestructura=resp.status_code >= 500,
            )
        cuerpo = resp.json()
        items = cuerpo.get("items", cuerpo) if isinstance(cuerpo, dict) else cuerpo
        return list(items) if isinstance(items, list) else []

    async def comisiones(self) -> list[dict[str, Any]]:
        resp = await self.request("GET", "/comisiones/")
        if resp.status_code != 200:
            raise ActiveIAError(
                f"GET /comisiones/ devolvió {resp.status_code}",
                es_infraestructura=resp.status_code >= 500,
            )
        cuerpo = resp.json()
        items = cuerpo.get("items", cuerpo) if isinstance(cuerpo, dict) else cuerpo
        return list(items) if isinstance(items, list) else []

    async def corregir_ejercicio(
        self,
        *,
        ejercicio_ref: str,
        alumno_ref: str,
        codigo: str,
        resultado_tests: dict[str, Any],
        comision_external_ref: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """`POST /correcciones/ejercicios/{ejercicio_ref}/corregir` — SINCRÓNICO.

        Es el endpoint del §3.4 de `activeia-cambios-pedidos.md`, que el equipo
        de Active-IA confirmó construido el 2026-08-24. Reemplaza al camino de
        tres pasos (subir zip → disparar → poletear): **una sola llamada**, la
        nota vuelve en la respuesta y no hay 202 ni polling.

        Tres cosas que dejan de existir con este endpoint, y por eso el llamador
        ya no las maneja:

        - **No hay 409.** Corregir de nuevo el mismo ejercicio del mismo alumno
          reusa la entrega y archiva la corrección anterior en su historial
          (§4.2 del documento de ellos). Reintentar es la misma llamada.
        - **No hay zip.** El código viaja como texto en el cuerpo.
        - **No hay poll.** Un ejercicio entra cómodo en los 90s de timeout.

        `comision_external_ref` es OPCIONAL y hoy no se manda: su modelo exige
        que toda entrega pertenezca a una comisión y nosotros no tenemos, así
        que configuraron una **comisión de integración** por materia que se usa
        cuando el campo no viene (§3.3). El parámetro queda por si algún día
        modelamos cohortes; mandarlo con un id que ellos no conocen sería peor
        que no mandarlo.

        Devuelve `(status_code, cuerpo)` en vez de levantar: el llamador
        distingue un 5xx (el motor no pudo, reintentar sirve) de un 4xx (nos
        rechazaron, reintentar devuelve lo mismo), y esa diferencia es la que
        decide si la UI le muestra el botón "Reintentar" al docente.
        """
        payload: dict[str, Any] = {
            "alumno_ref": alumno_ref,
            "codigo": codigo,
            "resultado_tests": resultado_tests,
        }
        if comision_external_ref:
            payload["comision_external_ref"] = comision_external_ref

        resp = await self.request(
            "POST", f"/correcciones/ejercicios/{ejercicio_ref}/corregir", json=payload
        )
        try:
            cuerpo = resp.json()
        except Exception:
            # Un cuerpo que no es JSON (un HTML de proxy, por ejemplo) no puede
            # convertirse en una nota. Se devuelve vacío y el status manda.
            cuerpo = {}
        return resp.status_code, dict(cuerpo) if isinstance(cuerpo, dict) else {}

    # ── Escritura de TPs: EXISTE desde el 2026-08-24 ──────────────────────
    #
    # `crear_o_actualizar_tp` habla contra `PUT /trabajos-practicos/by-ref/{ref}`,
    # que el equipo de Active-IA confirmó construido y probado en su documento
    # del 24/08 (§3.3 «Listo»). Hasta esa fecha esto era un contrato pedido y no
    # verificado, y por eso existe `ActiveIAClientMock`: hoy el mock es un
    # ensayo en seco, ya no una muleta obligatoria.
    #
    # Lo que SIGUE sin resolverse es la lectura: `GET /rubricas/{id}` devuelve
    # 403 con rol tutor, así que no se puede leer una rúbrica para comparar el
    # hash contra lo que tienen ellos. Por eso `rubrica_hash` compara contra lo
    # que MANDAMOS, no contra lo que quedó del otro lado.

    async def crear_o_actualizar_tp(
        self, *, external_ref: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Empuja el TP con sus ejercicios ANIDADOS (idempotente).

        Es el contrato de `activeia-cambios-pedidos.md` 3.3:
        `PUT /trabajos-practicos/by-ref/{external_ref}` con el TP entero.

        Uno solo y no N rúbricas sueltas: los ejercicios de un TP son partes
        de una misma entrega, y sin el TP que los agrupe la corrección del
        otro lado no tiene cómo saberlo.

        `external_ref` es NUESTRO UUID, así que reenviar el mismo TP actualiza
        en vez de duplicar. Sin él, cada publicación crearía un TP nuevo y el
        docente terminaría eligiendo entre diez copias — y elegir mal no da
        una nota floja: corrige otra cosa.

        La respuesta tiene que traer `ejercicios[]` con el `external_ref` de
        cada uno y su `rubrica_id`. Emparejar por orden o por título sería
        adivinar.
        """
        resp = await self.request("PUT", f"/trabajos-practicos/by-ref/{external_ref}", json=payload)
        if resp.status_code not in (200, 201):
            raise ActiveIAError(
                f"PUT /trabajos-practicos/by-ref/{external_ref} devolvió {resp.status_code}",
                es_infraestructura=resp.status_code >= 500,
            )
        return dict(resp.json())

    async def obtener_rubrica(self, rubrica_id: str) -> dict[str, Any]:
        """Lee una rúbrica. Hoy devuelve 403 con rol tutor."""
        resp = await self.request("GET", f"/rubricas/{rubrica_id}")
        if resp.status_code == 403:
            raise ActiveIAError(
                "La cuenta no tiene permiso para leer el detalle de la rúbrica "
                "(hace falta rol de coordinador)."
            )
        if resp.status_code != 200:
            raise ActiveIAError(
                f"GET /rubricas/{rubrica_id} devolvió {resp.status_code}",
                es_infraestructura=resp.status_code >= 500,
            )
        return dict(resp.json())


class ActiveIAClientMock(ActiveIAClient):
    """Simula SÓLO los endpoints de escritura que Active-IA todavía no tiene.

    Existe para que el resto del circuito —sincronizar al publicar, detectar
    que la rúbrica local cambió, mostrarlo en la vista del docente— se pueda
    construir y probar entero ahora, y el día que el endpoint exista se apague
    el flag y listo.

    **Dos reglas que lo hacen no confundible con lo real:**

    1. Todo lo que devuelve lleva `"simulado": True`, y el `rubrica_id` que
       inventa arranca con `MOCK-`. Si un `rubrica_id` que empieza con `MOCK-`
       llega a un disparo de corrección real, se ve.
    2. Loguea en WARNING cada llamada. Un mock silencioso en producción es
       indistinguible de una integración que anda.

    Lo que NO simula: el login ni las lecturas. Ésos van contra la API de
    verdad, así que conectar la cuenta sigue validando contra Active-IA real.
    """

    async def crear_o_actualizar_tp(
        self, *, external_ref: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        ejercicios = payload.get("ejercicios", [])
        log.warning(
            "activeia_mock_escritura",
            operacion="crear_o_actualizar_tp",
            external_ref=external_ref,
            n_ejercicios=len(ejercicios),
            detalle="Active-IA no expone escritura de TPs todavía; esto NO se envió.",
        )
        # Devuelve la MISMA forma que el contrato pedido, para que el día que
        # exista de verdad no haya que tocar al consumidor.
        return {
            "id": f"MOCK-{external_ref}",
            "external_ref": external_ref,
            "simulado": True,
            "ejercicios": [
                {
                    "external_ref": e["external_ref"],
                    "rubrica_id": f"MOCK-{e['external_ref']}",
                }
                for e in ejercicios
            ],
        }

    async def obtener_rubrica(self, rubrica_id: str) -> dict[str, Any]:
        log.warning(
            "activeia_mock_escritura",
            operacion="obtener_rubrica",
            rubrica_id=rubrica_id,
            detalle="GET /rubricas/{id} da 403 con rol tutor; esto NO se consultó.",
        )
        return {"id": rubrica_id, "simulado": True}
