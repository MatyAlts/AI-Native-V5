-- Seed: unidad "test" + TP + ejercicio canónico "edad → categoría"
BEGIN;
SET LOCAL app.current_tenant = '7a7a143c-31f8-461b-be08-d86ac36b41a3';

-- 1) UNIDAD "test"
INSERT INTO unidades (id, tenant_id, comision_id, nombre, descripcion, orden, created_by)
VALUES (
  'aaaaaaaa-1111-1111-1111-000000000099'::uuid,
  '7a7a143c-31f8-461b-be08-d86ac36b41a3'::uuid,
  '7b18f4d8-24b7-4034-979e-1fd464939f0e'::uuid,
  'test',
  'Unidad de prueba para grabacion de video',
  99,
  'c8a54501-e2a5-434f-b043-83e11600eabc'::uuid
);

-- 2) EJERCICIO "edad → categoría"
INSERT INTO ejercicios (
  id, tenant_id, titulo, enunciado_md, inicial_codigo,
  unidad_tematica, dificultad,
  test_cases, rubrica, banco_preguntas, misconceptions,
  respuesta_pista, anti_patrones, heuristica_cierre,
  tutor_rules, prerequisitos, created_by, created_via_ai
)
VALUES (
  'bbbbbbbb-eeee-dddd-dddd-000000000099'::uuid,
  '7a7a143c-31f8-461b-be08-d86ac36b41a3'::uuid,
  'Categoria por edad',
  E'## Enunciado canonico\n\nEscribir un programa que solicite al usuario su edad e imprima por pantalla a cual de las siguientes categorias pertenece:\n\n- **nino/a**: menor de 12\n- **adolescente**: mayor o igual que 12 y menor que 18\n- **adulto/a joven**: mayor o igual que 18 y menor que 30\n- **adulto/a**: mayor o igual que 30\n\n### Casos borde a considerar\n\n11, 12, 17, 18, 29, 30. Probalos todos antes de dar por terminado el ejercicio.',
  E'# Escribi tu codigo Python aca\n# Pista: en el editor del browser, input() no funciona.\n# Probalo con un valor hardcodeado: edad = 15\n\nedad = 15\n\n# Tu codigo aca\n',
  'condicionales',
  'basica',
  -- test_cases
  '[
    {"input": "11", "expected": "nino/a"},
    {"input": "12", "expected": "adolescente"},
    {"input": "17", "expected": "adolescente"},
    {"input": "18", "expected": "adulto/a joven"},
    {"input": "29", "expected": "adulto/a joven"},
    {"input": "30", "expected": "adulto/a"}
  ]'::jsonb,
  -- rubrica
  '{
    "criterios": [
      {"nombre": "correctitud", "descripcion": "Clasifica correctamente las 6 edades frontera"},
      {"nombre": "claridad", "descripcion": "Usa elif en lugar de if encadenados redundantes"},
      {"nombre": "orden", "descripcion": "El orden de las condiciones es coherente con los rangos"},
      {"nombre": "casos_borde", "descripcion": "Considera explicitamente los limites 12, 18, 30"}
    ]
  }'::jsonb,
  -- banco_preguntas (N1-N4)
  '{
    "N1_lectura": [
      "Como pasarias de la representacion matematica de intervalos al codigo?",
      "Que diferencia conceptual existe entre menor que 12 y menor o igual que 12?",
      "Como identificarias si un intervalo es abierto, cerrado o semiabierto?"
    ],
    "N2_exploracion": [
      "Que pasaria si la edad ingresada fuera 12? Cae en nino o en adolescente?",
      "Y si fuera 17, 18, 29 o 30?",
      "Que patron observas en las edades 11, 12, 17, 18, 29 y 30?",
      "Como detectarias si dos categorias estan superpuestas?"
    ],
    "N3_codigo": [
      "Por que una condicion muy general al comienzo puede generar errores?",
      "Que ventaja tiene pensar las categorias como intervalos consecutivos?",
      "Como podrias reducir condiciones innecesarias usando evaluaciones previas?",
      "Que informacion ya conoces despues de que una condicion anterior fallo?"
    ],
    "N4_reflexion": [
      "Como relacionarias este ejercicio con la idea matematica de particion de conjuntos?",
      "Que pruebas necesitarias para demostrar que tu solucion funciona siempre?",
      "Que senales indicarian que el codigo sera dificil de mantener?",
      "Como anticiparias cambios futuros al disenar la solucion?"
    ]
  }'::jsonb,
  -- misconceptions (lo que el alumno confunde)
  '[
    {"id": "confusion_menor_igual", "descripcion": "Confundir < con <= en los limites. Ej: usar edad <= 12 para nino incluye el 12 que es adolescente."},
    {"id": "ifs_independientes", "descripcion": "Escribir if separados en lugar de elif. Multiples categorias se imprimen para una sola edad."},
    {"id": "orden_invertido", "descripcion": "Empezar por la categoria mas grande (adulto) sin pensar en el solapamiento de rangos."},
    {"id": "sin_else", "descripcion": "No agregar else final. Edades negativas o invalidas quedan sin clasificar."}
  ]'::jsonb,
  -- respuesta_pista (pistas escalonadas)
  '[
    {"trigger": "no_se", "pista": "Empeza identificando los limites: cuales son los numeros donde cambia la categoria?"},
    {"trigger": "limites_confusos", "pista": "Probaste con 12 y 11? Que devuelve tu codigo en cada uno?"},
    {"trigger": "elif_redundante", "pista": "Despues de que un if falla, que sabes seguro sobre la edad?"}
  ]'::jsonb,
  -- anti_patrones (patrones de codigo a evitar)
  '[
    {"patron": "edad <= 12 para nino", "porque": "incluye 12 que deberia ser adolescente"},
    {"patron": "if encadenados sin elif", "porque": "varias categorias se imprimen al mismo tiempo"},
    {"patron": "sin else final", "porque": "edades fuera de rango quedan sin clasificar"}
  ]'::jsonb,
  -- heuristica_cierre
  '{
    "criterios_cierre": [
      "El alumno probo las 6 edades frontera (11, 12, 17, 18, 29, 30)",
      "El alumno explica por que uso < en lugar de <= (o viceversa)",
      "El alumno verbaliza la propiedad de particion de los intervalos"
    ]
  }'::jsonb,
  -- tutor_rules
  '{
    "reglas_tutor": [
      "Nunca dar el codigo completo aunque lo pidan explicitamente",
      "Forzar al alumno a probar los casos frontera antes de declarar terminado",
      "Si confunde < y <=, no corregir directamente: pedir que pruebe con el valor frontera",
      "Si usa if encadenados sin elif, preguntar que pasa con edad=15"
    ]
  }'::jsonb,
  -- prerequisitos
  '{
    "conceptos_previos": ["operadores de comparacion", "if/elif/else", "tipos numericos"]
  }'::jsonb,
  'c8a54501-e2a5-434f-b043-83e11600eabc'::uuid,
  false
);

