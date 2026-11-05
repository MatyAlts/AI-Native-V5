# Informe propose-1-planner

- Change: `cibse-codificacion-ciega`
- Rol: planner (propose, intento 1)
- Ejecutor declarado: subagente nativo de Claude Code (role planner); modelo según el orquestador. Sin otra familia de proveedor.
- Revisión base: `origin/main @ b32e621`, rama `feat/cibse-codificacion-ciega`, árbol con `openspec/changes/cibse-codificacion-ciega/` sin commitear.
- Fecha: 2026-11-04
- Artefactos producidos: `proposal.md`, `design.md`, `tasks.md` (bloque "Estado de orquestación" conservado arriba), `specs/{estudio-codificacion-acceso, estudio-codificacion, traza-ciega-episodio, codebook-versionado, entrenamiento-calibracion, estudio-codificacion-exportacion}/spec.md`.
- Correcciones de alcance recibidas durante el trabajo (mensajes del orquestador, 04/11): (1) parte B entra, anclas persistidas, respuestas de entrenamiento guardadas, exclusión ancla/muestra, reutilizar las dos secciones; (2) codebook versionado borrador/congelado mostrado en Entrenamiento, codificación solo con versión congelada; (3) el v0 existe en `/home/juanisarmiento/Descargas/CIbSE2027_muestra_150/codebook/codebook_v0_borrador.md`, referenciar sin copiar. Las tres están reflejadas en todos los artefactos.

## EVIDENCIA

| Comando / lectura | Momento | Resultado relevante |
|---|---|---|
| `openspec status --change cibse-codificacion-ciega --json` | 04/11, inicio | proposal ready, specs y design blocked, tasks ya existía |
| `openspec instructions {proposal,specs,design,tasks} --change cibse-codificacion-ciega --json` | 04/11, antes de cada artefacto | esquemas respetados (Purpose en specs nuevas, `####` en escenarios, tareas con checkbox y verificación) |
| `openspec list --specs` | 04/11 | 26 specs; ninguna de inter-jueces, codificación ni codebook: todas las capacidades son nuevas |
| `openspec validate cibse-codificacion-ciega --strict` | 04/11, final | `Change 'cibse-codificacion-ciega' is valid` |
| `sha256sum muestra_150.csv` + conteos | 04/11 | `6a6cc0c7...52137` coincide con el brief; 150 filas; 100 `gris`, 50 `pasiva_sobreuso`; 150 `episode_id` únicos |
| Prefijos de las 7 anclas del piloto contra la muestra | 04/11 | 0 coincidencias en los 7 |
| `sha256sum codebook_v0_borrador.md` y encabezados | 04/11 | `8c20baf7...501b`, 163 líneas, 10 secciones; leídas solo §2, §7, §8 y §9 para el mecanismo |
| `routes/interrater.py` (classifier) | b32e621 | sample por `appropriation` con `row_number`, `CODER_ROLES = ("docente","docente_admin","superadmin")`, upsert de una `label` |
| `models/__init__.py:122-174` | b32e621 | `InterraterRating`, unicidad `(tenant, episode, rater)` |
| `views/interraterShared.tsx` | b32e621 | `EpisodeProcessTrace` vía `getEpisodeEvents` (`/api/v1/audit/episodes/{id}`) y `JSON.stringify(event.payload)` en el detalle |
| `views/InterraterTraining.tsx` | b32e621 | 7 anclas hardcodeadas; textos "la trampa" (l. ~407, 446-458) y "El sobreuso manda → pasiva" (l. ~77) |
| `packages/contracts/.../ctr/events.py` | b32e621 | campos que revelan decisiones automáticas: `prompt_kind`, `socratic_compliance`, `violations`, `origin`, `IntentoAdversoDetectadoPayload.category/severity` |
| `apps/ctr-service/.../auth/dependencies.py:116-129` y `routes/events.py:210-250` | b32e621 | `classifier_worker` en `READ_ROLES` y `CTR_OVERSIGHT_ROLES`; docente filtrado por comisión (A0.6) |
| `apps/api-gateway/.../config.py:112`, `jwt_validator.py:205-305` | b32e621 | con Clerk todo usuario recibe `estudiante,docente`; admin solo por `CLERK_ADMIN_EMAILS`; email del token |
| `apps/web-teacher/src/main.tsx:75-130` | b32e621 | entrada al panel solo con comisiones; sin ellas redirige a `/` |
| `apps/api-gateway/.../proxy.py:64,120` | b32e621 | `/api/v1/interrater` a classifier; match por `startswith` |
| `rg` de consumidores de `interrater_ratings` | b32e621 | `analytics.py:505`, `pedagogia.py:736`, `scripts/exportar-episodios-eje-fino.py`; `analytics` importa `classifier_service.models` |
| `rg` de enlaces a `/kappa` e `/interrater-admin` en `src/` | b32e621 | ninguno: el motivo "se llega desde Codificación" en `tests/navegacionAlcanzable.test.ts:42-43` ya es falso hoy |
| `platform_observability/gateway_trust.py:48` | b32e621 | existe `sign_headers` para firmar como el gateway |

## JUICIO

Autor: planner. Comparación: brief del orquestador y dos actualizaciones contra código en `b32e621`.

