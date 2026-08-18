# Corrección con Active-IA en AI-Native — plan v3

> **Qué cambió respecto de la v1.** El primer análisis se hizo sobre la premisa de que
> Active-IA era un servicio de terceros — así lo describe su propia doc: *"un servicio
> externo y aparte de Moodle"*. **Es del mismo ecosistema y lo opera el mismo equipo.**
> Eso reescribe cinco de los ocho riesgos y habilita un camino que antes estaba cerrado.
>
> **v3 (17/08).** La unidad de corrección pasa a ser **el ejercicio**, no la entrega: su rúbrica,
> su código y sus tests. Y a Active-IA se le manda **el resultado de ejecutar los tests**, no los
> test cases — porque el sandbox ejecuta y Gemini sólo lee, y ahí está el origen de los tres bugs
> del motor.

---

## 1. La idea en tres líneas

El alumno entrega. El docente ve un botón **"Corregir con Active-IA"** en su panel de
correcciones. Al apretarlo, el código entregado se manda a Active-IA, que lo corrige contra
una rúbrica y devuelve nota sobre 100 más un PDF. El resultado lo ve **solo el docente**,
que decide qué hacer con eso. El alumno no recibe nada automáticamente y la nota la sigue
cargando una persona.

**El único problema de fondo que queda es nuestro, no de Active-IA:** hoy la entrega no
guarda el código del alumno. Eso se arregla en la Fase 1 y no se puede saltear.

---

## 2. Lo que cambió al saber que Active-IA es propio

| Tema | En la v1 (tercero) | Ahora |
|---|---|---|
| Comité de Ética | Gate bloqueante, trámite lento | Nota en el protocolo. **Pendiente confirmar la personería** (ver 2.1) |
| Los bugs del motor | Restricciones con las que convivir | **Bugs a arreglar** — nueva Fase A |
| Rúbricas | Mapeo manual, 6 de 9 huérfanas | **Push desde AI-Native** — nueva Fase 2 |
| El 409 de clave desconocida | Riesgo vivo | Se responde leyendo el código |
| Derecho al olvido | Roto sin contrato de borrado | Se implementa del lado de Active-IA |
| Que la entrega no guarde el código | Bloqueante | **Sigue igual de bloqueante** |
| Agujeros de permisos y comisión | Bloqueantes | **Siguen igual** |

### 2.1 Lo único que queda del gate de privacidad

Que el equipo sea el mismo no implica que el **responsable de datos declarado en el
protocolo** sea el mismo. Si AI-Native y Active-IA son dos personerías distintas, frente al
consentimiento que firmaron los alumnos sigue habiendo cesión, aunque los dueños coincidan.

**Qué hacer:** una línea en el protocolo que declare a Active-IA como parte del mismo
tratamiento de datos. Si son la misma entidad, es trámite administrativo. Si no lo son,
hay que agregarlo al consentimiento. **No bloquea el desarrollo; bloquea el despliegue con
datos reales.**

---

## 3. Las fases

### Fase 0 — Cinco preguntas, respondidas en el código propio
**Esfuerzo: chico. Sin latencia externa.**

Ya no es un spike contra una API ajena: es abrir el repo de Active-IA y responder.

1. ¿Qué campos exige `POST /entregas/` además del archivo? ¿Alguno es un id de Moodle
   (`cmid`, `groupId`, user id del campus)? — **Es la pregunta que define la Fase 2.**
2. ¿Acepta un alumno que no está en su padrón, o hay que darlo de alta?
3. ¿Qué extensiones y qué tamaño máximo acepta? ¿ZIP?
4. ¿`GET /correcciones/entregas/{id}` devuelve el desglose estructurado, o solo la nota?
5. ¿Con qué clave keyea el 409?

**Cómo se sabe que terminó:** las cinco respuestas escritas. Si la 1 dice que exige ids de
Moodle, la Fase 2 pasa de "empujar rúbricas" a "agregar un identificador propio en
Active-IA", que también está a tu alcance.

---

### Fase A — Arreglar el motor de corrección
**Esfuerzo: medio. Corre en paralelo con todo lo demás. Del lado de Active-IA.**

