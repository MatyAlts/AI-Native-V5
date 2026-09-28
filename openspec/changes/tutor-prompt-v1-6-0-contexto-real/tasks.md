# Tareas — tutor prompt v1.6.0

Orden deliberado: los tests de anclaje (1.x) van **antes** de escribir el prompt,
para que el ciclo TDD tenga algo que ver fallar. Un test escrito despues del
contenido que verifica no es una red: es una descripcion.

## 1. Anclajes de contenido (RED primero)

- [x] 1.1 Test: existe `ai-native-prompts/prompts/tutor/v1.6.0/system.md` en la
      ruta que sirve el governance-service. Debe fallar hoy.
- [x] 1.2 Test: el prompt v1.6.0 **NO** contiene la afirmacion falsa sobre el
      enunciado (`"no conoces el enunciado"` y variantes). Anclar por frase, no
      por numero de linea — el numero se mueve con cualquier edicion.
- [x] 1.3 Test: el prompt v1.6.0 **SI** contiene la prohibicion de pedir codigo
      pegado. Que falle de verdad si alguien revierte C2.
- [x] 1.4 Test: el prompt v1.6.0 **SI** contiene la prohibicion de derivar a
      herramientas externas (C3).
- [x] 1.5 Test: el prompt v1.6.0 **conserva** la instruccion valida
      `"NO supongas requisitos que el enunciado no establecio"`. Este test es el
      guardian del alcance: falla si alguien reescribio de mas.

## 2. El contenido

- [x] 2.1 Copiar `v1.5.0/system.md` a `v1.6.0/system.md`, byte a byte, sin tocar
      nada. Commit de la copia limpia primero, para que el diff posterior muestre
      **solo** los tres cambios.
- [x] 2.2 C1 — corregir la seccion "Contexto del TP". Verificar contra
      `tutor_core.py` (lineas 425, 623, 2396-2433) **que se inyecta exactamente**
      y escribir solo lo confirmado. Lo que se inyecta condicionalmente se
      escribe condicionalmente.
- [x] 2.3 C2 — seccion nueva sobre el codigo del estudiante: lo ve numerado,
      cita lineas, nunca pide pegado, y que hacer cuando todavia no hay codigo.
- [x] 2.4 C3 — prohibicion de derivar a herramientas externas, con el registro
      de las demas reglas duras del documento.
- [x] 2.5 Verificar registro: sin tildes, sin emojis, imperativo en segunda
      persona. Cotejar contra el resto del archivo, no contra la intuicion.

## 3. Los dos literales de version

- [x] 3.1 `ai-native-prompts/manifest.yaml`: entrada de v1.6.0 con fecha y
      motivo, respetando el formato de las lineas 13-24.
- [x] 3.2 `apps/tutor-service/src/tutor_service/config.py:96`:
      `default_prompt_version = "v1.6.0"`.
- [x] 3.3 Correr `apps/tutor-service/tests/unit/test_config_prompt_version.py`.
      Si su test de consistencia **no** falla con un solo literal movido, el test
      no cubre lo que dice cubrir: extenderlo.

## 4. Verificacion

- [x] 4.1 Suite del tutor-service en verde, con el comando y el SHA.
- [x] 4.2 Diff completo `v1.5.0 → v1.6.0` de `system.md`, para revision humana
      linea por linea. Es contenido con coautoria.
- [x] 4.3 **NO correr builds** — prohibido por las reglas del proyecto.

## Fuera de alcance

- El metodo socratico, el tono, el banco de preguntas N1-N4, las misconceptions.
- `tutor_core.py` — la inyeccion ya funciona; el defecto esta en el prompt.
- Activar v1.6.0 en produccion. Eso es deploy, y va aparte.
