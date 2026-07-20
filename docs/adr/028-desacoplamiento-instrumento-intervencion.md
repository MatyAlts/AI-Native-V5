# ADR-028 — Desacoplamiento instrumento-intervención: condiciones control con LLM externo capturado (DIFERIDO a post-piloto-1)

- **Estado**: Aceptado (decisión: **DIFERIR**, no implementar pre-defensa ni en piloto-1)
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: arquitectura, ctr, eje-b, agenda-confirmatoria, refactor-grande
- **Cierra**: G6 del audi1.md original; G15 del audi2.md.

## Contexto y problema

La tesis 11.6 reconoce el **confound intervención-medición**: el tutor socrático y el CTR están acoplados arquitectónicamente — ambos viven en el mismo plano "pedagógico-evaluativo". Cualquier estudio cuasi-experimental sobre el efecto del tutor también está midiendo el efecto del CTR. La 20.5.1 lo declara explícitamente como agenda futura:

> *"se propone el desacoplamiento arquitectónico entre el tutor como mediador pedagógico y el CTR como instrumento de registro... habilita condiciones control donde la mediación IA ocurra externa al sistema evaluativo"*.

En código, esto significa introducir una capa "instrumento-only" del CTR que pueda registrar eventos generados por interacciones con LLMs externos (Claude estándar, ChatGPT) en condiciones control, **sin que el `tutor-service` esté en el medio**.

## Decisión

**DIFERIR a post-piloto-1**. No es viable antes de defensa ni durante el piloto-1.

### Por qué

- **Refactor masivo**: ~1500 LOC en servicios + ~700 LOC en una extensión de navegador. Total ~2200 LOC (audi2.md G15).
- **Costo del piloto alto**: requiere reclutamiento adicional, capacitación en la extensión, gestión de consentimiento ampliado para captura de interacciones con LLMs externos. **No compatible con la cohorte activa del piloto-1**.
- **Estudio confirmatorio multisite necesita protocolo distinto**: la 20.5.1 lo declara como parte del estudio confirmatorio del Capítulo 20, no como ajuste al piloto inicial.

## Criterio para revisitar (post-piloto-1)

Implementar G15 cuando se cumpla **todo** lo siguiente:

1. Piloto-1 cerrado y resultados publicados/defendidos.
2. Reclutamiento adicional acordado: estudiantes que aceptan instalar extensión de navegador que captura interacciones con LLMs externos.
3. Consentimiento ampliado aprobado por comité de ética: captura de prompts/responses con Claude estándar / ChatGPT requiere protocolo distinto al piloto-1.
4. Decisión metodológica del comité doctoral sobre el estudio confirmatorio multisite.

### Arquitectura propuesta (referencia)

audi2.md G15 detalla:

1. **Capa "ingest" del CTR independiente del tutor**: nuevo endpoint `POST /api/v1/ctr/external-event` que acepta eventos generados por una extensión de navegador o un proxy externo, con schema discriminado y validación de origen.
2. **Extensión Chrome/Firefox** que captura interacciones con LLMs externos y las traduce al formato CTR (~600-800 LOC). El componente más nuevo y desafiante.
3. **Schema `condition_control` en `episodio_abierto`**: distingue tres condiciones: `tutor_socratico_uns_native`, `llm_externo_capturado`, `sin_llm`. El árbol de clasificación lee la condición para no aplicar reglas de delegación cuando la mediación es externa pero el estudiante explícitamente declaró usarla.

## Consecuencias de DIFERIR

### Positivas

- Piloto-1 mantiene la condición experimental simple (un solo plano pedagógico-evaluativo).
- La cadena del CTR sigue siendo bit-a-bit reproducible dentro de la única condición vigente.
- Cero LOC nuevo. Ninguna extensión de navegador que mantener. Ningún consentimiento adicional que gestionar.

### Negativas

- El confound 11.6 sigue presente en el piloto-1 — declarado como limitación metodológica.
- El estudio NO puede comparar "estudiante con tutor socrático del sistema" vs "estudiante con LLM externo" — todo el piloto-1 mide el modo "uns_native".

## Coordinación con tesis

La tesis NO requiere parche. La 20.5.1 ya declara el desacoplamiento como agenda explícita. Si en el futuro se implementa, mencionar la condición de captura externa en 11.6 al revisitar el confound.

## Referencias

- audi1.md G6 (slot 028 reservado).
- audi2.md G15 — propuesta detallada.
- Tesis 11.6 — confound intervención-medición.
- Tesis 20.5.1 — agenda futura, estudio confirmatorio multisite.
- Capítulo 20 — alcance del estudio confirmatorio.