Esto en la v1 no existía: eran restricciones. Ahora son bugs con dueño, y arreglarlos vale
para todos los que ya usan Active-IA desde Moodle, no solo para esta integración.

De la doc y del bug que reportaste el 04/08:

- **Descuenta puntos por archivos que sí están en la entrega.** Severidad alta, dejó a una
  alumna desaprobada. Es el más urgente y ya está reportado.
- **No aplica las penalizaciones que la propia rúbrica declara.** Caso medido: los criterios
  sumaban 87 y con el descuento del 30% declarado en C5 habría dado ~61. Además C5 mostraba
  0/10 con subcriterios que sumaban 5.
- **Cuenta presencia, no vínculo.** 100/100 a una entrega con "3 categorías OK" y "10
  productos OK" donde ningún producto quedaba vinculado a ninguna categoría.
- **Elogia como correcto código hardcodeado.** Puntaje completo a una "búsqueda" que era
  `if puntajes[i] == 990`.
- **Recomienda cosas que la cátedra prohíbe** (`try/except` en Programación 1).

**Por qué va acá y no al final:** cada uno de estos bugs, en la v1, obligaba a escribir un
guardrail en AI-Native para taparlo. Arreglar el motor borra ese trabajo en vez de sumarlo.
El único guardrail que sobrevive es el aritmético de la Fase 5, y pasa a ser una red, no un
parche.

---

### Fase 1 — Que la entrega contenga lo que se entregó
**Esfuerzo: medio. Da valor sola. NO CAMBIÓ.**

Hoy `Entrega` no guarda una sola línea del código
(`apps/evaluation-service/src/evaluation_service/models/entregas.py:52-71`). Lo único que
existe es el snapshot del CTR, ingestado asincrónicamente
(`apps/ctr-service/src/ctr_service/routes/events.py:80` devuelve 202; el worker escribe
después). Corregir leyendo eso certifica una lectura, no una entrega.

**Trabajo:**
- Persistir el código **en el submit**, mandado por el cliente. Migration + RLS `ENABLE` +
  `FORCE` + policy por tenant (molde
  `apps/academic-service/alembic/versions/20260507_0001_force_rls_byok_entregas_calificaciones.py:25-30`).
- Sembrar `ejercicio_estados` al crear la entrega: hoy se construye con `[]` hardcodeado
  (`routes/entregas.py:81`) y las filas solo aparecen si alguien llama al PATCH por
  ejercicio. "Falta un ejercicio" es el estado inicial de toda entrega, no un caso raro.
- Validar el conteo en el submit contra la lista esperada (`tp_ejercicios`), no contra lo
  presente: hoy `if estados:` con lista vacía no valida nada (`routes/entregas.py:236-245`).
- Arreglar el flush del debounce al desmontar el editor
  (`apps/web-student/src/components/CodeEditor.tsx:490-494` limpia el timeout sin invocar
  el callback pendiente).
- Resolver la TP monolítica: `apps/web-student/src/routes/episodio.$id.tsx:53-70` tiene el
  comentario literal `BUG-1: TP monolítica (sin ejercicioContext)`.
- `GET /api/v1/entregas/{id}/artefacto` — cuelga del prefijo ya mapeado
  (`apps/api-gateway/src/api_gateway/routes/proxy.py:87`), no toca el ROUTE_MAP.
- Botón "Descargar entrega" en las acciones del form de calificación
  (`CorreccionesView.tsx:1779`).
- Entregas viejas → `LEGACY`, reconstruibles best-effort desde el CTR pero **etiquetadas
  como reconstruidas** y no elegibles para corrección automática.
- **El artefacto se guarda POR EJERCICIO, no como un blob.** Con corrección por ejercicio (Fase 3)
  esto deja de ser una prolijidad: es el requisito. Cada fila lleva su `orden`, su `episode_id` y su
  `sha256` propio, más un `sha256` del conjunto.
- **Medir** cuántas entregas del piloto son ensamblables, monolíticas y LEGACY.

**Cómo se sabe que terminó:** un docente baja el archivo de una entrega nueva; el manifiesto
lista los N ejercicios esperados; el `sha256` está guardado y no se recalcula al leer.

---

### Fase 2 — Una rúbrica por ejercicio, empujada desde AI-Native
**Esfuerzo: medio. Da valor sola.**

