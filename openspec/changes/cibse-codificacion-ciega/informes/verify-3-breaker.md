# verify-3-breaker: rompedor, intento 3 (último del gate verify)

- Rol: breaker. Ejecutor: subagente nativo Claude Code (familia Anthropic, la misma que todos los roles previos). Sin independencia por proveedor.
- Fecha: 04/11/2026, 14:48 a 14:53 (-03:00). Nivel CRITICAL.
- Revisión atacada: árbol sobre HEAD `b32e621`, sin commits. Huella (`scratchpad/hash-arbol.sh`, excluye la carpeta del change):
  - 14:48:15 `diff_HEAD_sha256=d4e664d02f90ea5a14ccfc3187389638300fd01f9b78feaa6646ad4b2ba84216 untracked_n=59 untracked_list_sha256=62de33cf8563b29fe392225de3bb654accf985607ebd36b2d805da1c395745be arbol=50fadc6b8a034547`
  - 14:52:06 idéntica. **La huella no cambió.** Los tests temporales se copiaron, se corrieron y se borraron (`git status` sin restos); los originales están en `scratchpad/breaker/`.
- Lecciones L-NNN: no existen. Ruta leída: ninguna.
- No edité producción ni corrí mutantes. Ataqué primero y leí `apply-3-constructor-F.md` al final. No leí el grupo 15 de `tasks.md`.

## Veredicto

**LIMPIO**: N1, N2 y O1 están corregidas y no reproduje ninguna falla nueva. F1 a F7 siguen corregidas. Las observaciones y suposiciones que quedan no son defectos contra la spec.

| # | Estado |
|---|---|
| N1, deadlock entre primer uso y revocación | **Corregida**: 0 deadlocks y 0 respuestas 500 en 380 rondas concurrentes |
| N2, forma del CTR | **Corregida**: los cuerpos raros dan 502; 0 falsos rechazos en 16 variantes válidas y en 113 episodios reales |
| O1, ancla incompleta | **Corregida**: el alta y la edición avisan con `faltantes`; congelar rechaza con 422; un exento con notas pasa |
| F1 a F7 | Siguen corregidas (reejecuté mis reproducciones) |

## EVIDENCIA

Entorno: `cibse-test-pg` (`:55432`), `cibse-smoke-pg` (`:55433`), `cibse-smoke-redis` (`:6379`). No toqué `seguridad_jwt_db` (5432), producción ni EasyPanel.

Conteo propio: **383 tests**, más 2 skips del smoke, el barrido de 113 episodios reales y 380 rondas de concurrencia.

| Hora | Qué | Resultado |
|---|---|---|
| 14:49:18 | Unit: `test_zz_breaker3_unit.py` (16 variantes válidas del CTR), más mis unitarias de verify-1 y verify-2 | `66 passed`. Cuerpos raros: `sin_ts`, `ts_basura`, `ts_numero`, `problema_no_uuid` y `ejercicio_basura` ahora dan `CTRNoDisponibleError` (502), lo mismo que vacío, HTML, `null`, `[]`, `events` dict o str, payload lista y `seq` str. Se aceptan sin error aguas abajo (`motivo_rechazo`, `evidencia_fija`, `filtrar_traza`): `ts` con `Z`, con `+00:00`, con microsegundos `.123456Z` y `.000001+00:00`, con `-03:00` y con fracción de un dígito; `lectura_enunciado` sin `duration_seconds`, con float o con payload `null`; `ejercicio_id` ausente, `null` o en mayúsculas; `problema_id` en mayúsculas; sin `integrity_compromised`; `paused` abandonado; tipo de evento futuro con payload anidado. Fuzz: 1188 esquemas y 209 pedidos, 0 excepciones |
| 14:49:51 | Integración: `test_zz_breaker3_db.py`, más `test_zz_breaker2_db.py`, `test_zz_breaker2_s1_db.py` y mi archivo de verify-1 | sin 500. Los 3 rojos son los mismos **oráculos obsoletos de verify-1** que ya expliqué en verify-2 (F1 x2 congelan con 422; F4 da 409 con `detail` string), no defectos |
| 14:52:15 | `test_estudio_concurrencia_db.py` (la barrera del constructor), 5 veces seguidas | `6 passed` x5; `deadlock detected` en el log de Postgres: 0 |
| 14:50:30 | `cibse-smoke-pg`: `alembic downgrade 20260906_0006` y `upgrade head` | `20261104_0007`, 6 triggers `sin_truncate` |
| 14:51:03 | `make test-smoke` (stack de `scratchpad/smoke/start.sh`) | **`100 passed, 2 skipped, 20 deselected`**, exit 0. Log: `scratchpad/breaker/smoke-verify3.log` |
| 14:51:47 | Barrido: los 113 episodios de `ctr_store` leídos con `CTRLector` contra el ctr-service real (`:8007`) | `aceptado: 113`, falsos rechazos 0, `motivo None: 109`, `no terminado: 4`, sin excepciones aguas abajo. Formas de `ts`: las 544 con `Z` y microsegundos. El seed no tiene `lectura_enunciado`: ese caso lo cubre la unitaria |
| 14:52:02 | vitest `AdministracionEstudioView`, `CodificacionEstudioView`, `estudioApi`, `mensajesError` | `4 files, 102 passed` |
| 14:52 | limpieza | stack detenido; maté 2 contenedores `eclipse-temurin` que dejó el smoke (mismo síntoma que reportó E) |

