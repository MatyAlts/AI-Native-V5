"""Esquema de formulario del codebook, régimen según la regla y completitud (design D9).

Funciones PURAS: no tocan base ni HTTP. El código no trae texto, claves ni
reglas del codebook: todo llega en el esquema de cada versión (spec
codebook-versionado, "Sin contenido de codebook en el código").

Meta-esquema cerrado (claves desconocidas = error en cualquier nivel):

- `dimensiones` (1 a 8): `{clave, nombre, valores[2..6], cita_requerida_si[]}`.
- `regimenes` (2 a 6): `{clave, nombre}`.
- `regimen_evidencia_insuficiente`: una de las claves de `regimenes`.
- `regimenes_exentos` (opcional, default `[regimen_evidencia_insuficiente]`):
  regímenes que el codificador elige explícitamente y que la regla no deriva;
  debe incluir el de evidencia insuficiente.
- `dimensiones_opcionales_si_regimen`, `notas_obligatorias_si_regimen`
  (opcionales): claves de régimen.
- `marca_frontera` (bool, opcional) y `notas_obligatorias_si_frontera` (bool,
  opcional, exige `marca_frontera`). Esta última clave no está nombrada en D9:
  la agrega la construcción para el escenario "Notas obligatorias" de la spec
  (frontera sin notas cuando el esquema las exige). Declarado en el informe.
- `confianza` (opcional): `null` o `{valores[1..], obligatoria}`.
- `reglas_regimen` (opcional, default `[]`): lista ordenada `{regimen,
  condicion}`; `condicion` es una conjunción (lista no vacía) de cláusulas, cada
  cláusula una disyunción (lista no vacía) de átomos `{dimension, en[],
  con_cita?}`. Gana la primera regla cuya condición se cumple.
- `regimen_por_defecto`: obligatorio si hay reglas, prohibido si no hay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_CLAVE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

_CLAVES_ESQUEMA = frozenset(
    {
        "dimensiones",
        "regimenes",
        "regimen_evidencia_insuficiente",
        "regimenes_exentos",
        "dimensiones_opcionales_si_regimen",
        "notas_obligatorias_si_regimen",
        "marca_frontera",
        "notas_obligatorias_si_frontera",
        "confianza",
        "reglas_regimen",
        "regimen_por_defecto",
    }
)
_OBLIGATORIAS = ("dimensiones", "regimenes", "regimen_evidencia_insuficiente")
_CLAVES_DIMENSION = frozenset({"clave", "nombre", "valores", "cita_requerida_si"})
_CLAVES_REGIMEN = frozenset({"clave", "nombre"})
_CLAVES_CONFIANZA = frozenset({"valores", "obligatoria"})
_CLAVES_REGLA = frozenset({"regimen", "condicion"})
_CLAVES_ATOMO_OBLIGATORIAS = frozenset({"dimension", "en"})
_CLAVES_ATOMO = _CLAVES_ATOMO_OBLIGATORIAS | {"con_cita"}


def _es_texto(valor: Any) -> bool:
    return isinstance(valor, str) and valor.strip() != ""


def _es_clave_de(valor: Any, claves: set[str] | dict[str, Any]) -> bool:
    """`valor in claves` solo para texto: una lista u objeto del JSON no es
    hashable y `in` sobre un set o dict lanzaría TypeError (verify-1, F2/F3)."""
    return isinstance(valor, str) and valor in claves


def _lista_de_textos_unicos(valor: Any) -> bool:
    return (
        isinstance(valor, list)
        and all(_es_texto(v) for v in valor)
        and len(set(valor)) == len(valor)
    )


def _claves_cerradas(
    obj: Any, permitidas: frozenset[str], obligatorias: frozenset[str], donde: str
) -> list[str]:
    if not isinstance(obj, dict):
        return [f"{donde}: tiene que ser un objeto"]
    errores = [f"{donde}: clave desconocida '{k}'" for k in sorted(set(obj) - permitidas)]
    errores += [f"{donde}: falta '{k}'" for k in sorted(obligatorias - set(obj))]
    return errores


def _validar_dimensiones(dimensiones: Any) -> tuple[list[str], dict[str, list[str]]]:
    if not isinstance(dimensiones, list) or not 1 <= len(dimensiones) <= 8:
        return ["dimensiones: tiene que ser una lista de 1 a 8 entradas"], {}
    errores: list[str] = []
    valores_por_dim: dict[str, list[str]] = {}
    for i, dim in enumerate(dimensiones):
        donde = f"dimensiones[{i}]"
        malas = _claves_cerradas(dim, _CLAVES_DIMENSION, _CLAVES_DIMENSION, donde)
        if malas:
            errores += malas
            continue
        clave = dim["clave"]
        if not isinstance(clave, str) or not _CLAVE.match(clave):
            errores.append(f"{donde}: clave inválida")
            continue
        donde = f"dimension '{clave}'"
        if clave in valores_por_dim:
            errores.append(f"{donde}: clave repetida")
        if not _es_texto(dim["nombre"]):
            errores.append(f"{donde}: nombre vacío")
        valores = dim["valores"]
        if not _lista_de_textos_unicos(valores) or not 2 <= len(valores) <= 6:
            errores.append(f"{donde}: 'valores' tiene que tener de 2 a 6 textos distintos")
            valores = valores if isinstance(valores, list) else []
        cita = dim["cita_requerida_si"]
        if not isinstance(cita, list) or any(v not in valores for v in cita):
            errores.append(f"{donde}: 'cita_requerida_si' solo admite valores de la dimensión")
        valores_por_dim[clave] = [v for v in valores if isinstance(v, str)]
    return errores, valores_por_dim


def _validar_regimenes(regimenes: Any) -> tuple[list[str], set[str]]:
    if not isinstance(regimenes, list) or not 2 <= len(regimenes) <= 6:
        return ["regimenes: tiene que ser una lista de 2 a 6 entradas"], set()
    errores: list[str] = []
    claves: set[str] = set()
    for i, reg in enumerate(regimenes):
        donde = f"regimenes[{i}]"
        malas = _claves_cerradas(reg, _CLAVES_REGIMEN, _CLAVES_REGIMEN, donde)
        if malas:
            errores += malas
            continue
        if not isinstance(reg["clave"], str) or not _CLAVE.match(reg["clave"]):
            errores.append(f"{donde}: clave inválida")
            continue
        if reg["clave"] in claves:
            errores.append(f"{donde}: clave repetida")
        if not _es_texto(reg["nombre"]):
            errores.append(f"{donde}: nombre vacío")
        claves.add(reg["clave"])
    return errores, claves


def _validar_atomo(atomo: Any, donde: str, valores_por_dim: dict[str, list[str]]) -> list[str]:
    malas = _claves_cerradas(atomo, _CLAVES_ATOMO, _CLAVES_ATOMO_OBLIGATORIAS, donde)
    if malas:
        return malas
    errores: list[str] = []
    dimension = atomo["dimension"]
    if not _es_clave_de(dimension, valores_por_dim):
        return [f"{donde}: dimensión inexistente '{dimension}'"]
    en = atomo["en"]
    if not _lista_de_textos_unicos(en) or not en:
        errores.append(f"{donde}: 'en' tiene que ser una lista no vacía de valores")
    elif any(v not in valores_por_dim[dimension] for v in en):
        errores.append(f"{donde}: valor inexistente para '{dimension}'")
    if "con_cita" in atomo and not isinstance(atomo["con_cita"], bool):
        errores.append(f"{donde}: 'con_cita' tiene que ser booleano")
    return errores


def _validar_reglas(
    reglas: Any,
    valores_por_dim: dict[str, list[str]],
    regimenes: set[str],
    exentos: set[str],
) -> list[str]:
    if not isinstance(reglas, list):
        return ["reglas_regimen: tiene que ser una lista"]
    errores: list[str] = []
    for i, regla in enumerate(reglas):
        donde = f"reglas_regimen[{i}]"
        malas = _claves_cerradas(regla, _CLAVES_REGLA, _CLAVES_REGLA, donde)
        if malas:
            errores += malas
            continue
        if not _es_clave_de(regla["regimen"], regimenes):
            errores.append(f"{donde}: régimen inexistente '{regla['regimen']}'")
        elif regla["regimen"] in exentos:
            errores.append(f"{donde}: un régimen exento no se deriva por regla")
        condicion = regla["condicion"]
        if not isinstance(condicion, list) or not condicion:
            errores.append(f"{donde}: 'condicion' tiene que ser una lista no vacía de cláusulas")
            continue
        for j, clausula in enumerate(condicion):
            if not isinstance(clausula, list) or not clausula:
                errores.append(f"{donde}.condicion[{j}]: cláusula vacía o inválida")
                continue
            for k, atomo in enumerate(clausula):
                errores += _validar_atomo(atomo, f"{donde}.condicion[{j}][{k}]", valores_por_dim)
    return errores


def _validar_lista_de_regimenes(valor: Any, nombre: str, regimenes: set[str]) -> list[str]:
    if not isinstance(valor, list) or not all(_es_clave_de(v, regimenes) for v in valor):
        return [f"{nombre}: solo admite claves de régimen declaradas"]
    return []


def _validar_confianza(confianza: Any) -> list[str]:
    if confianza is None:
        return []
    malas = _claves_cerradas(confianza, _CLAVES_CONFIANZA, _CLAVES_CONFIANZA, "confianza")
    if malas:
        return malas
    errores: list[str] = []
    if not _lista_de_textos_unicos(confianza["valores"]) or not confianza["valores"]:
        errores.append("confianza: 'valores' tiene que ser una lista no vacía de textos distintos")
    if not isinstance(confianza["obligatoria"], bool):
        errores.append("confianza: 'obligatoria' tiene que ser booleano")
    return errores


def validar_esquema(esquema: Any) -> list[str]:
    """Errores del esquema contra el meta-esquema; lista vacía si es válido."""
    malas = _claves_cerradas(esquema, _CLAVES_ESQUEMA, frozenset(_OBLIGATORIAS), "esquema")
    if malas:
        return malas

    errores, valores_por_dim = _validar_dimensiones(esquema["dimensiones"])
    errores_reg, regimenes = _validar_regimenes(esquema["regimenes"])
    errores += errores_reg

    ei = esquema["regimen_evidencia_insuficiente"]
    if not _es_clave_de(ei, regimenes):
        errores.append("regimen_evidencia_insuficiente: no es uno de los regímenes declarados")

    exentos_valor = esquema.get("regimenes_exentos", [ei])
    errores += _validar_lista_de_regimenes(exentos_valor, "regimenes_exentos", regimenes)
    exentos = (
        {v for v in exentos_valor if isinstance(v, str)}
        if isinstance(exentos_valor, list)
        else set()
    )
    if not _es_clave_de(ei, exentos):
        errores.append("regimenes_exentos: tiene que incluir el de evidencia insuficiente")

    for nombre in ("dimensiones_opcionales_si_regimen", "notas_obligatorias_si_regimen"):
        errores += _validar_lista_de_regimenes(esquema.get(nombre, []), nombre, regimenes)

    marca = esquema.get("marca_frontera", False)
    notas_frontera = esquema.get("notas_obligatorias_si_frontera", False)
    if not isinstance(marca, bool):
        errores.append("marca_frontera: tiene que ser booleano")
    if not isinstance(notas_frontera, bool):
        errores.append("notas_obligatorias_si_frontera: tiene que ser booleano")
    elif notas_frontera and marca is not True:
        errores.append("notas_obligatorias_si_frontera: exige marca_frontera")

    errores += _validar_confianza(esquema.get("confianza"))

    reglas = esquema.get("reglas_regimen", [])
    errores += _validar_reglas(reglas, valores_por_dim, regimenes, exentos)
    tiene_reglas = isinstance(reglas, list) and len(reglas) > 0
    por_defecto = esquema.get("regimen_por_defecto")
    if tiene_reglas:
        if not _es_clave_de(por_defecto, regimenes):
            errores.append("regimen_por_defecto: obligatorio y declarado si hay reglas")
        elif por_defecto in exentos:
            errores.append("regimen_por_defecto: no puede ser un régimen exento")
    elif "regimen_por_defecto" in esquema:
        errores.append("regimen_por_defecto: solo tiene sentido con reglas")
    return errores


# ── Respuesta, régimen según la regla y cierre ────────────────────────────

_CLAVES_PEDIDO = frozenset(
    {"respuestas", "regimen", "regimen_propuesto", "es_frontera", "confianza", "notas"}
)
_CLAVES_RESPUESTA = frozenset({"valor", "cita"})


class PedidoInvalidoError(Exception):
    """Pedido rechazado. `status` 400: fuera del esquema (clave, valor o formato).
    `status` 422: régimen incoherente con la regla o régimen propuesto sin nota."""

    def __init__(self, status: int, errores: list[str]) -> None:
        super().__init__("; ".join(errores))
        self.status = status
        self.errores = errores


@dataclass(frozen=True)
class Evaluacion:
    """Lo que se persiste de una etiqueta o respuesta de entrenamiento (D9)."""

    respuestas: dict[str, dict[str, str | None]]
    regimen: str | None
    regimen_regla: str | None
    regimen_propuesto: str | None
    es_frontera: bool
    confianza: str | None
    notas: str | None

    @property
    def disiente_de_regla(self) -> bool:
        """Derivado, nunca persistido: hay propuesto y difiere del régimen."""
        return self.regimen_propuesto is not None and self.regimen_propuesto != self.regimen


def _vacio(texto: str | None) -> bool:
    return texto is None or texto.strip() == ""


def _dimensiones_referenciadas(reglas: list[dict[str, Any]]) -> set[str]:
    return {
        atomo["dimension"]
        for regla in reglas
        for clausula in regla["condicion"]
        for atomo in clausula
    }


def _atomo_se_cumple(atomo: dict[str, Any], respuestas: dict[str, Any]) -> bool:
    respuesta = respuestas.get(atomo["dimension"]) or {}
    if respuesta.get("valor") not in atomo["en"]:
        return False
    return not (atomo.get("con_cita") is True and _vacio(respuesta.get("cita")))


def derivar_regimen(esquema: dict[str, Any], respuestas: dict[str, Any]) -> str | None:
    """Régimen que da la regla sobre las dimensiones, o None.

    None si el esquema no tiene reglas o si alguna dimensión referenciada por
    CUALQUIER regla no tiene valor (no se evalúa con información parcial).
    Si no, el de la primera regla cuya condición (conjunción de disyunciones)
    se cumple, o `regimen_por_defecto`."""
    reglas = esquema.get("reglas_regimen", [])
    if not reglas:
        return None
    for dimension in _dimensiones_referenciadas(reglas):
        if (respuestas.get(dimension) or {}).get("valor") is None:
            return None
    for regla in reglas:
        if all(
            any(_atomo_se_cumple(atomo, respuestas) for atomo in clausula)
            for clausula in regla["condicion"]
        ):
            return regla["regimen"]
    return esquema["regimen_por_defecto"]


def _normalizar_respuestas(esquema: dict[str, Any], crudas: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(crudas, dict):
        raise PedidoInvalidoError(400, ["respuestas: tiene que ser un objeto"])
    valores_por_dim = {d["clave"]: d["valores"] for d in esquema["dimensiones"]}
    errores: list[str] = []
    normalizadas: dict[str, dict[str, Any]] = {}
    for clave, respuesta in crudas.items():
        if clave not in valores_por_dim:
            errores.append(f"respuestas: dimensión desconocida '{clave}'")
            continue
        if not isinstance(respuesta, dict) or set(respuesta) - _CLAVES_RESPUESTA:
            errores.append(f"respuestas.{clave}: formato {{valor, cita}}")
            continue
        valor = respuesta.get("valor")
        cita = respuesta.get("cita")
        if valor is not None and valor not in valores_por_dim[clave]:
            errores.append(f"respuestas.{clave}: valor fuera del esquema")
        if cita is not None and not isinstance(cita, str):
            errores.append(f"respuestas.{clave}: la cita es texto")
        normalizadas[clave] = {"valor": valor, "cita": cita}
    if errores:
        raise PedidoInvalidoError(400, errores)
    return normalizadas


def _errores_de_campos(
    esquema: dict[str, Any],
    regimenes: set[str],
    pedido_regimen: Any,
    propuesto: Any,
    es_frontera: Any,
) -> list[str]:
    errores: list[str] = []
    if pedido_regimen is not None and not _es_clave_de(pedido_regimen, regimenes):
        errores.append("regimen: fuera del esquema")
    if propuesto is not None and not _es_clave_de(propuesto, regimenes):
        errores.append("regimen_propuesto: fuera del esquema")
    if not isinstance(es_frontera, bool):
        errores.append("es_frontera: tiene que ser booleano")
    elif es_frontera and esquema.get("marca_frontera") is not True:
        errores.append("es_frontera: el esquema no ofrece la marca de frontera")
    return errores


def evaluar_pedido(esquema: dict[str, Any], pedido: dict[str, Any]) -> Evaluacion:
    """Valida un guardado (parcial o no) contra el esquema y fija el régimen.

    - `regimen` persistido: el de la regla; o un exento elegido explícitamente;
      o, sin reglas, el que elige el codificador.
    - `regimen_regla`: el de la regla siempre que sea calculable, aun con exento.
    - 422 si el pedido trae un régimen no exento distinto del derivado o con
      dimensiones incompletas, o un `regimen_propuesto` sin nota.
    """
    if not isinstance(pedido, dict):
        raise PedidoInvalidoError(400, ["pedido: tiene que ser un objeto"])
    desconocidas = sorted(set(pedido) - _CLAVES_PEDIDO)
    if desconocidas:
        raise PedidoInvalidoError(400, [f"pedido: clave desconocida '{k}'" for k in desconocidas])

    respuestas = _normalizar_respuestas(esquema, pedido.get("respuestas", {}))
    regimenes = {r["clave"] for r in esquema["regimenes"]}
    exentos = set(esquema.get("regimenes_exentos", [esquema["regimen_evidencia_insuficiente"]]))
    pedido_regimen = pedido.get("regimen")
    propuesto = pedido.get("regimen_propuesto")
    es_frontera = pedido.get("es_frontera", False)
    confianza = pedido.get("confianza")
    notas = pedido.get("notas")
    errores = _errores_de_campos(esquema, regimenes, pedido_regimen, propuesto, es_frontera)
    escala = esquema.get("confianza")
    if confianza is not None and (escala is None or confianza not in escala["valores"]):
        errores.append("confianza: fuera del esquema")
    if notas is not None and not isinstance(notas, str):
        errores.append("notas: tiene que ser texto")
    if errores:
        raise PedidoInvalidoError(400, errores)

    regimen_regla = derivar_regimen(esquema, respuestas)
    hay_reglas = bool(esquema.get("reglas_regimen"))
    if pedido_regimen in exentos or not hay_reglas:
        regimen = pedido_regimen
    elif pedido_regimen is None:
        regimen = regimen_regla
    elif regimen_regla is None:
        raise PedidoInvalidoError(
            422, ["regimen: con dimensiones incompletas solo se admite un régimen exento"]
        )
    elif pedido_regimen != regimen_regla:
        raise PedidoInvalidoError(
            422, [f"regimen: la regla da '{regimen_regla}'; para discrepar usar regimen_propuesto"]
        )
    else:
        regimen = regimen_regla

    if propuesto is not None and _vacio(notas):
        raise PedidoInvalidoError(422, ["notas: obligatorias al proponer un régimen"])

    return Evaluacion(
        respuestas=respuestas,
        regimen=regimen,
        regimen_regla=regimen_regla,
        regimen_propuesto=propuesto,
        es_frontera=es_frontera,
        confianza=confianza,
        notas=notas,
    )


def errores_respuesta_esperada(esquema: dict[str, Any], esperada: Any) -> list[str]:
    """Motivos por los que la respuesta esperada de un ancla no vale contra
    `esquema`; lista vacía si vale.

    Misma semántica que el etiquetado (`evaluar_pedido`): dimensiones y valores
    del esquema, régimen no exento igual al que da la regla, exento explícito
    permitido. Además, el régimen GUARDADO tiene que ser el que la regla da hoy:
    un ancla guardada con régimen nulo (dimensiones incompletas para la regla
    anterior) no vale si la regla actual ya deriva uno."""
    try:
        ev = evaluar_pedido(esquema, esperada)
    except PedidoInvalidoError as exc:
        return exc.errores
    guardado = esperada.get("regimen")
    if ev.regimen != guardado:
        return [f"regimen: el ancla espera '{guardado}' y la regla da '{ev.regimen}'"]
    return []


def motivos_ancla_para_congelar(esquema: dict[str, Any], esperada: Any) -> list[str]:
    """Por qué un ancla impide congelar contra `esquema`; lista vacía si no.

    Primero validez (`errores_respuesta_esperada`); si vale, completitud con la
    MISMA regla que el cierre de una codificación (`faltantes_cierre`), cada
    código con el prefijo `incompleta:` (decisión del orquestador, verify-2 O1)."""
    errores = errores_respuesta_esperada(esquema, esperada)
    if errores:
        return errores
    ev = evaluar_pedido(esquema, esperada)
    return [f"incompleta: {falta}" for falta in faltantes_cierre(esquema, ev)]


def faltantes_cierre(esquema: dict[str, Any], ev: Evaluacion) -> list[str]:
    """Qué le falta a una etiqueta para poder cerrar (lista vacía: completa).

    Formato estable: `regimen`, `dimension:<clave>`, `cita:<clave>`, `notas`,
    `confianza`. Una cita con solo espacios cuenta como vacía."""
    faltan: list[str] = []
    if ev.regimen is None:
        faltan.append("regimen")
    exceptuadas = ev.regimen in esquema.get("dimensiones_opcionales_si_regimen", [])
    for dim in esquema["dimensiones"]:
        respuesta = ev.respuestas.get(dim["clave"]) or {}
        valor = respuesta.get("valor")
        if valor is None:
            if not exceptuadas:
                faltan.append(f"dimension:{dim['clave']}")
            continue
        if valor in dim["cita_requerida_si"] and _vacio(respuesta.get("cita")):
            faltan.append(f"cita:{dim['clave']}")
    notas_exigidas = (
        ev.regimen in esquema.get("notas_obligatorias_si_regimen", [])
        or (ev.es_frontera and esquema.get("notas_obligatorias_si_frontera") is True)
        or ev.regimen_propuesto is not None
    )
    if notas_exigidas and _vacio(ev.notas):
        faltan.append("notas")
    escala = esquema.get("confianza")
    if escala is not None and escala["obligatoria"] and ev.confianza is None:
        faltan.append("confianza")
    return faltan
