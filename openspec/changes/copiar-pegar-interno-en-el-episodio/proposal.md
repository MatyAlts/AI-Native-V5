## Why

Hoy **copiar y pegar esta bloqueado entero** dentro del episodio. Eso resuelve
el problema real —que el alumno pegue codigo de ChatGPT— pero cobra un peaje
que nadie decidio: el alumno tampoco puede copiar **de la consigna al editor**.

Un nombre de variable que el enunciado exige literal, una cadena de prueba, un
formato de salida: todo eso hay que tipearlo a mano, y un error de tipeo se
lleva un caso de prueba. No es ergonomia: es ruido en la medicion.

Y hay un segundo costo, que salio probando el tutor contra produccion el
2026-09-30: el tutor **recomendo llevarse el codigo a un editor local** para no
perderlo. Con el bloqueo activo ese consejo no se puede ejecutar. El prompt
v1.8.0 lo corrige diciendo el hecho ("copiar y pegar esta bloqueado"), asi que
**si este change entra, esa linea del prompt pasa a ser falsa** y hay que
moverla en el mismo PR.

## What Changes

### La idea

El portapapeles **no guarda procedencia**: no hay forma de saber de donde vino
un texto. Pero si hay forma de saber otra cosa, que alcanza:

> **¿Eso lo puse yo ahi?**

Un portapapeles interno en memoria. Al copiar o cortar dentro de la pagina se
guarda `{texto, origen}`. Al pegar se compara el contenido del clipboard contra
lo guardado: **coincide → se permite; no coincide → se bloquea, como hoy.**

Copiaste de la consigna y pegas en el editor: coincide, pasa. Copiaste de
ChatGPT: no coincide, se bloquea. Copiaste algo interno y despues algo externo:
el interno queda viejo, la comparacion falla, y bloquea bien.

### Que se permite y que no

| Origen | Decision | Por que |
|---|---|---|
| **Consigna → editor** | PERMITIR | Es el caso que motiva el change |
| **Editor → editor** (codigo propio) | PERMITIR | Reordenar lo suyo no es tomar nada de nadie |
| **Panel del tutor → editor** | **BLOQUEAR** | **ADR-026.** Ver abajo |
| Salida / pruebas → editor | BLOQUEAR | Sin caso de uso; se puede revisitar |
| Externo | BLOQUEAR | Es el objetivo original, no se toca |

### 🔴 El panel del tutor queda AFUERA, y no es una omision

**ADR-026** (2026-04-29, deciders: Alberto Cortez) difirio a post-defensa el
boton "Insertar codigo del tutor", con este argumento:

> *Confound intervencion-medicion (tesis 11.6): el boton cambia la economia de
> la interaccion — ofrece un canal "barato" para tomar codigo del tutor, lo que
> puede inducir delegacion pasiva como variable confound. **No es un cambio
> neutro de instrumentacion; es una modificacion del entorno experimental.**
> Mid-cohort introduce sesgo de tratamiento.*

Permitir `Ctrl+C` sobre el panel del tutor **es el mismo canal barato por otra
puerta**, asi que cae bajo el mismo ADR. Sus criterios para revisitarlo son
cohorte nueva, decision academica de estudiarlo como variable, o post-defensa
con acuerdo del comite. Ninguno se cumple hoy.

**Consecuencia directa**: `copied_from_tutor` sigue sin emitirse. Este change
NO lo destraba, y eso es deliberado.

### El contrato del CTR

Se agrega **un** valor a `EdicionCodigoPayload.origin`:

```python
Literal["student_typed", "copied_from_tutor", "pasted_external",
        "snippet_expanded", "pasted_internal"]   # <- nuevo
```

**`pasted_internal` NO entra a `_EDICION_CODIGO_N4_ORIGINS`**
(`event_labeler.py:123`). Copiar el nombre de una variable de la consigna no es
apropiacion reflexiva; meterlo al override N4 inflaria la etiqueta mas
informativa de la tesis con un gesto mecanico.

`pasted_external` sigue siendo **inalcanzable desde este editor**, igual que
hoy: el pegado externo se prohibe y en su lugar sale `pega_intentada`. La rama
se conserva por la misma razon que ya estaba escrita en `CodeEditor.tsx:517`.

### El prompt del tutor

v1.8.0 dice, textual: *"en esta plataforma **copiar y pegar esta bloqueado**"*.
Con este change eso deja de ser cierto en general. **v1.9.0** lo ajusta: el
bloqueo pasa a ser *hacia afuera*, y se puede copiar dentro del episodio. El
consejo de "llevatelo a VS Code" sigue prohibido, ahora por el argumento
pedagogico y no por imposibilidad tecnica.

## Impact

- **`apps/web-student/src/components/CodeEditor.tsx`** — el nucleo. Hoy bloquea
  por dos vias independientes (`addCommand(Ctrl+V)` y un listener DOM en fase de
  CAPTURA). Las dos pasan de **cortar** a **validar**.
- **`packages/contracts/.../ctr/events.py`** — un valor mas en el Literal.
- **`apps/classifier-service/.../event_labeler.py`** — documentar por que
  `pasted_internal` NO entra al override N4. Sin cambio de comportamiento: un
  valor que no esta en el set cae al default.
- **`ai-native-prompts/prompts/tutor/v1.9.0/`** — el prompt, con sus cinco
  literales de version.
- El panel de la **consigna** necesita ser copiable (hoy puede tener
  `user-select: none` o un handler que lo impida — verificar).

## Gobernanza

Nivel **MEDIO-ALTO**. Toca el contrato del CTR, que alimenta la tesis, y cambia
lo que el alumno puede hacer en pantalla. Se implementa con checkpoint: el diff
se revisa antes de mergear, y la parte del prompt espera a Ana Garis como las
tres anteriores.

## Lo que NO se hace

- **El boton "Insertar codigo del tutor"** y `copied_from_tutor`: ADR-026.
- **Levantar el bloqueo externo.** El objetivo del change es habilitar lo
  interno, no debilitar lo otro.
- **Convertirlo en barrera de seguridad.** No lo es y nunca lo fue: las
  devtools lo saltean en diez segundos, igual que al bloqueo de hoy. Lo que
  sostiene la tesis no es que el alumno no pueda, es que **todo queda
  registrado con su procedencia en la cadena**. Cualquier redaccion que
  afirme lo primero es falsa.

## Open Questions

- **Normalizacion al comparar.** Monaco puede normalizar fin de linea (CRLF vs
  LF) entre el copiado y el pegado. Si la comparacion es exacta byte a byte,
  un copiado multilinea legitimo podria fallar. Hay que decidir —y testear— si
  se compara crudo o normalizado, y dejar escrito el porque.
- **El panel de la consigna es copiable hoy?** No verificado.
