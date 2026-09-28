# Tabla 3.11 — Tabla de decisión de la etapa semántica

Transcripta literal de `Propuesta_Tesis_Doctoral_MTAC_revisada_5.docx` (25/09/2026),
tabla #19 del documento. **Es la fuente normativa de este change.** Son SEIS casos, y
cada uno tiene su estado terminal declarado.

Criterio reflexivo: **V ∧ (E ∨ J) ∧ A**

| # | Valores de las dimensiones | Resultado de V ∧ (E ∨ J) ∧ A | Evidencia exigida | Salida de la regla determinista |
|---|---|---|---|---|
| 1 | V, A y al menos una de E o J presentes. | Verdadero. | Cita literal verificada del estudiante para V, para A y para la dimensión (E o J) que completa la fórmula; si E y J están presentes, basta con que una de ellas tenga cita verificada. | **Apropiación reflexiva**; automática por el juez. |
| 2 | Misma configuración de valores, pero alguna dimensión portadora sin cita verificada y sin combinación portadora alternativa completa. | Verdadero, **no auditable**. | No satisfecha. | **Derivado a revisión humana por evidencia insuficiente**; no produce etiqueta automática. |
| 3 | V ausente, o A ausente, o E y J ambas ausentes, cualquiera sea el valor de las restantes. | Falso. | Justificación referida al episodio para cada ausencia que hace falsa la fórmula; sin cita literal. | **Apropiación superficial**; automática por el juez. Las justificaciones de ausencia se auditan en la fracción aleatoria. |
| 4 | Ninguna dimensión hace falsa la fórmula y alguna dimensión necesaria es **no evaluable** (por ejemplo, V no evaluable; o V y A presentes con E no evaluable y J ausente). | **Indeterminado**. | No aplicable. | **Abstención por traza insuficiente**; derivado a revisión. |
| 5 | Alguna dimensión no registrada, valor fuera del dominio, o **cita portadora no localizable o atribuida a un turno del tutor**. | No evaluable por formato. | No aplicable. | **Salida inválida**; derivado a revisión. |
| 6 | Régimen propuesto por el modelo distinto del que la tabla deriva de los valores registrados. | Cualquiera. | No aplicable. | **Conflicto de reglas**; derivado a revisión. |

> Nota de la tesis al pie de la tabla: «Las etiquetas automáticas de esta tabla se limitan
> al eje fino; la delegación pasiva la decide el componente transparente.»

## Lo que esta tabla confirma y lo que exige

**El caso 3 fija la semántica trivaluada, y es Kleene FUERTE.** «V ausente, o A ausente,
o E y J ambas ausentes, **cualquiera sea el valor de las restantes**» → falso → superficial.
Es decir: una dimensión que hace falsa la fórmula gana sobre cualquier `no_evaluable` en
las demás. El desconocido se propaga **solo cuando cambia el resultado** (caso 4). La
decisión D1 del design coincide con la tesis.

**El caso 5 es el puente con el pendiente B4.** La tesis ya especifica que una
**cita atribuida a un turno del tutor** debe producir `salida_invalida`. La auditoría de
citas del 25/09/2026 encontró 2 citas del tutor atribuidas al estudiante (episodio
`339ee925`) y 9 citas no localizables en ningún turno, sobre 224 citas emitidas. Hoy
**ninguna** produce salida inválida: pasan de largo. El caso 5 no es una mejora deseable,
es una regla escrita que no está implementada.

**El caso 2 cuantifica lo que falta.** Las dimensiones portadoras exigen cita verificada.
La misma auditoría midió que el esquema exige 380 citas sobre 95 episodios y se emitieron
224 (59%), con `justificacion` cubierta en solo 36% de los episodios. Bajo el caso 2, una
fracción grande del corpus debería estar `derivado a revisión por evidencia insuficiente`.

---

# Tabla B.2 — Definiciones operativas de los valores de cada dimensión

Tabla #71 del documento. Es la que define qué significa cada valor, y por lo tanto qué
tiene que emitir el prompt del juez.

| Dimensión | Presente (exige cita cuando es portadora) | Ausente (exige justificación, sin cita) | No evaluable |
|---|---|---|---|
| **Verbalización (V)** | El estudiante formula con sus propias palabras una hipótesis, una explicación o un plan sobre el problema o el código, más allá de reproducir o parafrasear la propuesta del asistente. | La traza contiene turnos suficientes del estudiante y ninguno expresa razonamiento propio: solo pedidos de solución, pegado de errores o aceptaciones. | Turnos del estudiante escasos o truncados, episodio interrumpido o actividad fuera del sistema que impide juzgar. |
| **Verificación (E)** | El estudiante ejecuta, prueba, compara o comprueba una propuesta y refiere el resultado en la interacción o en los eventos de código. | Acepta propuestas sin ninguna acción ni argumento de contraste registrado, en un episodio con eventos suficientes. | Eventos de ejecución o prueba no registrados, o registro incompleto. |
| **Justificación (J)** | El estudiante explica por qué una decisión propia es correcta o preferible, con un fundamento causal, argumentado o estratégico. | Las decisiones se adoptan sin fundamento expresado, en una traza suficiente para observarlo. | La traza no contiene decisiones propias observables o está truncada. |
| **Autonomía (A)** | El estudiante transforma, cuestiona o pone a prueba la propuesta del asistente en lugar de tratarla como oráculo. | Incorpora las propuestas sin modificación ni cuestionamiento, con evidencia positiva de aceptación (por ejemplo, pegado literal seguido de entrega). | No hay propuestas del asistente sobre las que observar la conducta, o el registro está incompleto. |

> **Ojo con Autonomía**: la tesis SÍ admite `no evaluable` para A («no hay propuestas del
> asistente sobre las que observar la conducta»). El design.md había supuesto en su
> decisión D4 que `autonomia` podía quedar booleana porque el juez solo corre sobre
> subgrupos con `prompts > 0`. La tabla B.2 lo contradice: que haya prompts del estudiante
> no garantiza que haya **propuestas del asistente** que cuestionar. D4 hay que revisarla.

## Estados terminales que la tabla exige (Tabla 3.13 de la tesis)

De los seis casos salen estos estados, y son más que los cuatro que el código tiene hoy
(`ok`, `inconsistente`, `baja_confianza`, `error_parseo`):

- clasificación automática por el juez (casos 1 y 3)
- **derivado por evidencia insuficiente** (caso 2) — no existe en el código
- **abstención por traza insuficiente** (caso 4) — no existe en el código
- **salida inválida** (caso 5) — parcialmente cubierto por `error_parseo`
- **conflicto de reglas** (caso 6) — parcialmente cubierto por `inconsistente`
