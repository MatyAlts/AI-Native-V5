# Estado de la rama `desarrollo-juani` — Handoff para el equipo

> **Rama**: `desarrollo-juani` (`MatyAlts/AI-Native-V5`) · **67 commits sobre `main`** · todo pusheado.
> **Qué es**: implementación del `PLAN-NUEVA-VERSION.md`. Este doc define los códigos (`A0.x`, `P-x`, `F-x`, `NB-x`, `FR-x`, `BUG-x`, `UI-x`, `ED-x`, `BK-x`) y el estado de cada uno.
> **Verificación**: cada ítem pasó typecheck+build (front) / pytest (back). La auditoría QA externa (2026-07-13) corrió la suite completa: **1543 tests pasan (+142 vs `main`), 0 regresiones**.

---

## Resumen ejecutivo

| Bloque | Estado |
|---|---|
| **Bugs** (BUG-1..4, NB-1..23 + NB-2b) | **27/27 ✅** |
| **Seguridad** (A0.1..A0.7) | **7/7 ✅** (gateada OFF — activar en prod, ver §6) |
| **Performance** (P-1..P-18) | 14/17 ✅ (faltan P-6, P-7, P-16 — todos en la pantalla del episodio) |
| **Features** (F1..F15) | **14/14 ✅** (F15 = active-ia, fuera de scope) |
| **Interfaz alumno** (UI-1..8) · **Editor** (ED-1..8) · **BYOK** (BK-1..4) · **Fricciones** (FR-1..10) | **✅ completos** |

---

## 1. HECHO ✅

### Bugs (27/27)
- **Blockers**: NB-1 (invite_code), NB-2/NB-3 + **NB-2b** (BYOK resolver/constraint), NB-5 (wizard IA muerto).
- **Correctness**: BUG-1 (entrega monolítica), NB-4 (re-calificar PATCH), NB-6 (sessionStorage cross-episodio), NB-7 (TP vencida inaccesible), NB-8 (título/match por ejercicio_id), NB-10/11/12 (doble-click / doble-submit / race Reflection-Classification), BUG-4 (RAG embeddings falsos silenciosos), BUG-2 (reorden corrompe orden), BUG-3 (re-editar nota).
- **Medio/bajo**: NB-9 (dead code), NB-13 (bulk-import form stale), NB-14 (governance events acumular), NB-15/16 (comisiones optimistic/atomicidad), NB-17 (copy templates), NB-18/19 (KPIs / paginación selectores), NB-20 (aviso editar en uso), NB-21 (catches vacíos), NB-22 (filtro comisiones), NB-23 (BYOK /test → 501).

### Seguridad A0 (7/7) — **gateada OFF, activar en prod**
- **A0.1**: firma del gateway cableada en los 5 servicios que faltaban (ai-gateway, classifier, analytics, governance, integrity). Verificado en vivo: forjado→401, service-token→200, sign↔verify simétrico.
- **A0.2**: leak cross-tenant en `GET /universidades/{id}`.
- **A0.3**: alumno veía test cases ocultos + soluciones (**contamina la validez del piloto** — eventos N4 falsos). `content_visibility.py`.
- **A0.4**: governance-service sin auth. **A0.5**: check RLS valida activo Y forzado. **A0.6a** IDOR escritura Unidades/instrumentos · **A0.6b** ABAC lectura CTR por comisión. **A0.7**: rate-limit del invite code.

### Performance (14/17)
P-1 streaming tutor incremental · P-2 doble-writer CTR (`CTR_MODE=http`) · P-3 httpx pool · P-4/P-8 N+1 + engines analytics · P-5 HomeView 1+3×N · P-9 sesión DB /generate · P-10 embedder to_thread · P-11 Error Boundaries · P-12/13/18 fetch layer (interceptor + timeout + sin espera Clerk) · P-14 dedup RLS policy · P-17 ctr-client (cola offline + idempotencia).

### Features (14/14)
F1 probar código · **F2 tutor recibe todos los atributos** (tutor_rules + test_cases + TP monolítica, sin tocar el prompt) · **F3 RAG real observable** (ver chunks, probar retrieval, reingest; embedder real activable en prod) · F4 rúbrica corrección · **F5 corrección en lote** (cola con auto-avance) · **F6 diff entre intentos** (timeline) · **F7 alertas accionables** (home docente) · **F8 citas del RAG al alumno** (SSE aditivo) · F9 mi-progreso alumno · F10 feature flags · F11 uso/costo BYOK docente · F12 preview "como alumno" · F13 export Caliper/xAPI · F14 rúbrica por ejercicio.
F15 (corrección asistida IA) = ⛔ active-ia, fuera de scope.

