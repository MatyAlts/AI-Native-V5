## Context

AI-Native ejecuta el código de los alumnos en un sandbox propio (Docker sin privilegios, Java 21,
sin red, 10s de límite). Active-IA corrige código con Gemini **leyéndolo**, contra una rúbrica
cargada del lado de ellos, y devuelve nota /100 más un PDF. Son del mismo ecosistema y los opera el
mismo equipo.

Estado del código relevante, verificado el 2026-08-17:

- `Entrega` (`apps/evaluation-service/src/evaluation_service/models/entregas.py:52-71`) tiene
  `id, tarea_practica_id, student_pseudonym, comision_id, estado, ejercicio_estados, submitted_at`.
  **Ninguna columna con el código del alumno.**
- El detalle de una ejecución de tests vive en Redis con TTL 600s
  (`apps/execution-service/src/execution_service/services/execution_store.py:25`). Al CTR sólo va
  `total/passed/failed` (`.../result_mapper.py:85`), sin qué caso ni con qué entrada.
- El modelo de Active-IA es plano: `materia → unidad → rubrica_id`, y cruza por `cmid` (el
  `assign_id` de Moodle). **AI-Native no tiene `cmid` en ninguna parte** — cero ocurrencias en todo
  el monorepo.
- `evaluation-service` **no tiene enforcer de Casbin**: `require_permission` está hardcodeado sobre
  un frozenset de cinco roles (`auth/dependencies.py:93-127`).
- `tenant_session` sólo ejecuta `SET app.current_tenant` (`db/session.py:55`). No existe
  `app.current_user_id` en este servicio.
- El pool de conexiones es de 8 (`db/session.py:33-34`: `pool_size=2, max_overflow=6`).

Modos de fallo medidos del motor de Active-IA, que condicionan el diseño: le dio 100/100 a una
entrega donde ningún producto quedaba vinculado a ninguna categoría; le puso puntaje completo a una
"búsqueda" que era `if puntajes[i] == 990`; no aplicó una penalización del 30% que la propia rúbrica
declaraba; y un bug del 2026-08-04 dejó a una alumna desaprobada descontando por archivos que sí
estaban.

## Goals / Non-Goals

**Goals:**
- Que la entrega persista, de forma verificable y auditable, el código que el alumno entregó.
- Que el docente pueda pedir una corrección **por ejercicio** y recibir nota y desglose.
- Que el resultado sea una **sugerencia**: el docente sigue cargando la nota.
- Que un fallo de infraestructura sea siempre distinguible de un resultado.
- Que el Epic 1 dé valor sin que Active-IA exista.

**Non-Goals:**
- Que Active-IA ejecute código. El sandbox es nuestro.
- Que Active-IA calcule la nota final del TP. Devuelve una nota por ejercicio; el promedio lo
  hacemos nosotros y se muestra desglosado.
- Corrección en lote. Se dispara de a un ejercicio.
- Corregir entregas anteriores al Epic 1 (`LEGACY`).
- Mapear los criterios de Active-IA contra los de la rúbrica local.
- Introducir Casbin en `evaluation-service`.

## Decisions

### D1 — La unidad de corrección es el ejercicio, no la entrega

**Elegido:** un envío por ejercicio, con su rúbrica y su código.

**Alternativa descartada:** un archivo por entrega con delimitadores entre ejercicios. Activa el
modo de fallo más documentado del motor —*distingue presencia, no vínculo*— porque una pieza del
ejercicio 3 puede contar como cumplimiento de un criterio del 1. Además produciría una sola nota
/100 para cuatro rúbricas distintas, sin forma sensata de desglosarla.

**Costo asumido:** N llamadas a Gemini por entrega (100-160s contra 25-40s con cuatro ejercicios).
Se mitiga con corrección a demanda: el botón es por ejercicio y "corregir los 4" avisa el costo.

### D2 — Se manda el resultado de los tests ya ejecutados, no los test cases para que los interprete

**Elegido:** antes de cada envío, re-ejecutar los tests del ejercicio en el sandbox propio y mandar
el resultado detallado (por caso: entrada, esperado, obtenido, pasa/falla) junto al código.

**Por qué:** los tres modos de fallo del motor salen de juzgar leyendo. Un test ejecutado no se deja
engañar ni por piezas sueltas ni por un valor hardcodeado. Active-IA queda haciendo lo único que un
test no puede medir y que es lo que la rúbrica evalúa: si la excepción es verificada o de runtime,
si usó la interfaz o enumeró los tipos concretos, si el encapsulamiento es real.

**Los `test_cases` igual se sincronizan** (D4) porque son parte del enunciado: que un caso espere
que pidiendo cupo 1 entren 2 personas le dice al motor cuál es la regla de negocio.

**Alternativa descartada:** persistir el resultado de la ejecución del alumno y reusarlo. El detalle
se borra a los 600s y el CTR sólo guarda conteos. Re-ejecutar además garantiza que el resultado
corresponde exactamente al código que se manda, y es reproducible por cualquiera.