### N1: orden de locks y ciclos

Revisé por lectura todos los caminos. Los que bloquean el estudio (`_estudio_para_gestionar`, `investigador_con_estudio_bloqueado`, `bloquear_para_codificar`) lo toman ahora en `require_membresia`, **antes** de leer y atar la membresía. Después, según el camino: versión `FOR UPDATE`, enunciado `FOR UPDATE` o membresía `FOR UPDATE`. Los caminos que no bloquean el estudio (traza, ítems, `mi-etiqueta` GET, entrenamiento, exportación, progreso, lecturas y `mis-membresias`) solo atan la membresía y no toman después ningún lock que choque con la revocación. Los `INSERT` con FK toman `KEY SHARE` sobre membresía, ancla, versión o ítem, nunca sobre una fila que la revocación tenga y que espere a la vez. No encontré ningún ciclo.

40 rondas en paralelo con `asyncio.gather`, cada una con una membresía nueva y sin atar:

```
guardar_vs_revocar(inv)      {(200, 200): 37, (403, 200): 3}
guardar_vs_revocar(admin)    {(200, 200): 39, (403, 200): 1}
cerrar_vs_revocar            {(422, 200): 40}
items_vs_revocar             {(200, 200): 40}
traza_vs_revocar             {(403, 200): 6, (200, 200): 34}
mis_membresias_vs_revocar    {(200, 200): 40}
inv_crea_version_vs_revocar  {(201, 200): 38, (403, 200): 2}
inv_alta_membresia_vs_revocar {(201, 200): 40}
inv_exporta_vs_revocar       {(200, 200): 40}
mi S1 de verify-2            {(200, 200): 39, (403, 200): 1}
concurrencia mixta (2 guardados + vigente + progreso, 20 vueltas; 3 cierres + guardado): {200: 81, 409: 3}
```

En verify-2 la misma prueba dio 39 respuestas 500 de 40. Los 403 son el resultado correcto cuando la revocación entra primero.

### O1

- Ancla completa: `faltantes == []` y congela (200).
- Ancla vacía: `faltantes = ['regimen', 'dimension:d1', 'dimension:d2', 'dimension:d4']`, y congelar responde 422 con `incompleta: regimen; incompleta: dimension:d1; ...`. Si se edita con la cita de `d1` en espacios, `faltantes == ['cita:d1']` y congelar sigue en 422. Con la respuesta completa, `[]`. Editar solo la explicación mantiene `[]`, y entonces congela.
- Exenta `evidencia_insuficiente`: con notas, `[]`; sin notas, `['notas']` y congelar da 422. Si se borra la que no tiene notas, congela.
- La revalidación de F1 (regla cambiada, dimensión renombrada, exento renombrado, clon de una congelada) sigue en 422 y la exenta válida sigue pasando.

