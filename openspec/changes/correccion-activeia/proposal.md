## Why

Un docente que corrige una entrega hoy no puede ni siquiera **bajar el código que entregó el
alumno**: el modelo `Entrega` no persiste una sola línea del editor
(`apps/evaluation-service/src/evaluation_service/models/entregas.py:52-71`). Lo único que existe es
el snapshot del último `edicion_codigo` del CTR, que se ingesta de forma asíncrona
(`apps/ctr-service/src/ctr_service/routes/events.py:80` devuelve 202 y un worker escribe después).
Cualquier artefacto armado leyendo el CTR en el momento de corregir certifica *"esto es lo que leí
cuando lo pedí"*, no *"esto es lo que el alumno entregó"* — y ante una impugnación eso es
indefendible.

Sobre esa base falta, se quiere sumar la corrección asistida con **Active-IA**, el servicio de
corrección del mismo ecosistema: el docente aprieta un botón, se manda el código de un ejercicio
con su rúbrica y el resultado de ejecutar sus tests, y vuelve una nota sobre 100 con desglose y PDF.
El resultado lo ve **solo el docente**, que sigue cargando la nota a mano.

Esto revierte una decisión previa que declaraba F15 fuera de scope (`FEATURES.md:59`). El encuadre
que la fundaba era incorrecto: Active-IA no es otro negocio, es el mismo ecosistema y lo opera el
mismo equipo.

## What Changes

**Epic 1 — La entrega contiene lo que se entregó** (independiente de Active-IA, da valor solo)
- La `Entrega` persiste el código del alumno **por ejercicio** en el submit, mandado por el cliente,
  con `orden`, `episode_id` y `sha256` propio más un `sha256` del conjunto.
- `ejercicio_estados` se siembra al crear la entrega desde `tp_ejercicios`; hoy se construye con
  `[]` hardcodeado (`routes/entregas.py:81`) y las filas sólo aparecen si alguien llama al PATCH por
  ejercicio, así que "falta un ejercicio" es el estado inicial de toda entrega.
- El submit valida el conteo contra los ejercicios **esperados**, no contra los presentes: hoy
  `if estados:` con lista vacía no valida nada (`routes/entregas.py:236-245`).
- Endpoint `GET /api/v1/entregas/{id}/artefacto` y botón "Descargar entrega" en la vista de
  correcciones.
- Las entregas anteriores al cambio se marcan `LEGACY`, reconstruibles best-effort desde el CTR
  pero **etiquetadas como reconstruidas** y no elegibles para corrección automática.

**Epic 2 — Conectar y sincronizar**
- Credenciales de Active-IA **por docente**, encriptadas con AES-256-GCM
  (`packages/platform-ops/src/platform_ops/crypto.py`) y `ACTIVEIA_MASTER_KEY` propia. No se reusa
  `byok_keys`: su scope es tenant/materia y guarda los últimos 4 caracteres del plaintext en claro
  (`apps/ai-gateway/src/ai_gateway/services/byok.py:434`), lo que con un password humano es una fuga.
- Validación con login real al guardar la credencial: el listado de rúbricas de Active-IA devuelve
  `[]` también ante fallo de auth, así que "no hay rúbricas" y "no me pude loguear" son
  indistinguibles sin esto.
- Sincronizador: al publicar un TP se empuja a Active-IA su estructura completa — TP con sus
  ejercicios, y cada ejercicio con su `rubrica`, sus `test_cases` y su `peso_en_tp`. Se guarda el
  identificador devuelto y un hash de la rúbrica para detectar desincronización.
- Estado visible por ejercicio: sincronizado / desactualizado / sin sincronizar.

**Epic 3 — El disparo, por ejercicio**
- `POST /api/v1/entregas/{id}/correccion-ia` con `ejercicio_orden` opcional. Devuelve **202**.
- Antes de mandar, **se re-ejecutan los tests del ejercicio en el sandbox propio** y se envía el
  resultado detallado junto al código. El detalle de una ejecución previa no sirve: vive en Redis
  con TTL de 600s (`apps/execution-service/.../execution_store.py:25`) y al CTR sólo llega
  `total/passed/failed` (`.../result_mapper.py:85`).
