# Tareas

## El texto de los cambios 1 a 4 ya existe

Está en un borrador que se usó para el A/B:
`<scratchpad>/abtest/prompt-v1.10.0.md`, derivado de un archivo con **la misma
estructura de secciones** que `v1.8.0` (verificado: las cinco anclas existen y
los `## ` coinciden).

**No lo reescribas. Portalo.** El texto que corrió en el A/B es el texto que se
aprueba; si lo reformulás, lo que Ana lee deja de ser lo que se midió.

El borrador dice `v1.10.0` en el título y en su bloque de cita. **Acá la versión
es `v1.9.0`** (main llega hasta v1.8.0), así que esa parte del header se
reescribe — ver tarea 6.

## 0. Red de seguridad

- [x] Correr `uv run pytest apps/tutor-service apps/governance-service -q` y
      anotar el baseline exacto.
- [x] Si algo falla ya, **no lo arregles**: anotalo como pre-existente.

## 1. La copia limpia, en su propio commit

- [x] `ai-native-prompts/prompts/tutor/v1.9.0/system.md` = copia **byte a byte**
      de `v1.8.0/system.md`. Verificalo con `diff -q`.
- [x] Commit solo con eso: `chore(prompts): copia limpia v1.8.0 -> v1.9.0 del
      prompt del tutor`.
- [x] **Por qué importa**: así el segundo commit muestra el delta real y Ana lee
      ~200 líneas de diff en vez de un archivo nuevo de 600. Es el patrón de
      todas las versiones anteriores.

## 2. Los cuatro cambios del borrador

Portá de `prompt-v1.10.0.md`, con el mismo texto:

- [x] **Una sola pregunta por turno.** Reemplaza la línea `- Breve. Una o dos
      preguntas o sugerencias por turno.` en `## Formato de respuesta`.
- [x] **Nombrar la herramienta no es resolver.** Se agrega al final de `## Lo que
      SI se responde directo: la notacion del lenguaje`.
- [x] **Sección nueva `## Abrir el lazo`**, insertada **antes** de `## Cerrar el
      lazo: cuando el estudiante acierta` — entrada y salida del método quedan
      juntas y en orden.
- [x] **Sección nueva `## Usar el material del ejercicio`**, insertada **antes**
      de `## Uso del material de catedra (contexto RAG)`. Incluye el reemplazo
      de la media oración en `## Contexto del TP` (el `mapa privado para orientar
      tus preguntas — nunca para revelarlo`).

**Ojo con las anclas**: tres de las cinco aparecen **dos veces** en `v1.8.0`
(una en el cuerpo y otra en el índice o en las notas). Usá contexto suficiente
para que cada reemplazo sea único, y **afirmá que el reemplazo ocurrió** —un
`replace` que no matchea no falla, no hace nada, y el archivo queda sin el
cambio. Ya pasó en este repo.

## 3. El quinto cambio, que NO está en el borrador

**Crédito parcial en `## Cerrar el lazo`.** Hoy esa sección es binaria: confirma
cuando el alumno acierta. Falta el caso intermedio.

Qué tiene que decir, en dos o tres párrafos dentro de esa sección:

- Cuando el razonamiento del alumno **acierta en parte**, nombrá primero **qué
  parte está bien** —concreta, no "vas bien"— y después apuntá a la que no.
- El orden importa y no es cortesía: el alumno que sólo recibe la corrección no
  se entera de lo que resolvió bien, y es la mitad del aprendizaje que ya hizo.
- No cuenta como confirmar una conclusión sin razón: se confirma **la parte que
  él razonó**, no el resultado completo.
- Ante la duda sobre si una parte alcanza para confirmarse, confirmala. Es la
  misma regla de desempate que ya tiene la sección para el caso completo.