## Lentes sobre lo que tocaron las correcciones

1. **Ciego**: LIMPIO. `faltantes` y `anclas_invalidas` solo aparecen en respuestas de endpoints del investigador; los 502 del CTR siguen genéricos.
2. **Acceso**: LIMPIO. `require_membresia` conserva la búsqueda por email en minúsculas, el filtro de no revocada, el rol y la atadura. Con la revocación primero, el primer uso da 403. El smoke y la suite de acceso del constructor siguen verdes.
3. **Integridad**: LIMPIO. Sin ciclos de locks; los triggers y TRUNCATE no cambiaron (6 triggers tras re-migrar).
4. **Régimen**: LIMPIO. `motivos_ancla_para_congelar` usa la misma completitud que el cierre (`faltantes_cierre`).
5. **Bordes**: LIMPIO. Ver N2.
6. **Exportación**: sin cambios; el smoke la recorre.
7. **Cableado**: el panel consume `faltantes` en el alta de ancla (`AdministracionEstudioView.tsx:640`, `AnclaGuardada`). La edición de anclas no tiene UI (lo declara el constructor): ese aviso solo llega por la API. Smoke 100 passed.
8. **Docs**: el runbook (§12.3 y §12.6) describe `faltantes` y el 422 por `incompleta:` tal como se comporta.

## JUICIO

Autor: breaker verify-3. Comparación: árbol `50fadc6b8a034547` contra mis reproducciones de verify-1 y verify-2, D10b, D9 y D14, y las specs. Confianza alta: cada corrección se atacó por HTTP, con concurrencia real y con datos reales del CTR.

Observaciones que no son fallas:
- **Edición de ancla**: si el ancla guardada no vale contra el esquema (por ejemplo, tras un cambio de esquema) y se edita sin tocar `respuesta_esperada`, `faltantes` puede traer motivos de validez sin el prefijo, mezclados con los de completitud. Es cosmético y el 422 de congelar los distingue.
- **Specs**: siguen sin escenarios para el 422 de congelar, el 409 `sin_muestra`, el orden de locks y el 502 por formato. Es trabajo del planner, ya marcado por el constructor F.
- **S2** (lecturas al CTR que siguen después de un 502) y **S3** (celdas CSV que empiezan con LF o espacios): sin cambios, siguen como observación y suposición. **S4 y S5**: coherentes con D9.

## SUPOSICIÓN

- No ejecutado: CI, la firma real del gateway contra ctr-service, Clerk (el recorrido humano CRITICAL sigue pendiente) y la suite completa del classifier (reusé `708 passed + 4 ambientales`, 14:45:45, del constructor F).
- El barrido del CTR real no incluye `lectura_enunciado`, `tests_ejecutados`, copias ni pegados (el seed no los tiene); esos casos los cubre la unitaria sintética.

## Fuentes leídas

`routes/estudio.py` (`_buscar_estudio`, `_atar_o_verificar`, `require_membresia`, `_estudio_para_gestionar`, `investigador_con_estudio_bloqueado`), `routes/estudio_trabajo.py` (`bloquear_para_codificar`, `crear_ancla`, `editar_ancla`, `borrar_ancla`), `services/estudio_esquema.py` (`errores_respuesta_esperada`, `motivos_ancla_para_congelar`), `services/ctr_lectura.py` completo; ctr-service `models/event.py` (`ts` con zona); web-teacher `estudioApi.ts` y `AdministracionEstudioView.tsx` (`rg faltantes`); runbook §12.3 y §12.6; mis informes y tests de verify-1 y verify-2.

## Contaminación

Leí `apply-3-constructor-F.md` **después** de atacar y de recalcular la huella final. De ahí tomé solo, para la redacción: el conteo de la suite (`708 passed`), que la edición de anclas no tiene UI y que los escenarios de spec quedan para el planner. La barrera del constructor la usé como test existente (5 corridas), no como diseño de mis rondas. Mismo proveedor y familia que todos los roles.
