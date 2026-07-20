# Deploy limpio en EasyPanel (sin GPU y sin stack externo de observabilidad/Keycloak)

## Objetivo
Esta guía deja la plataforma lista para desplegar en EasyPanel evitando errores por:
- dependencias GPU,
- servicios externos removidos (Grafana/Keycloak/Otel/Jaeger/Prometheus/Loki/keycloak-db),
- conflictos de proxy (EasyPanel ya incluye reverse proxy),
- builds cruzados (un servicio instalando dependencias de todo el monorepo).

## 1) Servicios removidos del compose
En `infrastructure/docker-compose.prod.yml` se removieron/comentaron:
- `keycloak-db`
- `keycloak`
- `otel-collector`
- `jaeger`
- `prometheus`
- `loki`
- `grafana`

No se tocaron los demás servicios de negocio.

## 2) GPU removida
En `apps/content-service/src/content_service/embedding/embedder.py` se forzó `device = "cpu"` para evitar runtime CUDA/NVIDIA.

## 3) Build individual por servicio (cambio clave para EasyPanel)
Todos los Dockerfiles Python ahora instalan **solo su paquete** de workspace con `uv sync --package <nombre-paquete> --no-dev` (en lugar de `--all-packages`).

Esto evita que al buildear `api-gateway` (o cualquier otro) se descarguen deps de servicios no relacionados (por ejemplo, stacks de IA/GPU).

### Matrix de build (EasyPanel)
Para cada servicio en EasyPanel (tipo **App > Dockerfile**):

- **Build context**: raíz del repo (`/workspace/AI-Native-V5/AI-NativeV3-main` en local; en Git será la raíz del proyecto).
- **Dockerfile path**: `apps/<servicio>/Dockerfile`.
- **Port interno**: el `SERVICE_PORT`/`ENTRYPOINT` de cada servicio.

| Servicio | Dockerfile | Puerto |
|---|---|---:|
| api-gateway | `apps/api-gateway/Dockerfile` | 8000 |
| academic-service | `apps/academic-service/Dockerfile` | 8002 |
| evaluation-service | `apps/evaluation-service/Dockerfile` | 8004 |
| analytics-service | `apps/analytics-service/Dockerfile` | 8005 |
| tutor-service | `apps/tutor-service/Dockerfile` | 8006 |
| ctr-service | `apps/ctr-service/Dockerfile` | 8007 |
| classifier-service | `apps/classifier-service/Dockerfile` | 8008 |
| content-service | `apps/content-service/Dockerfile` | 8009 |
| governance-service | `apps/governance-service/Dockerfile` | 8010 |
| ai-gateway | `apps/ai-gateway/Dockerfile` | 8011 |

---

## 4) Variables `.env` por servicio (EasyPanel > Environment)

> Regla: usar los nombres en MAYÚSCULAS exactamente como abajo. Valores por ambiente (`dev/stage/prod`) y URLs internas de EasyPanel (`http://<service-name>:<port>`).

### api-gateway
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, KEYCLOAK_URL, KEYCLOAK_REALM, ACADEMIC_SERVICE_URL, EVALUATION_SERVICE_URL, ANALYTICS_SERVICE_URL, TUTOR_SERVICE_URL, CTR_SERVICE_URL, CLASSIFIER_SERVICE_URL, CONTENT_SERVICE_URL, GOVERNANCE_SERVICE_URL, AI_GATEWAY_URL, RATE_LIMIT_REDIS_URL, RATE_LIMIT_DEFAULT, RATE_LIMIT_ENABLED, JWT_ISSUER, JWT_AUDIENCE, JWT_JWKS_URI, JWT_JWKS_CACHE_TTL, DEV_TRUST_HEADERS, DEMO_USER_ID, DEMO_TENANT_ID, DEMO_USER_EMAIL, DEMO_USER_ROLES, DEMO_USER_REALM`

### academic-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, KEYCLOAK_URL, KEYCLOAK_REALM, ACADEMIC_DB_URL, DB_ECHO, GOVERNANCE_SERVICE_URL, AI_GATEWAY_URL, CONTENT_SERVICE_URL, CLASSIFIER_SERVICE_URL, TP_GENERATOR_PROMPT_VERSION, TP_GENERATOR_DEFAULT_MODEL, EJERCICIO_GENERATOR_PROMPT_VERSION, EJERCICIO_GENERATOR_DEFAULT_MODEL`

