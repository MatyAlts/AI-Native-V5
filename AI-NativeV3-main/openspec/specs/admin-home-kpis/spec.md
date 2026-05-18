# admin-home-kpis

## Purpose

Capability that owns la HomePage del `web-admin` como vista panorámica de la plataforma para roles superadmin / docente_admin. Reemplaza la lista textual "Recursos disponibles" por **3 KPI cards** alimentadas por endpoints existentes del `api-gateway`, con degradación graciosa cuando un endpoint falla. Pensada para que el comité doctoral, durante la defensa, vea métricas reales en vivo sin necesidad de explorar la app — la home actúa como dashboard de bienvenida.

Decisión deliberada: NO se incluye un KPI de `integrity_compromised` (% de episodios con la cadena CTR rota a nivel tenant) porque hoy no existe endpoint público que provea esa agregación. Mostrar un cero hardcoded sería deshonesto frente al comité; exponerlo correctamente requiere extender `analytics-service` y queda fuera de scope.

## Requirements

### Requirement: HomePage SHALL display 3 KPI cards from existing endpoints

La HomePage del `web-admin` (`apps/web-admin/src/pages/HomePage.tsx`) SHALL render exactly 3 KPI cards, cada una alimentada por un endpoint ya registrado en el ROUTE_MAP del `api-gateway`. La sección textual "Recursos disponibles" SHALL be replaced por estas cards.

Las 3 KPIs son:
- `# Universidades` — count del array devuelto por `GET /api/v1/universidades`.
- `# Comisiones activas` — count del array devuelto por `GET /api/v1/comisiones?estado=activa`.
- `# Episodios cerrados (últimos 7 días)` — derivado del response de `GET /api/v1/analytics/cohort/{any}/progression` cuando hay cohorte seleccionada; en su ausencia cae a `—`.

#### Scenario: Render exitoso con seeds activos

- **WHEN** el usuario navega a la HomePage del `web-admin` en modo dev con `seed-3-comisiones` aplicado
- **THEN** las 3 KPI cards renderizan con los counts reales (ej. Universidades=1, Comisiones=3, Episodios=N) sin estados de error visibles

#### Scenario: Endpoint devuelve 401/403/5xx — degradación graciosa

- **WHEN** uno de los 3 endpoints devuelve un status no-2xx (autenticación faltante, error de servidor, etc.)
- **THEN** la KPI card afectada SHALL render `—` como valor con un tooltip "Sin datos disponibles", el resto de las cards SHALL renderizar normalmente, y la página NO SHALL crashear

### Requirement: HomePage SHALL NOT mostrar el KPI de integrity_compromised en este pase

La HomePage NO SHALL incluir un KPI agregado de "% episodios con integrity_compromised=true a nivel tenant". Hoy no existe endpoint público que provea esa agregación; mostrar un cero hardcoded sería deshonesto frente al comité doctoral, y exponerlo correctamente requiere extender `analytics-service` (fuera de scope de este change).

#### Scenario: HomePage no muestra integrity card

- **WHEN** se inspecciona el DOM de la HomePage en cualquier estado
- **THEN** no SHALL existir card alguna con label "Integridad", "Integrity", o "% comprometidos"
