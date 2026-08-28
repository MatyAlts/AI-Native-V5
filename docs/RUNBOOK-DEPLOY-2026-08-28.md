# Runbook de deploy — 2026-08-28

Para el redeploy manual en EasyPanel de los ~120 commits del 24, 27 y 28 de agosto.

> Escrito el 2026-08-28. Si lo leés más adelante, **verificá el estado de las migraciones
> antes de confiar en la sección 1**: es lo que se pudre primero.

---

## 0) Antes de tocar un solo botón — los tres gates

Ninguno es opcional. Los tres pueden dejar producción peor que antes del deploy.

### G1 — DNS permanente en EasyPanel

⚠️ **Esta regla no está escrita en ningún otro lado del repo, y ya tiró producción una vez
(2026-08-24).** El `/etc/hosts` del api-gateway se borra al recrear el contenedor. Si el DNS
no está configurado como permanente en EasyPanel, el gateway levanta sin poder resolver a los
backends y el deploy "exitoso" deja el sistema caído.

**Resolvelo primero. No hay paso 1 sin esto.**

### G2 — `ACADEMIC_DB_URL` en el env de `ctr-service`

Hoy **no figura** en la lista de variables de ctr-service de `EASYPANEL-DEPLOY.md`. Sin ella,
el gate de autorización A0.6 (`ctr-service/auth/dependencies.py:173`) es un **no-op**: default
`""` y no valida nada.

Combinado con `clerk_base_roles = "estudiante,docente"` —que le da rol `docente` a todo usuario
logueado— eso deja `GET /api/v1/audit/episodes/{id}` devolviendo la cadena entera de cualquier
episodio a cualquiera.

**Chequealo en el panel.** Si alguien la seteó a mano sin documentarlo, no aplica. Si no está,
setearla es parte de este deploy.

### G3 — Migraciones

`20260818_0002_activeia_credenciales` **no estaba aplicada en producción** al 2026-08-27. El
evaluation-service levanta igual y **falla al primer query**.

Corré las migraciones del evaluation-service **antes** de deployarlo. Mismo criterio para
academic (`20260723_0001`, la de `language`) y classifier (`20260905_0005`).

> Gotcha verificado en local el 2026-08-28: si alguna vez alguien corrió alembic como
> superusuario, las tablas quedan con dueño `postgres` y el usuario de la app **no puede
> hacer `ALTER TABLE`** — alembic falla con `permission denied` o `must be owner`. Se arregla
> con `GRANT` + `ALTER TABLE ... OWNER TO <app_user>`.

---

## 1) El orden

**De a uno por vez. El VPS tiene la RAM justa.** Entre servicio y servicio, esperá el health y
recién ahí seguí.

**Ventana sin usuarios activos.** `ctr-service`, `tutor-service` y `evaluation-service` no se
redeployan en caliente: son los que están en el medio de un episodio.

| # | Servicio | Riesgo | Qué mirar antes de seguir |
|---|---|---|---|
| 1 | `governance-service` | bajo | `/health` 200 |
| 2 | `content-service` | bajo | `/health` 200 |
| 3 | `classifier-service` | bajo | migración `20260905_0005` aplicada |
| 4 | `analytics-service` | bajo | `/health` 200 |
| 5 | `ai-gateway` | medio | `/health/ready` — el check de `byok_resolver` sale KO si `BYOK_MASTER_KEY` está vacía |
| 6 | `academic-service` | **alto** | ver abajo |
| 7 | `execution-service` | bajo | queda **apagado** (`EXECUTION_ENABLED=false`) |
| 8 | `execution-runner` | bajo | no arranca sin `RUNNER_TOKEN` y `JAVA_IMAGE` por digest |
| 9 | `evaluation-service` | **alto** | migración de G3 **ya aplicada** |
| 10 | `tutor-service` | **alto** | sin usuarios activos |
| 11 | `ctr-service` | **el más alto** | sin usuarios activos. Es la cadena de evidencia |
| 12 | `api-gateway` | alto | último: es la puerta |
| 13 | frontends | bajo | al final, cuando el backend ya entiende lo nuevo |

