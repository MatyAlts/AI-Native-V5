# ONBOARDING — Testing del piloto AI-Native N4

> Documento operativo para quien recibe el proyecto **mañana** y tiene que ponerse a testearlo. Pensado para "qué hago la primera hora". Para overview conceptual ver [`README.md`](README.md); para invariantes técnicos del backend ver [`AI-NativeV3-main/CLAUDE.md`](AI-NativeV3-main/CLAUDE.md).

**Estado del proyecto al 2026-05-15**: 5 universidades aisladas en BD (1 universidad = 1 tenant, ADR aplicado), 25 ejercicios canónicos del piloto UTN, TenantSelector dinámico en los 3 frontends, workers CTR funcionando, tutor socrático con LLM real vía BYOK, tests E2E con Playwright validados.

---

## 1. Bienvenida

Lo que estás por testear es la plataforma **AI-Native N4**, la implementación de la tesis doctoral de Alberto Alejandro Cortez en UNSL. Es un sistema de tutoría socrática con trazabilidad cognitiva criptográfica para enseñanza de programación universitaria. En cristiano: un alumno escribe código Python en el browser, un tutor con LLM real lo guía con preguntas (sin darle la respuesta), y **cada evento del proceso queda anclado en una cadena SHA-256 append-only** que después permite auditar bit-a-bit cómo aprendió.

Lo que **NO es**: un producto comercial, una herramienta lista para venderse, ni un MVP con UX pulida. Es un **piloto académico** cuya aceptabilidad doctoral depende de invariantes criptográficas (append-only, reproducibilidad bit-a-bit, k-anonymity N≥5) y de poder defenderse frente a un comité. Eso explica decisiones que de afuera parecen sobre-ingeniería: el CTR, las 5 coherencias separadas, el `classifier_config_hash`, el bus Redis Streams particionado, los tests smoke E2E que blindan invariantes.

Lo que se te pide como tester: **encontrar el lugar donde el modelo se rompe**. No reportar errores de tipografía ni gustos de UI — reportar comportamientos que invaliden la promesa académica. Cross-tenant leaks. Episodios que se cierran sin clasificación. Cadenas CTR que dejan de validar. Datos que aparecen en una universidad que pertenecen a otra. Errores 500 en consola del navegador. Hashes que cambian entre dos clasificaciones del mismo episodio. Si encontrás algo de eso, anotalo y reportalo siguiendo la sección 6 de este documento.

---

## 2. Setup en 10 minutos

Si es la **primera vez** corriendo el proyecto en esta máquina, seguí el bootstrap completo del [`README.md`](README.md) (sección 4) — son ~10-15 minutos la primera vez (Docker compose pulling images, `uv sync`, migraciones, seeds). Acá NO lo duplico.

Si **ya está bootstrappeado** (la persona que te entregó la máquina ya corrió el bootstrap), arrancar el stack es esto:

```bash
cd /home/juanisarmiento/ProyectosFacultad/juani4/AI-NativeV3-main

# 1. Levantar infra Docker (Postgres, Redis, Keycloak, MinIO) — 30-60s
docker compose -f infrastructure/docker-compose.dev.yml up -d

# 2. Backend: 11 servicios Python + 8 workers CTR — 20-30s hasta que esté todo listening
bash scripts/dev-start-all.sh

# 3. Frontends Vite (en otra terminal o tmux pane)
make dev
```

**Verificación rápida** antes de abrir el browser (no salteés esto):

```bash
bash scripts/check-health.sh
```

Tenés que ver **10/11 servicios OK**. El que queda en `503` es `integrity-attestation-service:8012` — eso es **by design** en dev local (vive en VPS UNSL en piloto real). No es un bug, no es un bloqueante.

Si algún otro servicio falla en `check-health`, NO sigas al tour — pegale una mirada a la sección 10 (Troubleshooting) del [`README.md`](README.md). Los síntomas típicos son: container Docker ajeno en puerto 5173/5174/5175, BYOK_MASTER_KEY no seteada en `.env`, alembic con permission denied.

---

## 3. Tour guiado de 30 minutos

Tres URLs, un orden recomendado. Abrilas en pestañas separadas del mismo browser.

### 3.1. Admin (http://localhost:5173) — 10 minutos

Sos `superadmin` + `docente_admin`. En el header arriba a la derecha tenés el **TenantSelector**: un dropdown con las 5 universidades del seed. Verificá que:

