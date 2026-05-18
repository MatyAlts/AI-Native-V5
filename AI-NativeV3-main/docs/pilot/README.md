# Piloto UNSL — Guía de operación

Este directorio contiene los artefactos del estudio piloto en la UNSL:

- `protocolo-piloto-unsl.docx` — protocolo formal (20 páginas) con
  objetivos, hipótesis, metodología, consentimiento y cronograma.
  Diseñado para presentación al Comité de Ética y al jurado de tesis.
- `generate_protocol.js` — fuente que genera el DOCX. Permite regenerarlo
  tras revisiones sin editar a mano.

## Instalación de Grafana con los dashboards del piloto

En `docker-compose.dev.yaml`:

```yaml
grafana:
  image: grafana/grafana:10.4.0
  ports: ["3000:3000"]
  environment:
    - GF_SECURITY_ADMIN_USER=admin
    - GF_SECURITY_ADMIN_PASSWORD=admin
    - GF_USERS_ALLOW_SIGN_UP=false
  volumes:
    - ./ops/grafana/provisioning:/etc/grafana/provisioning:ro
    - ./ops/grafana/dashboards:/var/lib/grafana/dashboards:ro
```

Al arrancar:

```bash
docker compose -f docker-compose.dev.yaml up grafana
# Luego ir a http://localhost:3000 → Dashboards → Platform → UNSL Pilot
```

## Cronograma operativo del piloto

| Semana | Fase | Responsable | Producto |
|---|---|---|---|
| −4 a −1 | Preparación | Alberto + equipo técnico UNSL | Tenant UNSL configurado |
| 1 | Línea base | Docentes de cada cátedra | Clasificación N4 inicial |
| 2–15 | Intervención | Todos | ~1440 episodios esperados |
| 8 | Check intermedio | Alberto | Primer cómputo de κ |
| 16 | Cierre | Docentes | Dataset anonymizado + κ final |
| 17–20 | Entrevistas + análisis | Alberto | Capítulo empírico en borrador |

## Métricas a monitorear en vivo

Desde el Grafana UNSL Pilot Dashboard:

1. **Episodios del día** — verifica que haya uso sostenido
2. **Estudiantes activos** — identifica abandono temprano
3. **Integridad CTR** — alarma crítica si hay violaciones
4. **Distribución N4** — evolución durante el cuatrimestre
5. **Net progression ratio** — indicador principal de H1
6. **Kappa inter-rater** — indicador principal de H2
7. **Backlog de clasificaciones** — si crece, revisar el classifier-service
8. **LLM budget** — para prevenir overspend

## Operaciones comunes

### Ejecutar análisis Kappa mid-cohorte

```bash
# Desde la UI del web-teacher: tab "Inter-rater" → etiquetar ≥30 episodios → Calcular Kappa.
# Alternativa API:
curl -X POST https://plataforma.unsl.edu.ar/api/v1/analytics/kappa \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-User-Id: 11111111-1111-1111-1111-111111111111" \
  -d @ratings.json
```

### Exportar dataset para análisis externo

```bash
# Desde la UI del web-teacher: tab "Exportar" → completar form → descargar JSON.
# Alternativa API:
curl -X POST https://plataforma.unsl.edu.ar/api/v1/analytics/cohort/export \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" \
  -H "X-User-Id: 11111111-1111-1111-1111-111111111111" \
  -d '{
    "comision_id": "...",
    "period_days": 120,
    "include_prompts": false,
    "salt": "unsl-research-2026-alberto-secret",
    "cohort_alias": "UNSL_2026_P2"
  }'
```

### A/B testing de refinamiento del árbol N4

Si κ cae por debajo de 0,4 en el check intermedio:

1. Identificar clases problemáticas con `per_class_agreement` del output de Kappa
2. Proponer profile ajustado (ej. subir/bajar `EXTREME_ORPHAN_THRESHOLD`)
3. Llamar `POST /ab-test-profiles` con episodios gold standard + ambos profiles
4. Elegir el profile con mayor κ, commitearlo al repo con nuevo hash

### Regenerar el protocolo (DOCX)

```bash
cd docs/pilot/
npm install -g docx
node generate_protocol.js
python3 /path/to/validate.py protocolo-piloto-unsl.docx
```

## Contactos

- **Investigador principal**: Alberto Alejandro Cortez
- **Comité de Ética UNSL**: cei@unsl.edu.ar
- **Soporte técnico de la plataforma**: [mailing list interna]
