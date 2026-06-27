# Juez LLM del eje superficial↔reflexiva

Componente de contenido que clasifica el eje **superficial ↔ reflexiva** leyendo
la conversación del episodio con un LLM, en lugar del proxy conductual (`exp ≥ 0,4`,
número de ejecuciones) de `subgrupo.py` que da **κ ≈ 0** (azar) en ese eje.

Diseño de referencia: `Diseno-clasificador-cognitivo-LLM-v4`. Validación y datos:
informes en `~/manuales-n4/` (validación del clasificador, desacuerdos, plan).

## Principio: cirugía, no reemplazo

- **Etapa dura (sin cambios):** la delegación pasiva la decide el árbol con la
  señal de `overuse` (98 % de acuerdo con el criterio docente). No se toca.
- **Etapa cognitiva (este componente):** solo los episodios de **zona gris**
  (`colaborador_reflexivo` / `colaborador_funcional`, donde está el 89 % de los
  errores) pasan al juez LLM, que decide superficial vs reflexiva leyendo el
  contenido.

## Garantías de diseño implementadas

- **La regla la garantiza el código, no el LLM.** `regimen_segun_regla()` aplica
  la regla del manual a las 4 dimensiones que el modelo cita. Si el LLM devuelve
  un régimen que no respeta esa regla, se descarta (`estado="inconsistente"`) y
  va a revisión humana.
- **Ruteo a revisión humana** ante inconsistencia, baja confianza (< 0,70) o JSON
  inválido. Nunca se infiere una etiqueta de una salida dudosa.
- **Modo sombra:** el veredicto se persiste en `Classification.features['regimen_llm']`,
  sin tocar `appropriation` ni el `classifier_config_hash`. Aditivo y reversible.
- **Reproducibilidad por configuración fijada:** temperatura 0 + pinneo de modelo
  y `PROMPT_VERSION`, registrados en el resultado para auditoría.
- **Best-effort:** si el ai-gateway falla, se loguea y la clasificación oficial
  sigue intacta — el LLM nunca rompe el flujo.

## Archivos

| Archivo | Rol |
|---|---|
| `services/regimen_llm.py` | El juez: modelos, armado de contexto, prompt (system + few-shot + user), JSON schema, regla en código, `clasificar_regimen_llm`. |
| `services/clients.py` | `AIGatewayClient.complete` (patrón de academic-service). |
| `routes/classify_ep.py` | `_aplicar_juez_eje_fino_sombra` — enganche en modo sombra. |
| `config.py` | `eje_fino_llm_enabled` (OFF), `ai_gateway_url`, `eje_fino_model`. |
| `tests/unit/test_regimen_llm.py` | 14 tests (regla, consistencia, parseo, modo sombra). |
| `scripts/validar-eje-fino-llm.py` | Harness: corre el juez sobre N episodios y calcula κ vs gold. |
| `scripts/exportar-episodios-eje-fino.py` | Export BD → JSON para el harness. |

## Cómo validar (antes de activar)

```bash
# 1. Exportar los episodios del eje fino (gold + events) desde la BD de prod.
uv run python scripts/exportar-episodios-eje-fino.py \
    --classifier-db "$CLASSIFIER_DB_URL" --ctr-db "$CTR_STORE_URL" \
    --out episodios_eje_fino.json --solo-zona-gris

# 2. Correr el juez y medir el κ (requiere el ai-gateway corriendo + key BYOK).
uv run python scripts/validar-eje-fino-llm.py \
    --input episodios_eje_fino.json --tenant-id <UUID> --model gpt-4o \
    --out detalle.json
```

El harness reporta los estados (ok / inconsistente / baja_confianza / error) y el
**κ + AC1 + IC** del juez con `platform_ops.kappa_analysis` (la misma maquinaria
que produjo el κ 0,449 del clasificador actual). La mejora se lee como el delta
sobre el sub-eje (**κ ≈ −0,06** conductual).

**Sin fuga de datos (§6 del diseño):** los episodios usados como few-shot
(`01ab7004`, `23ad4ade`) NO deben estar en el conjunto de evaluación — el harness
avisa si los detecta. Para la validación final, correr en k-fold rotando los
few-shot por fold (un input por fold).

## Cómo activar

1. Validar (arriba) → confirmar que el κ del juez sube de ≈ 0.
2. Prender `EJE_FINO_LLM_ENABLED=true` (env) y deployar el classifier-service.
   A partir de ahí, cada clasificación de zona gris guarda el veredicto del juez
   en `features['regimen_llm']` (sombra, sin gobernar la etiqueta oficial).
3. **Promoción a oficial** (más adelante): hacer que `appropriation` de la zona
   gris se derive del juez → bump de `LABELER_VERSION` + reclasificación del
   histórico.

## Pendientes

- **3er ejemplo few-shot** (`_FEWSHOT` en `regimen_llm.py`): falta un caso real
  "verbaliza PERO autonomía=oráculo → SUPERFICIAL" para enseñar la condición (c).
  Debe extraerse de un episodio real del corpus, no fabricarse.
- **k-fold + ablation** en el harness: el k-fold con rotación de few-shot requiere
  ejemplos con las 4 dimensiones anotadas por docentes (hoy el corpus solo tiene
  la etiqueta final). El ablation (definiciones / +rúbrica / +few-shot) requiere
  variantes del system prompt. Ambos quedan como evolución del harness.
- **Enunciado del TP** en el modo sombra: hoy se pasa vacío; enriquecer desde
  `academic_main` mejoraría el contexto del juez.
