# Estado del repositorio — F8 completado

F8 cierra los **4 puntos prometidos tras F7**: adaptadores DB reales,
frontend docente con vistas F7, dashboards Grafana del piloto, y
protocolo formal del piloto como documento Word para el comité de
ética y la defensa de tesis.

## Entregables F8

### Punto 2 — Adaptadores reales de DB

`packages/platform-ops/src/platform_ops/real_datasources.py` — 10/10
tests pasando con SQLite in-memory.

- `RealCohortDataSource`: implementa la interfaz `_CohortDataSource` del
  `AcademicExporter` haciendo queries reales a `ctr_store` (episodes +
  events) y `classifier_db` (classifications) con sesiones separadas
  (ADR-005 multi-DB).
- `RealLongitudinalDataSource`: implementa la interfaz que consume
  `build_trajectories()`. La agrupación por estudiante se hace en
  Python porque las dos tablas viven en DBs distintas; esto es OK para
  el volumen del piloto.
- `set_tenant_rls(session, tenant_id)`: helper que setea
  `SET LOCAL app.current_tenant` al comienzo de cada transacción. El
  RLS de Postgres filtra automáticamente, y el patrón de doble filtro
  (WHERE + RLS) es defensivo.
- **Wire en analytics-service**: `data_source_factory` inspecciona
  `CTR_STORE_URL` y `CLASSIFIER_DB_URL`; si están seteadas, crea sesiones
  reales; si no, cae al stub. **El mismo binario corre en dev (stub) y
  prod (real) sin tocar código**, solo cambiando env vars.

Propiedades críticas verificadas con tests:
- Filtro por comisión (no trae de otras comisiones)
- Filtro por tenant (doble filtro defensivo)
- Filtro de ventana temporal (`since`)
- Ordenamiento por `seq` en eventos
- `get_current_classification` respeta `is_current=true`
- Aislamiento entre tenants (un DS de A no ve data de B)
- Agrupación longitudinal por estudiante con orden cronológico
- Aplicación de `pseudonymize_fn` para anonimización on-the-fly

### Punto 1 — Frontend docente con vistas F7

`apps/web-teacher/`:

- `src/lib/api.ts`: cliente HTTP tipado con todas las operaciones F7
  (`getCohortProgression`, `computeKappa`, `requestCohortExport`,
  `getExportStatus`, `downloadExport`).
- `src/views/ProgressionView.tsx`: vista de progresión con summary
  cards (mejorando / estable / empeorando / insuficiente), barra de
  `net_progression_ratio` con visualización bipolar, y timeline
  individual de cada estudiante con colores por categoría N4.
- `src/views/KappaRatingView.tsx`: UI de etiquetado humano con 3
  botones por episodio (reflexiva / superficial / delegación), al
  terminar dispara `POST /analytics/kappa` y muestra κ con
  interpretación Landis & Koch, matriz de confusión con diagonal
  resaltada, y gráfico per-class agreement.
- `src/views/ExportView.tsx`: formulario de export con validación en
  cliente (salt ≥ 16 chars), polling cada 2s al endpoint de status,
  progress bar con colores por estado, y descarga inline como JSON
  cuando el job está succeeded.
- `src/App.tsx`: navegación tabbed entre las 3 vistas con placeholder
  para `getToken` (se wireará a `useAuth()` cuando integremos
  keycloak-js al teacher, análogamente al student).

### Punto 3 — Dashboards Grafana del piloto

`ops/grafana/dashboards/unsl-pilot.json` — dashboard con 12 paneles
específicos del piloto UNSL:

- **Fila 1** (stats de salud diaria): episodios del día, estudiantes
  activos, duración media, código ejecutado por episodio, integridad
  CTR (alarma crítica si > 0).
- **Fila 2**: pie chart de distribución N4 actual + stacked time-series
  con evolución diaria de las 3 categorías.
- **Fila 3**: net_progression_ratio time-series con thresholds visuales
  (rojo < 0, verde > 0.3) + Kappa gauge con rangos Landis & Koch.
- **Fila 4**: backlog de clasificaciones pendientes, reclasificaciones
  en 30d, exports académicos generados, fracción de LLM budget usado.

Template variable `comision` permite alternar entre P1, P2 y TSU-IA sin
editar queries. Template `tenant_id` está hidden pero permite cambiar
de tenant si en el futuro se corre el piloto en otras universidades.

**Provisioning**:
- `ops/grafana/provisioning/dashboards/platform.yaml` — auto-carga
  dashboards del directorio `/var/lib/grafana/dashboards`.
- `ops/grafana/provisioning/datasources/prometheus.yaml` — datasources
  Prometheus (default) y Loki (opcional para correlación de logs).
- `docker-compose.dev.yml` actualizado: Grafana ahora monta ambos
  directorios (provisioning + dashboards).

### Punto 4 — Protocolo del piloto (DOCX)

`docs/pilot/protocolo-piloto-unsl.docx` (23 KB, 306 párrafos, validación
docx OK) — documento académico formal para:
1. Someter al Comité de Ética de la Investigación de UNSL
2. Presentar al jurado como parte del capítulo de metodología
3. Entregar a los docentes participantes como manual del piloto

