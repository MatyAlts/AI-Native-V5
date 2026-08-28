# Lo que quedó trabado — para Neyén

**Fecha:** 28 de agosto de 2026
**De:** Juani

Mergeé a `main` lo que se podía. **Dos de tus ramas quedaron afuera**, y las dos por lo mismo:
necesitan una decisión tuya, no un merge mío.

Abajo va exactamente qué está en `main`, qué falta, y por qué en cada caso paré.

---

## Lo que YA está en `main` (37 commits)

`main` pasó de `166619e` a `ab7f0f3`. Entró:

- **Todo el epic de Active-IA** (28 commits) + **tus 5 hallazgos de auditoría** (`fix/66-hallazgos-auditoria`)
- **BUG-1 cerrado por las dos puertas**: la mía y la que encontraste vos (`fix/68-segundo-call-site`)

**Verificado antes de pushear:** 1056 tests de backend, 143 de web-student, `tsc` y `biome` limpios.

### ⚠️ Un merge que resolví a mano y conviene que mires

`fix/66-hallazgos-auditoria` sale de `feat/entrega-artefacto`, que es **anterior** al fix de BUG-1.
O sea que traía el guard viejo:

```ts
if (entrega.estado === "draft" || entrega.estado === "returned") {
```

Un merge automático **habría reintroducido la pérdida de devoluciones**. Cada lado tenía una mitad
correcta, así que los combiné:

| Archivo | Qué quedó |
|---|---|
| `episodio.$id.tsx` | guard `debeEnviarLaEntrega` (tuyo/mío) **+** el cuerpo de artefactos (de `fix/66`) |
| `ExerciseListView.tsx` | tu relectura fresca con `getById` **+** `recuperarArtefactos` y la firma de 3 args |

Confirmado después del merge: `debeEnviarLaEntrega` se usa en **los dos** call-sites, y el guard
viejo no quedó en ningún lado del repo.

Si al leerlo te parece que la combinación perdió algo de tu intención, decímelo — lo resolví yo y
puedo estar equivocado.

### Migraciones nuevas

Tus dos migraciones (`20260827_0001` reconciliador, `20260827_0002` olvido) están en `main`.
**Ojo con el deploy**: la cadena entera de Active-IA (`20260818_0001` a `20260827_0002`) **no está
aplicada en producción** — verificado el 27/08, la tabla `activeia_rubrica_ejercicio` no existe.
Mi base local tampoco las tenía, y por eso vi 2 rojos falsos en tu rama antes de darme cuenta.

---

## 🔴 `fix/71-scope-por-propiedad` — no la mergeo yo

**Ocho conflictos en `apps/evaluation-service/src/evaluation_service/routes/entregas.py`**, que es
el archivo de seguridad.

El problema no es que sean muchos: es que **los dos lados reestructuraron los mismos guards con
nombres distintos**.

| `main` (viene de `fix/66`) | tu `fix/71` |
|---|---|
| `_DOCENTE_ROLES` | `DOCENTE_ROLES` |
| `_OVERSIGHT_ROLES` | `OVERSIGHT_ROLES` |
| `_READ_ARTEFACTO_ROLES` | — |
| `_assert_comision_visible` | `_assert_read_scope` |
| — | `_assert_write_scope` |

Resolver eso a mano y empujarlo a producción es la forma exacta de abrir un agujero sin que nadie
lo note: los conflictos se resuelven, los tests pasan, y el guard quedó aplicándose en un endpoint
menos.

**Vos escribiste las dos intenciones. Rebasá sobre `main` y decidí qué naming y qué estructura
gana.** Yo no tengo forma de saberlo sin adivinar.

### Y sobre el hallazgo de esa rama: tenés razón, y es un error mío

Tu commit dice que el guard preguntaba `if user.roles & DOCENTE_ROLES` y que en este deploy **eso
es verdadero para todo el mundo**, porque el gateway asigna `clerk_base_roles =
"estudiante,docente"` a cualquier usuario logueado. Lo verifiqué en
`api_gateway/config.py:112`: es exacto.

Yo verifiqué justamente eso y me dio bien. Neutralicé el guard, cayeron 8 tests, **todos de
docente y ninguno de alumno**, y concluí que el flujo del estudiante estaba a salvo.

**La mutación estaba bien; los fixtures no.** Los tests construyen usuarios con un rol; producción
les da los dos. Es literalmente la trampa que el repo documenta —*los datos de los tests salen de
grepear producción, no de inventarlos*— y caí igual.

Vale la pena que eso quede en los gotchas: **un test de autorización con un usuario de un solo rol
no prueba nada en este deploy.**

