# Spec Delta

## Purpose

Controla quién participa en un estudio de codificación humana y con qué rol, por identidad asignada y no por los roles genéricos del proveedor de identidad, y cómo entra esa persona al panel docente.

## ADDED Requirements

### Requirement: Alta de estudio restringida a administradores
El sistema SHALL permitir crear un estudio de codificación solo a usuarios con rol `superadmin` o `docente_admin`, y SHALL rechazar al resto con 403. La clave SHALL cumplir el patrón de minúsculas, dígitos y guiones (3 a 41 caracteres) y SHALL NOT coincidir con un segmento reservado de las rutas del estudio.

#### Scenario: Administrador crea un estudio
- **WHEN** un usuario con rol `superadmin` envía el alta de un estudio con clave `cibse-2027`
- **THEN** el sistema crea el estudio, fija la versión vigente de la lista blanca de la traza y responde 201 con su clave

#### Scenario: Docente común intenta crear un estudio
- **WHEN** un usuario con roles `estudiante,docente` y sin rol administrativo envía el alta de un estudio
- **THEN** el sistema responde 403 y no crea nada

#### Scenario: Clave repetida
- **WHEN** un administrador envía el alta con una clave que ya existe en su tenant
- **THEN** el sistema responde 409 y el estudio existente no cambia

#### Scenario: Clave reservada o inválida
- **WHEN** un administrador envía el alta con clave `mis-membresias` o `CIbSE 2027`
- **THEN** el sistema responde 422 y no crea nada

### Requirement: Procedencia de las llamadas
Todo endpoint del estudio SHALL exigir la procedencia del gateway con el mismo mecanismo que el resto de classifier-service: con la verificación de firma encendida, un pedido sin firma válida ni token de servicio SHALL recibir 401.

#### Scenario: Firma exigida y ausente
- **WHEN** la verificación de firma del gateway está encendida y llega un pedido a un endpoint del estudio con headers de identidad sin firma
- **THEN** el sistema responde 401

### Requirement: Membresía por email con un único rol
Un investigador del estudio o un administrador SHALL poder asignar un email como `investigador` o `codificador`. El sistema SHALL rechazar con 409 asignar a un email que ya tiene una membresía activa en ese estudio, sea con el mismo rol o con otro.

#### Scenario: Investigador asigna un codificador
- **WHEN** el investigador del estudio asigna `ana@ejemplo.org` como `codificador`
- **THEN** la membresía queda activa con un alias propio del estudio y una semilla de orden

#### Scenario: Mismo email como codificador e investigador
- **WHEN** el investigador intenta asignar como `investigador` un email que ya es `codificador` activo del estudio
- **THEN** el sistema responde 409 y la membresía existente no cambia

#### Scenario: Codificador intenta asignar a otro
- **WHEN** un codificador del estudio envía una asignación de membresía
- **THEN** el sistema responde 403

#### Scenario: Re-asignación después de revocar
- **WHEN** el investigador revoca a un codificador y vuelve a asignar el mismo email
- **THEN** se crea una membresía nueva con alias y semilla nuevos y sin etiquetas, y la revocada conserva sus etiquetas y su fecha de revocación

### Requirement: Membresía atada al usuario del primer uso
La primera vez que un email asignado usa el estudio, el sistema SHALL atar la membresía al identificador de usuario firmado por el gateway. Desde ahí, un pedido con ese email y otro identificador de usuario SHALL recibir 403 y quedar registrado.

#### Scenario: Primer uso
- **WHEN** el codificador asignado entra por primera vez
- **THEN** la membresía queda atada a su identificador de usuario

#### Scenario: Primer uso concurrente con una revocación
- **WHEN** un codificador sin usar todavía (guardado de etiqueta) o un investigador sin usar todavía (alta de versión del codebook o alta de membresía) hace su primer pedido mientras el investigador revoca esa misma membresía, y la revocación llega primero
- **THEN** la revocación responde 200 y el primer uso responde 403, nunca 500

#### Scenario: Otra cuenta con el mismo email
- **WHEN** llega un pedido con el email de una membresía ya atada y otro identificador de usuario
- **THEN** el sistema responde 403, no expone datos y emite un evento de log con el identificador de la membresía