### Interfaz alumno, editor, BYOK, fricciones
- **UI-1..8**: anotaciones N2, indicador N4, markdown chat, **UI-8 (error tutor NO cierra el episodio + reintentar)**, countdown, auto-skip unidades, borró WelcomeStage.
- **ED-1..8**: maximizar editor, layout persistido, fuente +/-, errores en la línea (Monaco markers), restaurar plantilla, salida redimensible con pestañas, historial de corridas, loading Pyodide.
- **BK-1..4**: BYOK descubrible (nav, banner, CTA, hint). **NB-23** endpoint /test honesto.
- **FR-1..10**: búsquedas, multiselect composición TP + paso obvio, paginación, editor rúbrica, banner de éxito, `ConfirmDialog` consistente, empty states.
- **MissingGreenlet** en `new_version()` de TPs.

---

## 2. PENDIENTE 🔜

### Features
- **Todas hechas** (F1..F14). Solo queda **F15** (corrección asistida por IA) = **⛔ toca active-ia, fuera de scope.**
- Nota F3: el pipeline es real y observable; para embeddings semánticos reales en prod hay que setear `EMBEDDER=gemini` + `GEMINI_API_KEY` (o `EMBEDDER=local`) en content-service y reprocesar materiales (endpoint reingest). Ver `apps/content-service/README.md`.

### Performance del episodio (pendiente)
- **P-6** re-render O(n²) del chat en streaming · **P-7** clasificación async al cierre · **P-16** Pyodide en Web Worker + self-host.

### Ops / no-código
- **Merge `desarrollo-juani → main`** (via PR) → deploy EasyPanel.
- **Activar la seguridad** en prod (§6).
- **Mover `.github/` a la raíz** — el CI nunca corrió (ver §3).
- Arreglar `restore.sh` (roto, pre-existente).

---

## 3. Auditoría QA (2026-07-13)
- **🔴 P-17 (bloqueante, era real)** → **ARREGLADO** (`165d83e`): la cola offline reintentaba un evento; `next_seq()` avanzaba el contador sin dedup → seq mismatch → dead-letter → `integrity_compromised` **permanente** (fatal para la tesis, salta en cada cambio de pestaña). Fix: Idempotency-Key por `event_uuid`.
- **🔴 P-2 puede no aplicar a prod**: el fix vive en `docker-compose.prod.yml`, pero EasyPanel puede setear env vars en su UI. **Verificar** `CTR_MODE` real + que estén los 8 `ctr-worker`.
- **🔴 CI nunca corrió**: los workflows están en `AI-NativeV3-main/.github/` pero GitHub solo lee `.github/workflows/` de la **raíz**. Por eso los bugs llegaron a prod sin portón.
- Menores: comentario P-2 corregido (`d398379`); migración dedup fechada sept-2026; `restore.sh` roto.

**Query tesis-crítica (solo lectura, contra `ctr_store`):**
```sql
SELECT COUNT(*) FILTER (WHERE integrity_compromised) AS comprometidos, COUNT(*) AS total FROM episodes;
```

---

## 4. Migraciones nuevas (3)
`20260504`/BYOK index `NULLS NOT DISTINCT` · dedup RLS policy en `classifications` · `calificaciones.updated_at`. Todas con `downgrade()`, ninguna borra datos. **Dump previo obligatorio antes de aplicar a prod.**

---

## 5. Verificación
- Backend: `make test-fast` / `uv run pytest apps/<svc>/tests`. RLS: `make check-rls` (ahora valida FORCE). Smoke: `make test-smoke`.
- Frontend: `pnpm --filter <app> run typecheck && ... run build`.
- **Los 14 tests que fallan son pre-existentes** (idénticos en `main`): entorno Windows cp1252, `academic_user` sin permisos, health `degraded`.

---

## 6. Activación de seguridad en prod (el orden importa)
1. Deploy `main` en EasyPanel (Stop+Implementar). Confirmar los 8 `ctr-worker` + `CTR_MODE=http` (P-2).
2. Setear el **mismo** `GATEWAY_SHARED_SECRET` en api-gateway + los 6 servicios que verifican.
3. Setear el **mismo** `INTERNAL_SERVICE_TOKEN` en servicios + callers (tutor, academic, reclassify).
4. `ACADEMIC_DB_URL` en ctr-service (A0.6b) + `ENFORCE_COMISION_ACCESS=true`.
5. **RECIÉN AHÍ** `REQUIRE_GATEWAY_SIGNATURE=true`. (Antes = 401 al tutor → rompe el chat.)

---

## 7. Setup dev local (gotchas)
- `make dev` = SOLO los 3 frontends (vite). Backends: `bash scripts/dev-start-all.sh`.
- Vite bindea IPv6 → entrar con **`localhost`**, no `127.0.0.1`. Puertos: :5173 admin, :5174 teacher, :5175 student.
- api-gateway: `DEV_TRUST_HEADERS=true` para aceptar los headers X-* del proxy.
- Sin API key real el tutor tira error (es el path que UI-8 maneja; en prod anda). `LLM_PROVIDER=mock` NO alcanza en dev (el resolver toma la key placeholder del `.env`).
- Los `vite.config.ts` inyectan la identidad dev; sincronizarlos con el seed activo (gotcha del CLAUDE.md).
