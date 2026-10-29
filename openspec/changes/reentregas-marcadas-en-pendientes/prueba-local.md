# Prueba local — reentregas-marcadas-en-pendientes

Hecha el 2026-10-28 con el stack real (Docker Postgres/Redis, `dev-start-all.sh` + `pnpm turbo dev`), TP `LOCAL-PNPC` de 3 ejercicios (ver `publicar-nota-y-pedir-correccion/prueba-local.md`). Hay que reiniciar evaluation-service (:8004) para que tome el código nuevo.

| Paso | Resultado |
|---|---|
| Entrega nueva `submitted` | API: `es_reentrega=false` |
| Calificar (7), pedir corrección del ej. 2, re-entregar | API: `submitted`, `es_reentrega=true`, `nota_final=7.0` |
| `GET /entregas?...&reentrega=true` / `=false` / sin filtro | 1 / 0 / 1 resultados (sólo existía la re-entrega en esa TP) |
| UI web-teacher Correcciones | tarjeta: "Enviada" + "Re-entrega · antes 7" + "Corrección pedida: ej. 2" (captura `m5-01-docente-lista-re-entrega-badge.png`) |
| Toggle "Sólo re-entregas" | queda sólo la re-entrega; la devuelta legacy `SMK-P4D2B` desaparece; "Corregir en lote" = 1 (`m5-02-docente-solo-reentregas-activo.png`) |
| Re-calificar (PATCH nota 9) | pasa a `graded`; `reentrega=true` devuelve `[]` |

Capturas en `capturas-prs-126-127/` (fuera del repo).
Reproducir: levantar el stack, correr el ciclo de `prueba-local-api.py` de #126 hasta el re-submit, abrir http://localhost:5174/teacher/correcciones?comisionId=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.
