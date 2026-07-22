## 1. Gates previos

- [ ] 1.1 Confirmar que `multi-language-research-integrity` está mergeada. Esta change es la que hace un ejercicio Java alcanzable por un alumno: sin la segmentación por lenguaje, el corpus de la tesis se mezcla desde el primer episodio sin ningún error visible.
- [ ] 1.2 Cargar la skill `impeccable` antes de tocar UI y pasar sus gates (`PRODUCT.md`, `DESIGN.md`, shape brief confirmado). No se saltean.
- [ ] 1.3 Consultar con Ana Garis el diff del prompt del tutor. Son dos líneas de generalización de ejemplos — llevar el diff concreto, no la descripción.

## 2. Tipos y transporte del lenguaje

- [ ] 2.1 Agregar el lenguaje a los tipos del cliente HTTP de web-student (`lib/api.ts:584-618,919-941`).
- [ ] 2.2 Agregar el lenguaje a los tipos del cliente HTTP de web-teacher (`lib/api.ts:1904-1945`).
- [ ] 2.3 Verificar que el lenguaje llega desde el endpoint que resuelve los ejercicios de una TP, sin pedirle nada extra al backend.

## 3. UI del docente

- [ ] 3.1 Selector de lenguaje en el formulario de ejercicios, en el grid de datos básicos junto a unidad temática y dificultad (`views/EjerciciosView.tsx:684`).
- [ ] 3.2 Lenguaje visible en el listado del banco.
- [ ] 3.3 Bloqueo de selección de lenguaje distinto en el modal de composición de TP (`views/TareasPracticasView.tsx`), con explicación visible.
- [ ] 3.4 Liberar el bloqueo al deseleccionar todos los ejercicios.
- [ ] 3.5 🔴 Corregir el ternario que rotula tipos de caso de prueba. Hoy es `type === "stdin_stdout" ? "stdin/stdout" : "pytest"` — con el tipo nuevo, Java se rotula como pytest. Está en el preview de casos y en la tabla de resultados.
- [ ] 3.6 Advertir al crear un ejercicio Java que todavía no podrá verificarse con el panel de prueba (ver 6.2).

## 4. UI del alumno

- [ ] 4.1 Badge de lenguaje en el selector de tareas (`components/TareaSelector.tsx`), en el encabezado de cada tarjeta junto al código y título. El archivo hoy no importa `Badge` de `@platform/ui`.
- [ ] 4.2 Badge en la cabecera del editor, reemplazando el `badge="Python"` fijo (`pages/EpisodePage.tsx:755`).
- [ ] 4.3 Usar variante neutra del badge. No inventar colores por lenguaje: el sistema reserva el color para lo que tiene carga semántica (severidad, niveles N1–N4, apropiación).

## 5. Editor

- [ ] 5.1 Ampliar el tipo de la prop de lenguaje de `CodeEditor`, hoy una unión de un solo miembro (`CodeEditor.tsx:114`).
- [ ] 5.2 Pasar el lenguaje real a Monaco al crear el modelo. El paquete ya se importa completo sin tree-shaking de lenguajes, así que el tokenizer de Java ya viaja en el bundle — es un cambio de una palabra, sin costo de peso.
- [ ] 5.3 Quitar el hardcode del payload del evento de edición (`pages/EpisodePage.tsx:799`) y emitir el lenguaje real.
- [ ] 5.4 🔴 Deshabilitar ejecutar y probar cuando no hay entorno para el lenguaje, con explicación visible. Hoy el efecto de Pyodide sale temprano (`CodeEditor.tsx:442`), `loading` queda en `false`, el botón sigue habilitado (`:973`) y el guard de ejecución retorna sin hacer nada (`:747`): click sin ningún efecto ni mensaje.
- [ ] 5.5 Corregir el rótulo accesible del botón de ejecutar, hoy fijo en Python (`CodeEditor.tsx:975`).
- [ ] 5.6 Anunciar el panel de salida a tecnologías de asistencia. Hoy el bloque de error no tiene rol ni región activa, así que un alumno con lector de pantalla no se entera de un error salvo que navegue hasta ahí.
- [ ] 5.7 Verificar que el camino de Python queda idéntico: carga de Pyodide, ejecución, casos de prueba, historial de corridas y marcadores de error.

## 6. Verificación manual con navegador

- [ ] 6.1 Recorrer el flujo completo logueado: crear ejercicio Java, componer TP, publicar, abrir como alumno, escribir código, conversar con el tutor.
- [ ] 6.2 Confirmar el comportamiento del panel de prueba del docente con un ejercicio Java. Corre sobre un runner de Pyodide propio, separado del editor del alumno — sin ejecución server-side no puede verificar autoría. Documentar qué muestra hoy y confirmar que no produce resultados engañosos.
- [ ] 6.3 Verificar con lector de pantalla los estados nuevos.

## 7. Prompt del tutor v1.3.0

- [ ] 7.1 Crear `ai-native-prompts/prompts/tutor/v1.3.0/system.md` generalizando las dos menciones a Python (líneas 47 y 133 de v1.2.0). Nada más: el método queda idéntico.
- [ ] 7.2 Crear `v1.3.0/manifest.yaml` con el hash del contenido declarado. Es lo que faltó en v1.2.0 y lo que permitió que se editara in-place sin que el cargador lo detectara.
- [ ] 7.3 Actualizar el manifiesto global y el config efectivo del tutor **en el mismo commit**. El servicio no lee el manifiesto en runtime; si divergen, las interfaces informan una versión y la trazabilidad registra otra.
- [ ] 7.4 Test golden del contenido de v1.3.0. Hoy no existe ninguno para v1.2.0.
- [ ] 7.5 Actualizar el test que verifica la alineación entre manifiesto y config. Se edita in-place, no se crea uno nuevo por versión.
- [ ] 7.6 Actualizar los rótulos de versión visibles en la UI.

## 8. Contexto y generadores

- [ ] 8.1 Rotular el bloque de código inicial con el lenguaje del ejercicio (`services/tutor_core.py:1931`). Es el único fence hardcodeado del builder: el código que el alumno escribe en vivo ya usa uno genérico.
- [ ] 8.2 Variante Java de `ejercicio_generator`, con progresión de dificultad propia (básica: tipos primitivos, entrada/salida; intermedia: métodos, arreglos, métodos de `String`; avanzada: clases, excepciones, colecciones) y el tipo de caso de prueba de Java.
- [ ] 8.3 Variante Java de `tp_generator`. Está tan atado a Python como el anterior: su tabla de construcciones por dificultad es sintaxis Python literal bajo una regla marcada "ESTRICTO".
- [ ] 8.4 Resolver la variante de prompt según el lenguaje solicitado. Hoy ambos generadores usan una versión fija de config, sin selección dinámica.
- [ ] 8.5 Verificar que una TP generada en Java pasa la validación de un solo lenguaje y se puede publicar.

## 9. Cierre

- [ ] 9.1 Smoke test del flujo de autoría Java, de creación a publicación.
- [ ] 9.2 `pnpm test` de las apps tocadas y `make test-fast` en verde.
- [ ] 9.3 Verificar que el hash de configuración del clasificador y la versión del etiquetador no cambiaron.
- [ ] 9.4 Actualizar `CLAUDE.md` si cambió el conteo de smoke tests.
