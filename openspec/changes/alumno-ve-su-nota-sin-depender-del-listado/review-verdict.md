# Veredicto de revisión

Cuatro revisores: el implementador (seis vueltas), QA, el auditor, y un DBA
convocado tarde. Queda acá para que se archive con la change.

## El hallazgo que justifica todo el ciclo

El test de integración, corrido contra Postgres real **con la mutación puesta**,
reprodujo en vivo la falla que el DBA había predicho leyendo el código:

```
PostgresSyntaxError: syntax error at or near "$1"
[SQL: SELECT id, codigo, titulo FROM tareas_practicas WHERE id IN $1
      AND deleted_at IS NULL]
```

Sacando `.bindparams(bindparam("ids", expanding=True))`, asyncpg intenta
bindear la lista entera como un solo parámetro posicional. **Compila limpio en
SQLAlchemy y revienta recién contra el driver.**

Y el `CLAUDE.md` del repo ya tiene documentado el incidente de esta clase
exacta: *"BYOK `SET LOCAL` con bind param que Postgres no acepta — pasó tests
porque mockeaban DB, falló en runtime"*.

El código estaba bien. Lo que no existía era la red: con sesión mockeada, ese
test pasa con `expanding=True` y sin él. Reproducido dos veces de forma
independiente — por el implementador y por el orquestador.

## Lo que encontró QA

