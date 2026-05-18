# Pre-flight checklist — despliegue UNSL

Checklist accionable para verificar que todo está listo **antes** de que
el primer estudiante toque la plataforma. Un ítem no verificado ≠ ítem
aprobado — se marca con `[✗]` y se bloquea el deploy.

El documento está ordenado por dependencia: verificar en orden.
Responsables: `TEC` = equipo técnico de UNSL · `INV` = Alberto ·
`DOC` = docentes participantes.

---

## Fase 1 — Infraestructura base (T-4 semanas)

### Servidores y red

- [ ] **Servidor dedicado o VM con al menos 8 CPU / 16 GB RAM / 200 GB SSD** (`TEC`)
  - Justificación: CTR + pgvector del content-service + Redis + Keycloak pueden demandar memoria en picos de uso (100+ estudiantes simultáneos).
- [ ] **Dominio público con TLS válido** (`TEC`)
  - Ej: `plataforma.unsl.edu.ar` con certificado Let's Encrypt renovable.
  - Subdominios para los 3 frontends: `student.plataforma.unsl.edu.ar`, `teacher.`, `admin.`.
- [ ] **Firewall abierto solo en 443 (HTTPS) y 22 (SSH restringido a IPs del equipo)** (`TEC`)
- [ ] **DNS resuelve desde red de UNSL y desde internet** (`TEC`)

### Databases

- [ ] **Postgres 15+ con 3 bases lógicas**: `academic_main`, `ctr_store`, `identity_realms` (`TEC`)
- [ ] **Row-Level Security habilitado** en todas las tablas con `tenant_id` (`TEC`)
  - Verificar con: `SELECT tablename, rowsecurity FROM pg_tables WHERE tenant_id IS NOT NULL`.
- [ ] **Backup automatizado nocturno verificado** (`TEC`)
  - Correr `scripts/backup.sh` manualmente al menos una vez + verificar restore con `scripts/restore.sh`.
- [ ] **Usuarios de DB separados** con `GRANT` mínimo por servicio (`TEC`)

### Redis

- [ ] **Redis 7+ en modo AOF persistente** (`TEC`)
  - Verificar: `redis-cli CONFIG GET appendonly` → `yes`.
- [ ] **Memoria asignada >= 2 GB** (para streams del CTR con backlog)

---

## Fase 2 — Identidad y autenticación (T-3 semanas)

- [ ] **Keycloak corriendo y accesible en puerto interno 8180** (`TEC`)
- [ ] **Realm `unsl` creado** con `python examples/unsl_onboarding.py` (`TEC` + `INV`)
  - Verificar: `curl https://keycloak/realms/unsl/.well-known/openid-configuration` responde 200.
- [ ] **Client `platform-backend` con `tenant_id` claim mapper** configurado (`TEC`)
  - Verificar: decoded de un JWT de prueba debe contener `"tenant_id": "aaaaaaaa-..."`.
- [ ] **4 roles creados**: `estudiante`, `docente`, `docente_admin`, `superadmin` (`TEC`)
- [ ] **LDAP federation funcionando** si UNSL usará LDAP institucional (`TEC` + `INV`)
  - Test: `kcadm.sh create users-storage --realm unsl ...` → usuario del LDAP aparece en Keycloak sin sync manual.
  - **Verificar editMode = READ_ONLY** (crítico: la plataforma nunca modifica el LDAP institucional).
- [ ] **JWKS endpoint accesible desde los servicios backend** (`TEC`)
  - Desde el contenedor de api-gateway: `curl http://keycloak:8180/realms/unsl/protocol/openid-connect/certs` responde 200.

---

## Fase 3 — Despliegue de servicios (T-2 semanas)

### Secretos

- [ ] **`ANTHROPIC_API_KEY` de UNSL configurada** (como env var o K8s Secret) (`TEC` + `INV`)
  - UNSL debería tener su propia cuenta Anthropic con budget dedicado al piloto.
- [ ] **`KEYCLOAK_ADMIN_PASSWORD` no es `admin`** (`TEC`)
- [ ] **`POSTGRES_PASSWORD` no es default** (`TEC`)
- [ ] **`EXPORT_WORKER_SALT` generado con `openssl rand -hex 32`** y guardado en vault (`INV`)
  - **Crítico**: sin este salt no se puede cross-referenciar análisis entre turnos. Guardarlo en password manager del grupo de investigación.

### Feature flags

- [ ] **`feature_flags.yaml` desplegado** con config del piloto (`TEC`)
  - `enable_code_execution: true` para UNSL
  - `show_n4_to_students: true` (decisión pedagógica: los estudiantes ven su propia clasificación)
  - `max_episodes_per_day: 200` (holgura para exploración)

### Servicios

- [ ] **Los 12 servicios Python corriendo en modo prod** (`TEC`)
  - `api-gateway`, `academic-service`, `enrollment-service`, `content-service`,
    `ctr-service`, `governance-service`, `ai-gateway`, `tutor-service`,
    `classifier-service`, `analytics-service`, `evaluation-service`, `identity-service`.
  - `dev_trust_headers=False` en el api-gateway (crítico: sino permite spoofing).
- [ ] **Healthchecks responden 200 en cada servicio** (`TEC`)
  - Script de smoke test: `for svc in api-gateway ctr-service tutor-service ...; do curl https://plataforma/health/$svc; done`
- [ ] **3 frontends buildeados y servidos** (`TEC`)
  - `web-student` (estudiantes) · `web-teacher` (docentes) · `web-admin` (admins).

---

## Fase 4 — Observabilidad y monitoreo (T-2 semanas)

- [ ] **Prometheus scrappeando las 12 métricas de servicios** (`TEC`)
  - Verificar en `http://prometheus:9090/targets` que todos estén `UP`.