### evaluation-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, KEYCLOAK_URL, KEYCLOAK_REALM, ACADEMIC_DB_URL, CTR_SERVICE_URL, ACADEMIC_SERVICE_URL`

### analytics-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, KEYCLOAK_URL, KEYCLOAK_REALM, CTR_STORE_URL, CLASSIFIER_DB_URL, ACADEMIC_DB_URL`

### tutor-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, REDIS_URL, GOVERNANCE_SERVICE_URL, CONTENT_SERVICE_URL, AI_GATEWAY_URL, CTR_SERVICE_URL, ACADEMIC_SERVICE_URL, EVALUATION_SERVICE_URL, DEFAULT_PROMPT_NAME, DEFAULT_PROMPT_VERSION, DEFAULT_MODEL, OPUS_MODEL, FEATURE_FLAGS_PATH, FEATURE_FLAGS_RELOAD_SECONDS, EPISODE_IDLE_TIMEOUT_SECONDS, ABANDONMENT_CHECK_INTERVAL_SECONDS, ENABLE_ABANDONMENT_WORKER, DISTRACTION_THRESHOLD_SECONDS, DISTRACTION_CHECK_INTERVAL_SECONDS, ENABLE_DISTRACTION_WORKER, SOCRATIC_COMPLIANCE_ENABLED`

### ctr-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, KEYCLOAK_URL, KEYCLOAK_REALM, CTR_DB_URL, DB_ECHO, REDIS_URL, NUM_PARTITIONS`

### classifier-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, CLASSIFIER_DB_URL, DB_ECHO, REDIS_URL, CTR_SERVICE_URL, LEXICAL_ANOTACION_OVERRIDE_ENABLED, GUARDRAIL_MODIFIER_ENABLED`

### content-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, KEYCLOAK_URL, KEYCLOAK_REALM, CONTENT_DB_URL, DB_ECHO, S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_MATERIALS`

### governance-service
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, PROMPTS_REPO_PATH`

### ai-gateway
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, REDIS_URL, LLM_PROVIDER, DEFAULT_MONTHLY_BUDGET_USD, ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, MISTRAL_API_KEY, BYOK_MASTER_KEY, BYOK_ENABLED, ACADEMIC_DB_URL`

### integrity-attestation-service (si lo publicás)
`SERVICE_NAME, SERVICE_PORT, ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_ENDPOINT, SENTRY_DSN, REDIS_URL, ATTESTATION_PRIVATE_KEY_PATH, ATTESTATION_PUBLIC_KEY_PATH, ATTESTATION_LOG_DIR`

---

## 5) Configuración de Domain en EasyPanel (frontend)
Para mostrar frontend correctamente, no uses Nginx externo adicional: EasyPanel ya maneja el proxy.

### Config recomendada
En el Domain del servicio frontend (`frontends`):

- **HTTPS**: ON
- **Host**: `tu-dominio` (ej: `ai-native-radar-b2b.3xzl86.easypanel.host`)
- **Path (arriba)**: `/`

**Destination**
- **Protocol**: `HTTP`
- **Port**: `80`
- **Path (destination)**: `/`
- **Compose Service**: `frontends`

### Reglas clave
1. **Un dominio por app pública** (frontend, api-gateway, etc.) para evitar rutas ambiguas.
2. Si frontend consume API por `/api`, apunta otro Domain al `api-gateway` o usa el mismo host con path `/api` al servicio API.
3. `CORS_ORIGINS` debe incluir el host final HTTPS del frontend.
4. No publicar puertos manualmente en compose para estos servicios; EasyPanel enruta internamente por Domain.


