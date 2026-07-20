# Catálogo de Features — AI-Native N4

> Todas las funcionalidades de la plataforma, agrupadas por usuario. Estado al 2026-07-16 (rama `desarrollo-juani` → `main`).
> ✅ = en producción · 🔜 = pendiente · ⛔ = fuera de scope.
> Para el detalle técnico de QA/deploy ver `ESTADO-DESARROLLO-JUANI.md`.

---

## 👩‍🏫 Docente

| ID | Feature | Qué hace | Estado |
|----|---------|----------|--------|
| **F1** | Probar ejercicio | Corre el código del ejercicio contra sus test cases (Pyodide) antes de asignarlo; ve qué pasa/falla. | ✅ |
| **F3** | RAG real observable | Ver los chunks generados de un material, probar una consulta de retrieval real (top-k con score) y reprocesar (reingest) un material. | ✅ |
| **F4** | Corrección con rúbrica | Califica cada entrega por criterio de la rúbrica, no una nota suelta. | ✅ |
| **F5** | Corrección en lote | Cola que auto-avanza a la siguiente entrega pendiente al guardar (X de N, saltar, salir). | ✅ |
| **F6** | Diff entre intentos | En el timeline del episodio, compara dos intentos de código (qué cambió, línea a línea). | ✅ |
| **F7** | Alertas accionables | En el home, señales de acompañamiento por comisión (regresión / bottom-quartile / tendencia a la baja) con drill-down. Respeta k-anonymity. | ✅ |
| **F10** | Feature flags | Activar/desactivar features por entorno. | ✅ |
| **F11** | Uso y costo de IA (BYOK) | El docente ve consumo/costo de su clave de proveedor. | ✅ |
| **F12** | Preview "como alumno" | Vista previa del ejercicio desde la óptica del alumno (limitada — ver F16 propuesta). | ✅ |
| **F13** | Export Caliper/xAPI | Exporta la actividad en estándares educativos anonimizados. | ✅ |
| **F14** | Editor de rúbrica por ejercicio | Arma la rúbrica estructurada de cada ejercicio. | ✅ |

## 🎓 Alumno

| ID | Feature | Qué hace | Estado |
|----|---------|----------|--------|
| **F1** | Probar mi código | Corre su código contra los test cases públicos (Pyodide), emite el evento N4. | ✅ |
| **F8** | Citas del RAG | Ve de qué material se apoyó el tutor ("Basado en: …"). | ✅ |
| **F9** | Mi progreso | Vista longitudinal no-reificante de su propia evolución. | ✅ |
| **UI-1..8** | Interfaz del episodio | Anotaciones N2, indicador de nivel N4, markdown en el chat, countdown, auto-skip de unidades, y **UI-8: si el tutor falla NO cierra el episodio — muestra "reintentá"**. | ✅ |
| **ED-1..8** | Editor de código | Maximizar, layout persistido, tamaño de fuente, errores en la línea (Monaco), restaurar plantilla, salida redimensible con pestañas, historial de corridas. | ✅ |

## 🔑 BYOK (claves de proveedor de IA)

| ID | Feature | Qué hace | Estado |
|----|---------|----------|--------|
| **BK-1..4** | BYOK descubrible | Nav "IA · Claves de proveedor", banner, CTA y hints para que el docente cargue su clave. | ✅ |
| **F11** | Uso/costo | (ver Docente) | ✅ |

## 🧩 Fricciones UX (FR-1..10)
Búsquedas (banco/alumnos), multiselect para componer TP con paso obvio, paginación "cargar más", editor de rúbrica, banners de éxito, confirmaciones consistentes, empty states. ✅

## 🔒 Plataforma / Seguridad (A0.1–A0.7)
Firma del gateway entre servicios, sin leaks cross-tenant, el alumno no ve test cases ocultos ni soluciones, auth en governance, RLS validado (activo Y forzado), sin IDOR, rate-limit del invite code. **Código listo, se activa por flags en prod.** ✅ (activar)

## ⚙️ Integridad (tesis-crítico)
CTR append-only con `next_seq` atómico (Redis INCR) + idempotencia — carrera de `integrity_compromised` cerrada de raíz. ✅

---

## 🔜 Pendientes / Propuestas

| ID | Feature | Qué haría | Estado |
|----|---------|-----------|--------|
| **F16** *(propuesta)* | Preview del episodio del alumno | El docente ve y **prueba** el episodio EXACTO que ve el alumno (chat con el tutor, editor, indicador N4) — en modo **sandbox** que NO contamina el CTR ni las analíticas. | 🔜 a diseñar |
| **F2b/F5b…** | Perf del episodio | P-6/P-7/P-16 (re-render del chat, clasificación async, Pyodide en worker). | 🔜 opcional |
| **F15** | Corrección asistida por IA | — | ⛔ vive en active-ia, fuera de scope |
