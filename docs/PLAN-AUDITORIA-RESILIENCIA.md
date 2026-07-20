# Plan de auditoría y testeo — AI-Native V5

> Objetivo: agarrar el proyecto servicio por servicio, mapear cómo se conectan entre sí,
> y responder con evidencia (no a ojo): **¿esto es sólido o es frágil?**
>
> Contexto: 11 servicios Python + frontends, deploy en EasyPanel (1 VPS, 4 cores / 15.6 GB),
> bus Redis Streams, Postgres con 4 DBs lógicas, RLS multi-tenant, CTR append-only.
>
> Este plan nació de un incidente real (2026-06-04) donde abrir un episodio fallaba por
> **4 bugs en 4 contenedores distintos**. Esos 4 son los casos de estudio del método.

---

## Cómo usar este plan

Trabajá las fases EN ORDEN. Cada fase deja un artefacto (un mapa, una matriz, una tabla de
resultados). No saltees la Fase 0 ni la 6: sin el mapa real y sin observabilidad, vas a
debuggear a ciegas (como nos pasó hoy con el spam de OTel tapando los tracebacks).

Marcá cada ítem: `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[!]` encontró problema.

---

## FASE 0 — Mapa de la realidad (topología viva)

No confíes en los diagramas de los `.md`: el deploy real difiere del dev. Construí el grafo
REAL de quién depende de quién.

- [ ] **Inventario de servicios desplegados** (EasyPanel proyecto `ai_native`). Anotá por cada uno:
  nombre del contenedor, puerto interno, imagen/branch, estado, CPU/RAM en idle.
- [ ] **Infra compartida**: `platform-prod-postgres` (¿cuántas DBs lógicas adentro?),
  `platform-prod-redis`, `platform-prod-minio`. Anotá host interno + puerto de cada uno.
- [ ] **Grafo de dependencias**: por cada servicio, listá sus env vars `*_SERVICE_URL`,
  `*_DB_URL`, `REDIS_URL`. Eso ES el grafo. Dibujalo (mermaid o papel).
- [ ] **Health de todos, de una**. Script base:

  ```bash
  # correr desde un contenedor cualquiera del proyecto (o adaptá a curl externo)
  for s in academic:8002 analytics:8005 ctr-service:8007 content:8009 \
           governance:8010 ai-gateway:8011 tutor:XXXX api-gateway:8000; do
    echo "== $s =="; curl -s --max-time 5 "http://ai_native_tutor-socratico-${s%%:*}.../health" ;
  done
  ```
  (ya verificamos a mano: academic `ready`, ctr `ready db+redis ok`, governance `200`.)

**Artefacto Fase 0:** un diagrama del grafo + tabla `servicio → [deps]` + RAM idle de cada uno.
⚠️ Dato ya conocido: **RAM del host al 82.8% en idle** — anotalo como riesgo base.

---

## FASE 1 — Auditoría servicio por servicio (plantilla repetible)

Copiá esta plantilla 1 vez por servicio (los 11). Empezá por los del **camino crítico de
abrir/usar un episodio**: `api-gateway → tutor → academic → governance → ctr → classifier`.

```
### Servicio: <nombre>
- Puerto / health: 
- Owner de datos (qué tablas/DB es suyo): 
- A QUIÉN llama (saliente): [servicio, sync HTTP / async Redis, con qué auth/rol]
- QUIÉN lo llama (entrante): 
- Arranque limpio: ¿startup sin tracebacks? ¿cuánto tarda? ¿migraciones al boot?
- Manejo de fallo de cada dependencia: ¿propaga 500 o degrada (fail-soft)?  ← CLAVE
- Pool de DB: ¿tamaño? ¿se reusa o se crea por request?  ← CLAVE escala
- Cliente HTTP: ¿reusa conexión o crea una por llamada?  ← CLAVE escala
- Tests propios: apps/<svc>/tests/  (¿corren? ¿cubren el camino real?)
- Veredicto: [sólido / aceptable / frágil] + por qué
```

**Pistas ya encontradas (úsalas de ejemplo del método):**
- `tutor-service/academic_client.py`: crea `httpx.AsyncClient()` **nuevo por llamada** → no
  hay pool reusado. 🚩 escala.
- `analytics-service`: crea `create_async_engine(pool_size=2)` y hace `dispose()` **por
  request**. 🚩 escala — pool exhaustion bajo carga.
- `tutor_core.open_episode`: algunas llamadas a academic son **fail-soft** (try/except →
  degrada), otras NO (`get_tarea_practica` propaga 403/500). Mapeá cuáles de cada tipo.

**Artefacto Fase 1:** 11 fichas completas + una lista priorizada de 🚩 por servicio.

---

## FASE 2 — Auditoría de las conexiones (los bordes del grafo)

