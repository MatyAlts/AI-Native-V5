## Why

El prompt del tutor le dice al modelo que **no tiene** informacion que el propio
sistema **si le manda**. Tres hechos verificados contra el codigo el 2026-09-28:

| Verificado | Archivo |
|---|---|
| El enunciado del TP se inyecta al contexto del LLM | `tutor_core.py:2432-2433` |
| El codigo del alumno se inyecta **numerado por linea** | `tutor_core.py:825-828` |
| `current_code` se reconstruye de `edicion_codigo` y `codigo_ejecutado` | `tutor_core.py:1306-1321` |

Y sin embargo `ai-native-prompts/prompts/tutor/v1.5.0/system.md:277-280` dice:

> "Vos no conoces el enunciado completo — el estudiante te lo va a compartir si
> es relevante."

**Consecuencia medida en produccion el 2026-09-28**: el tutor pide **tres veces**
que el alumno pegue su codigo, y **la plataforma bloquea copiar y pegar**. Es un
callejon sin salida que le estamos ordenando nosotros.

Segundo hallazgo, del mismo test: el tutor **deriva al alumno a Google**. El
prompt no menciona Google, ChatGPT ni Stack Overflow en ninguna linea
(`rg -i 'google|chatgpt|buscá|internet|stackoverflow'` → cero coincidencias), o
sea que es comportamiento **emergente**. Un comportamiento emergente solo se
corrige instruyendo explicitamente en contra.

## What Changes

Tres correcciones a `system.md`, y **nada mas**. El prompt tiene coautoria de
Ana Garis.

> **Correccion posterior a la auditoria (2026-09-28).** Este parrafo decia
> *"esto es correccion de hechos falsos, no autoria pedagogica"*, y era la
> frase que convertia la revision de Ana Garis en pendiente en vez de en
> bloqueante. El auditor mostro que excede lo verificado: C2 agrega
> directivas de conducta tutorial **con su fundamento** (*"referite a
> lineas concretas ... es mas preciso y el estudiante ve de inmediato de
> que le estas hablando"*, *"no asumas que el estudiante esta atascado"*) y
> C3 entra como bullet dentro de **"Lo que NO hace el tutor"**, que es
> seccion de metodo. Los tres bugs que encontro QA son sobre los tests; el
> **texto pedagogico no lo leyo nadie con criterio para juzgarlo**.
> La revision coautoral paso a **BLOQUEANTE** antes del deploy, y quedo
> **CERRADA el 2026-09-28**: Ana Garis leyo los cuatro textos nuevos y los
> aprobo sin cambios.

- **C1 — Seccion "Contexto del TP"**: reemplazar la afirmacion falsa por la
  verdadera (el tutor si recibe enunciado, y segun el caso codigo inicial,
  rubrica, casos de prueba, banco socratico y misconceptions). **Conservar
  intacta** la instruccion que si es correcta: *"NO supongas requisitos que el
  enunciado no establecio"*.
- **C2 — Seccion nueva sobre el codigo del estudiante**: el tutor lo ve numerado
  por linea y **debe citar lineas concretas**. Prohibicion dura de pedir que el
  alumno pegue o comparta codigo. Y la conducta correcta cuando el bloque no
  esta (el alumno todavia no escribio): invitar a escribir en el editor, no
  pedir un pegado.
- **C3 — Prohibicion de derivar afuera**: nada de Google, ChatGPT, Stack Overflow
  ni "buscá en la documentacion oficial". El camino es el material de catedra
  (bloque RAG que el prompt ya contempla) o la pregunta socratica.

Fuera de alcance, explicitamente: el metodo socratico, el tono, las reglas de
estilo, el banco de preguntas N1-N4 y las misconceptions. **No se tocan.**

## Impact

- **`ai-native-prompts/prompts/tutor/v1.6.0/system.md`**: nuevo, copia de v1.5.0
  con los tres cambios. Registro del documento: espanol rioplatense **sin
  tildes**, sin emojis, imperativo en segunda persona.
- **`ai-native-prompts/manifest.yaml`**: declara v1.6.0 como activa, con fecha y
  motivo, respetando el formato de entrada por version de las lineas 13-24.
- **`apps/tutor-service/src/tutor_service/config.py:96`**:
  `default_prompt_version` a `"v1.6.0"`. **Los dos literales se mueven juntos** —
  el tutor-service NO consulta el manifest en runtime, asi que mover uno solo
  deja a los frontends viendo una version y al CTR registrando otra.
- **CTR**: sin nuevos event types. `prompt_system_version` y
  `prompt_system_hash` de `Episode` pasan a registrar v1.6.0 en episodios nuevos;
  los viejos conservan el suyo, que es exactamente para lo que existe el campo.
- **`ai-native-prompts/prompts/tutor/v1.6.0/manifest.yaml`**: nuevo. **Entro
  fuera de las tareas** — no estaba en `tasks.md` ni en este Impact, y su
  unico evaluador fue quien lo escribio (hallazgo 4 de la auditoria). Lo
  revise el 2026-09-28: sigue el patron de v1.3.0/v1.4.0/v1.5.0 y es
  necesario, porque `test_version_activa_declara_el_hash_de_su_contenido`
  lo exige. **No es decorativo**: el governance-service verifica fail-loud
  que `sha256(system.md)` coincida con el hash declarado, asi que tocar
  una sola letra del prompt sin re-firmarlo **impide que el servicio
  levante**. Al corregir el titulo (BUG-1) hubo que re-firmarlo.
- **Sin cambios de codigo en `tutor_core.py`.** La inyeccion ya funciona bien: el
  defecto esta en lo que el prompt dice sobre ella.

## Gobernanza

Nivel **MEDIO**: contenido pedagogico de cara al alumno, con coautoria. Se
implementa con checkpoint — el diff completo de `system.md` se muestra para
revision humana antes de activar en produccion. Ana Garis lo leyo y lo aprobo
el 2026-09-28.

## Open Questions

- El bloque de codigo esta gateado por `if state.current_code and
  state.current_code.strip()` (`tutor_core.py:825`). **Cuantos episodios reales
  llegan a un primer prompt sin ninguna edicion previa?** Si es la mayoria, C2
  necesita mas desarrollo del camino "todavia no hay codigo" que del camino
  principal. No medido.
- El test en produccion del 2026-09-28 fue **un episodio, en Python**. Los tres
  defectos son reproducibles por lectura del prompt, pero su frecuencia real no
  esta medida.