### Por qué academic-service es el de alto riesgo

Es el que más cambió en comportamiento: **el commit ahora pasa antes de emitir la respuesta**
(`Depends(..., scope="function")`). Es una línea que afecta a las 95 rutas del servicio.

Lo que arregla: el cliente recibía `201` sobre escrituras que todavía no estaban en la base —
por eso el smoke fallaba "al azar", y por eso un docente podía agregar ejercicios a un TP y que
el publish siguiente dijera "TP vacía".

**Cambio de comportamiento declarado**: si el commit falla, ahora sale **500 antes** de emitir
la respuesta. Antes salía el `201` con el id de una fila inexistente. Es lo correcto, pero es
distinto: un error que antes era invisible ahora es visible.

**Qué mirar después de deployarlo**: crear un TP, agregarle un ejercicio y publicarlo, seguido.
Esa es la secuencia exacta que fallaba.

### Por qué los frontends van al final

Pydantic ignora los campos desconocidos, así que un frontend nuevo contra un backend viejo **no
rompe nada** — pero "Ejecutar" en Java se comporta como antes (corre los casos) hasta que suba
el `execution-service`. Verificado el 2026-08-28.

---

## 2) Lo que sube APAGADO

Mergear no es encender. Estos flags quedan en su default (`false`) porque no figuran en el
compose de producción:

| Flag | Efecto |
|---|---|
| `EXECUTION_ENABLED` | Java no ejecuta nada. Encender **después**, y de a una comisión con `EXECUTION_ENABLED_COMISIONES` |
| `ACTIVEIA_ENABLED` | La corrección asistida no corre |
| `ACTIVEIA_SYNC_RUBRICAS_ENABLED` | Depende de endpoints que Active-IA todavía no expone |

`ACTIVEIA_MASTER_KEY` **hay que generarla igual** (`openssl rand -base64 32`), aunque el flag
esté apagado: sin ella el docente no puede conectar su cuenta, y el modo de falla es confuso
—no explota al arrancar, explota recién cuando alguien intenta guardar una credencial—.

Es **propia y distinta de `BYOK_MASTER_KEY`**, a propósito (design D5).

---

## 3) Después del deploy — qué probar, en este orden

1. **Login** de un alumno y de un docente.
2. **Crear TP → agregar ejercicio → publicar**, seguido. Es la secuencia que fallaba.
3. **Abrir un episodio** y mandar un mensaje al tutor.
4. **Entregar un TP** y **calificarlo** desde el panel del docente.
5. `GET /health` del gateway. Un **503** por el check de Keycloak no es un problema si el
   check de `academic_service` sale OK.

---

## 4) Lo que este deploy NO arregla

**`DEV_TRUST_HEADERS=true` sigue en producción** (`docker-compose.prod.yml:240`).

Sin token, con `X-User-Id` y `X-Tenant-Id` forjados, se entra como cualquiera. Está documentado
como HALLAZGO CRÍTICO en `docs/FASE2-CONEXIONES.md`, con un probe real contra el dominio de
EasyPanel del 2026-06-04.

**Consecuencia directa para lo que subís hoy**: los dos gates de pertenencia que se cerraron el
28/08 (`sesion_del_emisor` y el de `GET /episodes/{id}`) comparan contra una identidad **que el
llamador elige**. En producción, hoy, no cierran nada.

**Por qué no se apaga con un flag**: los frontends no mandan el Bearer de Clerk — su nginx
inyecta los `X-*` en su lugar. Apagarlo sin cablear el token de punta a punta **deja afuera a
la cohorte entera**. El validador de Clerk ya está configurado y andando; falta usarlo.

Es un cambio de arquitectura de auth, no un fix. Decisión de Juani + Alberto.