- El dropdown lista las 5 universidades (UNSL, UTN-FRM, UTN-FRSN, y dos más del seed).
- Al cambiar de universidad, el dashboard muestra **otros datos** (otras comisiones, otros docentes, otros alumnos). Si los datos NO cambian, hay un bug grave de aislamiento — reportá inmediato.

Recorré las páginas del menú lateral:

- **Universidades**: ABM completo. Probá crear una nueva.
- **Comisiones**: 5 comisiones del seed (3 de A-Mañana / B-Tarde / C-Noche en una uni, 2 en otra).
- **BYOK Keys**: configuración de API keys de LLM por tenant. Cada universidad tiene las suyas.
- **Auditoría CTR**: el panel para verificar integridad criptográfica de un episodio. Lo vamos a usar en el escenario 4 más abajo.
- **Bulk import**: importación de inscripciones por CSV.

### 3.2. Docente (http://localhost:5174) — 10 minutos

Sos `docente01`, titular de Comisión 1. Acá la navegación es por **TanStack Router** (file-based) — fijate que los search params en la URL cambian al navegar (`?comisionId=...&studentId=...`).

Verificá:

- **TenantSelector también acá**. Cambiar de uni reflejado en todo.
- **Home**: dashboard con cards de progresión cohorte.
- **Templates**: bancos de TPs reusables a nivel `(materia, periodo)`.
- **Tareas Prácticas**: instancias por comisión.
- **Materiales / Banco de ejercicios**: los 25 ejercicios canónicos del piloto. Verificá que aparecen.
- **Progression**: vista cohorte con k-anonymity (N≥5 sobre cuartiles). Si la comisión tiene N<5 estudiantes con classifications, debería decir `insufficient_data`.
- **Kappa rating**: pantalla de validación intercoder (todavía sin uso real — está esperando coordinación de 2 docentes UNSL).

### 3.3. Alumno (http://localhost:5175) — 10 minutos

Sos `alumno01` (UUID `b1b1b1b1-0001-0001-0001-000000000001`, inscripto en Comisión 1 de A-Mañana). El flujo es:

1. **Comisión**: dropdown arriba — debe estar pre-seleccionada Comisión 1.
2. **Lista de TPs**: las que el docente publicó para esa comisión.
3. **Abrir un ejercicio**: te lleva a `EpisodePage` — la única página full-screen del repo (no usa `PageContainer`, layout custom).
4. En `EpisodePage` ves: consigna (markdown), editor Monaco con Python, panel del tutor socrático (SSE en streaming), botón "Cerrar episodio".

**Si NO ves TPs en la lista**, probablemente es la **brecha B.2 conocida** (ver sección 8). El selector cae al fallback hardcoded en `vite.config.ts`. Asegurate que el seed `seed-3-comisiones.py` haya corrido recientemente.

---

## 4. 5 escenarios concretos para testear

Cada escenario tiene **objetivo**, **pasos** y **criterio de éxito**. Si el criterio no se cumple, es un bug — reportalo siguiendo el formato de la sección 6.

### Escenario 1: Crear una universidad nueva debe aislar todo

**Objetivo**: validar que 1 universidad = 1 tenant, sin filtración de datos.

**Pasos**:
1. En el admin (5173) → Universidades → "Crear nueva".
2. Nombre: `Universidad Test`, abreviatura: `UT`.
3. Confirmar creación. Anotar el UUID que devuelve.
4. Cambiar a esa universidad en el TenantSelector.
5. Navegar a: Comisiones, Materias, Ejercicios, Alumnos.

**Criterio de éxito**:
- La universidad nueva arranca con **0 comisiones, 0 materias, 0 ejercicios, 0 alumnos**.
- **NO debe heredar** los 25 ejercicios canónicos ni las comisiones del seed.
- Volver a la universidad anterior con TenantSelector → todos los datos vuelven.
- En el backend (inspección manual, ver sección 7), `tenant_id` de la universidad nueva debe ser igual al `id` de la universidad (convención `universidad.id == tenant_id`).

### Escenario 2: TenantSelector cambia datos en los 3 frontends

**Objetivo**: validar que el switch de tenant funciona consistente en admin, docente y alumno.

**Pasos**:
1. En el admin, cambiar a una universidad B (no la inicial).
2. Abrir el web-teacher (5174) en otra pestaña. Ver qué comisiones lista.
3. Volver al admin, cambiar a universidad C.
4. Recargar el web-teacher.

**Criterio de éxito**:
- El cambio de tenant en el admin se propaga al teacher/student vía `localStorage` + header `x-selected-tenant`.
- Las comisiones que muestra el teacher cambian según el tenant activo.
- **Cero datos cruzados**: en consola del navegador (DevTools → Network), ningún response debe traer registros con `tenant_id` que no sea el activo.

