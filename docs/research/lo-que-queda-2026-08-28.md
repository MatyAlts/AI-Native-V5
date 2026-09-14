# Todo lo que queda — para Neyén

**Fecha:** 28 de agosto de 2026
**De:** Juani
**Estado de `main`:** `ab7f0f3` (+37 commits desde `166619e`)

Este es el documento único. Reemplaza al handoff de las ramas trabadas: acá está **todo** lo que
falta, no sólo lo que no pude mergear.

---

## 1. Lo primero: todas las ramas abiertas chocan con `main`

`main` absorbió los 37 commits de Active-IA + tus 5 hallazgos, y eso **movió los mismos archivos**
que tocan las ramas pendientes. No hay ninguna que entre sola.

| Rama | Trae | Choca en |
|---|---|---|
| `fix/ctr-seq-desincronizado` (PR #69) | +11 | `EpisodePage.tsx` |
| `fix/eventos-ctr-idempotencia` (PR #70) | +16 | `EpisodePage.tsx` |
| `fix/editor-y-eventos-del-alumno` (PR #72) | +18 | `CodeEditor.tsx`, `EpisodePage.tsx`, 2 tests |
| `fix/71-scope-por-propiedad` (tuya) | +9 | `entregas.py`, `test_recalificar.py` |
| `fix/72-idempotency-run-tests` (tuya) | +19 | los 4 de arriba |
| `fix/ci-corre-los-tests` (tuya) | +1 | `_mocks.tsx` |

**`EpisodePage.tsx` es el cuello de botella**: aparece en tres. Rebasar una sola no alcanza —
apenas mergees la primera, las otras dos vuelven a chocar ahí.

**Sugerencia de orden**, para pagar el conflicto una sola vez por archivo:

```
1. fix/ci-corre-los-tests     (1 archivo, y es el que evita que todo esto se repita)
2. fix/71-scope-por-propiedad (seguridad, aislado en evaluation-service)
3. fix/ctr-seq-desincronizado (#69)
4. fix/eventos-ctr-idempotencia (#70)   ← se rebasa sobre el 3
5. fix/editor-y-eventos-del-alumno (#72) ← se rebasa sobre el 3
6. fix/72-idempotency-run-tests (tuya)   ← se rebasa sobre el 5
```

---

## 2. `fix/ci-corre-los-tests` — hacela primero

**Tu diagnóstico es el mejor de los dos días**, y lo cito porque explica media auditoría:

> Vitest no corría en ningún lado. `rg "vitest" .github/workflows/` daba **cero**. Son ~450 tests.
> Y los de integración se auto-skipeaban porque la variable de la base no se seteaba en ningún job.
>
> No fallaba el criterio de nadie: **fallaba que nada lo ejecutaba.**

Eso explica por qué hubo rojos reales viviendo en `main` durante semanas, y por qué la auditoría
del 27 encontró tanto.

### Lo que falta antes de mergearla

Al hacer que el CI corra el frontend, **`main` queda en rojo**. Quedan **7 fallando** en
`web-teacher`:

```
HomeView > con 1 comision asignada renderiza card con kpis y CTA
CorreccionesView — EntregasListView   (2)
CorreccionesView — GradingFormView    (4)
```

Tu fix del `_mocks.tsx` bajó de 14 a 7 — la mitad. Los 7 que quedan son de tu harness nuevo:

```
Found multiple elements with the text: A-Manana
```

El router real que agregaste monta el componente más de una vez, o el fixture duplica. **No es un
bug de producto.** Confirmado que son de tu rama y no de mi merge: los mismos 7 fallan en
`origin/fix/ci-corre-los-tests` sola.

**Un CI que siempre está en rojo es peor que no tenerlo**: todo PR posterior muestra rojo y la
gente deja de leerlo. Por eso preferí dejarla afuera.

*Menor: hay `window.scrollTo` sin implementar en jsdom. Es ruido en el log, no la causa, pero un
stub en `setup.ts` limpia la salida.*

**Choque con `main`:** sólo `_mocks.tsx`. Yo había cambiado el estilo del import por lint; vos
agregaste los imports del `QueryClientProvider`. **Quedate con la tuya.**

---

## 3. `fix/71-scope-por-propiedad` — es tuya y es seguridad

**Ocho conflictos en `routes/entregas.py`**, y el problema no es la cantidad: es que los dos lados
reestructuraron los mismos guards con nombres distintos.

| `main` (viene de `fix/66`) | tu `fix/71` |
|---|---|
| `_DOCENTE_ROLES` | `DOCENTE_ROLES` |
| `_OVERSIGHT_ROLES` | `OVERSIGHT_ROLES` |
| `_READ_ARTEFACTO_ROLES` | — |
| `_assert_comision_visible` | `_assert_read_scope` |
| — | `_assert_write_scope` |

No lo resolví porque esto se resuelve mal **en silencio**: los conflictos se cierran, los tests
pasan, y el guard quedó sin aplicarse en un endpoint. Nadie se entera hasta que alguien lo
encuentra desde afuera.

**Vos escribiste las dos intenciones. Decidí qué naming y qué estructura gana.**

### Y sobre el hallazgo de esa rama: tenés razón, y es un error mío

Tu commit dice que el guard preguntaba `if user.roles & DOCENTE_ROLES` y que en este deploy **eso
es verdadero para todo el mundo**, porque el gateway asigna `clerk_base_roles =
"estudiante,docente"` a cualquier usuario logueado. Lo verifiqué en `api_gateway/config.py:112`:
es exacto. **Una alumna se comía un 403** en `submit`, `ejercicio` y las dos lecturas.

Yo verifiqué justamente eso y me dio bien. Neutralicé el guard, cayeron 8 tests, **todos de
docente y ninguno de alumno**, y concluí que el flujo del estudiante estaba a salvo.

**La mutación estaba bien; los fixtures no.** Los tests construyen usuarios con un rol; producción
les da los dos. Es literalmente la trampa que el repo documenta —*los datos de los tests salen de
grepear producción, no de inventarlos*— y caí igual.

Vale que quede en los gotchas: **un test de autorización con un usuario de un solo rol no prueba
nada en este deploy.**

---

## 4. Los tres PRs del CTR y del editor (#69, #70, #72)

Son míos y están verificados por reversión, pero **los tres chocan en `EpisodePage.tsx`** contra el
`main` nuevo. Si preferís que los rebase yo, decímelo — no lo hice para no pisarte mientras
trabajás sobre los mismos archivos.

### #69 — `fix/ctr-seq-desincronizado`

El seq desincronizado que **borraba trabajo del alumno y marcaba episodios sanos como adulterados**.
El worker reclama pendientes con `XAUTOCLAIM` (antes el retry a DLQ **nunca ocurría**), repone el
contador en vez de borrar la sesión, e `integrity_compromised` deja de ser terminal.

Incluye el fix del `prev_chain_hash` del dictamen CoNaIISI.

**Lo que NO cierra, y conviene que lo leas:** nadie se entera si vuelve a pasar. La métrica
`ctr_worker_xpending_count` reporta a un colector OTLP caído — es lo que hizo que esto corriera
semanas sin que nadie lo notara.

### #70 — la raíz del seq quemado, la reflexión y el doble abandono

Va **apilado sobre el #69**. Lo importante del fix: la compensación del seq es un
**compare-and-decrement**, no un `DECR`. Un `DECR` a secas habría sido peor que el hueco — si otra
corrutina reservó el número siguiente, bajar el contador hace que el evento próximo nazca con un
seq **ya usado**.

Un punto que **quedó frenado a propósito y necesita tu opinión**: se pidió que los eventos de
intento adverso dejaran de tragarse el error. Se hizo la mitad —el seq vuelve, el fallo se loguea
con traceback— pero **la excepción no se propaga**, porque el **ADR-019 / RN-129** declara que esa
detección *no bloquea y falla soft*. Propagar convertiría un fallo de side-channel en un prompt
abortado. **Si te parece que debería bloquear, se toca el ADR primero.**

### #72 — los cinco bugs del editor

BUG-3 (la "f" de los f-strings), BUG-4 (código perdido al cambiar el zoom), BUG-7
(`tests_ejecutados` fuera de la cola durable), BUG-8 (el latch de `beforeunload` envenenado) y
BUG-11 (la ejecución entrando a la cadena antes que la edición que la produjo).

Toca `packages/ctr-client` (paquete compartido) porque `tests_ejecutados` no usa el endpoint
genérico. **El `event_type` del contrato CTR no cambia** — sólo por dónde se manda.

Hay un test llamado *"el re-montaje NO emite un edicion_codigo fantasma"*. **No lo borres**: existe
para que nadie reintroduzca evidencia falsa en la cadena.

### `fix/72-idempotency-run-tests` (tuya)

Tu commit del `Idempotency-Key` en `/run-tests` es correcto y bien argumentado — es la otra mitad
del BUG-7. Choca en tres archivos de tests, y **en los tres tu versión es mejor que la mía**. En
uno la mía cambiaba lo que el test prueba: yo puse `window.matchMedia = undefined` y vos
`Reflect.deleteProperty`. El test dice *"si `matchMedia` no existe"* — un `undefined` asignado no
es lo mismo que ausente. **Quedate con las tuyas.**

---

## 5. Cinco features que están escritas y sin PR

Rama `feat/editor-y-corrector` (sobre `fix/editor-y-eventos-del-alumno`). Son las del informe del
alumno: **ED-2** (botón de salir más grande), **ED-3** (autocompletado de Python), **ED-4** (el
código se arrastra entre ejercicios), **JAVA-1** (corrector menos literal) y **JAVA-2** (más
boilerplate).

Pasaron por tres agentes —uno escribió, otro escribió 116 tests sin haber visto el código, y un
tercero verificó adversarialmente— y **cada uno encontró bugs de los anteriores**.

**Lo que dejó abierto el verificador**, y es lo que falta antes de un PR:

1. **La línea que decide el veredicto de TODOS los tests de Python no tiene test.** Reemplazándola
   por la identidad, los 274 siguen verdes.
2. **Dos fixes de esa misma rama pueden volver sin que nada falle**: el del scaffold del docente y
   el del `equalsSource` que generaba Java sin compilar. Ninguno dejó test de regresión.
3. **JAVA-2 genera Java que no compila cuando el campo es `final`** — verificado compilando con
   `javac` real adentro de un contenedor: 48 compilan, 12 fallan.

**Lo que sí quedó verificado y no hace falta volver a mirar:** la paridad entre el corrector de
Java y el de Python (8230 casos, **cero divergencias**), el eslabón del snippet hasta el payload
end-to-end, y que la siembra de ED-4 no emite `edicion_codigo` fantasma.

---

## 6. Tres bugs sin dueño, que no están en ninguna rama

Aparecieron auditando y quedaron sueltos:

**1. 🔴 `PATCH /entregas/{id}/ejercicio/{orden}` devuelve 200 y no persiste nada.**
Sólo guarda cuando **agrega** un ejercicio; cualquier actualización se pierde.
`list(entrega.ejercicio_estados)` es copia superficial → SQLAlchemy no ve cambio → no emite
`UPDATE`. **La reapertura docente del 2026-06-19 está rota en producción desde entonces**, y nadie
lo reportó porque contesta 200.

*El patrón general vale para todo el repo: con columnas JSONB, una copia superficial es un `UPDATE`
que no ocurre. Y el modo de falla es el peor — silencioso y con confirmación al usuario.*

**2. 🔴 Un alumno puede rutear su entrega a la cola del docente equivocado.**
`create_entrega` acepta un `comision_id` que no es el de la TP. El FK garantiza que la comisión
existe, no que corresponda. Como la cola filtra por ese campo, puede mandarla a otra comisión — o
esconderla de la suya.

**3. 🟠 `run-tests` no tiene el auto-heal** que sí tienen los otros eventos del alumno. Si se le
vence el TTL de la sesión justo al correr tests, ese evento se pierde donde los otros se recuperan
— y es el que alimenta N3/N4.

---

## 7. Cuatro cosas que necesitan una decisión, no un fix

Nadie las tocó a propósito:

- **FEAT-A (reabrir/rehacer TP)** — si "rehacer" implica una **segunda nota**, hay que versionar
  calificaciones: hoy hay un UNIQUE de una por entrega. Es un cambio de modelo de datos. Lo define
  Juani con Alberto.
- **ED-1 (copy/paste interno)**, **PAPER-1 (indeterminado como estado)** y **PAPER-2 (revisión
  humana terminal)** — los tres obligan a un ADR **y a bumpear el `LABELER_VERSION`**, lo que
  dispara **re-clasificación masiva** de los datos de la tesis.

---

## 8. Active-IA: lo que falta no es código

El epic está entero en `main`, apagado. Falta:

1. **Mandarles la respuesta** — está escrita y completa en
   `docs/research/activeia-respuesta-2026-08-27.md`.
2. **Pedirles la cuenta de coordinador** en el mismo mail. La de servicio no existe todavía y **ése
   es el freno real**: sin cuenta no hay una sola corrida contra ellos.
3. **`ACTIVEIA_MASTER_KEY`** ya está cargada en EasyPanel.
4. **Prender** para un docente, después de sincronizar.

Y quedaron dos preguntas abiertas para ellos, en la respuesta: el nombre del campo de la nota (hoy
leemos `nota_100` y caemos a otros tres) y si renombramos `salida_obtenida` o ajustan su parser.

---

## 9. 🚨 Antes de deployar cualquier cosa

**DNS permanente en EasyPanel** (`1.1.1.1`/`8.8.8.8` en el servicio, o `daemon.json` del host). El
`/etc/hosts` del api-gateway **se borra al recrear el contenedor**, y deployar lo recrea. Es lo que
tiró producción la mañana del 24/08.

**Las migraciones de Active-IA tienen que correr.** La cadena entera (`20260818_0001` a
`20260827_0002`, incluidas tus dos nuevas) **no está aplicada en producción** — verificado el
27/08: la tabla `activeia_rubrica_ejercicio` no existe. Si el servicio sube sin migrar, levanta y
falla al primer query.

**No redeployar en caliente** `ctr-service`, `tutor-service` ni `evaluation-service` con usuarios
activos. De a un servicio por vez.

Y el **backup remoto** sigue abierto.