Estructura (8 secciones + 2 anexos):

1. **Resumen ejecutivo** — objetivos, población (180 estudiantes), duración (16 semanas), instrumento.
2. **Objetivos e hipótesis operativas** — objetivo general, 5 objetivos específicos (OE1-OE5), 3 hipótesis (H1-H3).
3. **Diseño metodológico** — variables dependientes/independientes/control, instrumentos (plataforma, Kappa inter-rater, entrevistas), procedimiento con 4 fases.
4. **Métricas primarias y secundarias** — tablas con umbrales de éxito y criterios de ajuste (stopping rules).
5. **Estrategia de análisis** — análisis a nivel episodio/estudiante/cohorte + análisis cualitativo con Atlas.ti + herramientas.
6. **Consideraciones éticas** — consentimiento informado, minimización de datos, uso secundario, gestión de riesgo (con tabla de mitigaciones).
7. **Cronograma** — tabla semana por semana desde preparación hasta análisis.
8. **Productos esperados** — tesis + dataset + 2 papers (ICALT/SITE + WICC).

**Anexo A**: Modelo de consentimiento informado completo, listo para
firma, con derechos explícitos (retiro, acceso, olvido, queja).

**Anexo B**: Glosario técnico de 13 términos (N4, CTR, episodio, CT,
CCD, CII, Cohen's κ, net_progression_ratio, reference_profile, tenant,
RLS, salt de investigación), con definiciones al nivel del lector no
técnico que el comité de ética suele tener.

`docs/pilot/generate_protocol.js`: fuente docx-js. Permite regenerar
el DOCX tras revisiones sin editar el binario.

`docs/pilot/README.md`: guía operativa del piloto con cronograma,
cómo correr Grafana, y operaciones comunes (Kappa mid-cohorte, export,
A/B testing si κ cae).

## Suite completa — 320/320 tests pasan

```
Delta F8: +10 tests nuevos (10 real datasources)
Total:    320 tests

F7: 310 → F8: 320
```

## Propiedades críticas añadidas por F8

1. **Mismo binario, dos modos**: el analytics-service corre tanto en
   dev (sin DB, stub) como en prod (con DB real, RLS activo) sin
   cambios de código — solo env vars `CTR_STORE_URL` y
   `CLASSIFIER_DB_URL`. Esto reduce el riesgo de divergencia entre
   código-dev y código-prod que suele causar bugs en primeros
   despliegues.

2. **UI autoservicio para docentes**: Alberto ya no es el cuello de
   botella. Cualquier docente puede validar el clasificador (Kappa),
   analizar progresión de su cohorte, y exportar datasets para tesistas
   o papers — todo desde 3 tabs del web-teacher, sin tickets al equipo
   técnico.

3. **Observabilidad del piloto en vivo**: el dashboard UNSL Pilot es
   el "tablero de mando" del estudio. Alberto lo revisa 1×/día durante
   el piloto; si alguna métrica se desvía (integridad CTR, κ bajo,
   backlog alto) interviene antes de que afecte resultados.

4. **Protocolo defendible**: el DOCX está estructurado según los
   requerimientos típicos de comités de ética argentinos (Ley 25.326,
   Declaración de Helsinki). Incluye stopping rules explícitas,
   consentimiento con los 4 derechos clave (retiro, acceso, olvido,
   queja), y tabla de mitigación de riesgos. Listo para presentar
   sin revisión mayor.

## Cómo usar F8

### Correr Grafana con el dashboard del piloto

```bash
cd platform/infrastructure
docker compose -f docker-compose.dev.yml up grafana prometheus
# → http://localhost:3000 (admin/admin) → Dashboards → Platform → UNSL Pilot
```

### Activar adaptadores DB reales

```bash
export CTR_STORE_URL="postgresql+asyncpg://..."
export CLASSIFIER_DB_URL="postgresql+asyncpg://..."
export EXPORT_WORKER_SALT="unsl-pilot-2026-$(openssl rand -hex 16)"

# Arrancar analytics-service
cd apps/analytics-service
uv run uvicorn analytics_service.main:app --port 8005
```

Sin esas variables, cae automáticamente al stub (modo dev).

### Correr el web-teacher en dev

```bash
cd apps/web-teacher
pnpm install
pnpm dev
# → http://localhost:5176 con las 3 vistas F7 operativas
```

### Regenerar el protocolo DOCX

```bash
cd docs/pilot
npm install -g docx
node generate_protocol.js
python3 /path/to/docx-skill/scripts/office/validate.py protocolo-piloto-unsl.docx
```

## Qué queda

Con F8 cerramos los 4 puntos prometidos. Más allá del piloto, lo que
sigue son tareas de escalamiento operacional (no técnicas fundamentales):

- Migración del export a Parquet + S3 firmado cuando los datasets
  superen los 100 MB (hoy JSON inline alcanza).
- Retention automática (cron de `cleanup_old()` en el ExportJobStore).
- Segundo tenant del piloto (otra facultad de UNSL o universidad
  adyacente) para validar que el modelo generaliza.
- Integración real con el sistema de calificaciones de UNSL para el
  análisis de H3 (correlación CII vs rendimiento académico).