> **Cambio de diseño (v3).** La v2 empujaba la rúbrica de la TP y corregía la entrega entera en un
> archivo. Ahora la unidad es **el ejercicio**: su rúbrica, su código y sus tests. El motivo no es
> estético — al mezclar cuatro ejercicios en un archivo, el modo de fallo más documentado de
> Active-IA (*"distingue presencia, no vínculo"*) puede contar una pieza del ejercicio 3 como
> cumplimiento de un criterio del 1. Corrigiendo de a uno, eso desaparece.

**Lo que ya existe y no hay que construir:**

```
Ejercicio.rubrica      JSONB   los criterios con su puntaje   (models/operacional.py:479)
Ejercicio.test_cases   JSONB   los casos con expected
TpEjercicio.orden      int     posición en el TP              (models/operacional.py:512)
TpEjercicio.peso_en_tp         peso relativo dentro del TP
```

**Trabajo del lado de Active-IA:**
- Rúbricas **a nivel ejercicio**, no unidad. Hoy el modelo es `materia → unidad → rubrica_id` y
  cuelga de Moodle por `cmid`. Hace falta que una unidad pueda tener N rúbricas, o un nivel nuevo.
- `POST /rubricas/` y `PUT /rubricas/{id}` (hoy sólo hay `GET`), y un `external_ref` propio —
  el `ejercicio_id` de AI-Native — para no depender de `cmid`, que no tenemos en ningún lado.
- Cuenta de servicio con rol coordinador: con rol tutor, `GET /rubricas/{id}` da **403**.
- **Aceptar el resultado de los tests como entrada.** Ver Fase 3.

**Trabajo del lado de AI-Native:**
- Tabla `activeia_credenciales` — igual que en la v2 (RLS + FORCE + policy por tenant, filtro
  `user_id` en la query, cripto de `platform-ops` con `ACTIVEIA_MASTER_KEY` propia, **no**
  `byok_keys` porque guarda los últimos 4 chars del plaintext en claro,
  `ai-gateway/services/byok.py:434`).
- **Validar la credencial con un login real al guardarla.** El listado de rúbricas devuelve `[]`
  también ante un fallo de auth: "no hay rúbricas" y "no me pude loguear" se ven idénticos.
- Sincronizador **por ejercicio**: al publicar o editar un `Ejercicio`, empujar su `rubrica` y
  guardar el `rubrica_id` devuelto en una tabla `activeia_rubrica_ejercicio`
  (`tenant_id, ejercicio_id, rubrica_id, sincronizado_at, rubrica_hash`). El `rubrica_hash`
  detecta desincronización sin comparar JSONs.
- Estado por ejercicio en la UI: sincronizado / desactualizado / sin sincronizar.
- Endpoints `/api/v1/activeia/*` ⇒ **entrada nueva en el ROUTE_MAP** (`proxy.py:33-104`).
- Roles: constante `CORRECCION_IA_ROLES` en `auth/dependencies.py`. No tocar el seed de Casbin.

**Lo que elimina:** el riesgo #3 de la v1 entero. Si la rúbrica sale del ejercicio y se empuja
automáticamente, no hay par que verificar a mano ni rúbrica equivocada posible.

---

### Fase 3 — El disparo, ejercicio por ejercicio, con los tests como evidencia
**Esfuerzo: grande.**

> **La idea central de la v3.** Active-IA lee código con Gemini. AI-Native lo **ejecuta** en un
> sandbox real. Los tres bugs del motor salen todos de juzgar leyendo: le puso 100/100 a una
> entrega donde nada estaba vinculado porque *vio* las piezas; elogió `if puntajes[i] == 990`
> porque *leyó* una búsqueda. **Un test ejecutado no se deja engañar por ninguna de las dos.**
> Entonces no se le mandan los test cases para que los interprete: se le manda **el resultado de
> haberlos ejecutado**, y queda haciendo lo único que el sandbox no puede — el juicio cualitativo
> que la rúbrica evalúa.

**Qué se manda, por ejercicio:**

```
código del alumno para ese ejercicio
rubrica_id  (el de Active-IA, sincronizado en la Fase 2)
resultado de los tests, recién ejecutado:
    4/4 · por caso: nombre, entrada, esperado, obtenido, pasa/falla
```

