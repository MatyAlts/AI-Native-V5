# ADR-003 — Separación de bases lógicas por plano

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: datos, seguridad, operación

## Contexto y problema

La plataforma maneja tres dominios con requisitos muy distintos:

1. **Dominio académico**: operación transaccional clásica (universidades, comisiones, inscripciones). Escrituras puntuales, lecturas complejas con joins.
2. **CTR**: escrituras masivas append-only de eventos con cadena SHA-256; queries analíticas batch; particionado por tiempo.
3. **Identidad personal**: mapping pseudónimo → identidad real (DNI, email, nombre). Acceso altamente restringido, cambios esporádicos, altamente sensibles.

Si los tres viven en la misma base con el mismo rol, un compromiso de credenciales afecta a todo. Si viven en bases físicamente separadas, la operación se complica.

## Drivers de la decisión

- Minimizar el blast radius de un compromiso de credenciales.
- Separar cargas de trabajo (analítica batch no debe bloquear operación transaccional).
- Permitir que operaciones de mantenimiento (VACUUM, backups, réplicas) se programen independientemente.
- Mantener operabilidad con un equipo chico.

## Opciones consideradas

### Opción A — Una sola base, todo junto
Simple, pero los tres dominios se estorban mutuamente y un leak de credenciales expone todo.

### Opción B — Tres bases lógicas en un mismo cluster PostgreSQL
`academic_main`, `ctr_store`, `identity_store` como bases separadas dentro del mismo cluster. Cada una con su propio rol de Postgres.

### Opción C — Tres clusters físicamente separados
Aislamiento máximo. Costo operacional 3×. Overkill para la escala de pilotaje.

## Decisión

**Opción B — Tres bases lógicas en un mismo cluster.**

- `academic_main`: dominio académico + evaluación + analítica + contenido.
- `ctr_store`: eventos del CTR + clasificaciones + anotaciones Kappa.
- `identity_store`: mapping pseudónimo → identidad real + consentimientos.

Cada base tiene su propio rol:
- `academic_user` no puede conectarse a `ctr_store` ni `identity_store`.
- `ctr_user` solo puede escribir/leer eventos en `ctr_store`.
- `identity_user` solo accesible desde `identity-service`.

Joins cross-base no están permitidos: los servicios traen datos a la aplicación y combinan allí.

## Consecuencias

### Positivas
- Un leak de credenciales en un plano no expone los otros.
- Queries analíticas largas en `ctr_store` no bloquean ops del plano académico.
- VACUUM, backups, réplicas se configuran independientemente por carga.
- Facilita graduación futura a clusters separados si una base crece mucho.

### Negativas
- 3 conjuntos de conexiones, 3 backups, 3 migraciones.
- Joins entre planos requieren traer datos a la aplicación (penalidad de performance en queries cross-plano, mitigable con agregados materializados).
- Transacciones distribuidas no son posibles sin 2PC (no lo usamos; ver ADR-005 para saga pattern).

### Neutras
- Cada servicio se conecta solo a las bases que necesita (principio de menor privilegio).

## Referencias

- `infrastructure/docker-compose.dev.yml` (bases y roles definidos)
- `apps/*/alembic.ini` (cada servicio con su DSN propio)

## Update 2026-04-21 — identity_store deferred to F8+

`identity_store` fue creada en `infrastructure/postgres/init-dbs.sql` per esta ADR pero nunca se implementó el schema prometido (`pseudonym_mappings`, `consentimientos`, `audit_log`). En F0–F7 la pseudonimización terminó implementándose en `packages/platform-ops/src/platform_ops/privacy.py` rotando `student_pseudonym` en `academic_main.episodes` (y propagando al resto). El `identity-service` quedó como un wrapper de Keycloak sin DB (la connection SQLAlchemy quedó comentada en `main.py`); la identidad real (DNI, email, nombre) vive en Keycloak vía federación LDAP read-only del directorio institucional.

En sesión 2026-04-21 se decidió (Option A del BUG-25) **remover `identity_store` de `init-dbs.sql`** para eliminar el artefacto muerto y el drift entre ADR y código real que estaba confundiendo code review y onboarding. El rol `identity_user` también se removió porque solo apuntaba a esa base. Si en F8+ aparece el requisito de un mapping persistente pseudónimo↔identidad o un audit log de rotaciones de pseudónimos, esta ADR debe revisarse y un nuevo ADR debe **superseder** este addendum (no editar la decisión original — refleja lo que era cierto al momento de la separación de planos).
