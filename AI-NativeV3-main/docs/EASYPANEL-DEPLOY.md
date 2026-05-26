# Deploy limpio en EasyPanel (sin GPU y sin stack externo de observabilidad/Keycloak)

## Objetivo
Esta guía deja la plataforma lista para desplegar en EasyPanel evitando errores por:
- dependencias GPU,
- servicios externos removidos (Grafana/Keycloak/Otel/Jaeger/Prometheus/Loki/keycloak-db),
- conflictos de proxy (EasyPanel ya incluye reverse proxy).

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

## 3) Configuración de Domain en EasyPanel (frontend)
Para mostrar frontend correctamente, no uses Nginx externo adicional: EasyPanel ya maneja el proxy.

### Config recomendada (como tu captura)
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

## 4) Ejemplo de Domains mínimos

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

## 5) Qué revisar si el frontend no abre
1. Domain del frontend apunta a `frontends:80`.
2. El host que usas en navegador coincide exactamente con `CORS_ORIGINS` (si pega API).
3. El path del Domain está en `/` y no en subruta errónea.
4. No hay otro Domain con mismo host+path en conflicto.

## 6) Opciones para reemplazar lo removido (especial foco GPU)

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

## 7) Nota operativa
Si necesitás reactivar observabilidad o IdP, recomendación práctica para EasyPanel:
- mantenerlos fuera del compose principal (servicios gestionados o proyecto aparte),
- y conectar por variables de entorno/URLs.
