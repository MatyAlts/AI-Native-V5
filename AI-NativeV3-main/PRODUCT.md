# Product

## Register

product

## Users

**Audiencia primaria de la defensa (one-shot, 2026-Q2)**: comité doctoral UNSL — académicos senior expertos en educación universitaria y/o tecnología educativa. Auditan rigor metodológico (modelo N4, kappa, reproducibilidad bit-a-bit), defendibilidad criptográfica del CTR, y honestidad técnica del piloto.

**Audiencia primaria del producto (post-defensa, escala N facultades)**:

- **Docentes universitarios** (titulares + JTPs + auxiliares): gestionan materias, comisiones, tareas prácticas. Auditan progresión cognitiva de sus alumnos. Computan kappa con pares.
- **Estudiantes universitarios** (programación): trabajan tareas prácticas con un tutor socrático que NO les da la respuesta. Editor + Pyodide + chat.
- **Administradores institucionales** (DI / coordinación académica): bulk-import de inscripciones, gestión multi-tenant, governance de prompts, auditoría CTR, BYOK por materia.

**Audiencia secundaria operacional**: auditores externos académicos (verifican attestations Ed25519 + cadena CTR sin acceso al backend), director de informática institucional (deploys del attestation-service en infra separada).

## Product Purpose

Plataforma AI-Native con **Trazabilidad Cognitiva N4** para la formación universitaria en programación. La tesis postula que un tutor LLM sin trazabilidad rigurosa NO sirve académicamente; la solución es un sistema donde **cada interacción cognitiva queda auditable**: cadena criptográfica SHA-256 append-only, attestations Ed25519 externas, classifier reproducible bit-a-bit, 5 coherencias separadas (CT / CCD / CII), etiquetador N1-N4 derivado en lectura.

**Éxito en defensa**: el comité ve el sistema funcionando en vivo y concluye que el modelo N4 es defendible y que la implementación honra el modelo.

**Éxito post-defensa**: la plataforma se adopta primero en otra facultad de UNSL, después escala a otras universidades públicas argentinas, y eventualmente se vuelve infraestructura compartida del sistema universitario nacional.

## Brand Personality

**Tres palabras**: *riguroso · transparente · pedagógico*.

**Voice/tone**:

- Académico sin ser frío. La plataforma es producto de una tesis doctoral, no de una startup, y eso se ve.
- Honesto técnicamente. Cuando hay `insufficient_data`, lo decimos. Cuando un dato es operacionalización conservadora (CCD temporal, slope cardinal sobre ordinales), lo decimos en la UI, no solo en el ADR.
- Pedagógico explícito. El modelo N4 es la novedad de la tesis, así que la UI tiene que enseñarlo, no esconderlo. Un docente que entra por primera vez debe entender la jerarquía N1→N2→N3→N4 sin leer documentación.

**Emotional goal**:

- Para el comité: *"esto es serio"* (densidad técnica, claridad conceptual, polish que comunica gravitas, no decoración).
- Para el docente real: *"esto me ayuda a ver lo que antes no veía"* (slopes longitudinales, alertas pedagógicas, intentos adversos detectados).
- Para el alumno: *"esto me obliga a pensar, no me regala la respuesta"* (tutor socrático visible como tal, no como un chatbot que da código).

## Anti-references

**Lo que esto NO debería parecerse a, en orden de aversión**:

1. **Moodle / Blackboard / WebCT**: jerarquía pobre, navegación tipo carpetitas-dentro-de-carpetitas, formularios de los 2000s, ningún espacio cognitivo. Es la plataforma educativa que estamos superando.
2. **Coursera / Udemy / EdX marketing**: gradient-text, hero-grandes "aprende programación en 30 días", cards de cursos idénticas. Sobre-marketed, sub-rigoroso. La tesis es lo opuesto.
3. **SaaS dashboard genérico** (Stripe-clone, Linear-clone sin identidad): hero-metric template (big number + small label + supporting stats), identical card grids, navy-y-violet predeterminado. La skill `impeccable` lo banea explícitamente, respeto eso.
4. **EdTech gamificado** (Kahoot, Duolingo): colores chillones, microinteracciones constantes, badges-y-streaks. Distrae de la rigurosidad.
5. **Plataformas universitarias institucionales argentinas tipo "SIU Guaraní" / "Comdoc"**: visual de los 90s, formularios infinitos, sin polish. Cumplen función pero erosionan la sensación de seriedad técnica.

## Design Principles

1. **El modelo N4 es el producto.** La jerarquía pedagógica (N1 lectura inicial → N2 lectura activa → N3 reescritura → N4 apropiación) debe verse en cada pantalla relevante. Si el comité no entiende el modelo mirando la UI, perdimos. Color, tipografía, layout: todo subordinado a hacer visible la jerarquía.
2. **Auditabilidad visible, no oculta.** Cuando existe una cadena SHA-256 íntegra, una attestation Ed25519 firmada, un hash determinista, se muestran, no se esconden tras un botón "verificar". La confianza criptográfica viene de ver el hash, no de creer en la palabra del sistema.
3. **Densidad académica > whitespace SaaS.** Los users son docentes universitarios, no consumidores de SaaS. Toleran y necesitan densidad informativa. No tratamos al docente como si fuera un usuario casual: le mostramos toda la data que necesita en una pantalla, bien jerarquizada.
4. **Escala como ciudadana de primera.** La UI tiene que servir 1 facultad y 10 facultades sin reescritura. Si una vista solo se ve bien con 6 estudiantes (la cohorte demo) y se rompe con 200, falló. Ningún hardcode de N=fixed.
5. **Honestidad técnica explícita.** Cuando algo no funciona o tiene limitaciones declaradas (CCD ventana 2min como operacionalización conservadora; cuartiles `insufficient_data` por N<5; CII longitudinal que requiere ≥3 episodios por template), la UI lo dice. NO "coming soon", NO spinners eternos, NO mensajes vagos. La honestidad ES un asset académico.
6. **Dos capas, un toggle: docente y investigador.** Las 5 vistas analíticas del web-teacher (Progresión, Evolución del estudiante, Niveles N1-N4, Intentos adversos, Inter-rater) tienen dos modos de presentación sobre los mismos datos. **Vista docente** (default): lenguaje pedagógico plano, semáforos, sugerencias de acción, sin jerga técnica; responde "cómo le va al alumno y qué hago". **Vista investigador** (toggle): métricas completas, slopes, kappa, hashes, matrices de confusión, terminología N4; responde "qué dicen los datos formalmente". El toggle es global (header), persistido en localStorage. Ambas capas son igual de rigurosas; la diferencia es el vocabulario, no la profundidad.

## Accessibility & Inclusion

- **WCAG 2.1 AA** como piso mínimo (universidad pública argentina, ley 26.653 de Acceso a la Información Pública). Pendiente confirmar con DI UNSL si hay requisitos institucionales más estrictos.
- **Keyboard navigation completa** en flujos críticos (docente recorriendo episodios, estudiante abriendo TP). Nada de menus que requieren mouse exclusivo.
- **Color blindness safe**: pares N1-N4 nunca diferenciados solo por color (también forma + label). Pensamiento estructural, no decorativo.
- **Reduced motion respetado** (`prefers-reduced-motion`): comité doctoral con presbicia y baja tolerancia a animaciones gratuitas.
- **i18n-ready desde día 1**: el piloto es español rioplatense, pero la escala a "todas las facultades" puede incluir universidades de otras regiones. Strings extraídos, NO hardcoded en JSX.