**Por qué se escribe en vez de dejarlo emerger:** en el A/B el borrador hizo el
crédito parcial **sin que ninguna sección lo pidiera** (ver `ab-test.md`,
pregunta 5) — probablemente por efecto lateral de la regla de una sola pregunta.
Salió una vez, en un tiro. **Un comportamiento que emerge no es un
comportamiento garantizado**, y si se quiere como propiedad del tutor, se
escribe.

## 4. El manifest de la versión

- [x] `ai-native-prompts/prompts/tutor/v1.9.0/manifest.yaml`, con el patrón de
      los anteriores: `version`, `parent_version: v1.8.0`, `bump_kind`, el
      `sha256` de `system.md`, y las `notas` explicando cada cambio con su
      porqué.
- [x] **El sha256 tiene que ser el real.** El governance-service lo verifica
      fail-loud al cargar: si no coincide, el servicio no arranca. Calculalo
      después del último cambio al archivo, no antes.
- [x] En las notas: que la **revisión coautoral de Ana Garis está ABIERTA**, y
      que v1.8.0 también. No lo dejes implícito.

## 5. Lo que NO se toca, y es deliberado

- [x] `apps/tutor-service/src/tutor_service/config.py` — sigue en `v1.8.0`.
- [x] `ai-native-prompts/manifest.yaml` (el raíz) — sigue en `v1.8.0`.

**El motivo**: la versión viaja desactivada hasta que cierre la revisión. En la
change anterior se activó una versión sin revisar **y el header del prompt
afirmaba lo contrario**, así que el prompt le mentía al modelo sobre su propio
estado de activación. No se repite.

## 6. El header del prompt dice la verdad

- [x] El bloque de cita del header de `v1.9.0` tiene que decir: versión **en
      revisión**, `config.py` y el manifest raíz **en v1.8.0**, y la revisión de
      Ana **abierta** (la de v1.8.0 también).
- [x] Nada de "activa" ni de "espera aprobación para activarse" si no es
      exactamente lo que el repo hace. Verificá `config.py` antes de escribir esa
      línea.

## 7. Los tests

- [x] `apps/tutor-service/tests/unit/test_prompt_v1_9_0_calidad_de_pregunta.py`:
      - las cinco cosas nuevas están (una sola pregunta, nombrar la herramienta,
        `## Abrir el lazo`, `## Usar el material del ejercicio`, crédito parcial);
      - **y lo que NO cambió, no cambió**: los cuatro movimientos, los nueve
        principios y el resto de "Cerrar el lazo" **byte a byte idénticos a
        v1.8.0**. Es el patrón de `test_prompt_confirmacion_al_acertar.py`, que
        comparó los tres movimientos intactos contra v1.4.0. Así el manifest
        queda respaldado por una aserción y no por la palabra de nadie.
      - el manifest declara el sha256 real del archivo.
- [x] `apps/tutor-service/tests/unit/test_header_del_prompt_no_miente.py`
      (**nuevo**): compara lo que el header del prompt **afirma** sobre
      `default_prompt_version` contra lo que `config.py` **hace**.

      **Por qué existe**: el 2026-09-30 el header de una versión decía *"config.py
      sigue apuntando a v1.8.0"* y el mismo commit lo había movido a v1.9.0. Los
      21 tests del prompt pasaron igual, porque ninguno compara esas dos cosas.
      El test tiene que fallar si alguien vuelve a desincronizarlas.

- [x] **Verificá cada test nuevo por mutación.** Rompé a propósito lo que afirma
      y mirá que se ponga rojo. Un test que pasa no prueba que discrimine: en
      este repo ya hubo una aserción que pasaba de forma vacua porque un
      `indexOf` devolvía -1.

## Informe final

Categorías tipadas, sin promover nada por comodidad: **EVIDENCIA** (comando +
salida + timestamp), **JUICIO** (quién, contra qué, confianza), **SUPUESTO** (lo
que diste por sentado y qué hiciste en lugar de verificarlo).

Para cada mutación: qué rompiste, qué test se puso rojo, y la salida.

Si algo no pudiste hacer, decilo y decí por qué. No lo dejes invisible.