### Escenario 3: Episodio completo como alumno (consigna → código → tutor → cierre N4)

**Objetivo**: validar el flujo pedagógico end-to-end.

**Pasos**:
1. En el web-student (5175), abrir un TP de Comisión 1.
2. Seleccionar el primer ejercicio.
3. Leer la consigna (debe renderizar markdown).
4. Escribir código Python en el editor Monaco.
5. Ejecutar con Pyodide (botón "Run") — el resultado debe aparecer en el panel de output.
6. **Charlar con el tutor** mandando 2-3 preguntas. El tutor debe responder con **preguntas socráticas**, NO con la respuesta directa.
7. Cuando el código pase los tests, cerrar el episodio.
8. Después del cierre, esperar 1-3 segundos.

**Criterio de éxito**:
- El tutor responde **en streaming** (SSE) con LLM real (Mistral/OpenAI/Anthropic/Gemini según BYOK del tenant).
- Las respuestas del tutor son **socráticas** (preguntas, no spoiler de la solución).
- Al cerrar el episodio, aparece un **diagnóstico N4** con las 5 coherencias separadas: CT, CCD_mean, CCD_orphan_ratio, CII_stability, CII_evolution.
- El diagnóstico incluye una `appropriation`: `autonomo` / `superficial` / `delegacion_pasiva` / `delegacion_extrema` / `regresivo`.
- En consola del navegador, **cero errores 500 ni 4xx** durante todo el flujo.

### Escenario 4: Verificar integridad del CTR desde admin

**Objetivo**: validar que la cadena criptográfica del episodio anterior está sana.

**Pasos**:
1. Anotar el `episode_id` del episodio que cerraste en el escenario 3 (visible en la URL de `EpisodePage` o en el panel admin → Auditoría CTR).
2. En admin (5173) → Auditoría CTR.
3. Pegar el `episode_id` en el buscador.
4. Hacer click en "Verificar cadena".

**Criterio de éxito**:
- Respuesta `is_valid: true` con todos los eventos del episodio en orden secuencial (`seq=0, 1, 2, ...`).
- Para cada evento, `chain_hash` calculado debe coincidir con el almacenado.
- `prev_chain_hash` del primer evento es `GENESIS_HASH = "0" * 64`.
- `self_hash` recomputado debe coincidir con el almacenado.

### Escenario 5: Tampering test manual

**Objetivo**: validar que cualquier modificación a la BD del CTR es **detectada** por verify chain.

**Pasos**:
1. Tomar el mismo `episode_id` del escenario 4.
2. Conectarse a Postgres (ver sección 7) y modificar el `self_hash` de un evento al azar:

   ```bash
   docker exec -it platform-postgres psql -U postgres -d ctr_store -c "
     SET row_security = off;
     UPDATE events SET self_hash = 'deadbeef' || substring(self_hash from 9)
     WHERE episode_id = '<EPISODE_ID_AQUI>' AND seq = 2;
   "
   ```

3. Volver al admin → Auditoría CTR → Verificar la cadena del mismo episodio.

**Criterio de éxito**:
- La verificación devuelve `is_valid: false` con un mensaje indicando **qué evento (seq=2)** y **qué hash** falló.
- El episodio queda marcado como `integrity_compromised: true` en `episodes`.
- El frontend muestra un banner claro de tampering detectado.

**IMPORTANTE post-test**: restaurar el `self_hash` original o correr `reset-to-seed.sh` para limpiar el estado. Una BD con tampering no remediado contamina escenarios posteriores.

---

## 5. Qué NO debe pasar

Si ves alguna de estas situaciones, **es bug crítico, reportar inmediato**:

- **Cross-tenant leak**: navegar como tenant A y ver datos (comisiones, alumnos, ejercicios, episodios, classifications) que pertenecen a tenant B.
- **Errores 500 en consola del navegador** durante flujos normales (abrir episodio, mandar prompt al tutor, cerrar episodio). Los 500 indican excepción no-handled del backend.
- **Episodios "huérfanos" sin cerrar**: episodios con estado `abierto` después de >30 min sin actividad que no terminan en `episodio_abandonado` (el doble trigger ADR-025 debería garantizar esto: frontend `beforeunload` + worker server-side a 60s).
- **`is_valid: true` después de tampering manual**: si modificás `self_hash` o `chain_hash` y verify NO detecta el cambio, está roto el invariante append-only criptográfico — eso invalida la tesis entera.
- **Clasificaciones con `classifier_config_hash` distinto** entre dos clasificaciones del mismo episodio idéntico: rompe reproducibilidad bit-a-bit.
- **TenantSelector que no propaga el cambio**: cambiar de uni y seguir viendo datos de la anterior.
- **Las 5 coherencias colapsadas en un score único** en el frontend: la tesis exige que se muestren separadas.
- **`reflexion_completada`, `tp_entregada` o `tp_calificada` afectando la clasificación**: están explícitamente excluidos del feature extraction (ADR-027/044). Si una clasificación cambia al emitir uno de estos, está contaminado el classifier.