- Tabla `correcciones_ia`, una fila por ejercicio corregido, con `tests_snapshot` de lo que se mandó.
- Asíncrono con polling; idempotencia por `(entrega_id, tp_ejercicio_id, rubrica_id, artefacto_sha256)`.
- Un fallo de infraestructura (`GEMINI_OVERLOADED`, timeout) **nunca produce una nota**.
- Kill switch con default `False` y cuota por docente y día que falla **cerrada**.

**Epic 4 — Mostrar sin decidir**
- Card de resultado en la vista de correcciones: nota /100 por ejercicio, promedio ponderado por
  `peso_en_tp` **con el cálculo desglosado a la vista**, y link al PDF.
- Si falta la corrección de algún ejercicio **no se promedia**: se muestra parcial y se dice cuál
  falta.
- Botón "Usar como base" que rellena el campo de nota (÷10) y **no guarda**.
- **BREAKING (de política, no de API): la plataforma nunca escribe en `calificaciones`.** Calificar
  sigue siendo un acto explícito del docente vía `POST /{id}/calificar`.

## Capabilities

### New Capabilities
- `entrega-artefacto`: persistencia del código entregado por ejercicio, con hash verificable, y su
  descarga por el docente. Incluye el estado `LEGACY` para lo anterior al cambio.
- `activeia-integracion`: credenciales de Active-IA por docente y sincronización de la estructura
  del TP (ejercicios, rúbricas, test cases y pesos) hacia el servicio externo.
- `activeia-correccion`: disparo de corrección por ejercicio con el resultado de los tests como
  evidencia, persistencia del resultado, y su presentación al docente sin escritura automática de
  notas.

### Modified Capabilities
- `entregas-submission`: el submit pasa a exigir el código de cada ejercicio y a validar el conteo
  contra los ejercicios esperados del TP, no contra los marcados.
- `correccion-grading`: la vista de corrección suma el artefacto descargable y el resultado de
  Active-IA como sugerencia; el acto de calificar no cambia.

## Impact

**Servicios**
- `evaluation-service` — dueño de la feature. Tablas nuevas (`entrega_artefactos`,
  `activeia_credenciales`, `activeia_rubrica_ejercicio`, `correcciones_ia`), migrations con RLS
  `ENABLE` + `FORCE`, cliente HTTP a Active-IA con timeout 90s, y trabajo asíncrono con
  `BackgroundTasks` + reconciliador en el lifespan.
- `execution-service` — se lo invoca para re-ejecutar los tests antes de corregir. Sin cambios de
  contrato.
- `api-gateway` — entrada nueva en el `ROUTE_MAP` para el prefijo `/api/v1/activeia`
  (`apps/api-gateway/src/api_gateway/routes/proxy.py:33-104`). Todo lo que cuelga de
  `/api/v1/entregas` ya está mapeado (`:87`).
- `web-student` — el submit manda el código; arreglar el flush del debounce al desmontar el editor
  (`apps/web-student/src/components/CodeEditor.tsx:490-494`).
- `web-teacher` — botón de descarga, conexión de cuenta, estado de sincronización, botón por
  ejercicio y card de resultado en `CorreccionesView`.

**Dependencias externas**
- Requiere cambios **del lado de Active-IA**, especificados en
  `docs/research/activeia-cambios-pedidos.md`: un nivel de "ejercicio" bajo el TP, `external_ref`
  para no depender de `cmid` (AI-Native no tiene ninguno), endpoints de escritura de rúbricas,
  aceptar el resultado de tests, cuenta de servicio y borrado por alumno. **El Epic 1 no depende de
  esto; los Epics 2 a 4 sí.**

**Invariantes que NO se tocan**
- No se emiten eventos nuevos al CTR: el rastro es un meta-evento de negocio por structlog, patrón
  `tp_calificada` (`routes/entregas.py:391-400`). El append-only (ADR-010) no se ve afectado.
- No se toca `_EXCLUDED_FROM_FEATURES` ni el `classifier_config_hash`.
- No pasa por el `ai-gateway`: Active-IA corre su propio Gemini y no recibe ninguna key nuestra.
  Requiere ADR nuevo porque `docs/adr/004-ai-gateway-propio.md:9` nombra este caso de uso.

**Riesgos que quedan fuera del alcance técnico**
- Confirmar que AI-Native y Active-IA son la misma personería frente al consentimiento firmado por
  los alumnos. No bloquea el desarrollo; bloquea el despliegue con datos reales.
- El histórico del piloto nunca va a tener snapshot del momento del submit (de ahí `LEGACY`).