**Acá vivieron los 4 bugs de hoy.** El problema no suele estar dentro de un servicio sino en
el borde entre dos. Por cada arista del grafo, llená esta matriz:

| Origen | Destino | Tipo | Auth (rol/headers) | Si destino tira 4xx | Si destino tira 5xx | Si destino timeout/down |
|--------|---------|------|--------------------|--------------------|--------------------|------------------------|
| tutor  | academic (GET tarea) | HTTP sync | `X-User-Roles: tutor_service` | ¿? | **propaga 500** ✅ visto | ¿reintenta? |
| tutor  | governance (prompt)  | HTTP sync | service headers | — | propaga 500 | — |
| tutor  | redis (session)      | TCP | password | — | **gaierror → 500** ✅ visto | — |
| tutor  | redis stream (CTR)   | XADD | — | — | 500 | — |
| ctr-workers | redis stream    | XREADGROUP | — | — | — | **lee pero no persiste** ✅ visto |
| ctr-workers | postgres        | asyncpg | — | — | **no ACK → pending** ✅ visto | — |
| api-gateway | todos           | HTTP + inyecta X-* | JWT/Clerk | — | — | — |

- [ ] Completar la matriz para **todas** las aristas.
- [ ] Por cada celda "propaga 500": preguntate **¿debería degradar en vez de explotar?**
  (ej: el 403 de academic debería ser un error claro al alumno, no un 500 opaco).
- [ ] **Auditoría de auth servicio-a-servicio**: ¿qué rol manda cada servicio? ¿el Casbin de
  cada destino tiene ese permiso? (hoy faltaba `tutor_service:tarea_practica:read` Y el gate
  `assert_comision_access` no eximía al servicio). Repetí esa verificación para CADA llamada
  interna.

**Artefacto Fase 2:** la matriz completa + lista de bordes que "explotan cuando deberían
degradar" + lista de permisos de servicio faltantes/frágiles.

---

## FASE 3 — Resiliencia / caos (¿se cura solo o hay que reiniciar a mano?)

Hoy aprendimos que **dos servicios perdieron conexiones tras un restart y NO se recuperaron
solos**. Eso es lo que hay que medir acá. Experimentos (en staging, NO en prod con alumnos):

- [ ] **Matar Redis 30s y revivirlo** → ¿tutor/ctr reconectan solos o quedan zombis?
- [ ] **Matar Postgres 30s** → ¿los workers del CTR reintentan o pierden eventos?
- [ ] **Reiniciar un servicio** → ¿se re-engancha a la red (DNS) o queda aislado?
  (hoy el tutor necesitó *redeploy*, no alcanzó *restart*).
- [ ] **Latencia inyectada** (academic responde a 2s) → ¿timeouts en cadena? ¿el pool se agota?
- [ ] **CTR: matar un worker a mitad de procesar** → ¿reclama los `pending` al volver?
  (hoy: **NO** los reclama → 81 eventos huérfanos). 🚩
- [ ] **Healthchecks de EasyPanel**: ¿están configurados para reiniciar el contenedor cuando
  `/health` da 503? (si no, una caída no se auto-cura).

**Rúbrica por experimento:** `se cura solo / se cura con restart / se cura solo con redeploy /
queda roto + pierde datos`.

**Artefacto Fase 3:** tabla de experimentos con el resultado real de cada uno. Esto es el 80%
de la respuesta "¿es frágil?".

---

## FASE 4 — Integridad de datos (tesis-crítico, no negociable)

Esto sostiene la tesis. Un fallo acá invalida el piloto, no solo molesta.

- [ ] **CTR append-only**: verificar la cadena de hashes de episodios cerrados
  (`POST /api/v1/audit/episodes/{id}/verify`). ¿La cadena valida bit a bit?
- [ ] **Eventos huérfanos**: ¿cuántos `pending` hay en los streams `ctr.p0..p7` que nunca
  llegaron a Postgres? (hoy: 81). ¿Representan trabajo real perdido? Definir proceso de
  reprocesamiento (XAUTOCLAIM).
- [ ] **RLS multi-tenant**: confirmar que un tenant NO ve datos de otro (correr `make
  test-rls` contra la DB real con usuario non-superuser).
- [ ] **Reproducibilidad de hashes**: `classifier_config_hash`, `self_hash`, `chain_hash`
  deterministas (suite `test_pipeline_reproducibility.py`).
- [ ] **Aislamiento docente/alumno**: que un alumno solo vea lo suyo (`usuarios_comision` vs
  `inscripciones`).