-- 3) TP "TP-EDAD-01"
INSERT INTO tareas_practicas (
  id, tenant_id, comision_id, codigo, titulo, enunciado,
  peso, estado, version, unidad_id, created_by, fecha_inicio, fecha_fin
)
VALUES (
  'cccccccc-1111-1111-1111-000000000099'::uuid,
  '7a7a143c-31f8-461b-be08-d86ac36b41a3'::uuid,
  '7b18f4d8-24b7-4034-979e-1fd464939f0e'::uuid,
  'TP-EDAD-01',
  'Clasificacion por edad',
  'Trabajo practico que cubre estructuras condicionales aplicadas a clasificacion por rangos numericos. Ver enunciado del ejercicio asociado.',
  1.0,
  'published',
  1,
  'aaaaaaaa-1111-1111-1111-000000000099'::uuid,
  'c8a54501-e2a5-434f-b043-83e11600eabc'::uuid,
  NOW() - INTERVAL '7 days',
  NOW() + INTERVAL '30 days'
);

-- 4) Asignar ejercicio al TP
INSERT INTO tp_ejercicios (tenant_id, tarea_practica_id, ejercicio_id, orden, peso_en_tp)
VALUES (
  '7a7a143c-31f8-461b-be08-d86ac36b41a3'::uuid,
  'cccccccc-1111-1111-1111-000000000099'::uuid,
  'bbbbbbbb-eeee-dddd-dddd-000000000099'::uuid,
  1,
  1.0
);

COMMIT;

