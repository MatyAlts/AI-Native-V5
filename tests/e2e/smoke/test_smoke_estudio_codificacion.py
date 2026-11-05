"""Smoke - estudio de codificacion ciega (ADR-063, change `cibse-codificacion-ciega`).

Recorre contra el stack real (api-gateway -> classifier-service -> ctr-service ->
Postgres) el ciclo minimo de un estudio: alta, membresias, codebook congelado,
muestra sintetica, enunciados revisados, traza ciega, etiqueta, cierre y
exportacion.

Por que smoke y no solo integracion: los tests `_db` del classifier usan un CTR
FALSO inyectado. La lectura classifier -> ctr-service real (cuenta de servicio
`classifier_worker`, gate de comision, forma de `EpisodeWithEvents`) solo se
ejercita aca, igual que el prefijo `/api/v1/interrater` del ROUTE_MAP.

Muestra SINTETICA: el CSV se arma en el test con episodios cerrados del seed
(`seeded_episode_id` y otro del mismo tenant). Nunca los episodios de la muestra
real del estudio.

Limitacion declarada: el seed de CI (`seed-3-comisiones.py`) no siembra eventos
`intento_adverso_detectado`, asi que la ausencia de esa marca en la traza no
discrimina en este smoke (la cubren `tests/unit/test_traza_ciega.py` y sus
mutantes). Lo que SI discrimina contra el seed es `prompt_kind`: el evento crudo
lo trae y la traza no puede traerlo (se afirma la precondicion).

Cada corrida crea un estudio nuevo (clave unica). No hay endpoint de baja de
estudios: queda en `classifier_db` como el resto de los recursos de smoke.

Requiere: stack up con `DEV_TRUST_HEADERS=true`, seed con episodios cerrados
del tenant demo y `SMOKE_PG_DSN` apuntando al Postgres del stack.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Any

import httpx
import pytest
from _helpers import TENANT_DEMO, fetch_pg

BASE = "/api/v1/interrater/estudios"

# Esquema construido para el smoke (no es el del codebook v0).
ESQUEMA_SMOKE: dict[str, Any] = {
    "dimensiones": [
        {
            "clave": "d1",
            "nombre": "D1",
            "valores": ["presente", "ausente"],
            "cita_requerida_si": ["presente"],
        },
        {
            "clave": "d2",
            "nombre": "D2",
            "valores": ["presente", "ausente"],
            "cita_requerida_si": [],
        },
    ],
    "regimenes": [
        {"clave": "alto", "nombre": "Alto"},
        {"clave": "bajo", "nombre": "Bajo"},
        {"clave": "evidencia_insuficiente", "nombre": "Evidencia insuficiente"},
    ],
    "regimen_evidencia_insuficiente": "evidencia_insuficiente",
    "dimensiones_opcionales_si_regimen": ["evidencia_insuficiente"],
    "notas_obligatorias_si_regimen": ["evidencia_insuficiente"],
    "reglas_regimen": [
        {
            "regimen": "alto",
            "condicion": [
                [{"dimension": "d1", "en": ["presente"]}],
                [{"dimension": "d2", "en": ["presente"]}],
            ],
        }
    ],
    "regimen_por_defecto": "bajo",
    "regimenes_exentos": ["evidencia_insuficiente"],
}

# Lo que dice la regla con d1 y d2 presentes. El pedido NO manda `regimen`:
# el que se persiste es el derivado.
ETIQUETA_SMOKE: dict[str, Any] = {
    "respuestas": {
        "d1": {"valor": "presente", "cita": "mensaje 1"},
        "d2": {"valor": "presente", "cita": None},
    }
}

# Claves que la traza ciega nunca puede traer, en ningun nivel (design D4).
CLAVES_PROHIBIDAS = {
    "seq",
    "ts",
    "prompt_kind",
    "chain_hash",
    "self_hash",
    "prev_chain_hash",
    "event_uuid",
    "episode_id",
    "student_pseudonym",
    "caller_id",
    "prompt_system_hash",
}
TIPOS_TRAZA = {
    "inicio",
    "lectura",
    "mensaje_alumno",
    "respuesta_tutor",
    "codigo",
    "ejecucion",
    "prueba",
    "nota",
    "copia",
    "pegado",
    "fin_cerrado",
    "fin_abandonado",
}

_state: dict[str, Any] = {}


class _Persona:
    """Cuenta como las de Clerk: toda cuenta trae `estudiante,docente`."""

    def __init__(self, email: str, roles: str = "estudiante,docente") -> None:
        self.user_id = str(uuid.uuid4())
        self.email = email
        self.roles = roles

    def headers(self, **extra: str) -> dict[str, str]:
        return {
            "X-User-Id": self.user_id,
            "X-Tenant-Id": TENANT_DEMO,
            "X-User-Email": self.email,
            "X-User-Roles": self.roles,
            **extra,
        }


def _ruta(sufijo: str = "") -> str:
    return f"{BASE}/{_state['clave']}{sufijo}"


def _detalle(resp: httpx.Response) -> Any:
    try:
        return resp.json().get("detail")
    except ValueError:
        return None


def _requiere(*claves: str) -> None:
    faltan = [c for c in claves if c not in _state]
    if faltan:
        pytest.fail(f"paso previo del modulo no completado: falta {faltan}")


def _claves_recursivas(valor: Any) -> set[str]:
    claves: set[str] = set()
    if isinstance(valor, dict):
        claves |= set(valor)
        hijos = list(valor.values())
    elif isinstance(valor, list):
        hijos = valor
    else:
        hijos = []
    for v in hijos:
        claves |= _claves_recursivas(v)
    return claves


def _episodios_de_la_muestra(seeded_episode_id: str) -> list[str]:
    """El episodio canonico del seed y otro cerrado del mismo tenant."""
    filas = fetch_pg(
        "ctr_store",
        "SELECT id::text FROM episodes WHERE tenant_id = %s AND estado = 'closed' "
        "AND NOT integrity_compromised AND id <> %s ORDER BY id LIMIT 1",
        (TENANT_DEMO, seeded_episode_id),
    )
    assert filas, "el seed no tiene otro episodio cerrado en el tenant demo"
    return [seeded_episode_id, filas[0][0]]


@pytest.mark.smoke
def test_alta_de_estudio_y_membresias(client: httpx.Client) -> None:
    """Administrador crea el estudio; asigna investigador y codificador por email.

    El codificador ve el estudio en `mis-membresias` (primer uso: ata su
    `X-User-Id`); una cuenta sin membresia recibe 403 al leer el estudio.
    """
    _state["clave"] = f"smoke-{uuid.uuid4().hex[:10]}"
    admin = _Persona("admin-smoke@demo-uni.edu", "estudiante,docente,superadmin")
    inv = _Persona(f"inv-{_state['clave']}@ejemplo.org")
    cod = _Persona(f"cod-{_state['clave']}@ejemplo.org")
    _state.update(admin=admin, inv=inv, cod=cod)

    r = client.post(
        BASE, json={"clave": _state["clave"], "titulo": "Smoke"}, headers=admin.headers()
    )
    assert r.status_code == 201, f"alta de estudio: {r.status_code} {r.text[:300]}"
    assert r.json()["traza_version"] == "traza_v1", r.json()

    for persona, rol in ((inv, "investigador"), (cod, "codificador")):
        r = client.post(
            _ruta("/membresias"),
            json={"email": persona.email.upper(), "rol": rol},
            headers=admin.headers(),
        )
        assert r.status_code == 201, f"membresia {rol}: {r.status_code} {r.text[:300]}"
        assert r.json()["rol"] == rol

    r = client.get(_ruta("/membresias"), headers=admin.headers())
    assert r.status_code == 200, r.text[:300]
    assert sorted((m["email"], m["rol"], m["estado"]) for m in r.json()) == [
        (cod.email, "codificador", "activa"),
        (inv.email, "investigador", "activa"),
    ], "las membresias se guardan con el email en minusculas"

    r = client.get(f"{BASE}/mis-membresias", headers=cod.headers())
    assert r.status_code == 200, r.text[:300]
    assert [(m["clave"], m["rol"], m["cerrada"]) for m in r.json()] == [
        (_state["clave"], "codificador", False)
    ]

    ajeno = _Persona(f"ajeno-{_state['clave']}@ejemplo.org")
    r = client.get(_ruta("/codebook/versiones"), headers=ajeno.headers())
    assert r.status_code == 403, f"cuenta sin membresia: {r.status_code} {r.text[:300]}"


@pytest.mark.smoke
def test_codebook_congelado_y_vigente(client: httpx.Client) -> None:
    """Version borrador con texto y esquema, vigente y congelada con sha256."""
    _requiere("clave", "inv")
    inv = _state["inv"]
    assert (
        client.post(_ruta("/codebook"), json={"etiqueta": "v0"}, headers=inv.headers()).status_code
        == 201
    )
    r = client.put(
        _ruta("/codebook/v0"),
        json={"contenido_md": "# Codebook de smoke", "esquema": ESQUEMA_SMOKE},
        headers=inv.headers(),
    )
    assert r.status_code == 200, f"PUT borrador: {r.status_code} {r.text[:300]}"
    r = client.put(_ruta("/codebook-vigente"), json={"etiqueta": "v0"}, headers=inv.headers())
    assert r.status_code == 200, r.text[:300]
    r = client.post(_ruta("/codebook/v0/congelar"), headers=inv.headers())
    assert r.status_code == 200, f"congelar: {r.status_code} {r.text[:300]}"

    r = client.get(_ruta("/codebook/vigente"), headers=_state["cod"].headers())
    assert r.status_code == 200, r.text[:300]
    vigente = r.json()
    assert vigente["estado"] == "congelada", vigente
    assert len(vigente["contenido_sha256"] or "") == 64, vigente

    r = client.put(
        _ruta("/codebook/v0"),
        json={"contenido_md": "otro", "esquema": ESQUEMA_SMOKE},
        headers=inv.headers(),
    )
    assert r.status_code == 409, f"PUT sobre congelada: {r.status_code} {r.text[:300]}"
    _state["codebook"] = True


@pytest.mark.smoke
def test_muestra_sintetica_y_enunciados_revisados(
    client: httpx.Client, seeded_episode_id: str
) -> None:
    """CSV sintetico con episodios cerrados del seed, leidos del ctr-service real.

    Luego el CSV de enunciados cubre exactamente lo que la cobertura pide y el
    investigador los revisa: sin eso la codificacion queda bloqueada.
    """
    _requiere("clave", "inv", "codebook")
    inv = _state["inv"]
    episodios = _episodios_de_la_muestra(seeded_episode_id)
    _state["episodios"] = episodios
    contenido = "estrato,origen,tp,episode_id\n" + "".join(
        f"E{i},smoke,TP{i},{ep}\n" for i, ep in enumerate(episodios)
    )
    r = client.post(
        _ruta("/muestra"),
        content=contenido.encode("utf-8"),
        headers=inv.headers(**{"Content-Type": "text/csv"}),
    )
    assert r.status_code == 200, f"carga de muestra: {r.status_code} {r.text[:400]}"
    assert r.json()["items"] == len(episodios), r.json()

    r = client.get(_ruta("/enunciados"), headers=inv.headers())
    assert r.status_code == 200, r.text[:300]
    faltantes = r.json()["cobertura"]["faltantes"]
    assert faltantes, "la cobertura no pidio ningun enunciado para la muestra"
    filas = ["tipo,tp_id,ejercicio_id,enunciado"]
    for f in faltantes:
        texto = f'"Consigna de smoke {f["tipo"]} {f["id"][:8]}"'
        filas.append(
            f"tp,{f['id']},,{texto}" if f["tipo"] == "tp" else f"ejercicio,,{f['id']},{texto}"
        )
    r = client.post(
        _ruta("/enunciados"),
        content=("\n".join(filas) + "\n").encode("utf-8"),
        headers=inv.headers(**{"Content-Type": "text/csv"}),
    )
    assert r.status_code == 200, f"carga de enunciados: {r.status_code} {r.text[:400]}"

    r = client.get(_ruta("/enunciados"), headers=inv.headers())
    for enunciado in r.json()["enunciados"]:
        rr = client.post(
            _ruta(f"/enunciados/{enunciado['id']}/revision"),
            json={"contenido_mostrado_md": None},
            headers=inv.headers(),
        )
        assert rr.status_code == 200, f"revision: {rr.status_code} {rr.text[:300]}"
    cobertura = client.get(_ruta("/enunciados"), headers=inv.headers()).json()["cobertura"]
    assert cobertura["faltantes"] == [] and cobertura["sin_revisar"] == [], cobertura
    _state["muestra"] = True


@pytest.mark.smoke
def test_traza_ciega_sin_marcas_de_la_maquina(client: httpx.Client) -> None:
    """La traza del codificador viene del ctr-service real y sale filtrada.

    Precondicion afirmada: el evento crudo del seed trae `prompt_kind`, asi que
    su ausencia en la traza prueba que el filtro corrio sobre datos reales.
    """
    _requiere("clave", "cod", "muestra", "episodios")
    cod = _state["cod"]
    r = client.get(_ruta("/items"), headers=cod.headers())
    assert r.status_code == 200, r.text[:300]
    items = r.json()
    assert sorted(i["posicion"] for i in items) == list(range(1, len(_state["episodios"]) + 1))
    assert all(set(i) == {"item_id", "posicion", "estado"} for i in items), items
    _state["items"] = [i["item_id"] for i in items]

    crudo = fetch_pg(
        "ctr_store",
        "SELECT count(*) FROM events WHERE episode_id = ANY(%s::uuid[]) "
        "AND payload ? 'prompt_kind'",
        (_state["episodios"],),
    )[0][0]
    assert crudo > 0, "precondicion: el seed deberia traer prompt_kind en los eventos crudos"

    for item_id in _state["items"]:
        r = client.get(_ruta(f"/items/{item_id}/traza"), headers=cod.headers())
        assert r.status_code == 200, f"traza: {r.status_code} {r.text[:400]}"
        cuerpo = r.json()
        assert cuerpo["traza_version"] == "traza_v1"
        assert cuerpo["enunciado"], "la traza deberia traer el enunciado revisado"
        elementos = cuerpo["elementos"]
        assert elementos, "traza vacia: el classifier no leyo eventos del ctr-service"
        assert [e["n"] for e in elementos] == list(range(1, len(elementos) + 1))
        assert {e["tipo"] for e in elementos} <= TIPOS_TRAZA, elementos
        assert elementos[-1]["tipo"] == "fin_cerrado", elementos[-1]
        assert not (_claves_recursivas(cuerpo) & CLAVES_PROHIBIDAS), (
            _claves_recursivas(cuerpo) & CLAVES_PROHIBIDAS
        )
        texto = json.dumps(cuerpo, ensure_ascii=False)
        for marca in ("intento_adverso", "overuse", "jailbreak", "aclaracion_enunciado"):
            assert marca not in texto, f"la traza filtra la marca {marca!r}"
        for episodio in _state["episodios"]:
            assert episodio not in texto, "la traza expone un episode_id real"


@pytest.mark.smoke
def test_etiqueta_con_regimen_derivado_y_cierre(client: httpx.Client) -> None:
    """Etiqueta de cada item: el regimen persistido es el de la regla; cierre
    exitoso y despues ya no se puede guardar."""
    _requiere("clave", "cod", "items")
    cod = _state["cod"]
    for item_id in _state["items"]:
        r = client.put(
            _ruta(f"/items/{item_id}/mi-etiqueta"), json=ETIQUETA_SMOKE, headers=cod.headers()
        )
        assert r.status_code == 200, f"guardar etiqueta: {r.status_code} {r.text[:400]}"
        assert (r.json()["regimen"], r.json()["regimen_regla"]) == ("alto", "alto"), r.json()

    r = client.post(_ruta("/mi-codificacion/cerrar"), headers=cod.headers())
    assert r.status_code == 200, f"cierre: {r.status_code} {r.text[:400]}"

    r = client.put(
        _ruta(f"/items/{_state['items'][0]}/mi-etiqueta"),
        json=ETIQUETA_SMOKE,
        headers=cod.headers(),
    )
    assert (r.status_code, _detalle(r)) == (409, "codificacion_cerrada"), r.text[:300]
    _state["cerrada"] = True


@pytest.mark.smoke
def test_exportacion_solo_investigador_sin_emails(client: httpx.Client) -> None:
    """El investigador exporta una fila por item con el regimen de la regla; el
    codificador recibe 403. Ningun email en el CSV."""
    _requiere("clave", "inv", "cod", "cerrada")
    inv, cod = _state["inv"], _state["cod"]
    params = {"contenido": "etiquetas", "formato": "csv"}

    r = client.get(_ruta("/exportacion"), params=params, headers=cod.headers())
    assert r.status_code == 403, f"codificador exportando: {r.status_code} {r.text[:300]}"

    r = client.get(_ruta("/exportacion"), params=params, headers=inv.headers())
    assert r.status_code == 200, f"exportacion: {r.status_code} {r.text[:300]}"
    filas = list(csv.DictReader(io.StringIO(r.text)))
    assert sorted(f["episode_id"] for f in filas) == sorted(_state["episodios"]), filas
    assert {(f["alias"], f["regimen"], f["dim_d1_valor"]) for f in filas} == {
        ("C1", "alto", "presente")
    }, filas
    assert all(f["cerrada_at"] for f in filas), filas
    assert "@" not in r.text, "la exportacion trae un email"