**Artefacto Fase 4:** reporte de integridad (cadena CTR OK/roto, # huérfanos, RLS OK).

---

## FASE 5 — Carga y escala (la pregunta de los 100 alumnos)

- [ ] **Escenario realista**: 100 aperturas repartidas en 2 min (~1/s). Medir latencia p50/p95
  y errores. (hipótesis: aguanta).
- [ ] **Escenario pico**: 100 aperturas en <5s. Medir lo mismo. (hipótesis: riesgo real).
- [ ] **Mientras corre, mirar el VPS en vivo**: `htop` / memoria. El umbral peligroso es RAM
  → si toca el techo, el OOM killer mata contenedores (y reaparecen los bugs de red de hoy).
- [ ] Herramienta sugerida: **k6** o **locust**. Script: login alumno → `POST /episodes` →
  `GET /episodes/{id}` (el camino completo, incluyendo la persistencia del CTR).
- [ ] Probar también **N mensajes concurrentes** dentro de un episodio (ahí entra el LLM /
  ai-gateway, que en el `open` no se toca pero en el chat sí es el cuello).

**Artefacto Fase 5:** curva carga vs latencia/errores + el punto donde se rompe + qué recurso
lo rompe (casi seguro RAM antes que CPU).

---

## FASE 6 — Observabilidad (arreglar PRIMERO, sino testeás a ciegas)

Hoy debuggear fue infernal porque el log estaba inundado de
`Failed to export metrics to 127.0.0.1:4317` (collector OTel caído) y tapaba los tracebacks.

- [ ] **Arreglar o silenciar OTel**: o levantás el collector (Jaeger/Prometheus), o seteás
  `OTEL_SDK_DISABLED=true` para que deje de spamear. **Sin esto, cada debug futuro es a ciegas.**
- [ ] **Logs estructurados consultables**: hoy no se podía grepear el log de un contenedor.
  Considerar un agregador (Loki/Grafana ya están en el stack dev).
- [ ] **Métricas mínimas vivas**: RAM por contenedor, errores 5xx/min por servicio, lag y
  pending de los streams CTR, latencia de las llamadas internas.
- [ ] **Alertas**: al menos RAM del host > 90% y `pending` de CTR creciendo.

**Artefacto Fase 6:** observabilidad funcionando. Es habilitador de todo lo demás.

---

## Baseline: las suites que YA existen (no reinventes)

El repo ya trae redes de seguridad. Corrélas primero para tener una línea base:

```bash
cd AI-NativeV3-main
make test-fast      # unit Python + casbin matrix
make test-rls       # 4 tests de RLS real (necesita Postgres con user non-superuser)
make test-smoke     # 30+ smoke E2E contra el stack levantado (<2s)
make test-e2e       # Playwright contra los frontends
make check-rls      # toda tabla con tenant_id tiene policy
make check-claude-md # detecta drift entre claims del CLAUDE.md y el código
```

- [ ] Correr cada una y anotar qué pasa / qué falla / qué cobertura real tiene.
- [ ] **Gap clave**: estas suites corren contra el stack **local**, no contra prod. Faltan
  smoke tests apuntados a prod (un "synthetic check" del camino abrir-episodio cada N min).

---

## Orden sugerido (por dónde empezar)

1. **Fase 6 (observabilidad)** — primero, sino vas a ciegas.
2. **Fase 0 (mapa)** — la base de todo.
3. **Fase 2 (conexiones)** — acá están la mayoría de los bugs reales.
4. **Fase 3 (caos)** — esto responde "¿es frágil?" directo.
5. **Fase 1 (por servicio)** — en paralelo, profundizás cada nodo.
6. **Fase 4 (integridad)** — antes de cualquier dato real de piloto.
7. **Fase 5 (carga)** — al final, cuando lo anterior esté sano.

---

## Veredicto: cómo decidir "sólido vs frágil" (rúbrica)

Puntuá cada eje 1-5. Si el promedio < 3, es frágil para producción real.

| Eje | 1 (frágil) | 5 (sólido) |
|-----|-----------|-----------|
| **Recuperación** | hay que reiniciar a mano (como hoy) | se cura solo (reconexión + healthcheck) |
| **Degradación** | un servicio caído tira 500 opacos | degrada con mensaje claro o fail-soft |
| **Aislamiento de fallo** | una caída tumba el flujo entero | el fallo queda contenido |
| **Integridad de datos** | pierde eventos (huérfanos) | nunca pierde, reprocesa |
| **Observabilidad** | debug a ciegas | tracebacks + métricas + alertas |
| **Escala** | RAM al techo con poca carga | headroom + pools dimensionados |
| **Auth interna** | permisos frágiles/faltantes | service-accounts bien modelados |

**Estado al 2026-06-04 (línea base, honesta):** Recuperación ~1, Observabilidad ~1, Escala ~2,
resto sin medir. O sea: **funciona, pero hoy es frágil** — lo probamos en carne propia. La
buena noticia: las 4 fallas eran reparables y el diseño de fondo (planos separados, CTR) es
defendible. La fragilidad está en la **operación/resiliencia**, no en la arquitectura.