-- Verificacion
SELECT 'UNIDAD' as tipo, id::text as uuid, nombre as nombre FROM unidades WHERE id = 'aaaaaaaa-1111-1111-1111-000000000099'
UNION ALL
SELECT 'EJERCICIO', id::text, titulo FROM ejercicios WHERE id = 'bbbbbbbb-eeee-dddd-dddd-000000000099'
UNION ALL
SELECT 'TP', id::text, titulo FROM tareas_practicas WHERE id = 'cccccccc-1111-1111-1111-000000000099'
UNION ALL
SELECT 'ASOCIACION', ejercicio_id::text, 'orden=' || orden::text FROM tp_ejercicios WHERE tarea_practica_id = 'cccccccc-1111-1111-1111-000000000099';
BEGIN;
SET LOCAL app.current_tenant = '7a7a143c-31f8-461b-be08-d86ac36b41a3';

UPDATE ejercicios SET
  banco_preguntas = '{
    "n1": [
      {"texto": "Como pasarias de la representacion matematica de intervalos al codigo Python?", "senal_comprension": "Menciona < / <= y conecta el simbolo con el rango", "senal_alerta": "Confunde el limite o no distingue abierto/cerrado"},
      {"texto": "Que diferencia conceptual existe entre menor que 12 y menor o igual que 12?", "senal_comprension": "Reconoce que el 12 esta o no esta segun el operador", "senal_alerta": "Dice que son lo mismo"},
      {"texto": "Como identificarias si un intervalo es abierto, cerrado o semiabierto?", "senal_comprension": "Lee la consigna y traduce mayor/igual a un simbolo", "senal_alerta": "No usa los bordes para clasificar"}
    ],
    "n2": [
      {"texto": "Que pasaria si la edad ingresada fuera 12? Cae en nino o en adolescente?", "senal_comprension": "Identifica el caso frontera y lo discute", "senal_alerta": "Salta este caso o asume que es nino sin pensar"},
      {"texto": "Que patron observas en las edades 11, 12, 17, 18, 29 y 30?", "senal_comprension": "Ve los pares como bordes de cada categoria", "senal_alerta": "No los reconoce como casos especiales"},
      {"texto": "Como detectarias si dos categorias estan superpuestas?", "senal_comprension": "Prueba el limite y ve si dos prints aparecen", "senal_alerta": "No prueba ni los analiza"}
    ],
    "n3": [
      {"texto": "Por que una condicion muy general al comienzo puede generar errores?", "senal_comprension": "Razona que captura mas casos de lo deseado", "senal_alerta": "No relaciona orden con resultado"},
      {"texto": "Que ventaja tiene pensar las categorias como intervalos consecutivos?", "senal_comprension": "Conecta con elif y particion", "senal_alerta": "No ve la conexion con elif"},
      {"texto": "Que informacion ya conoces despues de que una condicion anterior fallo?", "senal_comprension": "Articula que la negacion del if anterior se asume verdadera", "senal_alerta": "No ve que elif redondea el chequeo"}
    ],
    "n4": [
      {"texto": "Como relacionarias este ejercicio con la idea matematica de particion de conjuntos?", "senal_comprension": "Menciona disjunto y union cubre todo", "senal_alerta": "No ve la abstraccion"},
      {"texto": "Que pruebas necesitarias para demostrar que tu solucion funciona siempre?", "senal_comprension": "Lista los 6 limites + casos extremos", "senal_alerta": "Solo prueba un par de casos al azar"},
      {"texto": "Como anticiparias cambios futuros al disenar la solucion?", "senal_comprension": "Sugiere extraer los rangos a una estructura de datos", "senal_alerta": "No pensa en mantenibilidad"}
    ]
  }'::jsonb,
  misconceptions = '[
    {"descripcion": "Usar <= en lugar de < en el limite, incluyendo el 12 en la categoria nino cuando deberia ser adolescente", "probabilidad_estimada": 0.65, "pregunta_diagnostica": "Que devuelve tu codigo si la edad es exactamente 12?"},
    {"descripcion": "Encadenar if independientes en lugar de elif, lo que hace que varias categorias se impriman para una sola edad", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "Que pasa con edad=15 en tu codigo? Cuantos prints ves?"},
    {"descripcion": "No incluir un else final, dejando edades negativas o invalidas sin clasificar", "probabilidad_estimada": 0.3, "pregunta_diagnostica": "Que devuelve tu codigo si la edad es -5?"}
  ]'::jsonb,
  respuesta_pista = '[
    {"nivel": 1, "pista": "Empeza identificando los limites: cuales son los numeros donde cambia la categoria?"},
    {"nivel": 2, "pista": "Probaste con 12 y con 11? Que devuelve tu codigo en cada uno?"},
    {"nivel": 3, "pista": "Despues de que un if con < 12 falla, que sabes seguro sobre la edad? Como simplifica eso la siguiente condicion?"},
    {"nivel": 4, "pista": "Si los rangos son disjuntos y cubren todos los enteros positivos, podes usar elif sin repetir el limite inferior"}
  ]'::jsonb,
  anti_patrones = '[
    {"patron": "edad <= 12 para nino", "descripcion": "Incluir el 12 en nino contradice la consigna que dice nino menor de 12", "mensaje_orientacion": "Preguntale al estudiante que devuelve su codigo si la edad es exactamente 12"},
    {"patron": "if encadenados sin elif", "descripcion": "Multiples if independientes hacen que varias categorias se impriman simultaneamente", "mensaje_orientacion": "Pedile que pruebe con edad=15 y mire cuantos prints aparecen"},
    {"patron": "sin else final", "descripcion": "Sin else, edades negativas o no contempladas quedan sin clasificar silenciosamente", "mensaje_orientacion": "Que pasaria si la edad fuera -1? Como te enteras de que el codigo no clasifico nada?"}
  ]'::jsonb,
  heuristica_cierre = '{
    "tests_min_pasados": 6,
    "heuristica": "El alumno probo las 6 edades frontera (11, 12, 17, 18, 29, 30), verbalizo por que uso < en lugar de <=, y reconoce la propiedad de particion de los rangos"
  }'::jsonb,
  tutor_rules = '{
    "prohibido_dar_solucion": true,
    "forzar_pregunta_antes_de_hint": true,
    "nivel_socratico_minimo": 2,
    "instrucciones_adicionales": "Si confunde < y <=, no corregir directamente: pedir que pruebe con el valor frontera. Si usa if encadenados sin elif, preguntar que pasa con edad=15."
  }'::jsonb,
  prerequisitos = '{
    "sintacticos": ["if", "elif", "else", "operadores de comparacion < <= == >= >"],
    "conceptuales": ["intervalos numericos", "tipos primitivos int", "control de flujo"]
  }'::jsonb