**Los tests se re-ejecutan en el momento de corregir, no se leen de ningún lado.**
El detalle vive en Redis con TTL de 600s (`execution_store.py:25`) y se borra solo; al CTR sólo
va `total/passed/failed` (`result_mapper.py:85`), sin qué caso ni con qué entrada. Re-ejecutar
sale barato, el sandbox ya está, y tiene tres ventajas sobre persistir:
1. El resultado corresponde **exactamente** al código que se va a mandar.
2. Es reproducible: cualquiera puede volver a correrlo y obtener lo mismo.
3. Valida de paso que lo entregado compila, antes de gastar una llamada a Gemini.

**Trabajo:**
- Tabla `correcciones_ia`: `id, tenant_id, entrega_id (FK, sin unique), **tp_ejercicio_id**,
  **orden**, disparado_por, rubrica_id, estado, nota_100 Numeric(5,2), desglose JSONB,
  tests_snapshot JSONB, artefacto_sha256, error_code, error_detail, timestamps`.
  RLS + FORCE. **Nunca escribe en `calificaciones`.**
  El `tests_snapshot` guarda lo que se mandó: sin eso, el PDF de Active-IA cita un resultado que
  nadie puede reconstruir después.
- Endpoints bajo el prefijo ya mapeado:
  `POST /api/v1/entregas/{id}/correccion-ia` con `{ejercicio_orden?: int, confirmado: bool}`.
  Sin `ejercicio_orden` corrige **todos**; con él, uno solo. → **202**.
  `GET .../correccion-ia` devuelve las N del último intento.
- **Corrección a demanda por defecto.** Cuatro ejercicios son cuatro llamadas a Gemini: entre 100 y
  160 segundos y 4× el costo, contra 25-40s de una sola. Con 9 alumnos entregando eso se nota. El
  botón por ejercicio es el camino barato; "corregir los 4" existe pero avisa el costo.
- **Membresía de comisión explícita en los tres endpoints.** No copiar `_assert_can_read`
  (`routes/entregas.py:585-593`): sólo mira el frozenset de roles, no filtra por comisión, y en
  prod todos los docentes comparten tenant.
- **Preview con `confirmado=false`**: qué ejercicio, qué rúbrica, qué tests van a correr y el
  tamaño de lo que se manda, sin gastar nada.
- **Gate**: sin artefacto persistido por ejercicio (Fase 1) no se dispara. LEGACY no elegible.
- **Idempotencia**: clave `(entrega_id, tp_ejercicio_id, rubrica_id, artefacto_sha256)`. Molde
  `routes/entregas.py:50-108`, con el detalle de re-setear el tenant RLS después del rollback del
  IntegrityError (`:93-97`). El ciclo `returned → submitted` reusa la misma fila y el mismo
  `entrega_id`: cambia el `artefacto_sha256`, no el id.
- Trabajo en `BackgroundTasks` con **sesión corta y semáforo**: el pool es de 8
  (`db/session.py:33-34`) y cuatro correcciones de 180s lo agotan. Con corrección por ejercicio el
  riesgo se multiplica por cuatro — el semáforo deja de ser opcional.
- **Presupuesto de tiempo total repartido entre intentos**, no N segundos por intento (molde:
  `academic-service/routes/ejercicios.py:300-372`).
- `GEMINI_OVERLOADED` y cualquier timeout = fallo de infraestructura, **nunca una nota**.
- Kill switch `activeia_enabled` default **False**; cuota por docente y día que falla **cerrada**,
  contando filas en Postgres (no hay Redis en evaluation-service y su dep declarada está muerta).
- Frontend: botón por ejercicio en las tarjetas de `CorreccionesView`, no uno global. Polling con
  `setTimeout` recursivo y limpieza en el unmount (molde `ExportView.tsx:46-76`).
  **Dos clases de error, dos banners** (molde `EjerciciosView.tsx:1259-1308`).

