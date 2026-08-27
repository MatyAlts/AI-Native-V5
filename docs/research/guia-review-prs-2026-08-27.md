# Guía de review y merge — 6 PRs abiertos

**Fecha:** 27 de agosto de 2026
**Para:** Neyén
**De:** Juani

Hay seis PRs esperando. **Dos están apilados**, así que el orden no es opcional. Abajo va el
orden, y para cada uno qué mirar concretamente — no "revisar el código", sino los dos o tres
puntos donde este PR se puede romper.

---

## Antes de arrancar: tres cosas del repo

**1. `main` no tiene protección de rama.** Se puede mergear con el CI en rojo y un approval
sobrevive a un push posterior sin revisar (pasó en el PR #57). O sea que el gate real sos vos, no
GitHub.

**2. Todos los fixes están verificados por reversión.** La regla de este repo: escribir el test,
romper el fix a propósito, confirmar que el test cae. Cada PR dice qué se rompió y qué cayó. **Si
querés verificar uno, ése es el camino más rápido**: revertí el fix y corré el test que el PR
nombra. Si no falla, el test es vacuo y el PR no sirve.

**3. Nada de esto enciende nada.** Lo de Active-IA sube apagado. Los bugfixes son fixes.

---

## El orden

```
1. #68  ──┐
2. #71  ──┼── independientes, en cualquier orden entre sí
3. #69  ──┘   pero el #69 destraba a los dos de abajo
      ↓
4. #70  ── apilados sobre #69. NO tienen CI hasta que el #69 mergee:
5. #72  ── GitHub los reapunta solo y ahí recién corren los checks
      ↓
6. #66  ── el más grande. Va último porque es el que más tarda en revisar
```

**Empezá por el #68 y el #71.** Son chicos, urgentes y no dependen de nada.

---

## #68 — La entrega que borraba devoluciones

**Tamaño:** chico. Un guard, una función extraída, cuatro tests.
**Urgencia:** 🔴 está pasando en producción ahora.

### Qué hacía

El docente devuelve una entrega para corregir. El alumno entra al episodio **para leer la
devolución**. La hidratación ve el episodio cerrado, llama `onExit()` sola, y el guard viejo
—`draft || returned`— la re-envía. **La devolución desaparece.** Nadie apretó nada.

### Qué mirar

- **Que `draft` siga enviándose.** Para la TP monolítica, cerrar el episodio ES la entrega. Si eso
  se rompe, la card del selector se queda en "Empezar" para todos. Hay un test que lo cubre.
- **Que el default sea no enviar.** Un estado desconocido no dispara envío. Enviar por defecto es
  exactamente como apareció este bug.

### Lo que el PR NO arregla, y está bien

`onExit` se llama en **cinco** lugares y sólo uno significa "el alumno terminó". Los cinco caen en
el mismo `handleExit`. Separar "salgo" de "terminé" es un cambio de diseño del flujo del alumno y
va aparte. Este PR corta la pérdida de datos, que es lo urgente.

---

## #71 — 🔴 Seguridad: seis endpoints sin aislamiento por comisión

**Tamaño:** mediano. Dos helpers, seis endpoints, ~30 tests.
**Urgencia:** 🔴 cualquier docente podía escribir sobre entregas de cualquier comisión.

### La causa

`_assert_can_write` y `_assert_can_read` **sólo frenan a estudiantes**. Para cualquier rol docente
devuelven sin mirar nada. Y como en producción todos los docentes comparten un tenant, **la RLS no
los separa**: aísla tenants, no comisiones.

El `entrega_id` ni siquiera es secreto — viaja en las URLs del web-teacher.

### Qué mirar, en este orden

1. **Que el alumno no quede afuera.** Es el riesgo real del PR. `submit` y `ejercicio` los llama el
   estudiante también, y los alumnos **no están en `usuarios_comision`** (están en
   `inscripciones`). Aplicarles ese guard les daría 403 a todos.
   Por eso existe `_assert_write_scope`, que bifurca. **Verificación rápida:** neutralizá la rama
   docente del guard y corré la suite. Tienen que caer 8 tests, **todos de docente ajeno y ninguno
   de alumno**. Si cae alguno de alumno, el guard está mal.

2. **Dónde va el guard.** En `get_calificacion` va **antes** del lookup de la nota, a propósito: si
   va después, un docente ajeno distingue 403 (ya corregida) de 404 (sin nota) — un oráculo sobre
   el avance de corrección de otra comisión. Hay un test que lo fija.

3. **Que coordinación siga pasando.** `OVERSIGHT_ROLES` corrige cross-comisión a propósito.

### Un commit que parece fuera de lugar y no lo está

Hay un commit que **borra `apps/evaluation-service/tests/__init__.py`**. No es limpieza: sin eso el
CI aborta la colecta de **todo el repo** antes de correr un test. Está explicado en el mensaje del
commit.

---

## #69 — El seq desincronizado del CTR

**Tamaño:** mediano-grande. 9 commits, 13 archivos.
**Urgencia:** alta — borraba trabajo del alumno y marcaba episodios sanos como adulterados.
**⚠️ Este destraba al #70 y al #72.**

### Qué hacía

Cada evento lleva un número de orden que se reserva **antes** de publicar. Si el publish fallaba,
quedaba un hueco. El worker leía el hueco como *"alguien alteró la cadena"* → DLQ →
`integrity_compromised`. Y un episodio marcado así **desaparece de las vistas** de docente y
alumno.

### Qué mirar

- **`XAUTOCLAIM`.** Antes el worker leía con `">"` sin reclamar, así que el retry a DLQ **nunca
  ocurría** y los mensajes quedaban colgados sin que nadie se enterara.
- **Que reponga el contador en vez de borrar la sesión.** Es la decisión de diseño del PR: converge,
  no echa al alumno de su episodio, y no depende de que el frontend colabore.
- **`integrity_compromised` deja de ser terminal.** Un episodio marcado por un hueco vuelve a `open`
  con el evento siguiente.
- **El fix del `prev_chain_hash`** (dictamen CoNaIISI): `verify_chain_integrity` ahora coteja el
  hash persistido contra el real del anterior. Antes, alterar esa columna sin tocar `self_hash` ni
  `chain_hash` pasaba inadvertido.

### Lo que NO cierra — importante que lo leas

- **Mitiga el síntoma de BUG-5, no la raíz.** La raíz va en el #70.
- **Nadie se entera si vuelve a pasar.** La métrica `ctr_worker_xpending_count` reporta a un
  colector OTLP caído. Eso es lo que hizo que esto corriera semanas sin que nadie lo notara.
- **Hay ~10 hallazgos de auditoría abiertos.** El peor es **preexistente y no lo introduce este
  PR**: un alumno puede escribir en el episodio de otro (`/message` y los 8 handlers nunca miran
  `user`). Quedó a la vista porque el heal SÍ valida dueño.

### Al deployar

**No redeployar `ctr-service` ni `tutor-service` en caliente con usuarios activos.** De a un
servicio por vez.

---

## #70 — La raíz del seq quemado, la reflexión y el doble abandono

**Base:** `fix/ctr-seq-desincronizado`. **Mergear el #69 primero.**
**Sin CI hasta entonces** — el workflow sólo corre en PRs que apuntan a `main`. No está roto.

### Qué mirar

**El compare-and-decrement, que es el corazón del PR.** Compensar el seq quemado parece un `DECR` y
listo. **Un `DECR` a secas habría sido peor que el hueco**: si otra corrutina reservó el número
siguiente mientras publicábamos, bajar el contador hace que el evento próximo nazca con un seq **ya
usado** — dos eventos con el mismo número, que es justo lo que el #69 vino a cerrar.

Por eso es un CAS con `WATCH`/`MULTI`: sólo compensa si nadie reservó en el medio. Cuando pierde, el
hueco es real, se loguea, y queda la red del worker.

**El helper único.** Los 16 puntos donde se publica pasan por `_publicar_evento`. Si dependiera de
que cada call-site se acuerde, se rompe en el primero que se agregue.

**Que la reflexión NO use el helper.** Ahí el seq sale de `events_count`, no del contador — no hay
nada que devolver. Ese camino lo cubre la Idempotency-Key.

### Lo que decidió NO hacer, y necesita tu opinión

Se pidió que los eventos de **intento adverso** y **sobreuso** dejaran de tragarse el error. Se hizo
la mitad —el seq vuelve y el fallo se loguea con traceback— pero **la excepción no se propaga**.

El motivo: el **ADR-019 / RN-129** declara explícitamente que la detección adversa *"NO bloquea, el
prompt llega al LLM sin modificar"* y *"falla soft"*. Propagar convertiría un fallo del side-channel
en un prompt abortado para el alumno.

**Si te parece que debería bloquear, hay que tocar el ADR primero.** Se paró a propósito.

---

## #72 — Los cinco bugs del editor

**Base:** `fix/ctr-seq-desincronizado`. **Mergear el #69 primero.** Sin CI hasta entonces.

Cierra BUG-3, 4, 7 y 11. Cuatro salieron del informe de un alumno; el de `tests_ejecutados` es de
integridad de la cadena.

### Qué mirar, por orden de riesgo

1. **El cambio en `packages/ctr-client`** — es un paquete compartido. `tests_ejecutados` no usa el
   endpoint genérico: va a `POST /episodes/{id}/run-tests` porque el backend valida los conteos
   antes de appendear. Se agregó un mapa de rutas. **El `event_type` del contrato CTR no cambia** —
   sólo por dónde se manda. Verificá eso.

2. **El test del evento fantasma.** En BUG-4 el editor se remonta y Monaco re-siembra. Un
   `useEffect(() => editor.setValue(...))` habría emitido un `edicion_codigo` **que el alumno no
   hizo** — evidencia falsa en la cadena de la tesis, peor que el bug original. Se resolvió colgando
   el espejo del listener de Monaco. Hay un test llamado *"el re-montaje NO emite un edicion_codigo
   fantasma"* para que nadie lo reintroduzca. **No lo borres.**

3. **"Restaurar plantilla inicial".** El fix de BUG-4 la rompía como efecto colateral; se cerró en
   el mismo commit congelando la plantilla aparte.

4. **La infraestructura de test nueva.** Monaco ni siquiera resuelve bajo Vitest. Se agregó un mock
   enchufado por `test.alias` — **sólo en tests, el bundle usa el real**. Verificá que el alias no
   se filtre al build.

### Nota honesta del PR

El test de BUG-3 (la "f" de los f-strings) es una **aserción de configuración**, no una simulación
del tipeo: Monaco real no corre en jsdom. Es todo lo que ese bug da.

---

## #66 — Active-IA, corrección asistida por ejercicio

**Tamaño:** el más grande. 28 commits, 86 archivos, +15.000 líneas.
**Se deploya APAGADO** (`ACTIVEIA_ENABLED=false`). Mergear ≠ encender.

Va último porque es el que más tiempo de review pide. No bloquea a nadie.

### Las dos reglas que no se negocian

1. **Un fallo de infraestructura NUNCA se convierte en nota.** Si el motor está saturado, la
   respuesta es "no se pudo", nunca un número. La base lo obliga con un CHECK.
2. **La plataforma nunca escribe en `calificaciones`.** "Usar como base" rellena el formulario y
   **no guarda**. La nota la pone una persona.

La regla 2 no es prudencia genérica: Active-IA tiene modos de fallo medidos — le puso 100/100 a una
entrega donde nada estaba vinculado, y un bug suyo dejó a una alumna desaprobada el 04/08.

### Qué mirar

- **Que el ejercicio viaje en la URL y no haya campo de comisión.** Eso cierra el «`comision_id` mal
  cableado»: la ruta pasaba `activeia_comision_id=vinculo.external_ref`, y ese campo guarda el UUID
  del **ejercicio**. Le mandábamos un id de ejercicio en el campo de una comisión — **el nombre del
  parámetro mentía**, y por eso sobrevivió a cinco rondas de review.
- **Que no vuelva el 409 ni el poll.** Hay tests que fallan si alguien los reintroduce.
- **`criterios_sin_ejecucion`** debe llegar hasta el panel: los criterios que no se pudieron
  verificar dicen "sin verificar", no un cero pelado.

### ⚠️ Antes de deployar esto

- **La migración `20260818_0002` NO está aplicada en producción** (verificado: la tabla
  `activeia_rubrica_ejercicio` no existe). El deploy tiene que correr las migraciones o el servicio
  levanta y falla al primer query.
- **`ACTIVEIA_MASTER_KEY`** ya está cargada en EasyPanel.
- **No redeployar `evaluation-service` en caliente**: la corrección corre en `BackgroundTasks` sin
  cola durable.

---

## 🚨 Antes de CUALQUIER deploy, de cualquiera de estos PRs

**DNS permanente en EasyPanel** (`1.1.1.1`/`8.8.8.8` en el servicio, o `daemon.json` del host).

El `/etc/hosts` del api-gateway **se borra al recrear el contenedor**, y deployar lo recrea. Es lo
que tiró producción la mañana del 24/08.

Y el **backup remoto** sigue abierto.

---

## Tres bugs nuevos que aparecieron auditando y NO están en ningún PR

Se dejaron sin arreglar a propósito: son otros bugs, van a su propio PR.

**1. 🔴 `PATCH /entregas/{id}/ejercicio/{orden}` devuelve 200 y no persiste nada.**
Sólo guarda cuando **agrega** un ejercicio; cualquier actualización se pierde.
`estados = list(entrega.ejercicio_estados)` es copia superficial, así que mutar el dict de adentro
muta también el valor ya cargado — SQLAlchemy no ve cambio neto y no emite el `UPDATE`.
**La reapertura docente del 2026-06-19 está rota en producción desde entonces**, y nadie lo reportó
porque no falla: contesta 200.

**2. 🔴 Un alumno puede rutear su entrega a la cola del docente equivocado.**
`create_entrega` acepta un `comision_id` que no es el de la TP. El FK garantiza que la comisión
existe, no que corresponda. Como la cola filtra por ese campo, puede mandarla a otra comisión — o
esconderla de la suya.

**3. 🟠 `run-tests` no tiene el auto-heal** que sí tienen los otros eventos del alumno. Si se le
vence el TTL de la sesión justo al correr tests, ese evento se pierde donde los otros se recuperan
— y es el que alimenta N3/N4.

---

## Y cuatro cosas que necesitan una decisión, no un fix

Ningún PR las toca a propósito.

- **FEAT-A (reabrir/rehacer TP)** — si "rehacer" implica una **segunda nota**, hay que versionar
  calificaciones: hoy hay un UNIQUE de una por entrega. Es un cambio de modelo de datos.
- **ED-1 (copy/paste interno)**, **PAPER-1 (indeterminado como estado)** y **PAPER-2 (revisión
  humana terminal)** — los tres obligan a un ADR **y a bumpear el `LABELER_VERSION`**, lo que
  dispara **re-clasificación masiva** de los datos de la tesis.
