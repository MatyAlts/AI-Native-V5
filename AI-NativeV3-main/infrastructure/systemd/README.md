# Systemd timers — backup automatico para VPS sin Kubernetes

Estos archivos reemplazan al `ops/k8s/backup-cronjob.yaml` (que requiere
Kubernetes) cuando la stack corre en un VPS con `docker-compose.prod.yml`.

## Instalacion en el VPS UTN

```bash
# 1. Copiar los archivos al systemd del sistema
sudo cp infrastructure/systemd/platform-backup.service /etc/systemd/system/
sudo cp infrastructure/systemd/platform-backup.timer /etc/systemd/system/

# 2. Crear el archivo de env vars protegido (modo 600)
sudo mkdir -p /etc/platform
sudo tee /etc/platform/backup.env >/dev/null <<EOF
PG_BACKUP_PASSWORD=poner_la_password_del_user_backup_user_aca
EOF
sudo chmod 600 /etc/platform/backup.env
sudo chown root:root /etc/platform/backup.env

# 3. Crear el user backup_user en Postgres con permisos solo de READ
docker exec -it platform-prod-postgres psql -U postgres -c "
CREATE USER backup_user WITH PASSWORD 'CAMBIAR';
GRANT CONNECT ON DATABASE academic_main, ctr_store, classifier_db, content_db TO backup_user;
\\c academic_main; GRANT pg_read_all_data TO backup_user;
\\c ctr_store; GRANT pg_read_all_data TO backup_user;
\\c classifier_db; GRANT pg_read_all_data TO backup_user;
\\c content_db; GRANT pg_read_all_data TO backup_user;
"

# 4. Habilitar y arrancar el timer
sudo systemctl daemon-reload
sudo systemctl enable --now platform-backup.timer

# 5. Verificar
sudo systemctl list-timers platform-backup.timer
sudo systemctl status platform-backup.timer
```

## Operacion

```bash
# Disparar manualmente (sin esperar al timer)
sudo systemctl start platform-backup.service

# Ver logs del backup
sudo journalctl -u platform-backup.service -n 100

# Ver proxima ejecucion
sudo systemctl list-timers platform-backup.timer

# Pausar (no ejecuta mas backups hasta re-enable)
sudo systemctl disable --now platform-backup.timer
```

## Verificar que el backup funciono

```bash
# Hoy
ls -lh /var/backups/platform/$(date +%Y-%m-%d)/

# Verificar manifest
cat /var/backups/platform/$(date +%Y-%m-%d)/manifest-*.txt
```

Deberias ver 4 archivos `.sql.gz` (una por base) + `attestations-*.tar.gz` (si
hubo episodios cerrados) + `manifest-*.txt`.

## Restore (DR drill)

**HACER ESTO ANTES DEL PRIMER DIA DEL PILOTO**. Un backup sin restore probado no
es un backup.

```bash
# Stage 1: probar restore en una base temporaria
docker exec -it platform-prod-postgres psql -U postgres -c "CREATE DATABASE academic_main_restore_test;"

zcat /var/backups/platform/YYYY-MM-DD/academic_main-*.sql.gz \
  | docker exec -i platform-prod-postgres pg_restore \
    -U postgres \
    -d academic_main_restore_test \
    --no-owner --no-privileges

# Stage 2: verificar conteos
docker exec -it platform-prod-postgres psql -U postgres -d academic_main_restore_test \
  -c "SELECT count(*) FROM episodes;"

# Stage 3: limpiar
docker exec -it platform-prod-postgres psql -U postgres -c "DROP DATABASE academic_main_restore_test;"
```

## Que se guarda

1. **4 bases Postgres** (custom format, compress=9):
   - `academic_main` — comisiones, usuarios, episodes, tareas-practicas
   - `ctr_store` — eventos CTR append-only (cadena criptografica)
   - `classifier_db` — clasificaciones N4 con classifier_config_hash
   - `content_db` — materiales + chunks pgvector (RAG)

2. **`/var/lib/platform/attestations/attestations-*.jsonl`** — firmas Ed25519
   del integrity-attestation-service. **Evidencia criptografica de la tesis**
   — perderlos invalida la cadena de custodia.

3. **`manifest-*.txt`** — checksums SHA-256 de todos los archivos.

## Retencion

El `ExecStartPost` del service borra backups mas viejos a 30 dias. Si necesitas
retencion mas larga (ej. archive trimestral en storage externo), agregar un
segundo paso que copie selectivamente.
