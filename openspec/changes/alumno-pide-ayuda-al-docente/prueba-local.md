# Prueba local reproducible — alumno-pide-ayuda-al-docente

Estado: **PENDIENTE** (tarea 7.1). No se corrió el stack local completo en la implementación;
la corre el orquestador / Neyén. Los tests automáticos (unit + integración contra Postgres +
vitest) ya pasan: ver `STATUS.md`.

## 0. Preparar

Desde `rama desarrollo/` (o el worktree de la rama `feat/alumno-pide-ayuda-al-docente`), Git Bash:

1. Si el Postgres 18 de Windows está prendido, frenarlo (pisa el 5432).
2. Levantar el stack:
   `DEV_TRUST_HEADERS=true PROMPTS_REPO_PATH="$(cygpath -w "$(pwd)/ai-native-prompts")" bash scripts/dev-start-all.sh`
   y en otra terminal `pnpm turbo dev`.
   web-student http://localhost:5175, web-teacher http://localhost:5174.
   Alumno de dev `e19354fb-c05a-4535-a0bf-a7d3ea09692d`, tenant `aaaa…`.
   Si abrir un episodio da 403: es el tenant `bbbb…` que dejan los smoke.
3. Migrar (OJO: esto sí toca `academic_main`; hacerlo recién acá, con el stack propio):
   `ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main uv run alembic -c apps/evaluation-service/alembic.ini upgrade head`
   (alternativa: `cd apps/evaluation-service && uv run alembic upgrade head` con la misma variable).
   Después `make check-rls`: tiene que decir OK (ya dio OK contra una base descartable).
4. Reiniciar evaluation-service y api-gateway para que carguen la ruta nueva.

## 1. Pedido desde un ejercicio
web-student → una TP publicada → abrir un ejercicio → "Pedir ayuda a tu docente" →
"No puedo avanzar" + "no entiendo el while" → Enviar.
Esperado: "Tu pedido le llegó a tu docente" y, al reabrir el modal, el pedido figura *Pendiente*.
El episodio sigue abierto (no se pausó ni se cerró).

## 2. Anti-spam
Enviar otro enseguida → "Esperá N segundos antes de mandar otro pedido." No se crea.

## 3. Pedido sin episodio
Volver a la lista de ejercicios → "Pedir ayuda a tu docente" → "Error de la plataforma" →
(opcional: elegir ejercicio) → Enviar, pasado el minuto.

## 4. Pantalla de error del ejercicio (el caso que originó el change)
Con el worker del CTR apagado (o forzando el 404 del estado del episodio): al tocar "Empezar"
aparece "El ejercicio no terminó de abrirse" con Reintentar / Pedir ayuda a tu docente / Volver.
Pedir ayuda desde ahí debe salir con el `episode_id` del intento fallido.

## 5. Docente
web-teacher → elegir la comisión → "Mis comisiones" muestra "2 pedidos de ayuda" → menú
"Pedidos de ayuda": dos filas con alumno, TP, ejercicio (uno vacío), categoría, mensaje;
"Ver episodio" (sólo en el que tiene episodio) abre la timeline.

## 6. Resolver
"Marcar resuelto" en uno → pasa a *Resueltos*, el contador baja a 1. En web-student el pedido
figura *Resuelto*.

## 7. Privacidad (opcional, con headers)
Con un docente que no esté en la comisión, el listado da 404.

## 8. Tesis
`git diff origin/main --stat -- apps/ctr-service apps/classifier-service apps/tutor-service apps/governance-service packages/contracts ai-native-prompts packages/platform-ops/src/platform_ops/academic_export.py`
→ debe salir vacío. Además: en la timeline del episodio del paso 1 NO debe aparecer ningún evento
nuevo por haber pedido ayuda.

Anotar el resultado de cada paso en `STATUS.md`.