---

## 6. Cómo reportar bugs

Formato sugerido (texto plano o markdown, lo que prefieras):

```
### Título del bug
(una línea descriptiva)

### Severidad
crítica | alta | media | baja
(crítica = invalida invariante doctoral; alta = bloquea flujo; media = degradación UX; baja = cosmético)

### Pasos para reproducir
1. ...
2. ...
3. ...

### Resultado esperado
(qué debería pasar)

### Resultado obtenido
(qué pasa en realidad)

### Evidencia
- Screenshot del browser (DevTools abierto si hay error en consola)
- Logs del servicio relevante (ver sección 7: cómo leer logs)
- Si hay request fallido: copy del Network tab (request + response headers + body)

### Tenant activo
(qué universidad estaba seleccionada en TenantSelector)

### Frontend afectado
admin (5173) | docente (5174) | alumno (5175)

### Reproducible
sí, siempre | sí, intermitente | una sola vez (no reproducible)
```

**Antes de reportar**, leé la sección 8 ("Limitaciones conocidas") — si tu hallazgo cae ahí, no es bug, es deuda ya catalogada.

---

## 7. Atajos útiles

### Inspeccionar BD directamente

Hay 4 bases lógicas en el mismo Postgres container (`platform-postgres`):

```bash
# Académico (universidades, comisiones, ejercicios, TPs, inscripciones, BYOK keys)
docker exec -it platform-postgres psql -U postgres -d academic_main

# Cadena CTR (events, episodes)
docker exec -it platform-postgres psql -U postgres -d ctr_store

# Clasificaciones N4
docker exec -it platform-postgres psql -U postgres -d classifier_db

# RAG / content
docker exec -it platform-postgres psql -U postgres -d content_db
```

Queries rápidas tipo dentro de psql:

```sql
-- Listar universidades / tenants
SET row_security = off;
SELECT id, nombre, abreviatura FROM universidades;

-- Cuántos episodios cerrados hay por estudiante
SET row_security = off;
SELECT student_pseudonym, COUNT(*) FROM episodes WHERE estado = 'cerrado' GROUP BY 1;

-- Ver eventos de un episodio en orden
SET row_security = off;
SELECT seq, event_type, n_level FROM events WHERE episode_id = '<UUID>' ORDER BY seq;
```

**Importante**: `SET row_security = off` antes de las queries de inspección manual. Si no, RLS te filtra por el `app.current_tenant` que está vacío y no ves nada.

### Reset rápido entre tests

```bash
bash /home/juanisarmiento/ProyectosFacultad/juani4/AI-NativeV3-main/scripts/reset-to-seed.sh
```

Borra TPs creadas, unidades, episodios, classifications, ejercicios generados con IA. **Preserva**: comisiones, docentes, alumnos, los 25 ejercicios canónicos, policies Casbin, BYOK keys. Útil antes de re-correr un escenario desde cero. Tarda ~3 segundos.

### Logs de los servicios

`dev-start-all.sh` arranca cada servicio en background con su log redirigido. Los logs viven en:

```
AI-NativeV3-main/logs/<servicio>.log
```

Para seguir en vivo el log de un servicio:

```bash
tail -f AI-NativeV3-main/logs/tutor-service.log
tail -f AI-NativeV3-main/logs/ctr-service.log
```

(Si tu shell tiene `bat`/`rg`, `bat -f` o `rg --follow` también valen).

### Stop / restart limpio

```bash
# Parar backend (mata los 11 servicios + 8 workers)
bash AI-NativeV3-main/scripts/dev-stop-all.sh

# Parar frontends: Ctrl+C en el shell de `make dev`

# Reset duro de Docker (último recurso)
docker compose -f AI-NativeV3-main/infrastructure/docker-compose.dev.yml down
docker compose -f AI-NativeV3-main/infrastructure/docker-compose.dev.yml up -d
```

### Health check rápido

```bash
bash AI-NativeV3-main/scripts/check-health.sh
```