- [ ] **Grafana con el dashboard UNSL Pilot auto-cargado** (`TEC`)
  - Abrir `https://grafana.plataforma.unsl.edu.ar` → Dashboards → Platform → UNSL Pilot.
- [ ] **Alertas críticas configuradas**:
  - [ ] `PlatformBackupJobFailed` (backup nocturno falló) → email a `TEC + INV`
  - [ ] `CTRIntegrityCompromised` (cadena criptográfica rota) → PagerDuty o equivalente
  - [ ] `AIGatewayBudgetExceeded` (se pasa del budget diario) → email
- [ ] **Logs centralizados en Loki** (`TEC`)
  - Logs de los 12 servicios indexados por service_name + tenant_id.

---

## Fase 5 — Verificación funcional end-to-end (T-1 semana)

Ejecutar el happy path completo con una cuenta de prueba **antes** de
que ningún estudiante real toque el sistema.

- [ ] **Login con usuario de LDAP funciona** (`TEC` + `INV`)
  - Crear usuario test en LDAP UNSL → login en `student.plataforma.unsl.edu.ar` → debe ver el dashboard.
- [ ] **El JWT tiene `tenant_id` correcto** (`TEC`)
  - Decodificar `Authorization` header en DevTools del browser → verificar payload.
- [ ] **Abrir un episodio → tutor responde via SSE** (`INV`)
  - Crear episodio, enviar mensaje, verificar que se recibe streaming.
  - Chequear en Grafana que `ctr_episodes_opened_total` incrementó.
- [ ] **Ejecutar código en el editor Pyodide** (`INV`)
  - Python `print(1+1)` debe mostrar `2` en output.
  - Verificar que `codigo_ejecutado` event llegó al CTR: query SQL en `ctr_store.events`.
- [ ] **Cerrar episodio → queda con `estado='closed'`** (`INV`)
  - Verificar en `ctr_store.episodes` + `chain_hash` del último evento es consistente.
- [ ] **Ejecutar clasificación manual → classifier responde** (`INV`)
  - `POST /api/v1/classify_episode/{id}` → debe volver clasificación N4 con las 5 coherencias.
  - Verificar hash del classifier config es determinista.
- [ ] **Verificar integridad del CTR** (`TEC`)
  - `python scripts/verify_ctr_integrity.py --tenant unsl` debe pasar.

---

## Fase 6 — Preparación pedagógica (T-1 semana)

- [ ] **3 docentes capacitados** (`INV`)
  - Sesión 1 (90 min): panorama de la plataforma + filosofía pedagógica del N4.
  - Sesión 2 (90 min): operación concreta del `web-teacher` (las 3 vistas) + casos difíciles.
- [ ] **Cada docente puede loguear como `docente` y ver la vista Progresión** (`DOC`)
- [ ] **Cada docente tiene asignada su comisión en `enrollment-service`** (`INV`)
- [ ] **Los 3 problemas del primer cuatrimestre cargados en `content-service`** (`DOC`)
  - Incluyendo el problema de palíndromos para la línea base.
- [ ] **Materiales de cátedra subidos** con tags por comisión (`DOC`)
  - Verificar que el RAG devuelve chunks correctos al preguntar en un episodio de prueba.

---

## Fase 7 — Ética y consentimiento (T-1 semana)

- [ ] **Protocolo aprobado por el Comité de Ética de UNSL** (`INV`)
  - Tener el dictamen por escrito (mail oficial o resolución) antes de reclutar.
- [ ] **Formulario de consentimiento informado impreso** (`INV`)
  - 180 copias listas (una por estudiante potencial).
- [ ] **Procedimiento de retiro documentado** (`INV`)
  - Si un estudiante se retira: (a) marcar en la planilla de seguimiento, (b) no procesar eventos futuros suyos, (c) si pide anonimización, correr `platform_ops.anonymize_student`.
- [ ] **Política de datos comunicada** (`INV`)
  - Los 3 docentes conocen dónde se almacenan los datos y qué NO pueden hacer (por ejemplo: compartir exports con terceros sin aprobación).

---

## Fase 8 — Día 1 del piloto (T-0)

- [ ] **Reunión de kickoff con los 3 docentes + Alberto** (`INV` + `DOC`)
  - 30 min para revisar qué se espera en las primeras 2 semanas.
- [ ] **Grafana abierto durante las primeras horas** (`TEC` + `INV`)
  - Monitorear episodios abiertos, errores 5xx, latencia del tutor, violaciones de integridad.
- [ ] **Canal Slack/Teams dedicado al soporte del piloto** (`TEC` + `INV` + `DOC`)
  - Para reportes rápidos de bugs o dudas. No bloquear el piloto por problemas menores.

---

## Criterios de go/no-go

**GO al piloto** si todos los ítems de Fase 1–7 están `[✓]` o explícitamente waiverados con justificación escrita.

**NO-GO** si falta alguno de estos (bloqueos absolutos):

- Backup automático no verificado
- `dev_trust_headers=True` en producción
- Protocolo sin aprobación del Comité de Ética
- Alguno de los 12 servicios no responde healthcheck
- `ANTHROPIC_API_KEY` no configurada

---

## Post-piloto (T+16 semanas)

- [ ] **Exportar dataset final** con salt del grupo de investigación
- [ ] **Backup del CTR del período completo** con naming `unsl_piloto_2026_Q1`
- [ ] **Retention: mantener datos 5 años** según política del comité de ética
- [ ] **Publicar salt_hash** (no el salt) en el paper para reproducibilidad
- [ ] **Baja graceful**: desactivar `enable_code_execution` si el piloto termina y no continúa la plataforma en esa cohorte
