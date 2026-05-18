## ADDED Requirements

### Requirement: 5 dashboards SHALL be provisioned via filesystem

El piloto SHALL exponer exactamente 5 dashboards Grafana provisionados desde `infrastructure/grafana/provisioning/dashboards/`, cada uno como un archivo JSON commiteable. Los dashboards son:

1. `Plataforma — visión general` (folder `Plataforma`, refresh `30s`)
2. `CTR — integridad` (folder `CTR`, refresh `15s`)
3. `AI Gateway — costos y latencia` (folder `AI Gateway`, refresh `1m`)
4. `Tutor — engagement` (folder `Tutor`, refresh `30s`)
5. `Classifier — kappa & coherencias` (folder `Classifier`, refresh `5m`)

Cada dashboard SHALL declarar su audiencia explícita en la descripción (comité doctoral, auditor, doctorando, etc.) para que el reviewer entienda la intención de cada panel.

#### Scenario: Grafana muestra los 5 dashboards en folders correspondientes

- **WHEN** el desarrollador corre `make dev-bootstrap` con el provisioning aplicado y abre `http://localhost:3000`
- **THEN** Grafana muestra exactamente 5 folders (`Plataforma`, `CTR`, `AI Gateway`, `Tutor`, `Classifier`), cada uno con su dashboard correspondiente

#### Scenario: Refresh rate por dashboard

- **WHEN** se abre cada dashboard
- **THEN** su refresh rate por default SHALL ser el declarado (30s/15s/1m/30s/5m respectivamente), configurable por el usuario en sesión sin afectar el JSON commiteado

### Requirement: Dashboards SHALL use templating variables for tenant/cohort filtering

Los 5 dashboards SHALL declarar variables de templating que permitan filtrar por tenant y cohorte sin duplicar JSON. Las variables son:

- `$tenant` — `label_values(ctr_events_total, tenant_id)`, default tenant demo `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`.
- `$cohort` — `label_values(ctr_events_total{tenant_id="$tenant"}, comision_id)`, all-by-default.
- `$service` — `label_values(up, service_name)` (solo dashboard 1).
- `$template_id` — `label_values(classifier_classifications_total{tenant_id="$tenant"}, template_id)` (solo dashboard 5).

#### Scenario: Cambio de tenant filtra todos los paneles del dashboard

- **WHEN** el usuario cambia `$tenant` en el dropdown del dashboard
- **THEN** todos los paneles del dashboard SHALL recargar con queries filtradas por el nuevo `tenant_id`, sin queries que ignoren la variable

### Requirement: Dashboards SHALL show real data after seed + demo flow

Después de `make dev-bootstrap` + arrancar los 12 servicios Python + 8 workers CTR + `uv run python scripts/seed-3-comisiones.py` + flujo demo (1 episodio abierto + cerrado desde web-student), **al menos 12 paneles** distribuidos entre los 5 dashboards SHALL mostrar datos reales (no `No data`). Los paneles que dependen de eventos no producidos por el flow demo (ej. `intento_adverso_detectado`) PUEDEN quedar vacíos pero NO SHALL crashear.

#### Scenario: Smoke test post-seed

- **WHEN** se ejecuta el flujo descrito y se abren los 5 dashboards
- **THEN** ≥12 paneles muestran series temporales o stat values con datos reales del seed + demo

#### Scenario: Panel `integrity_compromised` muestra 0

- **WHEN** se abre el dashboard `CTR — integridad`
- **THEN** el panel `integrity_compromised events` muestra valor exactamente `0` (target estricto del piloto)

### Requirement: Dashboards SHALL load each panel in less than 3 seconds on manual refresh

Todos los paneles de los 5 dashboards SHALL cargar en **< 3 segundos** cuando el usuario haga refresh manual con la base de datos seeded. Si un panel toma > 3s, su query SHALL ser refactoreada (reduce time range, use recording rule, simplify aggregation) antes de mergear.

