## ADDED Requirements

### Requirement: Identificación de la pasiva por sobreuso

El sistema SHALL considerar "pasiva por sobreuso" a toda clasificación con `appropriation = "delegacion_pasiva"`, `features.subgrupo.key = "dependiente_sobreuso"`, **sin** `features.revision_humana` y **sin** `features.regimen_llm.estado = "ok"`. Ninguna otra combinación cuenta como tal. La regla vive solo en `platform_ops.pasiva_por_sobreuso`; los datasources y la API devuelven el booleano `pasiva_por_sobreuso` ya calculado y los frontends no la recalculan. La etiqueta persistida no se modifica.

#### Scenario: Pasiva originada por la regla de sobreuso
- **WHEN** una clasificación tiene `appropriation = "delegacion_pasiva"` y subgrupo `dependiente_sobreuso`
- **THEN** se trata como pasiva por sobreuso

#### Scenario: Pasiva por delegación real
- **WHEN** una clasificación tiene `appropriation = "delegacion_pasiva"` y subgrupo `dependiente_delegador`
- **THEN** se sigue tratando como delegación pasiva, igual que hoy

#### Scenario: Subgrupo de sobreuso con etiqueta distinta de pasiva
- **WHEN** una clasificación tiene subgrupo `dependiente_sobreuso` pero `appropriation` distinto de `delegacion_pasiva` (por ejemplo, una revisión humana la cambió)
- **THEN** NO se trata como pasiva por sobreuso y se muestra según su `appropriation`

#### Scenario: Pasiva confirmada por un docente
- **WHEN** una clasificación tiene `appropriation = "delegacion_pasiva"`, subgrupo `dependiente_sobreuso` y `features.revision_humana` (un docente revisó y confirmó la pasiva)
- **THEN** NO se trata como pasiva por sobreuso: se muestra como delegación y cuenta en el progreso

#### Scenario: Pasiva decidida por el juez del eje fino
- **WHEN** una clasificación tiene `appropriation = "delegacion_pasiva"`, subgrupo `dependiente_sobreuso` y `features.regimen_llm.estado = "ok"`
- **THEN** NO se trata como pasiva por sobreuso

#### Scenario: Backend viejo sin el booleano
- **WHEN** un frontend recibe una clasificación o un punto sin el campo `pasiva_por_sobreuso`
- **THEN** lo trata como `false` y lo muestra como delegación, igual que antes del cambio

#### Scenario: Clasificación vieja sin subgrupo
- **WHEN** una clasificación con `appropriation = "delegacion_pasiva"` no tiene `features.subgrupo`
- **THEN** se trata como delegación pasiva, igual que hoy

### Requirement: Presentación al docente como uso intensivo del tutor

Las vistas del docente SHALL mostrar una pasiva por sobreuso como "Uso intensivo del tutor", con estilo de alerta (no de peligro), y explicar que es una alerta de frecuencia de consultas y no un régimen de apropiación. Esto aplica al veredicto del episodio, al resumen por subgrupo y a los puntos de las vistas de progresión y trayectoria.

#### Scenario: Veredicto del episodio
- **WHEN** el docente abre un episodio con pasiva por sobreuso
- **THEN** el chip principal dice "Uso intensivo del tutor" y NO dice "Delegacion pasiva"

#### Scenario: Punto en la trayectoria
- **WHEN** la trayectoria de un alumno incluye un episodio con pasiva por sobreuso
- **THEN** el punto se dibuja con el color neutro de alerta y su leyenda dice "Uso intensivo del tutor"

### Requirement: Feedback al alumno sin atribuir delegación

El feedback del episodio que ve el alumno SHALL, ante una pasiva por sobreuso, hablar del ritmo de consultas al tutor y NO afirmar que el tutor hizo el trabajo cognitivo.

#### Scenario: Alumno con pasiva por sobreuso
- **WHEN** el alumno ve el feedback de un episodio con pasiva por sobreuso
- **THEN** el mensaje sugiere intentar un paso propio entre consultas y no contiene la afirmación de que el trabajo lo hizo el tutor

### Requirement: Exclusión de la escala de progreso

Los cálculos de progreso (progresión de cohorte, tercios, máximo alcanzado, pendiente longitudinal por template, por unidad y general, cuartiles y alertas que dependen de esas pendientes) SHALL excluir las pasivas por sobreuso de la escala ordinal, igual que excluyen `autonomo` y `sin_clasificar`. El episodio sigue figurando en la lista de puntos.

#### Scenario: Alumno con tramo de sobreuso
- **WHEN** un alumno tiene, en orden, reflexiva, reflexiva, pasiva por sobreuso, pasiva por sobreuso, reflexiva
- **THEN** su escala ordinal se calcula sobre las tres reflexivas y no aparece como "empeorando"

#### Scenario: Delegación real sigue contando
- **WHEN** un alumno tiene pasivas con subgrupo `dependiente_delegador`
- **THEN** esas pasivas siguen valiendo 0 en la escala ordinal

#### Scenario: Exportación académica intacta
- **WHEN** se genera la exportación académica
- **THEN** las etiquetas exportadas son las mismas que antes del cambio