**Cómo se combinan las cuatro notas — hay que decidirlo, no que salga por descarte.**
Vuelven N notas /100 y el docente carga una sola /10. La propuesta: **promedio ponderado por
`TpEjercicio.peso_en_tp`**, que ya existe. Se muestra el cálculo desglosado, nunca sólo el
resultado. Y si falta la corrección de algún ejercicio, **no se promedia**: se muestra parcial y
se dice cuáles faltan. Un promedio sobre 3 de 4 con el cuarto en cero es exactamente cómo se
fabrica una nota injusta.

**Cómo se sabe que terminó:** un docente corrige el Ejercicio 2 de una entrega real y ve su nota
/100 con el resultado de los tests que se mandó. Con la sesión del alumno abierta, el alumno no ve
nada. Doble click = una corrección. Un `GEMINI_OVERLOADED` muestra banner ámbar y no crea nota.
Corregir los 4 muestra la tabla completa y el promedio ponderado con su cálculo a la vista.

---

### Fase 4 — El PDF y el borrado
**Esfuerzo: medio (era más grande).**

- Extraer `BaseStorage`/`MockStorage`/`S3Storage` de content-service
  (`services/storage.py:21-152`) a un paquete compartido. **PR propia**, con el smoke de
  materiales verde antes de seguir.
- Bajar el PDF al cerrar la corrección, guardar `pdf_storage_key`, key no adivinable,
  prefijo propio, nunca el bucket de materiales.
- `GET .../correccion-ia/{cid}/pdf` con el mismo gate de comisión. Nunca link público.
- **Extender `anonymize_student`** (`packages/platform-ops/src/platform_ops/privacy.py:147-192`):
  hoy solo rota `episodes.student_pseudonym`. Hay que rotar también en `correcciones_ia`,
  borrar el PDF del storage y borrar el artefacto de la Fase 1.
- **Y ahora sí: borrar también del lado de Active-IA.** En la v1 esto era imposible y quedaba
  como riesgo permanente. Con el servicio propio, el retiro del piloto se puede cumplir
  entero. Hace falta un endpoint de borrado por alumno del otro lado.
- Retención de PDFs y artefactos: N meses, con job o procedimiento documentado.
- Resolver la dep muerta `weasyprint>=62` (`apps/evaluation-service/pyproject.toml:25`,
  cero imports): se usa o se saca.

---

### Fase 5 — El cruce: de la sugerencia a la nota del docente
**Esfuerzo: medio.**

- Card de resultado entre la barra de progreso y las tarjetas de ejercicios
  (`CorreccionesView.tsx:1487-1531`): nota /100, /10 propuesta, desglose, link al PDF y qué
  rúbrica se usó.
- Botón **"Usar como base"** que rellena el campo de nota (÷10, mostrando el redondeo) y deja
  el foco ahí. **No guarda.** `POST /{id}/calificar` (`routes/entregas.py:346`) sigue siendo
  un acto del docente.
- **Guardrail aritmético**: sumar los criterios y comparar con el total. Con la Fase A esto
  debería no dispararse nunca — por eso queda como red, no como parche.
- **No mapear los criterios de Active-IA contra los de la rúbrica local.** `mapSavedToInputs`
  empareja `detalle_criterios` por string del criterio
  (`CorreccionesView.tsx:738-761,821-837`): un match por nombre produce cruces falsos que
  parecen datos. Lado a lado, sin fusionar.
- Entrada en `helpContent` y tests en `apps/web-teacher/tests/CorreccionesView.test.tsx`.

---

### Fase 6 — Hardening y cierre
**Esfuerzo: medio.**

- Smoke E2E en `tests/e2e/smoke/` con Active-IA reemplazado por un doble HTTP: camino feliz,
  409, `GEMINI_OVERLOADED`, credencial inválida, artefacto ausente.
- Métricas OTel (molde `execution-service/services/metrics.py:27-92`) y rastro structlog
  (`correccion_ia_disparada`, patrón `tp_calificada` en `routes/entregas.py:391-400`).
  **Meta-evento de negocio, NO va a la cadena del CTR** (ADR-010).
- **Cerrar el gate de comisión del CTR, que hoy es no-op en producción**:
  `apps/ctr-service/src/ctr_service/auth/dependencies.py:173` corta si falta
  `academic_db_url`, y `docs/EASYPANEL-DEPLOY.md:110` no lista esa variable en el env del
  servicio. Agregarla y verificar.