#### Scenario: Refresh manual de cualquier dashboard

- **WHEN** el usuario hace click en `Refresh` en cualquier dashboard
- **THEN** todos los paneles del dashboard renderizan en < 3 segundos en el ambiente dev local

### Requirement: Dashboards heredados SHALL be archived with deprecation README

Los dashboards heredados en `ops/grafana/dashboards/{platform-slos,unsl-pilot}.json` y el provisioning bajo `ops/grafana/provisioning/` SHALL ser movidos a `ops/grafana/_archive/` en el mismo PR de apply. El directorio `_archive/` SHALL contener un `README.md` que documente:

- Que los JSONs son **aspiracionales** y referencian métricas que nunca se emitieron en el piloto.
- Apunta al nuevo path canónico `infrastructure/grafana/provisioning/dashboards/`.
- Lista las métricas que los dashboards heredados esperaban (`ctr_episodes_opened_total`, etc.) para futura referencia.

#### Scenario: Path heredado archivado correctamente

- **WHEN** se inspecciona `ops/grafana/` post-apply
- **THEN** existe sólo el subdirectorio `_archive/` con los JSONs viejos + README; no quedan archivos de provisioning activos en `ops/grafana/`

### Requirement: Provisioning SHALL use new canonical path infrastructure/grafana/

El provisioning de datasources y dashboards SHALL vivir en `infrastructure/grafana/provisioning/{datasources,dashboards}/`. El `docker-compose.dev.yml` del piloto SHALL montar este path como `/etc/grafana/provisioning` en el container.

El provider de dashboards SHALL usar `foldersFromFilesStructure: true` para que la jerarquía de folders surja del filesystem (un subdirectorio por folder).

#### Scenario: docker-compose monta el path nuevo

- **WHEN** se inspecciona `infrastructure/docker-compose.dev.yml` sección `services.grafana.volumes`
- **THEN** el path host es `infrastructure/grafana/provisioning/`, NO `ops/grafana/`

### Requirement: README documenting the operational workflow

`infrastructure/grafana/provisioning/dashboards/README.md` SHALL document:

- Workflow de edición: editar en UI → `Share → Export → Save to file` → reemplazar JSON commiteado → PR con git diff.
- Política de cardinalidad: las labels prohibidas (`student_pseudonym`, `episode_id`, `user_id`, cualquier UUID per-instancia) y por qué.
- Naming convention: prefijo por servicio (`ctr_*`, `ai_gateway_*`, `tutor_*`, `classifier_*`), formato OTel-friendly (`*_total`, `*_seconds`, `*_count`).
- Comando para empezar limpio: `docker compose -f infrastructure/docker-compose.dev.yml down -v` antes del primer `make dev-bootstrap` post-apply.
- Lista de métricas custom emitidas con su definición + label set permitido.

#### Scenario: README presente y completo

- **WHEN** se inspecciona `infrastructure/grafana/provisioning/dashboards/README.md`
- **THEN** contiene secciones para los 5 puntos listados, cada una con texto suficiente para que un developer nuevo pueda iterar dashboards sin romper el provisioning

### Requirement: Cardinality budget SHALL be enforced post-apply

Después de seed + flujo demo, la cardinalidad total de Prometheus SHALL ser **< 5000 series**. Verificable con `curl http://localhost:9090/api/v1/label/__name__/values | jq 'length'`.

Las labels prohibidas SHALL NUNCA aparecer en métricas Prometheus emitidas por servicios del piloto: `student_pseudonym`, `episode_id`, `user_id`, `prompt_id`, ni cualquier UUID per-instancia.

#### Scenario: Cardinalidad post-seed dentro del budget

- **WHEN** se ejecuta el flujo `dev-bootstrap` + seed + demo episodio
- **THEN** `curl http://localhost:9090/api/v1/label/__name__/values | jq 'length'` devuelve un valor < 5000
