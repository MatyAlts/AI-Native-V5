## ADDED Requirements

### Requirement: Pagina de gestion BYOK en web-admin
El sistema SHALL mostrar una pagina dedicada para gestionar BYOK keys del tenant, accesible desde el sidebar en el grupo "Operacional".

#### Scenario: Listar keys existentes
- **WHEN** el admin navega a la pagina BYOK
- **THEN** el sistema muestra una tabla con las keys del tenant (fingerprint_last4, scope_type, scope_id, provider, created_at, revoked_at, last_used_at)

#### Scenario: Filtrar keys por scope
- **WHEN** el admin selecciona un scope_type en el filtro
- **THEN** la tabla muestra solo las keys con ese scope_type

#### Scenario: Estado vacio
- **WHEN** no hay keys creadas
- **THEN** se muestra un mensaje informativo con boton para crear la primera key

### Requirement: Crear BYOK key
El sistema SHALL permitir crear una key con scope_type (tenant/materia), provider, plaintext y budget mensual opcional.

#### Scenario: Crear key exitosamente
- **WHEN** el admin completa el formulario con scope_type, provider y plaintext validos
- **THEN** la key se crea, la tabla se refresca y el modal se cierra

#### Scenario: Error por BYOK_MASTER_KEY ausente
- **WHEN** el ai-gateway no tiene BYOK_MASTER_KEY configurada
- **THEN** el formulario muestra el error 500 devuelto por el backend

### Requirement: Rotar BYOK key
El sistema SHALL permitir rotar el plaintext de una key activa.

#### Scenario: Rotar key activa
- **WHEN** el admin hace click en "Rotar" de una key no revocada e ingresa el nuevo plaintext
- **THEN** la key se rota, la tabla se refresca mostrando el nuevo fingerprint_last4

#### Scenario: No se puede rotar key revocada
- **WHEN** la key esta revocada
- **THEN** el boton "Rotar" no esta disponible (disabled o ausente)

### Requirement: Revocar BYOK key
El sistema SHALL permitir revocar una key con confirmacion.

#### Scenario: Revocar con confirmacion
- **WHEN** el admin hace click en "Revocar" y confirma en el dialogo
- **THEN** la key se revoca (revoked_at no null) y la fila muestra estado revocada

### Requirement: Ver uso de BYOK key
El sistema SHALL mostrar el uso acumulado del mes para cada key.

#### Scenario: Ver uso de una key
- **WHEN** el admin hace click en "Uso" de una key
- **THEN** se muestra tokens_input, tokens_output, cost_usd y request_count del mes actual