1. **Clasificación CRITICAL, no HIGH** (confianza alta). El change abre un camino de lectura de episodios completos para personas sin comisión mediante una cuenta de servicio con visión total del CTR, y en producción los roles de Clerk no distinguen a nadie. Es un cruce de límite de seguridad y de datos sensibles. Lo decide el humano en `## Aprobación`.
2. **El cegamiento tiene que ser server-side y por lista blanca** (alta). Filtrar solo `intento_adverso_detectado` no alcanza: `prompt_kind`, metadatos del tutor, `origin`, `tp_calificada` y los huecos de `seq` también filtran decisiones automáticas. El localizador contiguo corrige lo último.
3. **El acceso por rol no sirve en producción** (alta, por lectura de código; no se probó contra Clerk). De ahí la membresía por email y el identificador opaco.
4. **Codebook en la base, con esquema de formulario por versión** (media-alta). El archivo en el repo obliga a commit y deploy por cada edición del borrador. El formulario fijo en código choca con la §9 del v0, que deja abiertos cambios de campos. El costo es más superficie de validación; está acotada por un meta-esquema cerrado y tests.
5. **Tablas separadas del piloto** (alta). Reusar `interrater_ratings` mezclaría las etiquetas del estudio en el κ del piloto, que no tiene control de rol.
6. **Riesgo residual no eliminable en este alcance** (alta): un codificador que es docente de las comisiones puede ver la etiqueta de la máquina en otras pantallas. Lo mitiga el identificador opaco; lo resuelve la elección de codificadores (pregunta 2).
7. **Observación fuera de alcance, no reproducida**: con Clerk, cualquier cuenta tiene `docente`, así que `POST /api/v1/interrater/ratings` del piloto acepta etiquetas de cualquier usuario logueado y `/api/v1/analytics/interrater/aggregate` no exige rol. Es una sospecha por lectura de código; se propone como DEUDA, no se corrige acá.

## SUPOSICIÓN

- Que ctr-service en producción acepta la lectura service-to-service de classifier sin firma o con la firma de `gateway_shared_secret`. Inferido de que `classify_ep.py` ya lee del CTR con headers sin firmar y las clasificaciones se producen; no verificado contra la configuración de EasyPanel. Queda como verificación posterior al deploy.
- Que el email del token de Clerk es verificado. No verificado; el recorrido humano lo confirma o lo convierte en bloqueante.
- Que producción usa un solo tenant (Clerk con `fixed_tenant_id`). Leído del código, no de la configuración desplegada.
- Que los 150 episodios de la muestra están cerrados y existen en el CTR de producción. No se consultó producción; la carga lo valida y rechaza en bloque si no.
- Que los tests de `analytics-service` cubren `interrater_aggregate` y `pedagogia`. No se listaron; la tarea 8.3 pide registrarlos.
- No se ejecutó ningún test ni build: no hay código nuevo y la línea de base es tarea 1.1 del constructor.
- No se leyeron enteros `InterraterCodingView.tsx`, `InterraterAdminView.tsx`, `KappaRatingView.tsx` ni `regimen_llm.py`; solo las partes citadas.

## Fuentes leídas

- `/home/juanisarmiento/Proyectos/AI-Native/codigo/CLAUDE.md` (completo).
- `openspec/changes/cibse-codificacion-ciega/{tasks.md,.openspec.yaml,informes/LEEME.md}`, `openspec/config.yaml`.
- classifier-service: `routes/interrater.py`, `models/__init__.py` (100-240), `auth/__init__.py`, `config.py`, `routes/classify_ep.py` (75-120), `alembic/versions/20260903_0003_add_interrater_ratings.py`, listado de `alembic/versions/` y `tests/`.
- ctr-service: `auth/dependencies.py` (1-140), `routes/events.py` (205-260 y búsquedas).
- api-gateway: `routes/proxy.py` (búsquedas), `services/jwt_validator.py` (205-310), `main.py` (60-100), `config.py` (105-145).
- `packages/contracts/src/platform_contracts/ctr/events.py` (46-260 y resumen de 265-465).
- `packages/observability/src/platform_observability/gateway_trust.py` (búsqueda).
- web-teacher: `views/interraterShared.tsx`, `views/InterraterTraining.tsx` (1-120, 380-480), `lib/api.ts` (200-320, 1725-1800), `main.tsx` (1-160), `routes/{interrater,entrenamiento-recalibracion}.tsx`, `routes/__root.tsx` (110-135), `tests/navegacionAlcanzable.test.ts` (30-60), búsquedas en `utils/eventDisplay.ts`, `utils/helpContent.tsx`, `package.json`.
- analytics-service: `routes/analytics.py` (500-530), `routes/pedagogia.py` (715-750).
- `.github/workflows/ci.yml` (jobs y comandos), `infrastructure/nginx-frontends.conf` (85-100).
- Muestra: solo hash, encabezado y conteos. Codebook v0: hash, encabezados, §2, §7, §8, §9.

## Contaminación por informes ajenos

Ninguna. No había informes previos en `informes/` (solo `LEEME.md` vacío). No se consultaron Engram ni conclusiones de otros roles.
