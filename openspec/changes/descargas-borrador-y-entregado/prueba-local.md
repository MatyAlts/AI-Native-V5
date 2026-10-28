# Prueba local reproducible (pendiente)

No se corrio: el agente que implemento no levanta el stack. Lo corre Neyén.

1. **Levantar el stack** desde la raíz de `rama desarrollo/` en Git Bash:
   - `DEV_TRUST_HEADERS=true PROMPTS_REPO_PATH="$(cygpath -w "$(pwd)/ai-native-prompts")" bash scripts/dev-start-all.sh`
   - en otra terminal: `pnpm turbo dev`
   - web-student en http://localhost:5175, web-teacher en http://localhost:5174. Alumno de dev `e19354fb-c05a-4535-a0bf-a7d3ea09692d`, tenant `aaaa…`. Si el Postgres 18 de Windows está prendido, frenarlo (pisa el 5432).
2. En web-teacher, una TP de 2 ejercicios en Python publicada en la comisión del alumno.
3. **Borrador**: como alumno, ejercicio 1 → `print("v1")` → finalizar. En la pantalla de la TP el ejercicio 1 muestra **sólo** "Descargar borrador (.py)". Bajarlo: dice `print("v1")`.
4. Completar el 2 (`print("dos")`) y "Entregar TP". Ahora cada ejercicio muestra **sólo** "Descargar lo entregado (.py)". Bajarlo: `print("v1")`.
5. En web-teacher: calificar y devolver (o "Pedir corrección" si ya está aplicado ese change). En web-student, con la TP devuelta: cada ejercicio muestra "Descargar lo entregado" aunque esté sin completar.
6. Abrir el ejercicio 1, cambiar a `print("v2")`, finalizar **sin entregar**. El ejercicio 1 muestra **los dos** botones: "borrador" baja `print("v2")`, "lo entregado" baja `print("v1")`.
7. **Mis notas** → el trabajo corregido: los botones dicen "Descargar lo entregado (.py)" y bajan `print("v1")`.
8. **CTR sin cambios**: antes del paso 3 y después del 7, en `ctr_store`: `SELECT event_type, count(*) FROM events GROUP BY 1 ORDER BY 1;` → ningún `event_type` nuevo; las descargas solas (repetir 6–7 sin editar) no suben ningún conteo.