**BLOQUEANTE — skeleton eterno.** Si `listMisMaterias` fallaba, `materias`
quedaba `null` para siempre, `loading` daba `true` para siempre, y el panel de
error nunca se montaba. El alumno veía el esqueleto cargando sin enterarse
nunca. Es la violación exacta del principio 5 de `PRODUCT.md` (*"NO spinners
eternos"*) que las propias tareas de esta change nombraban con esas palabras.
Reproducido con un test desechable, dos veces.

**Y por qué no se vio**, que importa más que el bug: los tests renderizaban
`MisNotasList` con props fijas y **nunca montaban `MisNotasPage`**, así que toda
la lógica del orquestador —los dos fetch, `loading`, `error`, `limitReached`— no
tenía un solo test. El checkbox de "Error: se dice" estaba marcado habiendo
verificado un camino de fetch y no el otro. Ahora el orquestador tiene cuatro
tests.

**Informativo — el `field_validator` de `EntregaOut` es código muerto** en los 8
call-sites: todos construyen vía `model_validate(entrega_orm)` (atributo ausente
→ default sin pasar por el validator) o por asignación directa (sin
`validate_assignment`). La defensa real es el `float()` explícito más la
coerción de pydantic al serializar.

## Lo que encontró el auditor

**La garantía de aislamiento no tenía un solo test.** El filtro
`Entrega.student_pseudonym == user.id` estaba donde tenía que estar —eso se
verificó— pero ningún test lo ejercitaba: los nueve usan una sesión mockeada que
devuelve filas pre-armadas **sin importar qué `WHERE` se construyó**. Si alguien
reordenaba esa condición en un refactor, nada en rojo lo avisaba.

Cerrado con dos tests que afirman sobre el `Select` compilado, y la mutación que
los valida **simula el IDOR**: cambiando `user.id` por el parámetro de query, el
SQL compilado mostraba el UUID del *otro* alumno.

**Y que no se había convocado al DBA.** El `CLAUDE.md` fija un piso: cuando el
cambio toca datos de usuario, el DBA se convoca sin importar lo que el
orquestador juzgue necesario, y su ausencia se escribe como decisión y no como
silencio. Se saltó y no se declaró. Es el silencio que esa regla existe para
prohibir.

## Lo que encontró el DBA

**No encontró el agujero de aislamiento, y lo descartó mejor que QA**: QA lo
verificó leyendo, el DBA lo verificó **ejecutando** `list_entregas` y capturando
el `SELECT` compilado con el filtro adentro.

**`_notas_metadata` no filtraba `deleted_at`,** y sus dos hermanas en el mismo
archivo sí (`get_calificacion`, `recalificar_entrega`). Hoy es inerte —nada
escribe esa columna, no hay soft-delete de calificaciones— pero la columna y su
índice ya existen. El día que exista, la lista mostraría una nota que el detalle
trata como inexistente: la misma discrepancia que esta change vino a resolver,
al revés. Corregido con el porqué escrito en el código.

**RLS verificado**, leyendo las migraciones: las tres tablas tienen `ENABLE` +
`FORCE ROW LEVEL SECURITY`. El `FORCE` importa porque `academic_user` es OWNER y
Postgres exime al dueño salvo que esté forzada. Las dos queries corren sobre la
misma sesión con el contexto de tenant seteado; el SQL crudo no lo esquiva.
Declarado como leído de las migraciones, **no ejecutado**: un drift entre
migración y base real no lo vería.

**N+1 verificado ejecutando: 3 consultas para 50 filas**, no 101.

**Sin índices nuevos ni migración**, correctamente: las dos queries atacan PK e
índice único con un `IN` acotado al lote.

## Lo que encontró el implementador de su propio trabajo

**`Decimal("8.50") == 8.5` da `True` en Python**, así que su primer test del cast
pasaba la mutación con el bug de tipo puesto. Lo encontró corriendo la mutación,
no leyendo el test, y lo reforzó a `isinstance`. **Es una clase nueva de
aserción vacua**, distinta de las cuatro de la change anterior: esas eran todas
"subcadena corta en documento largo".

**`toLocaleDateString` con `{month: "2-digit"}` no rellena el mes** en este
runtime: devolvía `12/9`, no `12/09`. Estaba desde la primera vuelta y ningún
test afirmaba el formato exacto.

**`PgUUID` compila el literal sin guiones**, así que `str(uuid) in compiled` da
falso y `uuid.hex in compiled` da verdadero. Otra aserción que habría pasado sin
medir nada, evitada por verificar antes de escribir.

**Corrigió a QA en un punto, y tenía razón**: el validator de `CalificacionOut`
(preexistente) **no** es código muerto — esa columna es `NOT NULL` y siempre
está como atributo. El muerto era sólo el que él agregó. Corrigió su propio
comentario y no tocó el ajeno. Confirmado por el auditor en el modelo.

**Y declaró un commit que no hizo** (`33a2ab8`, del orquestador), en vez de
asumirlo inocuo.

## Dos decisiones del orquestador sin consultar al usuario

Mandar la nota al mismo lote, y recuperar `graded_at`. El argumento fue que
completaban una decisión ya aprobada. El auditor lo revisó y lo sostiene, **con
una corrección**: la base de esa defensa es el **mockup** que el usuario
confirmó —que sí mostraba la nota y las dos fechas en la lista— y **no** el
texto técnico del proposal, que sólo especificaba dos campos. Es más preciso que
como el orquestador lo había planteado.

## Lo que queda abierto

**El test de RLS está skippeado, no ejecutado.** El único Postgres disponible
corre con el rol `postgres`, que es superuser y bypassa RLS, así que la TP ajena
se vería igual y el test no probaría nada. Skippea con ese motivo escrito.
**El test hermano del repo** (`test_entrega_comision_de_la_tp_db.py`) skippea por
lo mismo en el mismo contenedor: no es una limitación de esta change, es la del
patrón de la casa. Para ejecutarlo de verdad hace falta un rol `NOBYPASSRLS`.

**RLS no se verificó contra una base viva**, sólo leyendo las migraciones. Un
drift entre migración y ambiente real no se vería.

**El layout a 320px no se verificó.** jsdom no calcula layout, así que "sin
scroll horizontal" es una decisión de CSS sin test que la pruebe. Y nadie corrió
la pantalla en un navegador en seis vueltas — QA señala que eso habría atrapado
el skeleton eterno de inmediato, aunque lo encontró igual con una reproducción
dirigida.

**Lo que esta change NO le devuelve al alumno: el enunciado** del TP archivado.
Recupera la nota y la corrección. Dárselo exige relajar el chequeo de
`academic-service` —el camino (B) del proposal— y eso es un cambio de control de
acceso que bajo la gobernanza del proyecto necesita aprobación humana explícita.
Descartado para esta change, no para siempre.

**El aviso al archivar** —que `archive()` cuente las entregas sin calificar
antes de confirmar— no entra. Y **archivar sigue sin poder deshacerse**, que es
una pregunta de producto y no técnica.

**27 fallos pre-existentes adicionales** aparecen al correr la suite completa CON
base (`test_correccion_metrics_db.py`, `test_olvido_db.py`), además de los 5 de
siempre. Ajenos a esta change, sin investigar, nombrados para que queden
escritos.

## Un supuesto que resultó falso, y vale como lección

Durante cinco vueltas el implementador declaró "sin Postgres real" como una
limitación del entorno, y el orquestador la aceptó como tal. **Era falsa**:
había un contenedor `platform-postgres` corriendo todo el tiempo. Y el repo ya
tenía tests de integración para helpers hermanos, así que no tenerlos no era una
limitación aceptada sino un hueco contra el estándar de la casa.

Un supuesto bien declarado sigue siendo un supuesto: lo que lo volvió inofensivo
fue declararlo, y lo que lo resolvió fue que alguien lo cuestionara en vez de
heredarlo.

## Verificación final

```
ruff format --check   exit 0
ruff check            exit 0
biome (web-student)   exit 0
tsc --noEmit          exit 0

apps/evaluation-service      346 passed, 5 failed (pre-existentes), 100 skipped
apps/web-student             592 passed (48 archivos)
integración contra Postgres    5 passed, 1 skipped (el de RLS, por el rol)
```

Los 5 fallos se confirmaron pre-existentes tres veces de forma independiente:
por QA con `git stash`, por el orquestador con `git stash`, y por el auditor
re-corriendo las suites.
