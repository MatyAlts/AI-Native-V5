## Why

Cuando un alumno se traba dentro de un ejercicio —no puede avanzar, la plataforma falla, no entiende la consigna— hoy no tiene cómo avisarle a una persona desde la plataforma. El reclamo termina en un foro de Moodle, **sin ningún dato para diagnosticar**: ni qué TP, ni qué ejercicio, ni qué episodio, ni a qué hora. Los casos del 23/10 ("Episode no encontrado", workers del CTR caídos) llegaron así, y reconstruir quién estaba dónde llevó horas.

Decisión del dueño (Neyén, 2026-10-26 y 2026-10-28): un **botón de pedir ayuda a un humano** (opción B). No es ayuda de uso (A) ni pistas (C): las pistas competirían con el tutor socrático y ensuciarían la trazabilidad N4. El pedido le llega **a los docentes de la comisión del alumno, dentro de web-teacher**, no por mail.

## What Changes

- **Alumno (web-student)**: botón **"Pedir ayuda a tu docente"** en dos lugares: la pantalla del episodio (incluida la pantalla de error "El ejercicio no terminó de abrirse") y la lista de ejercicios de la TP. Abre un modal con:
  - categoría obligatoria: *No puedo avanzar* / *Error de la plataforma* / *Duda sobre la consigna* / *Otro*;
  - texto libre opcional (hasta 1000 caracteres);
  - aviso explícito: "Esto le llega a tu docente, no al tutor. No es una pista: el tutor sigue siendo tu ayuda para resolver el ejercicio.";
  - confirmación "Tu pedido le llegó a tu docente" y la lista de sus pedidos de esa TP con estado (*Pendiente* / *Resuelto*).
- **El pedido lleva el contexto solo**: TP, comisión (la deriva el servidor de la TP), número de ejercicio, `episode_id` y `entrega_id` si los hay, hora del servidor y un mínimo de diagnóstico de pantalla (en qué pantalla estaba y qué error mostraba). `episode_id` es **opcional**: en el caso "Episode no encontrado" el episodio no existe en la base, y el pedido igual tiene que poder salir.
- **Anti-spam**: como mucho un pedido por minuto por alumno y como mucho 3 pendientes por alumno en la misma TP.
- **Docente (web-teacher)**: ítem nuevo **"Pedidos de ayuda"** en el menú (grupo "Trabajo del docente"), con la lista por comisión: alumno, TP, ejercicio, categoría, mensaje, hace cuánto, link al episodio si lo hay, y botón **"Marcar resuelto"**. Pestañas *Pendientes* / *Resueltos*. El contador de pendientes aparece en la tarjeta de cada comisión de "Mis comisiones". Sin push en tiempo real: se ve al entrar o al refrescar.
- **Privacidad**: sólo los docentes asignados a la comisión del alumno (y `docente_admin`/`superadmin`) leen los pedidos; el alumno sólo ve los suyos.
- **Backend (`apps/evaluation-service`)**: tabla nueva `pedidos_ayuda` en `academic_main` con RLS por tenant (`ENABLE` + `FORCE` + policy), migración Alembic, y cuatro endpoints bajo `/api/v1/pedidos-ayuda`.
- **Textos de ayuda / onboarding** en las dos apps para que el alumno sepa que existe y el docente sepa dónde mirarlo.
- **Nada de la tesis cambia**: el pedido **no** emite evento CTR, no toca el tutor, ni prompts, ni el clasificador, ni `packages/contracts` (ver design, "Tesis: qué NO se toca").

## Capabilities

### New Capabilities
- `pedidos-de-ayuda`: el alumno pide ayuda a un humano desde un ejercicio con el contexto adjunto; los docentes de su comisión los ven en web-teacher y los marcan resueltos; aislamiento por tenant y por comisión; anti-spam; fuera del CTR.

### Modified Capabilities
- (ninguna) — el flujo del ejercicio y la corrección no cambian de comportamiento; el botón se suma sin alterar ningún requisito existente.

## Impact

- **Backend** (`apps/evaluation-service`): `models/pedidos_ayuda.py`, `schemas/pedido_ayuda.py`, `routes/pedidos_ayuda.py` (router nuevo incluido en `main.py`), migración `alembic/versions/2026xxxx_0001_pedidos_ayuda.py`. Lee `inscripciones`, `usuarios_comision` y `tareas_practicas` por SQL, como ya hace `routes/entregas.py`.
- **web-student**: `pages/EpisodePage.tsx` (header y pantalla de error), `components/ExerciseListView.tsx` (header de la TP), componente nuevo `components/PedirAyudaModal.tsx`, `lib/api.ts`, `utils/helpContent.tsx`, onboarding del alumno.
- **web-teacher**: ruta `routes/pedidos-ayuda.tsx`, vista `views/PedidosAyudaView.tsx`, ítem en `NAV_GROUPS` (`routes/__root.tsx`), contador en `components/ComisionDelDocenteCard.tsx`, `lib/api.ts`, `utils/helpContent.tsx`.
- **Sin cambios** en `apps/ctr-service`, `apps/classifier-service`, `apps/tutor-service`, `packages/contracts`, `ai-native-prompts`, el export académico (`packages/platform-ops/academic_export.py`).
- **Deploy**: una migración nueva en `academic_main` (aditiva, reversible). `make check-rls` tiene que seguir en verde.
- **Gobernanza**: MEDIO-ALTO (tabla nueva con texto libre de alumnos + RLS).
