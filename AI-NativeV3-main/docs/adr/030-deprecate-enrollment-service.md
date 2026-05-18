# ADR-030 — Deprecación de `enrollment-service`

- **Estado**: Aceptado
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: backend, infraestructura, deprecation, simplificación
- **Cierra**: D.6 de la auditoría de coherencia backend ↔ frontend (2026-04-29).
- **Coordinado con**: [ADR-029](./029-bulk-import-inscripciones.md) (bulk de inscripciones en academic-service).

## Contexto y problema

`enrollment-service` (puerto 8003) fue agregado en F0 con la responsabilidad declarada *"gestión de inscripciones y sincronización con SIS institucionales"*. La iter 2 de auditoría detectó:

1. **Ningún frontend lo consumía**. Los 3 frontends (web-admin, web-teacher, web-student) NO referencian `/api/v1/imports/*` — verificado con grep cruzado de los inventarios del 2026-04-29.
2. **El commit estaba sin terminar**. [`apps/enrollment-service/src/enrollment_service/routes/imports.py:70`](../../apps/enrollment-service/src/enrollment_service/routes/imports.py#L70) tenía un TODO explícito: *"integrate academic-service"*. La ruta validaba CSV pero no persistía nada.
3. **Solapamiento funcional con `academic-service` bulk-import**. ADR-029 cerró el gap B.1 sumando `inscripciones` a `SUPPORTED_ENTITIES` del bulk-import unificado en academic-service. Tener dos servicios para el mismo flow es deuda silenciosa.
4. **El plan de "sync con SIS institucionales"** quedó como agenda futura sin ADR redactado. No hay caso de uso real ni planificación concreta para piloto-1.

## Drivers de la decisión

- **Coherencia arquitectónica**: las inscripciones son parte del dominio académico (modelo `Inscripcion` vive en `academic_main`), no parte de un plano de ingest separado. Centralizarlas en academic-service alinea el código con su diseño semántico.
- **Eliminar caminos paralelos**: dos endpoints (academic bulk + enrollment imports) que hacen import de CSV es deuda silenciosa. Los frontends no sabían cuál llamar.
- **Reducir superficie de deploy**: 1 menos pod en staging/prod, 1 menos servicio en docker-compose, 1 menos uvicorn que arrancar a mano en dev (per CLAUDE.md "make dev no levanta los 13 servicios Python").
- **Honestidad del catálogo de servicios**: tener un servicio sin frontend ni roadmap claro es exactamente lo que CLAUDE.md llama *"deuda silenciosa vs decisión informada"*. Este ADR convierte la deuda en decisión.

## Opciones consideradas

### A — Deprecar y centralizar en academic-service (ELEGIDA)

Sacar `enrollment-service` del workspace, ROUTE_MAP, helm. Preservar el código en disco con README de deprecation para trazabilidad histórica y posibilidad de revival.

### B — Completar `enrollment-service` con commit funcional + UI

Implementar el TODO de [`imports.py:70`](../../apps/enrollment-service/src/enrollment_service/routes/imports.py#L70) (persistencia via academic-service) + agregar UI dedicada en web-admin.

**Descartada porque**:
- Introduce dependencia HTTP service-to-service entre `enrollment-service` y `academic-service` (latencia + flakiness + transaccionalidad cross-service).
- No agrega valor sobre el bulk-import unificado de ADR-029.
- El supuesto caso de uso "sync con SIS institucionales" no tiene ADR redactado ni roadmap.

### C — Eliminar el directorio físico completo

Rama agresiva: borrar `apps/enrollment-service/` por completo del repo.

**Descartada porque**:
- Pérdida de trazabilidad histórica del esfuerzo F0.
- Si emerge un caso de uso real para SIS sync, recrear el esqueleto cuesta más que mantenerlo dormido.
- CLAUDE.md (sección "Executing actions with care") prescribe *"investigate before deleting or overwriting"* para state inesperado. El directorio NO es inesperado, pero el principio aplica: borrar tiene costo cero de mantenimiento (no afecta runtime) pero alto costo de revisión.

## Decisión

**Opción A**. `enrollment-service` queda deprecated. Código preservado en disco. Sacado de workspace + ROUTE_MAP + helm + tabla de puertos de CLAUDE.md.

### Cambios concretos

| Archivo | Cambio |
|---|---|
| [`pyproject.toml`](../../pyproject.toml) | `"apps/enrollment-service"` removido de `[tool.uv.workspace].members` con comentario explicativo. NO se sincroniza con `uv sync`, NO aparece en `pytest apps/*/tests/`. |
| [`apps/api-gateway/src/api_gateway/routes/proxy.py`](../../apps/api-gateway/src/api_gateway/routes/proxy.py) | Línea `"/api/v1/imports": settings.enrollment_service_url` removida del `ROUTE_MAP`. El endpoint **queda inalcanzable** desde frontend (devuelve 404 del gateway). |
| [`infrastructure/helm/platform/values.yaml`](../../infrastructure/helm/platform/values.yaml) | Bloque `enrollment-service:` removido. **No se deploya** en staging/prod. |
| [`apps/enrollment-service/README.md`](../../apps/enrollment-service/README.md) | Reemplazado por nota de deprecation completa, con instrucciones de revival y referencia a ADR-029/030. |
| [`CLAUDE.md`](../../CLAUDE.md) | Tabla de puertos marca el puerto 8003 como deprecated (~~tachado~~ con explicación). Mención en plano académico-operacional removida. |

### Lo que NO se cambió

- `apps/api-gateway/src/api_gateway/config.py:27` (`enrollment_service_url`) — settings de configuración. Lo dejé porque es configuración inerte (no se usa post-ROUTE_MAP-removal). Limpiarlo es cosmético; futura sesión puede sacarlo si emerge el caso.
- `apps/enrollment-service/` directorio físico — preservado completo per Opción A.
- Tests del servicio en `apps/enrollment-service/tests/` — preservados pero NO se ejecutan en CI (sacado del workspace).

## Consecuencias

### Positivas

- **1 menos servicio Python que mantener**: 12 servicios efectivos (12 con `evaluation-service` esqueleto + `identity-service` `/health`-only by design = 10 operacionales con frontend o consumo claro).
- **Coherencia tesis ↔ código**: la auditoría 2026-04-29 detectó este gap; el ADR lo cierra con decisión informada en lugar de deuda silenciosa.
- **Menos confusión para futuros desarrolladores**: ya no hay ambigüedad entre `bulk` y `imports` para el mismo flow.
- **Reducción de superficie de deploy**: 1 pod menos en helm.

### Negativas / trade-offs

- **Pérdida de capacidad declarada para sync con SIS**: si UNSL pide sync con su sistema institucional (Guarani u otro), va a haber que revivir o re-arquitecturar. **Mitigación**: el README del directorio documenta cómo revivir; el código del esqueleto está intacto.
- **`enrollment_service_url` queda como settings dormido**: cosmético, no afecta runtime.
- **Si alguien intenta subir CSV al endpoint viejo**, recibe 404 del gateway. **Mitigación**: la UI del web-admin nunca expuso ese endpoint, así que no hay usuarios externos legítimos que se rompan.

### Neutras

- El directorio `apps/enrollment-service/` sigue versionado pero "muerto". Linters/typecheckers fuera del workspace lo ignoran.
- El test `test_health.py` no se ejecuta en CI post-ADR-030. Si se restaura el servicio, los tests vuelven automáticamente al re-incluir el path en el workspace.

## Posible revival futuro (instrucciones operativas)

Si emerge un caso de uso real (ej. sync con Guarani), el revival es reversible siguiendo el README del servicio:

1. Re-incluir `"apps/enrollment-service"` en `pyproject.toml` `[tool.uv.workspace].members`.
2. Re-agregar `"/api/v1/imports": settings.enrollment_service_url` en `proxy.py` `ROUTE_MAP`.
3. Re-agregar el bloque `enrollment-service:` en `infrastructure/helm/platform/values.yaml`.
4. Resolver el TODO original en [`routes/imports.py`](../../apps/enrollment-service/src/enrollment_service/routes/imports.py#L70) (commit que persiste).
5. Marcar este ADR como `Superseded por ADR-XXX` y redactar el ADR de revival explicando el caso de uso nuevo.

## Referencias

- Auditoría de coherencia backend ↔ frontend (2026-04-29) — gap D.6.
- ADR-029 — bulk de inscripciones en academic-service (coordinado).
- audi2.md — auditoría doctoral que motivó iter 2.
- CLAUDE.md sección "Executing actions with care" — principio de reversibilidad.
- README del directorio: [`apps/enrollment-service/README.md`](../../apps/enrollment-service/README.md).
