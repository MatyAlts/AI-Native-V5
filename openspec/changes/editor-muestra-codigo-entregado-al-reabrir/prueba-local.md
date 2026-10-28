# Prueba local — editor-muestra-codigo-entregado-al-reabrir

## Lo que SI se verifico (2026-10-28)

1. **Contrato real del endpoint** que usa el cambio. Con Postgres/gateway/academic/evaluation reales, `GET /api/v1/entregas/{id}/artefacto`
   como el alumno dueño (la entrega `cf0c493b-...` que deja `publicar-nota-y-pedir-correccion/prueba-local-api.py`) devuelve 200 con
   `entrega_id, legacy, artefactos[]`, y cada fila trae `orden, ejercicio_id, episode_id, codigo, language, sha256, created_at`: exactamente
   el tipo `EntregaArtefacto` de `apps/web-student/src/lib/api.ts`.
2. **Comportamiento de EpisodePage** con el componente real y `fetch` mockeado (`pnpm test`): siembra, cierre sin editar, BUG-1 y
   no-emision de `edicion_codigo`. Ver `STATUS.md`.

```bash
# desde la raiz, con el stack minimo (ver publicar-nota-y-pedir-correccion/prueba-local.md) y despues de correr su prueba-local-api.py
curl -s http://127.0.0.1:8000/api/v1/entregas/<ENTREGA_ID>/artefacto \
  -H "X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" -H "X-User-Id: e19354fb-c05a-4535-a0bf-a7d3ea09692d" \
  -H "X-User-Email: d@x.edu" -H "X-User-Roles: estudiante"
cd apps/web-student && pnpm exec vitest run tests/ReaperturaSiembraCodigoEntregado.test.tsx tests/TpDevueltaCerrarSinEditar.test.tsx tests/cascadaCodigo.test.ts
```

## Lo que NO se verifico (falta un humano con el navegador)

Los pasos 1-11 de `design.md` con el stack completo (tutor, CTR, workers) y `pnpm turbo dev`: en particular el paso 6 (el editor muestra
el codigo y "Siguiente ejercicio" desbloquea el 2), el paso 7 (cadena cortada), el paso 8 (a lo sumo un GET `/artefacto` y un PATCH en
Network) y la comparacion de `event_type` en `ctr_store` antes/despues (pasos 5 y 11). No se levanto el stack completo ni un navegador.