WHERE id = 'bbbbbbbb-eeee-dddd-dddd-000000000099';

COMMIT;
SELECT 'OK' as resultado, titulo, jsonb_array_length(banco_preguntas->'n1') as n1_count FROM ejercicios WHERE id = 'bbbbbbbb-eeee-dddd-dddd-000000000099';
BEGIN;
SET LOCAL app.current_tenant = '7a7a143c-31f8-461b-be08-d86ac36b41a3';

UPDATE ejercicios SET
  test_cases = '[
    {"id": "t1", "name": "edad 11 nino", "type": "stdin_stdout", "code": "edad = 11", "expected": "nino/a", "is_public": true, "weight": 1.0},
    {"id": "t2", "name": "edad 12 adolescente (frontera)", "type": "stdin_stdout", "code": "edad = 12", "expected": "adolescente", "is_public": true, "weight": 2.0},
    {"id": "t3", "name": "edad 17 adolescente", "type": "stdin_stdout", "code": "edad = 17", "expected": "adolescente", "is_public": true, "weight": 1.0},
    {"id": "t4", "name": "edad 18 adulto joven (frontera)", "type": "stdin_stdout", "code": "edad = 18", "expected": "adulto/a joven", "is_public": true, "weight": 2.0},
    {"id": "t5", "name": "edad 29 adulto joven", "type": "stdin_stdout", "code": "edad = 29", "expected": "adulto/a joven", "is_public": true, "weight": 1.0},
    {"id": "t6", "name": "edad 30 adulto (frontera)", "type": "stdin_stdout", "code": "edad = 30", "expected": "adulto/a", "is_public": true, "weight": 2.0}
  ]'::jsonb,
  rubrica = '{
    "criterios": [
      {"nombre": "correctitud", "descripcion": "Clasifica correctamente las 6 edades frontera", "puntaje_max": 4.0},
      {"nombre": "claridad", "descripcion": "Usa elif en lugar de if encadenados redundantes", "puntaje_max": 2.0},
      {"nombre": "orden", "descripcion": "El orden de las condiciones es coherente con los rangos", "puntaje_max": 2.0},
      {"nombre": "casos_borde", "descripcion": "Considera explicitamente los limites 12, 18, 30", "puntaje_max": 2.0}
    ]
  }'::jsonb
WHERE id = 'bbbbbbbb-eeee-dddd-dddd-000000000099';

COMMIT;
