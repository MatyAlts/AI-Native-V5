# Retención de artefactos y PDF de corrección

Qué se guarda de la corrección asistida, por cuánto, y quién lo borra.
Documento operativo — el procedimiento es manual a propósito (ver el final).

## Qué se guarda

| Dato | Dónde | Qué es |
|---|---|---|
| `entrega_artefactos.codigo` | Postgres, `academic_main` | El código que el alumno entregó, uno por ejercicio |
| `entregas.artefacto_sha256` | Postgres | Hash del conjunto: la constancia de qué se corrigió |
| `correcciones_ia.pdf_storage_key` | Postgres | Dónde quedó el PDF |
| El PDF | Bucket `correcciones` (S3/MinIO) | La devolución de Active-IA, con el nombre del alumno |
| El zip subido | **Active-IA, fuera de nuestro perímetro** | El mismo código, del otro lado |

Esa última fila es la que importa para cualquier decisión de retención: **una
copia del código de cada alumno vive en un sistema que no es este**. Borrar acá
no la borra allá.

## Por cuánto

**Los artefactos y los PDF viven lo que vive la entrega.** No hay expiración
por tiempo, y es deliberado: el artefacto es la evidencia de qué se corrigió, y
una nota sin la evidencia de sobre qué se puso es una nota que no se puede
auditar. La tesis se apoya en eso.

Lo que sí tiene fecha es el piloto. **Al cierre del período académico:**

1. Correr `scripts/medir-entregas-artefacto.py` para saber el universo.
2. Exportar lo que vaya al análisis (`export-academic`, que anonimiza con
   `student_alias`).
3. Recién ahí, borrar.

## Cómo se borra

**Por alumno** — es el derecho al olvido, y corre por
`platform_ops.privacy.anonymize_student` con el adaptador
`evaluation_service.services.olvido.OlvidoCorreccionAdapter`:

- el artefacto y el hash del conjunto se **borran**;
- el PDF se **borra** del storage;
- el pseudónimo de la entrega se **rota**, así la corrección queda disociada.

El informe devuelve `pdfs_con_error` con los que no se pudieron borrar y
`borrado_externo_ok`. **Un `None` ahí significa "no se intentó"**, no "salió
bien": hoy Active-IA no expone borrado por alumno (pedido 3.6 de
`activeia-cambios-pedidos.md`), así que ese paso hay que hacerlo a mano desde
su panel. Mientras eso siga así, **el olvido de este sistema es incompleto** y
el informe lo dice.

**Masivo, al cierre del piloto**: no hay job. Es a mano, con las mismas tres
piezas, y con la lista de alumnos del período.

## Por qué no hay un job automático

Un borrado automático de evidencia académica es un borrado que nadie revisó.
Si el job se equivoca de filtro, lo que se pierde son las entregas sobre las
que ya se puso una nota — y no hay de dónde recuperarlas, porque el CTR guarda
eventos, no artefactos.

El día que haya un job, tiene que: correr en dry-run primero, listar qué va a
borrar, y pedir confirmación. Hasta entonces, manual y documentado es más
seguro que automático y confiado.

## Lo que este documento NO resuelve

Si AI-Native y Active-IA son la misma personería frente al consentimiento del
piloto (gate 0.5). De eso depende si mandar el código allá es un tratamiento
interno o una cesión a un tercero, y con ello qué hay que informarle al alumno.
**Está abierto y bloquea el despliegue con datos reales, no el desarrollo.**