---

## 🟠 `fix/72-idempotency-run-tests` — depende de la anterior

Tu commit del `Idempotency-Key` en `/run-tests` es correcto y está bien argumentado. El problema es
que la rama arrastra `fix/editor-y-eventos-del-alumno` entero, y ahí chocan tres archivos de tests
con lo que ya está en `main`:

- `apps/web-student/tests/useMediaQuery.test.ts`
- `apps/web-student/tests/setup.ts`
- `apps/web-student/tests/alumnoOnboarding.test.tsx`

**En los tres tu versión es mejor que la mía**, y en uno la mía cambiaba lo que el test prueba: yo
puse `window.matchMedia = undefined` y vos `Reflect.deleteProperty`. El test dice *"si `matchMedia`
no existe"* — un `undefined` asignado no es lo mismo que ausente.

Cuando rebases, **quedate con las tuyas**.

---

## 🟡 `fix/ci-corre-los-tests` — la más importante, y la que más cuidado pide

**El diagnóstico es el mejor de todo el día**, y lo cito porque explica media auditoría:

> Vitest no corría en ningún lado. `rg "vitest" .github/workflows/` daba **cero**. Son ~450 tests.
> Y los de integración se auto-skipeaban porque la variable de la base no se seteaba en ningún job.
>
> No fallaba el criterio de nadie: **fallaba que nada lo ejecutaba.**

Eso explica por qué hubo rojos reales viviendo en `main` durante semanas.

**Pero no la mergeé, y el motivo importa:** al hacer que el CI corra los tests del frontend,
**`main` queda en rojo**. Quedan **7 fallando** en `web-teacher`:

```
HomeView > con 1 comision asignada renderiza card con kpis y CTA
CorreccionesView — EntregasListView  (2)
CorreccionesView — GradingFormView   (4)
```

Tu fix del `_mocks.tsx` bajó de 14 a 7 — la mitad. Los que quedan son de tu harness nuevo:
`Found multiple elements with the text: A-Manana`. El router real que agregaste monta el
componente más de una vez, o el fixture duplica. **No es un bug de producto.**

Confirmé que son de tu rama y no de mi merge: los mismos 7 fallan en
`origin/fix/ci-corre-los-tests` sola.

**Un CI que siempre está en rojo es peor que no tenerlo**: todo PR posterior muestra rojo y la
gente deja de leerlo. Por eso preferí dejarla afuera hasta que cierres esos 7 — y ahí sí es la
rama más valiosa de las cinco.

*(Nota menor: hay `window.scrollTo` sin implementar en jsdom. Es ruido en el log, no la causa de
los fallos, pero un stub en `setup.ts` limpia la salida.)*

---

## Lo que te pido, en orden

1. **`fix/ci-corre-los-tests`** — cerrá los 7 de `web-teacher` y mergeala. Es la que evita que
   vuelva a pasar todo lo demás.
2. **`fix/71-scope-por-propiedad`** — rebasá sobre `main` y resolvé el naming de los guards. Es
   seguridad, y es tuya.
3. **`fix/72-idempotency-run-tests`** — rebasá, quedándote con tus tres archivos de tests.

Si querés que resuelva alguno yo, decime cuál y con qué criterio — lo que no quiero es adivinar tu
intención en un archivo de autorización.

---

## Tres bugs que siguen abiertos y no están en ninguna rama

Aparecieron auditando el 27/08 y quedaron sin dueño:

1. **🔴 `PATCH /entregas/{id}/ejercicio/{orden}` devuelve 200 y no persiste nada.** Sólo guarda
   cuando **agrega** un ejercicio; cualquier actualización se pierde. `list(entrega.ejercicio_estados)`
   es copia superficial → SQLAlchemy no ve cambio → no emite `UPDATE`. **La reapertura docente del
   2026-06-19 está rota en producción desde entonces**, y nadie lo reportó porque contesta 200.
2. **🔴 Un alumno puede rutear su entrega a la cola del docente equivocado.** `create_entrega`
   acepta un `comision_id` que no es el de la TP.
3. **🟠 `run-tests` no tiene el auto-heal** que sí tienen los otros eventos del alumno.

---

## Y lo del deploy, que no cambió

🚨 **DNS permanente en EasyPanel antes de deployar cualquier cosa.** El `/etc/hosts` del
api-gateway se borra al recrear el contenedor, y deployar lo recrea. Es lo que tiró producción la
mañana del 24/08.

Y las migraciones de Active-IA tienen que correr, o el servicio levanta y falla al primer query.