### Requirement: Acceso a endpoints del estudio solo con membresía activa
Todo endpoint del estudio, salvo el alta de estudio y la gestión de membresías por un administrador, SHALL exigir una membresía activa del usuario autenticado en ese estudio y con el rol requerido. Los roles genéricos `docente`, `estudiante`, `superadmin` o `docente_admin` SHALL NOT bastar.

#### Scenario: Cuenta logueada sin membresía
- **WHEN** un usuario con roles `estudiante,docente` sin membresía pide la lista de ítems del estudio
- **THEN** el sistema responde 403 sin revelar si el estudio existe

#### Scenario: Superadmin sin membresía
- **WHEN** un `superadmin` sin membresía pide la exportación del estudio
- **THEN** el sistema responde 403

#### Scenario: Membresía revocada
- **WHEN** el investigador revoca la membresía de un codificador y ese codificador vuelve a pedir un ítem
- **THEN** el sistema responde 403 y sus etiquetas previas se conservan

#### Scenario: Email con mayúsculas distintas
- **WHEN** la membresía se dio de alta como `Ana@Ejemplo.org` y el token trae `ana@ejemplo.org`
- **THEN** el sistema reconoce la membresía

### Requirement: Mis membresías
El sistema SHALL devolver al usuario autenticado la lista de sus membresías activas (clave, título, rol, si su codificación está cerrada), y una lista vacía si no tiene ninguna.

#### Scenario: Usuario sin membresías
- **WHEN** un usuario sin membresías consulta sus membresías
- **THEN** recibe 200 con una lista vacía

### Requirement: Entrada al panel docente para miembros sin comisiones
El panel docente SHALL dejar entrar a un usuario con membresía activa aunque no tenga comisiones. En ese modo restringido SHALL mostrar solo Entrenamiento-Recalibración y Codificación (inter-jueces), y SHALL NOT iniciar el tour docente, mostrar el onboarding docente, montar los selectores de comisión o tenant ni pedir comisiones.

#### Scenario: Codificador externo entra al panel
- **WHEN** un usuario sin comisiones y con membresía de codificador abre el panel docente
- **THEN** ve el panel con solo esas dos secciones, sin tour, sin carteles de onboarding y sin selectores

#### Scenario: Codificador externo navega a otra ruta
- **WHEN** ese usuario abre directamente la ruta de Progresión
- **THEN** el panel lo redirige a Codificación

#### Scenario: Usuario sin comisiones ni membresía
- **WHEN** un usuario sin comisiones y sin membresías abre el panel docente
- **THEN** es redirigido al panel de alumno, como hoy

### Requirement: Disponibilidad del panel ante fallas del servicio del estudio
Un docente con comisiones SHALL entrar al panel completo aunque la consulta de membresías falle; la falla SHALL afectar solo a las dos secciones del estudio. Un usuario con membresía válida SHALL entrar en modo restringido aunque la consulta de comisiones falle.

#### Scenario: Servicio del estudio caído
- **WHEN** la consulta de membresías devuelve error y el usuario tiene comisiones
- **THEN** entra al panel completo y solo las dos secciones del estudio muestran un error

#### Scenario: Consulta de comisiones caída con membresía
- **WHEN** la consulta de comisiones falla y el usuario tiene una membresía activa
- **THEN** entra en modo restringido

### Requirement: Docente sin membresía en las secciones del estudio
Un docente sin membresía SHALL ver en ambas secciones un aviso de que se usan para el estudio, sin datos del estudio, y un enlace a la vista histórica del acuerdo del piloto.

#### Scenario: Docente del piloto abre Codificación
- **WHEN** un docente con comisiones y sin membresía abre Codificación (inter-jueces)
- **THEN** ve el aviso y el enlace a `/interrater-admin`, y ninguna llamada a endpoints del estudio devuelve datos

### Requirement: Registro de cambios de membresía sin emails
El sistema SHALL registrar en el log estructurado cada alta y revocación de membresía con estudio, rol, identificador y alias de la membresía, identificador de usuario del autor y momento. El log SHALL NOT contener emails ni contenido de episodios.

#### Scenario: Alta registrada
- **WHEN** el investigador asigna un codificador
- **THEN** se emite un evento `estudio_membresia_alta` con estudio, rol, identificador y alias de la membresía y autor, y sin ningún email
