## ADDED Requirements

### Requirement: Descargas diferenciadas de borrador y de lo entregado
El alumno SHALL poder distinguir, por el rótulo del botón, si descarga su **borrador** (el código vigente del episodio del ejercicio) o **lo entregado** (el código sellado en la última entrega). Los rótulos SHALL ser "Descargar borrador (.ext)" y "Descargar lo entregado (.ext)", con `.ext` igual a `.java` para Java y `.py` en cualquier otro caso. Ningún botón de descarga del alumno SHALL decir sólo "Descargar (.ext)".

#### Scenario: Rótulo del borrador en la pantalla de la TP
- **WHEN** el alumno ve un ejercicio completado de una entrega en `draft`
- **THEN** el botón de descarga de ese ejercicio dice "Descargar borrador (.py)"
- **AND** no hay botón "Descargar lo entregado" (la TP nunca se entregó)

#### Scenario: Rótulo en la vista de trabajo corregido
- **WHEN** el alumno abre un trabajo corregido desde Mis notas
- **THEN** cada botón de descarga dice "Descargar lo entregado (.py)" o "(.java)" según el lenguaje del artefacto sellado

### Requirement: La pantalla de la TP ofrece lo entregado
La pantalla de la TP SHALL ofrecer "Descargar lo entregado" por ejercicio cuando la entrega fue entregada al menos una vez y no es `legacy`, en los estados `submitted`, `graded` y `returned`. El archivo SHALL contener exactamente el código sellado de ese ejercicio en la última entrega, con la misma forma que la descarga de la vista de trabajo corregido. La descarga SHALL ser de sólo lectura: no abre, cierra ni reanuda episodios y no emite eventos.

#### Scenario: TP devuelta
- **WHEN** el docente devolvió la TP y los ejercicios quedaron sin completar
- **THEN** cada ejercicio con código sellado muestra "Descargar lo entregado"
- **AND** el archivo descargado es el código de la entrega anterior, no lo que el alumno escribió después

#### Scenario: TP calificada
- **WHEN** la entrega está `graded`
- **THEN** cada ejercicio muestra "Descargar lo entregado" y no muestra "Descargar borrador"

#### Scenario: Ejercicio sin código sellado
- **WHEN** el alumno aprieta "Descargar lo entregado" y la entrega no tiene artefacto para ese ejercicio
- **THEN** no se descarga nada y se muestra un aviso con palabras, sin romper el resto de la pantalla

#### Scenario: Error de red
- **WHEN** falla la lectura del código entregado
- **THEN** se muestra el aviso de error en la pantalla de la TP y los demás botones siguen andando

### Requirement: El borrador sólo se ofrece cuando difiere de lo entregado
"Descargar borrador" SHALL mostrarse sólo en ejercicios completados de una entrega editable (`draft` o `returned`), o en ejercicios completados de una entrega `legacy`. En una entrega `submitted` o `graded` no `legacy` SHALL ofrecerse sólo "Descargar lo entregado".

#### Scenario: Entrega legacy calificada
- **WHEN** la entrega es `legacy` y está `graded`
- **THEN** el ejercicio completado muestra "Descargar borrador" (única fuente de código disponible) y no muestra "Descargar lo entregado"

#### Scenario: Re-entrega en curso
- **WHEN** la entrega está `returned` y el alumno ya volvió a completar el ejercicio 2
- **THEN** el ejercicio 2 muestra los dos botones, "Descargar borrador" y "Descargar lo entregado"
