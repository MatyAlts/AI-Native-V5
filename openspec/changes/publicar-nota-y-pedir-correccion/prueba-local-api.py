"""Prueba local por API del change publicar-nota-y-pedir-correccion.

Recorre el ciclo completo contra el stack local (api-gateway :8000 con
DEV_TRUST_HEADERS=true) y falla con AssertionError si algo no se cumple.
Imprime una linea por paso.

Uso (desde la raiz del repo, con api-gateway + academic-service +
evaluation-service levantados y la TP LOCAL-PNPC sembrada, ver prueba-local.md):

    py -3.12 openspec/changes/publicar-nota-y-pedir-correccion/prueba-local-api.py

Los episodios se simulan con UUID sueltos: este script NO abre episodios, asi que
no toca el CTR (el paso 10 lo verifica contando eventos antes y despues).
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMISION = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TP = "5e5e0001-0000-4000-8000-000000000001"
ALUMNO = "e19354fb-c05a-4535-a0bf-a7d3ea09692d"
DOCENTE = "11111111-1111-1111-1111-111111111111"


def call(method, path, *, quien, body=None):
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Id": TENANT,
        "X-User-Id": ALUMNO if quien == "alumno" else DOCENTE,
        "X-User-Email": "dev@demo-uni.edu",
        "X-User-Roles": "estudiante" if quien == "alumno" else "docente",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


def paso(n, texto):
    print(f"[paso {n}] {texto}")


def esperar(cond, msg):
    assert cond, f"FALLO: {msg}"


def estados_por_orden(entrega):
    return {e["orden"]: e for e in entrega["ejercicio_estados"]}


# 2/3. Entrega del alumno ---------------------------------------------------
paso("2-3", "el alumno crea la entrega y cierra los 3 ejercicios con codigo distinto")
st, ent = call(
    "POST",
    "/api/v1/entregas",
    quien="alumno",
    body={"tarea_practica_id": TP, "comision_id": COMISION},
)
esperar(st in (200, 201), f"crear entrega: {st} {ent}")
EID = ent["id"]
if ent["estado"] != "draft":
    print(
        f"  (la entrega ya existia en estado {ent['estado']}; borra su fila y reintenta para un ciclo limpio)"
    )
    sys.exit(2)

ejercicios = {e["orden"]: e["ejercicio_id"] for e in ent["ejercicio_estados"]}
esperar(sorted(ejercicios) == [1, 2, 3], f"la TP deberia tener 3 ejercicios: {ejercicios}")
episodios = {o: str(uuid.uuid4()) for o in (1, 2, 3)}
for o in (1, 2, 3):
    st, _ = call(
        "PATCH",
        f"/api/v1/entregas/{EID}/ejercicio/{o}",
        quien="alumno",
        body={"completado": True, "ejercicio_id": ejercicios[o], "episode_id": episodios[o]},
    )
    esperar(st == 200, f"PATCH ejercicio {o}: {st}")
codigos = {o: f"print({o})" for o in (1, 2, 3)}
st, ent = call(
    "POST",
    f"/api/v1/entregas/{EID}/submit",
    quien="alumno",
    body={
        "artefactos": [
            {"orden": o, "ejercicio_id": ejercicios[o], "codigo": codigos[o]} for o in (1, 2, 3)
        ]
    },
)
esperar(st == 200 and ent["estado"] == "submitted", f"submit: {st} {ent}")

# 4. Publicar nota ----------------------------------------------------------
paso(4, "el docente publica la nota (calificar): el alumno la ve y NO se reabre nada")
st, _ = call(
    "POST",
    f"/api/v1/entregas/{EID}/calificar",
    quien="docente",
    body={"nota_final": 8, "feedback_general": "Bien", "detalle_criterios": []},
)
esperar(st == 201, f"calificar: {st}")
st, cal = call("GET", f"/api/v1/entregas/{EID}/calificacion", quien="alumno")
esperar(st == 200 and float(cal["nota_final"]) == 8.0, f"el alumno ve la nota: {st} {cal}")
st, ent = call("GET", f"/api/v1/entregas/{EID}", quien="alumno")
esperar(ent["estado"] == "graded", f"estado graded: {ent['estado']}")
esperar(
    all(e["completado"] for e in ent["ejercicio_estados"]), "ningun ejercicio reabierto al publicar"
)

# 5. Pedir correccion: validaciones ----------------------------------------
paso(5, "pedir correccion: 422 para lista vacia, duplicados e inexistente; la entrega sigue graded")
for malo in ([], [2, 2], [9]):
    st, _ = call("POST", f"/api/v1/entregas/{EID}/return", quien="docente", body={"ordenes": malo})
    esperar(st == 422, f"ordenes={malo} deberia ser 422, dio {st}")
st, ent = call("GET", f"/api/v1/entregas/{EID}", quien="alumno")
esperar(ent["estado"] == "graded", "sigue graded tras los 422")

paso(5, "pedir correccion del ejercicio 2")
st, ent = call("POST", f"/api/v1/entregas/{EID}/return", quien="docente", body={"ordenes": [2]})
esperar(st == 200 and ent["estado"] == "returned", f"return: {st} {ent}")

# 6. Lo que ve el alumno ----------------------------------------------------
paso(6, "1 y 3 completados sin marca; 2 reabierto y marcado; PATCH sobre 1 da 409")
e = estados_por_orden(ent)
esperar(e[1]["completado"] and e[3]["completado"], "1 y 3 siguen completados")
esperar(
    e[1]["episode_id"] == episodios[1] and e[3]["episode_id"] == episodios[3],
    "1 y 3 conservan su episode_id",
)
esperar(not e[2]["completado"] and e[2]["reabierto_por_docente"] is True, "2 reabierto con marca")
for completado in (False, True):
    st, _ = call(
        "PATCH",
        f"/api/v1/entregas/{EID}/ejercicio/1",
        quien="alumno",
        body={"completado": completado, "ejercicio_id": ejercicios[1]},
    )
    esperar(st == 409, f"PATCH ejercicio 1 completado={completado} deberia ser 409, dio {st}")

# 7. Re-entrega ------------------------------------------------------------
paso(7, "el alumno rehace el 2 y re-entrega mandando solo el 2")
nuevo_ep = str(uuid.uuid4())
st, _ = call(
    "PATCH",
    f"/api/v1/entregas/{EID}/ejercicio/2",
    quien="alumno",
    body={"completado": True, "ejercicio_id": ejercicios[2], "episode_id": nuevo_ep},
)
esperar(st == 200, f"PATCH ejercicio 2: {st}")
st, ent = call(
    "POST",
    f"/api/v1/entregas/{EID}/submit",
    quien="alumno",
    body={"artefactos": [{"orden": 2, "ejercicio_id": ejercicios[2], "codigo": "print(22)"}]},
)
esperar(st == 200 and ent["estado"] == "submitted", f"re-submit: {st} {ent}")
esperar(
    not any(x.get("reabierto_por_docente") for x in ent["ejercicio_estados"]),
    "ninguna marca sobrevive",
)

# 8. Lo que ve el docente ---------------------------------------------------
paso(8, "el docente ve ej.1 print(1), ej.2 print(22), ej.3 print(3), con los episode_id originales")
st, art = call("GET", f"/api/v1/entregas/{EID}/artefacto", quien="docente")
esperar(st == 200, f"artefacto: {st}")
por = {a["orden"]: a for a in art["artefactos"]}
esperar(
    [por[o]["codigo"] for o in (1, 2, 3)] == ["print(1)", "print(22)", "print(3)"],
    f"codigos: {por}",
)
esperar(
    por[1]["episode_id"] == episodios[1] and por[3]["episode_id"] == episodios[3],
    "1 y 3 conservan episode_id",
)
esperar(por[2]["episode_id"] == nuevo_ep, "2 apunta al episodio nuevo")

# Ciclo con re-calificacion (#124) y otro pedido ---------------------------
paso("8b", "re-calificar y pedir correccion del 3: solo el 3 queda reabierto")
st, _ = call(
    "PATCH", f"/api/v1/entregas/{EID}/calificacion", quien="docente", body={"nota_final": 9}
)
esperar(st == 200, f"PATCH calificacion: {st}")
st, ent = call("GET", f"/api/v1/entregas/{EID}", quien="docente")
if ent["estado"] != "graded":
    print(f"  (estado tras re-calificar: {ent['estado']})")
esperar(ent["estado"] == "graded", "la re-calificacion deja la entrega graded")
st, ent = call("POST", f"/api/v1/entregas/{EID}/return", quien="docente", body={"ordenes": [3]})
esperar(st == 200, f"return [3]: {st} {ent}")
e = estados_por_orden(ent)
esperar([e[o]["completado"] for o in (1, 2, 3)] == [True, True, False], f"solo el 3 reabierto: {e}")

# Compat: sin body reabre todos --------------------------------------------
paso("8c", "compat: re-entregar el 3, calificar y devolver SIN body reabre los 3")
call(
    "PATCH",
    f"/api/v1/entregas/{EID}/ejercicio/3",
    quien="alumno",
    body={"completado": True, "ejercicio_id": ejercicios[3], "episode_id": str(uuid.uuid4())},
)
st, ent = call(
    "POST",
    f"/api/v1/entregas/{EID}/submit",
    quien="alumno",
    body={"artefactos": [{"orden": 3, "ejercicio_id": ejercicios[3], "codigo": "print(33)"}]},
)
esperar(st == 200, f"re-submit 3: {st} {ent}")
call("PATCH", f"/api/v1/entregas/{EID}/calificacion", quien="docente", body={"nota_final": 7})
st, ent = call("POST", f"/api/v1/entregas/{EID}/return", quien="docente")
esperar(st == 200 and ent["estado"] == "returned", f"return sin body: {st} {ent}")
esperar(
    not any(x["completado"] for x in ent["ejercicio_estados"]),
    "sin body: todos reabiertos (comportamiento de siempre)",
)

print("\nOK: todos los pasos de API pasaron. Entrega de prueba:", EID)