### D3 — El artefacto se persiste por ejercicio, en el submit, mandado por el cliente

**Elegido:** una fila por ejercicio con su `orden`, `episode_id`, código y `sha256`, más un `sha256`
del conjunto. Se escribe en el submit, con el contenido que manda el cliente.

**Alternativa descartada:** leer el CTR en el momento de corregir. El CTR se ingesta asincrónicamente
(202 + worker) y el editor emite fire-and-forget, así que lo que se lea puede no ser lo último que
el alumno escribió. Certificaría una lectura, no una entrega.

**Consecuencia:** hay que arreglar el flush del debounce al desmontar el editor
(`apps/web-student/src/components/CodeEditor.tsx:490-494` limpia el timeout sin invocar el callback
pendiente), o el submit puede perder los últimos segundos de tipeo.

### D4 — La sincronización empuja la estructura del TP, no rúbricas sueltas

**Elegido:** al publicar un TP se manda a Active-IA el TP con sus ejercicios anidados, cada uno con
`rubrica`, `test_cases` y `peso_en_tp`, identificados por un `external_ref` propio.

**Por qué el `external_ref`:** el resolver de Active-IA cruza por `cmid` y no tenemos ninguno. Un
identificador propio elimina el mapeo manual, que hoy es el 100% del caso y es la fuente del riesgo
"una rúbrica equivocada no da una nota floja: corrige otra cosa".

**Depende de un cambio en Active-IA** (nivel de ejercicio bajo el TP + endpoints de escritura),
especificado en `docs/research/activeia-cambios-pedidos.md`.

### D5 — Credenciales en tabla propia, no en `byok_keys`

**Elegido:** `activeia_credenciales` con `encrypted_password BYTEA` cifrado con
`packages/platform-ops/src/platform_ops/crypto.py` (AES-256-GCM) y `ACTIVEIA_MASTER_KEY` propia.

**Por qué no `byok_keys`:** su scope es tenant/facultad/materia y las credenciales de Active-IA son
**por docente** (los ids de comisión y rúbrica salen de la cuenta logueada). Además guarda los
últimos 4 caracteres del plaintext en claro (`ai-gateway/services/byok.py:434`), lo que con un
password humano es una fuga. **Sin columna de fingerprint.**

**Master key propia** para no ampliar el blast radius de `BYOK_MASTER_KEY` a un segundo pod.

### D6 — RLS por tenant, aislamiento por usuario en la query

**Elegido:** policy RLS `ENABLE` + `FORCE` **por tenant solamente**, más `WHERE user_id = :uid`
explícito en las tres queries que tocan credenciales.

**Por qué no RLS por usuario:** `tenant_session` sólo setea `app.current_tenant`
(`db/session.py:55`). Una policy que evalúe `current_setting('app.current_user_id', true)` haría que
el reconciliador del lifespan —que corre sin request y sin headers `X-*`
(`main.py:19-20,29`)— vea cero filas **sin tirar error**: en Postgres una policy que no matchea
filtra en SELECT, no falla. Fallo silencioso.

El `FORCE` no es opcional: ya se olvidó una vez y tiene una migration entera dedicada a repararlo
(`apps/academic-service/alembic/versions/20260507_0001_force_rls_byok_entregas_calificaciones.py:25-30`).

### D7 — Membresía de comisión explícita en cada endpoint nuevo

**Elegido:** verificar contra `usuarios_comision` en los tres endpoints de corrección, y devolver
**404 y no 403** cuando el caller no es dueño (molde
`apps/execution-service/src/execution_service/routes/executions.py:236`).

**Por qué:** `_assert_can_read` (`routes/entregas.py:585-593`) sólo chequea el frozenset de roles y
no filtra por comisión. En producción todos los docentes comparten tenant, así que la RLS no los
separa. Sin esta feature es un agujero de enumeración; con ella significa gastar cuota ajena y
mandar el código de un alumno de otra comisión a un servicio externo.

### D8 — La plataforma nunca escribe en `calificaciones`

**Elegido:** el resultado vive en `correcciones_ia`. La UI muestra la nota /100, propone la
conversión a /10, y un botón "Usar como base" rellena el campo **sin guardar**.

**Por qué:** `calificaciones` tiene `CheckConstraint("nota_final >= 0 AND nota_final <= 10")`
(`models/entregas.py:128-129`), UNIQUE por entrega, y el alumno la ve cuando la entrega pasa a
`graded`. Con los modos de fallo medidos del motor, cualquier escritura automática rompe el
humano-en-el-medio en el mismo commit.

### D9 — `BackgroundTasks` + tabla persistente + reconciliador

**Elegido:** el trabajo corre en `BackgroundTasks` (molde `executions.py:215`) escribiendo estado en
`correcciones_ia`, con un reconciliador en el lifespan que levanta las `running` viejas y re-poletea
(molde `abandonment_worker.py:91-116`).

