# ADR-001 — Multi-tenancy por Row-Level Security

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: seguridad, datos, multi-tenant

## Contexto y problema

La plataforma aloja múltiples universidades en la misma instancia. Cada universidad opera como un tenant cuyo aislamiento es condición necesaria del acuerdo institucional: bajo ninguna circunstancia los datos de una universidad pueden ser leídos, escritos ni modificados por usuarios de otra, ni siquiera por un bug de aplicación.

El aislamiento puede implementarse en tres capas distintas (aplicación, schema/base, o instancia física), con trade-offs significativos entre seguridad, operabilidad y costo.

## Drivers de la decisión

- Prevenir filtración cross-tenant incluso ante bugs de código de aplicación (defensa en profundidad).
- Operabilidad: un equipo chico no puede mantener 30 bases de datos separadas.
- Permitir queries analíticas cross-tenant para `superadmin` sin crear pipelines separados.
- Mantener posibilidad de "graduar" un tenant a base dedicada si crece o por requisitos de compliance.

## Opciones consideradas

### Opción A — Database-per-tenant
Cada universidad su propia base PostgreSQL. Aislamiento físico máximo. Operación pesada: una conexión, un backup, un schema migration por cada una.

### Opción B — Schema-per-tenant
Un schema Postgres por universidad dentro de una misma base. Aislamiento a nivel schema. Migraciones complicadas (N schemas a sincronizar). Search_path propenso a errores.

### Opción C — RLS con tenant_id en cada tabla
Una sola base, columna `tenant_id` en toda tabla de dominio, políticas RLS que filtran por `current_setting('app.current_tenant')`. Aislamiento en la capa del motor de BD.

## Decisión

**Opción C — RLS con tenant_id.**

La aplicación inyecta el `tenant_id` extraído del JWT como `SET app.current_tenant = :id` al inicio de cada transacción. Las políticas RLS de Postgres filtran automáticamente cada query.

Cada tabla con datos multi-tenant:
- Tiene columna `tenant_id UUID NOT NULL` indexada.
- Tiene política `CREATE POLICY tenant_iso ON t USING (tenant_id = current_setting('app.current_tenant')::uuid)`.
- Tiene `ALTER TABLE t FORCE ROW LEVEL SECURITY` (aplica incluso a owners).

Un helper SQL `apply_tenant_rls(table_name)` centraliza la aplicación y se llama desde cada migración. Un test en CI verifica que ninguna tabla con `tenant_id` quede sin política.

## Consecuencias

### Positivas
- Aislamiento en la capa de base, no de aplicación. Un bug de código no filtra datos.
- Una sola base para operar, backupear, migrar.
- Queries cross-tenant posibles para superadmin (bypass explícito con rol privilegiado).
- Posibilidad futura de "graduar" un tenant a base dedicada sin cambiar código de aplicación.

### Negativas
- Requiere rigor operacional en las políticas: un error en una policy afecta a todos los tenants.
- Queries complejas necesitan índices compuestos que consideren `tenant_id`.
- El rol del servicio debe ser **no-superusuario** (los superusuarios bypasean RLS por default; `FORCE ROW LEVEL SECURITY` lo corrige pero hay que verificarlo).

### Neutras
- Migración a Opción A es viable en el futuro per-tenant manteniendo la interfaz de aplicación.

## Referencias

- [PostgreSQL RLS docs](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)
- `docs/plan-detallado-fases.md` → F0 semana 2