10/11 OK = todo bien. Si baja a 9/11, mirar el log del servicio que cae y reiniciarlo individual.

---

## 8. Limitaciones conocidas (NO reportar como bugs)

Estas las tenemos catalogadas. Si tu hallazgo cae acá, no perdés tiempo escribiendo el bug — ya está en el backlog.

| Limitación | Síntoma observable | Tracking |
|---|---|---|
| **Gap B.2: comisiones del alumno** | `GET /api/v1/comisiones/mis` devuelve vacío para estudiantes reales. El web-student cae al `selectedComisionId` hardcoded en `vite.config.ts`. | Se destraba con claim `comisiones_activas` en JWT de Keycloak (coordinación con DI UNSL pendiente). Plan en `docs/research/plan-b2-jwt-comisiones-activas.md`. |
| **Hashes ceremoniales `"c" * 64`** en algunos eventos seed | Algunos eventos del seed tienen `self_hash = "cccc...cccc"` (placeholder). No son episodios reales — son seed data. | By design del seed inicial; episodios creados en runtime SÍ tienen hashes reales. No verificar la cadena de los episodios del seed con `"c"*64`. |
| **106 classifications con hash legacy** | Hashes pre-LABELER_VERSION 1.2.0 (`9dd96894...`). | Acción A1 del plan, requiere re-clasificar con DB del piloto real. |
| **`integrity-attestation-service:8012` devuelve 503** | `check-health` lo marca como degraded. | By design en dev local — vive en VPS UNSL en piloto real. No bloqueante. |
| **`byok_keys_usage` vacía cuando resolver cae a env_fallback** | Auditoría de costos BYOK puede no tener todos los registros. | Backlog QA pass 2026-05-07. Sentinel pattern UUID v5 cerrando gap, ver `audi2.md`. |
| **`tutor_respondio.payload` sin tokens_input/output/provider** | Solo persiste `model`, `content`, `chunks_used_hash`. | Backlog QA pass 2026-05-07. |
| **`nota_final` serializado como string `"8.50"`** | Frontends que tipan como `number` pueden romper con `.toFixed()`. | Backlog QA pass 2026-05-07. |
| **Re-POST `/classify_episode/{id}` da 500 duplicate-key** | Debería ser idempotente (no-op con classification existente). | Backlog QA pass 2026-05-07. |
| **Filtro `unidad_id` en `GET /tareas-practicas` no filtra** | Devuelve todas las TPs aunque pases `unidad_id`. | Backlog QA pass 2026-05-07. |
| **Leak parcial de `student_pseudonyms` en `/comisiones/{id}/inscripciones`** | Handler devuelve todos en vez de filtrar a `WHERE student_pseudonym = user.id` para estudiantes. | Backlog QA pass 2026-05-07. |
| **Vite cambia de puerto si 5173/5174/5175 están ocupados** | `make dev` puede arrancar en 5176/5177. | Ver salida real de `make dev` para confirmar puertos. Container Docker ajeno = matarlo. |
| **Socratic compliance / lexical anotación OFF** | Las features `socratic_compliance` y override léxico de `anotacion_creada` están en feature-flag OFF. | Bloqueado por validación intercoder κ ≥ 0.70 (ADR-044, ADR-045, ADR-046). |
| **Kappa rating sin uso real** | La pantalla existe pero no hay etiquetadores activos. | Bloqueado por coordinación con 2 docentes UNSL (~25-30h por docente). |

Para detalle completo de capabilities y su estado real, ver [`AI-NativeV3-main/docs/CAPABILITIES.md`](AI-NativeV3-main/docs/CAPABILITIES.md) y [`audi2.md`](audi2.md).

---

## Documentos relacionados

- [`README.md`](README.md) — overview del proyecto, arquitectura, bootstrap completo.
- [`AI-NativeV3-main/CLAUDE.md`](AI-NativeV3-main/CLAUDE.md) — invariantes, constantes hash, gotchas operacionales (~600 líneas, leer si vas a tocar código).
- [`AI-NativeV3-main/README.md`](AI-NativeV3-main/README.md) — README técnico extendido del monorepo.
- [`audi2.md`](audi2.md) — auditoría de completitud (20 capabilities × 4 criterios).
- [`plan-accion.md`](plan-accion.md) — plan de acciones del piloto (estado 23/26 cerradas).
- [`paper-draft.md`](paper-draft.md) — paper académico consolidado.

---

**Última actualización**: 2026-05-15.
**Autor del proyecto**: Alberto Alejandro Cortez · Doctorado UNSL · Co-directora: Daniela Carbonari.