**Dos reglas duras:** sesión de DB corta (abrir, escribir, cerrar — no `Depends(get_db)` sostenido
durante 180s) y semáforo de concurrencia. El pool es de 8 y con corrección por ejercicio cuatro
alumnos entregando lo agotan.

**Alternativa descartada:** un worker aparte. Suma pod, deploy y health check para un volumen que
todavía no lo justifica. El reconciliador es lo que hace tolerable que `BackgroundTasks` sea
in-process y pierda el trabajo si el pod se cae.

### D10 — El promedio ponderado lo calcula AI-Native

**Elegido:** Active-IA devuelve una nota por ejercicio; el promedio ponderado por `peso_en_tp` se
calcula acá y se muestra **con el cálculo desglosado**. Si falta la corrección de algún ejercicio
**no se promedia**: se muestra parcial y se dice cuál falta.

**Por qué:** es aritmética de dos líneas y `peso_en_tp` ya existe. Cada cuenta que se delega es un
lugar más donde puede fallar, y el motor ya tuvo un caso donde los criterios sumaban 87 y la nota
final no reflejaba la penalización declarada. Promediar 3 de 4 con el cuarto en cero es cómo se
fabrica una nota injusta.

## Risks / Trade-offs

- **Personería frente al consentimiento** → No es técnico. Confirmar que AI-Native y Active-IA son
  el mismo responsable de datos declarado en el protocolo del piloto. Bloquea el despliegue con
  datos reales, no el desarrollo.
- **El histórico del piloto nunca tendrá snapshot del submit** → Estado `LEGACY` explícito en
  pantalla, reconstrucción best-effort marcada como reconstruida, y sin botón de corrección.
- **`jtp` y `auxiliar` pasan cualquier permiso** (`auth/dependencies.py:100,109-110`: el frozenset
  devuelve el user sin mirar `resource` ni `action`, replicado en cuatro lugares) → Constante
  `CORRECCION_IA_ROLES` propia para esta feature. La granularidad real requiere el enforcer y es
  otra PR.
- **El gate de comisión del CTR es no-op en el deploy** (`ctr-service/auth/dependencies.py:173`
  corta si falta `academic_db_url`, y `docs/EASYPANEL-DEPLOY.md:110` no lista esa variable) →
  Agregarla al env y verificarlo. Es de donde sale el código del alumno.
- **N llamadas a Gemini por entrega** → Corrección a demanda por ejercicio; cuota por docente y día
  que falla cerrada; kill switch con default `False`.
- **Bugs del motor que producen números plausibles y mal** → D2 mitiga parcialmente los de
  "presencia sin vínculo" y "elogia hardcodeado". Los de penalización no aplicada y desglose que no
  cierra se arreglan del lado de Active-IA (`docs/research/activeia-cambios-pedidos.md`, sección 4).
  Mientras tanto, guardrail aritmético en la UI: sumar los criterios y comparar con el total.
- **Depender de cambios en Active-IA** → El Epic 1 no depende de nada. Los Epics 2 a 4 sí, y el
  orden de prioridad de lo que se les pide está escrito en el documento de cambios.

## Migration Plan

1. Migrations con RLS `ENABLE` + `FORCE` por tabla nueva. `make check-rls` verde antes de mergear.
2. Epic 1 se despliega solo y queda andando sin Active-IA: el docente ya puede descargar entregas.
3. Epics 2 a 4 detrás del kill switch `activeia_enabled = False`. Se prende por comisión después de
   verificar una corrección real contra una rúbrica sincronizada.
4. Rollback: apagar el kill switch. Las tablas quedan; ninguna escribe en `calificaciones`, así que
   no hay dato académico que revertir.
5. Deploy de a un servicio por vez en EasyPanel. Evaluar si `evaluation-service` se suma a la lista
   de "nunca redeployar en caliente" que hoy nombra sólo `ctr-service` y `tutor-service`.

## Open Questions

- **¿Active-IA puede modelar un TP con ejercicios hijos?** Hoy es `materia → unidad → rubrica_id`,
  una rúbrica por unidad. Es la pregunta que destraba el Epic 2 entero.
- **¿Qué campos exige `POST /entregas/` además del archivo?** La doc dice "multipart: archivo +
  metadatos" y nunca los enumera. Si alguno es un id de Moodle, el Epic 2 cambia de forma.
- **¿Con qué clave keyea el 409?** Se sabe que 409 = "ya existía" y no se sabe contra qué. El ciclo
  `returned → submitted` reusa el mismo `entrega_id` y cambia sólo el `artefacto_sha256`.
- **¿El poll devuelve el desglose estructurado o sólo la nota?** Si es sólo la nota, el PDF **es**
  el desglose y la UI tiene que decirlo en vez de mostrar una tabla vacía.
- **¿Personería única frente al consentimiento?**
