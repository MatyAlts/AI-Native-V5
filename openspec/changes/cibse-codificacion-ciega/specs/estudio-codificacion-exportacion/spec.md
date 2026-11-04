# Spec Delta

## Purpose

Entrega al investigador del estudio los datos de codificación y de entrenamiento en formatos aptos para análisis, con trazabilidad de versión y orden, sin exponerlos a codificadores.

## ADDED Requirements

### Requirement: Exportación restringida al investigador
El sistema SHALL permitir exportar etiquetas, respuestas de entrenamiento e historial del estudio solo a miembros activos con rol `investigador`. Codificadores, docentes y administradores sin esa membresía SHALL recibir 403.

#### Scenario: Codificador pide exportar
- **WHEN** un codificador pide la exportación de etiquetas
- **THEN** recibe 403

#### Scenario: Investigador exporta en JSON
- **WHEN** el investigador pide las etiquetas en JSON
- **THEN** recibe una entrada por codificador e ítem con `episode_id`, identificador opaco, alias y membresía del codificador, semilla, posición en su orden, versión y sha256 del codebook, versión de la traza, valor y cita de cada dimensión del esquema, `regimen` (el persistido: de la regla o exento), `regimen_regla` siempre que sea calculable, `regimen_propuesto`, sha256 original y mostrado de cada enunciado y sha256 del archivo del que se cargó, desacuerdo con la regla derivado, marca de frontera, confianza, notas, `created_at`, `updated_at`, fecha de cierre y de revocación

### Requirement: Formatos CSV y JSON equivalentes
El sistema SHALL ofrecer cada contenido en CSV y en JSON con las mismas filas y valores. En CSV, toda celda de texto que empiece con `=`, `+`, `-`, `@`, tabulador o retorno de carro SHALL exportarse prefijada con una comilla simple.

#### Scenario: Misma información en ambos formatos
- **WHEN** el investigador exporta etiquetas en CSV y en JSON
- **THEN** ambos tienen la misma cantidad de filas y los mismos valores por fila

#### Scenario: Nota que parece fórmula
- **WHEN** una nota empieza con `=HYPERLINK(`
- **THEN** en el CSV la celda empieza con `'=HYPERLINK(`

#### Scenario: Estudio sin etiquetas
- **WHEN** el investigador exporta un estudio sin etiquetas
- **THEN** recibe un CSV solo con encabezado o un JSON con lista vacía

### Requirement: Sin datos personales de codificadores ni contenido de episodios
La exportación SHALL NOT incluir emails de codificadores ni contenido de episodios (mensajes, código, salidas).

#### Scenario: Revisión de columnas
- **WHEN** se inspecciona la exportación de etiquetas
- **THEN** no hay columna de email ni de contenido de episodio

### Requirement: Registro de cada exportación
Cada exportación SHALL registrarse en el log estructurado con estudio, contenido, formato, identificador de usuario del autor, cantidad de filas y momento, sin datos exportados ni emails.

#### Scenario: Descarga registrada
- **WHEN** el investigador exporta el historial en CSV
- **THEN** se emite un evento `estudio_exportacion` con esos campos, sin valores de etiquetas y sin emails