- Extender el filtro por comisión a los cuatro endpoints que hoy no lo tienen (`GET /{id}`,
  `calificar`, `PATCH /calificacion`, `return`).
- **ADR nuevo** (el último es el 060): por qué Active-IA no pasa por el ai-gateway.
  `docs/adr/004-ai-gateway-propio.md:9` nombra este caso de uso por su nombre y CLAUDE.md lo
  declara invariante. El bypass es defendible —Active-IA corre su propio Gemini y no recibe
  ninguna key nuestra— pero hay que escribirlo, no disimularlo.
- `FEATURES.md:59` deja de decir "⛔ vive en active-ia, fuera de scope".
- Runbook: kill switch, rotación de `ACTIVEIA_MASTER_KEY` y por qué es distinta de
  `BYOK_MASTER_KEY`, qué pasa con las `running` durante un deploy.
- Nota viva de Obsidian: **reescribir** frontmatter, Estado actual, Últimos avances y
  Próximos pasos; **apilar** en Gotchas y Decisiones clave.

---

## 4. Lo que no vamos a hacer

- **No se escribe en `calificaciones`.** Ni una fila. `CheckConstraint("nota_final >= 0 AND
  nota_final <= 10")` (`models/entregas.py:128-129`) y el alumno la ve en `graded`.
  Automatizar eso rompe el humano-en-el-medio en el mismo commit.
- **No hay corrección en lote**, aunque la vista ya tenga cola de lote
  (`CorreccionesView.tsx:933-1049`). Va a pedirse en la primera demo; la respuesta es no
  hasta que el circuito completo esté probado.
- **No se mapean los criterios de Active-IA contra los de la rúbrica local.**
- **No se siembra `correccion_ia` en Casbin**: evaluation-service no tiene enforcer.
- **No se agrega Redis** a evaluation-service para la cuota. Es un `count(*)`.
- **No se emiten eventos nuevos al CTR.**
- **No se corrigen entregas LEGACY.**
- **No se fuerza la corrección donde no aplica** (los TP de Git son URLs, no código subido).
- **No se monta un visor de PDF.** Descarga y listo.

---

## 5. Riesgos vivos (de 8 quedaron 4)

1. **La personería frente al consentimiento.** Ver 2.1. No bloquea el desarrollo; bloquea el
   despliegue con datos reales.
2. **El artefacto reconstruido no es reproducible para el histórico.** Se arregla hacia
   adelante (Fase 1), pero las entregas ya cerradas del piloto nunca van a tener snapshot
   del momento del submit. Cualquier corrección sobre ellas es sobre una lectura.
3. **`jtp` y `auxiliar` pasan cualquier permiso.** `auth/dependencies.py:100,109-110`: el
   frozenset de cinco roles devuelve el user sin mirar `resource` ni `action`, y está
   replicado en cuatro lugares. Mitigado con una constante propia; la granularidad real
   requiere el enforcer.
4. **Aislamiento por comisión.** En prod todos los docentes comparten tenant y la RLS no los
   separa; solo el listado filtra a mano (`routes/entregas.py:152-172`). Con un UUID en mano
   cualquier docente del tenant lee cualquier entrega. Es enumeración, no navegación, pero
   alcanza para gastar cuota ajena y mandar código de un alumno de otra comisión.

**Resueltos por la premisa correcta:** el gate de Comité como bloqueante, la copia que no se
disocia, la rúbrica equivocada, y el 409 de clave desconocida.

---

## 6. Por dónde empezar

**Esta semana, en paralelo:**

- **Fase 0** — las cinco preguntas, leyendo el código de Active-IA. Media hora.
- **Fase A** — el bug del 04/08 que desaprobó a una alumna. Ya está reportado y no depende
  de nada de esto.

**Después, en orden:**

- **Fase 1** — arregla algo roto hoy: que el docente pueda bajar el código de una entrega.
  Sirve aunque Active-IA nunca se conecte.
- **Fase 2** — depende de la respuesta 1 de la Fase 0.
- **Fase 3** en adelante — recién acá aparece el botón.

**La regla que atraviesa todo:** la plataforma propone, el docente decide. En el momento en
que la nota se cargue sola, todo el diseño pierde sentido.
