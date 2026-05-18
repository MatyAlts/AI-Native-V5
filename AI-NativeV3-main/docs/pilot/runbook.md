# Runbook del Piloto UNSL

Qué hacer cuando algo falla durante las 16 semanas del piloto. Este
runbook se usa por el equipo técnico y los docentes participantes;
cada incidente debe quedar registrado en el Google Sheet
`pilot-incidents` para el análisis post-mortem que irá al capítulo
de discusión de la tesis.

## Índice de incidentes

| Código | Síntoma | Severidad | Sección |
|---|---|---|---|
| I01 | Integridad del CTR comprometida | 🔴 Crítica | [§1](#i01) |
| I02 | Tutor no responde / timeouts altos | 🟠 Alta | [§2](#i02) |
| I03 | Clasificador dejó de procesar episodios | 🟠 Alta | [§3](#i03) |
| I04 | Kappa intermedio < 0.4 | 🟡 Media | [§4](#i04) |
| I05 | Net progression ratio < -0.2 en una cátedra | 🟡 Media | [§5](#i05) |
| I06 | Estudiante solicita borrado de datos | 🟢 Normal | [§6](#i06) |
| I07 | Export académico falla | 🟢 Normal | [§7](#i07) |
| I08 | LDAP no autentica a un usuario | 🟢 Normal | [§8](#i08) |
| I09 | LLM budget agotado en un tenant | 🟡 Media | [§9](#i09) |
| I10 | Backup diario falló | 🟠 Alta | [§10](#i10) |

---

## I01. Integridad del CTR comprometida  <a id="i01"></a>

**Síntomas**:
- Alerta `ctr_episodes_integrity_compromised_total > 0` en Grafana
- Logs del `ctr-service` con `integrity_check_failed` o `chain_hash mismatch`
- El canary de Argo Rollouts bloqueó un deploy

**Severidad**: 🔴 Crítica — afecta la validez científica del estudio.

**Accion inmediata**:

1. **Pausar el canary si hay uno en progreso**:
   ```bash
   kubectl argo rollouts pause tutor-service -n platform
   ```

2. **Verificar qué episodios están afectados**:
   ```sql
   SELECT id, tenant_id, comision_id, integrity_compromised, last_chain_hash
   FROM episodes
   WHERE integrity_compromised = true
   ORDER BY opened_at DESC LIMIT 20;
   ```

3. **Identificar el evento culpable desde la DLQ**:
   ```sql
   SELECT * FROM dead_letters
   WHERE created_at > NOW() - INTERVAL '1 hour'
   ORDER BY created_at DESC;
   ```

4. **Verificación forense de la cadena**:
   ```bash
   cd apps/ctr-service
   uv run python -m ctr_service.scripts.verify_chain --episode <episode_id>
   # Debe reportar: "Chain verified: N events"
   ```

**Acción de recuperación**:

- **Si el daño está acotado a un episodio**: marcar el episodio como
  `integrity_compromised=true` (ya lo hizo el consumer), NO reutilizar
  esos datos en el análisis final. Documentar en pilot-incidents.
- **Si el daño es sistémico (>10 episodios)**: detener el piloto en la
  cátedra afectada, restaurar del último backup verificado
  (`scripts/restore.sh`) con checksums OK, y reiniciar la operación
  desde el timestamp del último evento consistente.

**Análisis post-mortem obligatorio** antes de retomar. Documentar en
`docs/pilot/incidents/I01-YYYY-MM-DD.md`.

---

## I02. Tutor no responde / timeouts altos  <a id="i02"></a>

**Síntomas**:
- Estudiantes reportan "el tutor no contesta" o "se queda pensando"
- Panel "tutor-p95-latency" > 5s en Grafana
- HTTP 504 en logs del api-gateway

**Severidad**: 🟠 Alta — afecta la experiencia del estudiante.

**Diagnóstico**:

1. **¿Es el LLM provider?** Ver `ai_gateway_tokens_used` vs budget,
   latencia de la API de Anthropic:
   ```bash
   curl -s http://prometheus:9090/api/v1/query?query=ai_gateway_llm_latency_seconds_bucket
   ```

2. **¿Es el retrieval RAG?**
   ```bash
   kubectl logs -n platform -l app=content-service --tail=100 | grep retrieval
   ```

3. **¿Es Redis (session manager) saturado?**
   ```bash
   kubectl exec -n platform redis-0 -- redis-cli INFO stats | grep instantaneous_ops_per_sec
   ```

**Acción**:

- **LLM provider caído**: activar fallback a provider secundario
  (feature flag `llm_provider_fallback=openai`) y notificar a docentes
  vía Slack/email que el estilo del tutor puede variar.
- **Retrieval lento**: verificar que pgvector tenga el índice IVFFlat
  activo (`SELECT * FROM pg_indexes WHERE tablename='chunks'`). Si falta,
  crearlo con `CREATE INDEX CONCURRENTLY`.
- **Redis saturado**: scale del statefulset a 3 replicas con sharding.

---

## I03. Clasificador dejó de procesar episodios  <a id="i03"></a>

**Síntomas**:
- Panel "Backlog de clasificaciones" crece linealmente en Grafana
- `classifier_classifications_total` deja de incrementar

**Diagnóstico**:

1. **¿El worker está vivo?**
   ```bash
   kubectl get pods -n platform -l app=classifier-service
   kubectl logs -n platform -l app=classifier-service --tail=50
   ```

2. **¿Hay eventos del ctr-service que el worker no puede consumir?**
   ```bash
   kubectl exec redis-0 -- redis-cli XLEN ctr-stream
   kubectl exec redis-0 -- redis-cli XINFO GROUPS ctr-stream
   ```

**Acción**:

- **Worker crasheado**: `kubectl rollout restart deploy/classifier-service -n platform`.
- **Evento con payload inválido atascando el consumer**: identificar el
  `event_uuid`, moverlo a DLQ manualmente:
  ```sql
  INSERT INTO dead_letters (event_uuid, reason, original_payload, created_at)
  VALUES ('<uuid>', 'manual_quarantine', '<json>', NOW());
  ```

---

## I04. Kappa intermedio < 0.4  <a id="i04"></a>

**Pre-piloto**: ver [`docs/pilot/kappa-workflow.md`](kappa-workflow.md) para el
procedimiento de etiquetado intercoder inicial (OBJ-13). Este incidente cubre
sólo la regresión de κ **durante** el piloto, una vez que la baseline ya
quedó establecida.

**Criterio del protocolo §4.3**: si el primer cómputo de Kappa resulta
inferior a 0.4, se revisa el árbol de decisión antes de continuar.

**Procedimiento**:

1. Identificar clases problemáticas en `per_class_agreement` del report
   (usualmente superficial ↔ delegación se confunden más).

2. Proponer 2-3 profiles candidatos con umbrales distintos:
   ```python
   # En docs/pilot/kappa-tuning/profile_candidates.py
   profile_stricter = {
     **DEFAULT_REFERENCE_PROFILE,
     "name": "stricter",
     "thresholds": {
       **DEFAULT_REFERENCE_PROFILE["thresholds"],
       "EXTREME_ORPHAN_THRESHOLD": 0.75,  # era 0.8
     },
   }
   ```

3. Correr A/B testing sobre los 60 episodios gold standard:
   ```bash
   curl -X POST https://plataforma.unsl.edu.ar/api/v1/analytics/ab-test-profiles \
     -H "Authorization: Bearer $TOKEN" \
     -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
     -H "X-User-Id: 11111111-1111-1111-1111-111111111111" \
     -d @ab-request.json | jq .
   ```

4. Si algún candidato supera κ=0.6, committear el profile al repo con
   nuevo hash, correr alembic migration con el `classifier_config_hash`
   nuevo, y **reclasificar** los episodios del piloto con el profile
   nuevo (los viejos quedan `is_current=false`, auditable).

5. Documentar el cambio en `docs/pilot/kappa-tuning/profile-vN.md` con:
   - κ antes y después
   - Hash del profile viejo y nuevo
   - Justificación pedagógica del ajuste

---

## I05. Net progression ratio < -0.2 en una cátedra  <a id="i05"></a>

**Criterio del protocolo §4.3**: reunión extraordinaria con el docente
responsable.

**Preparación de la reunión**:

1. Exportar el dataset anonymizado de la cátedra afectada con
   `include_prompts=true` (justificado por el análisis diagnóstico).

2. Identificar trayectorias típicas de "empeorando" y caracterizar
   el patrón:
   ```python
   import json
   data = json.load(open("cohort.json"))
   empeorando = [t for t in data["trajectories"] if t["progression_label"] == "empeorando"]
   # ¿Tienen más codigo_ejecutado que prompts? (copypaste puro)
   # ¿Cambiaron de problema antes de resolver el anterior?
   # ¿Están en el mismo grupo de prácticas?
   ```

3. Discutir con el docente si hay un factor del contexto de la cátedra
   (ej. el docente cambió el tipo de problemas, o hubo un parcial que
   hizo que los estudiantes pasen a modo "resolver rápido").

**Posibles acciones**:

- **No intervenir** y documentar el fenómeno (si es contextual y
  esperado): queda como hallazgo de la tesis.
- **Ajustar el onboarding** con los estudiantes si hay malinterpretación
  del propósito de la plataforma.
- **Pausar la cátedra del piloto** si el daño es claro.

En todos los casos, documentar.

---

## I06. Estudiante solicita borrado de datos  <a id="i06"></a>

**Derecho garantizado en el consentimiento** (Anexo A del protocolo).

**Procedimiento**:

1. Verificar identidad del solicitante (firma + DNI vs consentimiento
   archivado).

2. Ejecutar anonimización:
   ```python
   from platform_ops.privacy import anonymize_student
   report = anonymize_student(
       student_pseudonym=UUID("..."),
       data_source=academic_data_source,
   )
   ```

3. La cadena CTR **se preserva** (los eventos siguen ahí con los hashes
   intactos), pero el pseudónimo nuevo no se liga a la identidad real.
   Esto cumple el derecho al olvido sin romper la trazabilidad del
   registro.

4. Comunicar al estudiante por escrito:
   - Fecha de ejecución
   - Confirmación de anonimización
   - Aclaración de que los eventos agregados en análisis publicados
     no se retiran porque ya no son atribuibles a su persona.

---

## I07. Export académico falla  <a id="i07"></a>

**Síntomas**: `GET /cohort/export/{job_id}/status` devuelve `failed`.

**Diagnóstico**:

1. Leer el campo `error` del status response.
2. Ver logs del analytics-service:
   ```bash
   kubectl logs -n platform -l app=analytics-service | grep export_failed
   ```

**Causas comunes**:

- **Salt < 16 chars**: el cliente debería haberlo rechazado antes; si
  llegó al worker, hay un bug en el frontend. Fix: el endpoint ya
  rechaza esto.
- **Timeout de DB**: el pool del CTR_STORE_URL está saturado; subir
  `pool_size` en `services/export.py` o reducir `period_days` del
  export.
- **Dataset muy grande**: >100 MB inline es incómodo; migrar al modo
  S3 firmado (pendiente post-piloto).

---

## I08. LDAP no autentica a un usuario  <a id="i08"></a>

**Síntomas**: estudiante reporta "no puedo entrar" con credenciales de UNSL.

**Diagnóstico**:

1. **¿El user existe en el LDAP de UNSL?**
   ```bash
   ldapsearch -x -H ldaps://ldap.unsl.edu.ar \
     -D "cn=admin,dc=unsl,dc=edu,dc=ar" \
     -b "ou=people,dc=unsl,dc=edu,dc=ar" \
     "uid=jperez"
   ```

2. **¿Keycloak sincronizó?**
   ```bash
   # Admin UI → Realm 'unsl' → User Federation → sync users
   ```

3. **¿El usuario tiene un rol asignado?** Si no, Keycloak autentica
   pero la plataforma rechaza (sin rol = sin acceso).

**Fix**: agregar al usuario al grupo LDAP correspondiente (`docentes`,
`estudiantes`, `administradores`); el mapper de grupo → rol se
sincroniza en el próximo login.

---

## I09. LLM budget agotado en un tenant  <a id="i09"></a>

**Síntomas**: `ai_gateway_tokens_used / ai_gateway_tokens_budget >= 1.0` en Grafana.

**Efecto**: los estudiantes del tenant reciben HTTP 429 al intentar
nuevos episodios.

**Acciones**:

- **Temporal (emergency)**: aumentar el budget diario en el ai-gateway:
  ```bash
  curl -X PATCH http://ai-gateway:8011/api/v1/budgets/$TENANT_ID \
    -d '{"daily_token_budget": 2000000}'
  ```
- **Estructural**: si pasa recurrentemente, migrar al tenant a su
  propia API key de Anthropic (ya soportado por `TenantSecretResolver`),
  con su propio plan de facturación directa con Anthropic.

---

## I10. Backup diario falló  <a id="i10"></a>

**Alerta**: `PlatformBackupJobFailed` o `PlatformBackupMissing` desde
PrometheusRule del `ops/k8s/backup-cronjob.yaml`.

**Diagnóstico**:

```bash
kubectl logs -n platform -l job-name=platform-db-backup --tail=200
kubectl describe cronjob platform-db-backup -n platform
```

**Causas típicas**:
- PVC `platform-backups` lleno → expandir PVC o limpiar backups viejos.
- Credenciales de `PG_BACKUP_PASSWORD` expiraron en el Secret.
- pg_dump timeout → la DB creció y el backup toma más que el deadline;
  subir `startingDeadlineSeconds` del CronJob.

**Acción inmediata**: correr el backup manualmente para no quedar sin
fallback mientras se diagnostica:

```bash
cd platform/
PG_BACKUP_PASSWORD="$PG_BACKUP_PASSWORD" ./scripts/backup.sh
```

---

## Contactos de escalamiento

| Severidad | Primer contacto | Segundo contacto | Tiempo máx respuesta |
|---|---|---|---|
| 🔴 Crítica | Alberto (WhatsApp) | Equipo técnico UNSL | 30 min |
| 🟠 Alta | Email + Slack | — | 2 h |
| 🟡 Media | Jira ticket + Slack | — | 24 h |
| 🟢 Normal | Jira ticket | — | 72 h |

Todos los incidentes se documentan en `docs/pilot/incidents/INNN-YYYY-MM-DD.md`.
Al cierre del piloto, los docs se agregan al apéndice de la tesis como
evidencia del rigor operacional del estudio.