## 6.1) Frontends en EasyPanel (Vite dev/proxy)

Si publicas `web-admin`, `web-teacher` o `web-student` con Vite, el proxy de `/api` usa `VITE_API_URL`.

- Si `VITE_API_URL` no esta seteada durante el **build** del frontend, el bundle puede terminar apuntando al fallback local en escenarios de Vite/proxy mal configurados.
- En EasyPanel con `infrastructure/frontends.Dockerfile`, `VITE_API_URL` debe cargarse como **Build Arg** (no solo variable runtime), porque Vite inyecta `import.meta.env` al compilar.
- Configura `VITE_API_URL` con la URL publica del gateway (ej. `https://api.tudominio.com`). Si usas URL interna (`http://api-gateway:8000`), solo sirve cuando quien resuelve esa URL es otro contenedor, no el navegador del usuario final.
- Evita hostnames mal tipeados: el nombre interno debe coincidir exactamente con el service name de EasyPanel (sin inventar `_` o `-`).

Ejemplo recomendado para frontends publicados por dominio:

```env
VITE_API_URL=https://api.ai-native-tutor-socratico-api-gateway.3xzl86.easypanel.host
```

Con eso, llamadas como `/api/v1/universidades/mine` y `/api/v1/materias/mias` dejan de depender del fallback local.

## 6) Ejemplo de Domains mínimos

### Frontend público
- Host: `app.tudominio.com`
- Path: `/`
- Destination service: `frontends`
- Destination port: `80`

### API pública
- Host: `api.tudominio.com`
- Path: `/`
- Destination service: `api-gateway`
- Destination port: `8000`

> Alternativa: mismo host para ambos
- `app.tudominio.com` + Path `/` -> `frontends:80`
- `app.tudominio.com` + Path `/api` -> `api-gateway:8000`

## 7) Qué revisar si un servicio no levanta en EasyPanel
1. El Dockerfile del servicio correcto está seleccionado (`apps/<servicio>/Dockerfile`).
2. No usaste `--all-packages` en build (ya queda corregido en repo).
3. Las variables `.env` requeridas del servicio están cargadas en Environment.
4. URLs internas entre servicios apuntan a `http://<service-name>:<port>`.
5. El Domain (si aplica) apunta al puerto correcto del servicio.
6. Si ves `ModuleNotFoundError: No module named 'platform_observability'` en `api-gateway`, confirmá que la imagen incluya la versión con `platform-observability` en `apps/api-gateway/pyproject.toml` y rebuild sin cache.

## 8) Opciones para reemplazar lo removido (especial foco GPU)

### Reemplazos para GPU (si más adelante la necesitás)
1. **Mantener CPU (actual)**
   - Costo menor y máxima compatibilidad EasyPanel.
2. **Embeddings externos vía API**
   - OpenAI / Azure OpenAI / servicios gestionados.
   - Evita gestionar drivers GPU.
3. **Servicio de embeddings separado con GPU**
   - Desplegar en proveedor dedicado (RunPod, vast.ai, k8s con GPU) y consumir por HTTP interno/privado.
4. **Modelo más liviano CPU-first**
   - Ajustar `model_name` a variantes optimizadas para CPU.

### Reemplazos para servicios removidos
- **Keycloak**: Auth0, Clerk, Cognito, Supabase Auth, Zitadel.
- **Observabilidad**: Grafana Cloud (Prom/Loki/Tempo), Datadog, New Relic, Elastic Cloud.
- **OTel Collector**: agente gestionado del proveedor de observabilidad.

## 9) Nota operativa
Si necesitás reactivar observabilidad o IdP, recomendación práctica para EasyPanel:
- mantenerlos fuera del compose principal (servicios gestionados o proyecto aparte),
- y conectar por variables de entorno/URLs.
