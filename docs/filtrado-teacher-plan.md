# Filtrado de vistas del docente — plan para mañana

## 🐛 Síntoma (reportado por Juani, 2026-06-01)

Logueado como docente de una **comisión y carrera NUEVAS**, en el panel docente
aparecen las **Unidades, Banco de ejercicios, Trabajos Prácticos, Materiales y
Correcciones de OTRO docente** (de otra carrera/comisión). O sea: **las vistas no
aíslan los datos por el docente / su contexto académico** — muestran datos cruzados.

## 🎯 Estado deseado (por eje de filtrado)

| Vista | Debe filtrar por | Hoy filtra por | Acción |
|---|---|---|---|
| Banco de ejercicios (`EjerciciosView`) | **materia** | `materia_id` OPCIONAL → si vacío toma "la primera materia" global | hacer estricto: materia de la comisión activa; si no hay, vacío |
| Materiales (`MaterialesView`) | **materia** | deriva materia_id de la comisión | verificar que filtre estricto (no global) |
| Unidades (`UnidadesView`) | **profesor** (docente logueado) | `comision_id` | agregar filtro `created_by` (backend + front) |
| Trabajos Prácticos (`TareasPracticasView`) | **profesor** | `comision_id` | agregar filtro `created_by` (backend + front) |
| Correcciones (`CorreccionesView`) | **comisión** | `comision_id` | ✅ ok — pero ver "causa raíz" abajo |
| Plantillas (`TemplatesView`) | — | — | ✅ YA sacada del menú (commit 171faf4) |

## 🔎 Causa raíz probable (revisar PRIMERO)

El teacher elige una **comisión** (ComisionSelector). Sospechas a verificar:

1. **El ComisionSelector por defecto** puede estar cayendo a una comisión global (de otro
   docente) en vez de a las del docente logueado. Verificar que `/comisiones/mis` devuelva
   SOLO las del docente (filtra por `user_id` en `usuarios_comision`) y que el selector use esas.
   - Archivos: `apps/web-teacher/src/components/ComisionSelectorRouted.tsx`, hooks de contexto,
     y `comision_service.list_for_user`.
2. Con la comisión correcta, **derivar materia_id de esa comisión** para las vistas "por materia".
3. Las vistas "por profesor" (unidades, TPs) ignoran al docente — necesitan filtro nuevo.

## 🛠️ Cambios concretos

### Backend (academic-service)
- `routes/unidades.py` (+ service): aceptar filtro `created_by` (= `user.id`) al listar.
- `routes/tareas_practicas.py` (+ service): listar TPs del docente (`created_by = user.id`),
  no por comisión.
- Verificar que Ejercicios/Materiales exijan `materia_id` y NO caigan a "primera materia" global.

### Frontend (web-teacher)
- `EjerciciosView`: `materia_id` obligatorio (de la comisión activa). Si no hay → estado vacío
  "seleccioná una comisión", no datos de otra carrera.
- `MaterialesView`: idem (ya deriva materia; asegurar estricto).
- `UnidadesView` / `TareasPracticasView`: filtrar por la identidad del docente, no por comisión.
- Revisar el **ComisionSelector**: que liste solo las comisiones del docente logueado.

## ⚠️ Riesgo
Filtrado de datos académicos mal hecho = datos cruzados entre carreras/docentes (el bug actual).
Hacerlo con foco, verificando CADA vista con un docente nuevo (sin datos) que NO debe ver nada ajeno.

## ✅ Test de aceptación
Con un docente NUEVO (comisión/carrera nuevas, sin contenido cargado):
- Unidades, Banco, TPs, Materiales → **vacíos** (no los del otro docente).
- Correcciones → solo entregas de SU comisión.
- Al cargar contenido propio → aparece solo lo suyo.

## Contexto (cómo quedó la auth, para retomar)
- Auth real con Clerk ACTIVA en prod (gateway valida JWT, identidad real). Ver `docs/auth-clerk-gateway-plan.md`.
- Rol: default alumno; docente si su email está en `usuarios_comision` (asignado por el admin).
- Ruteo: al cargar `/` (alumno), si es docente → redirige a `/teacher/`.
- invite_code: se genera al crear la comisión.
