# Analisis de sensibilidad — override temporal de `anotacion_creada` (ADR-023, v1.1.0)

Generado por `scripts/g8a-sensitivity-analysis.py` (seed=42, episodios=2000, anotaciones totales=5137).

## Distribucion de anotaciones por nivel segun ventanas (N1, N4)

| Ventana N1 (s) | Ventana N4 (s) | Anot N1 | Anot N2 | Anot N4 | % N1 (vs baseline) | % N4 (vs baseline) |
|---:|---:|---:|---:|---:|---:|---:|
| 60 | 30 | 607 | 3675 | 855 | -52.7% | -51.0% |
| 90 | 30 | 953 | 3329 | 855 | -25.7% | -51.0% |
| 120 **(baseline)** | 60 | 1283 | 2109 | 1745 | +0.0% | +0.0% |
| 180 | 60 | 1315 | 2077 | 1745 | +2.5% | +0.0% |
| 180 | 120 | 1313 | 1921 | 1903 | +2.3% | +9.1% |
| 240 | 120 | 1343 | 1891 | 1903 | +4.7% | +9.1% |

## Ratio de tiempo por nivel (sobre el corpus completo)

| Ventana N1 (s) | Ventana N4 (s) | ratio N1 | ratio N2 | ratio N3 | ratio N4 | ratio meta |
|---:|---:|---:|---:|---:|---:|---:|
| 60 | 30 | 0.0131 | 0.5372 | 0.1514 | 0.2500 | 0.0483 |
| 90 | 30 | 0.0211 | 0.5291 | 0.1514 | 0.2500 | 0.0483 |
| 120 **(baseline)** | 60 | 0.0303 | 0.4956 | 0.1514 | 0.2743 | 0.0483 |
| 180 | 60 | 0.0313 | 0.4947 | 0.1514 | 0.2743 | 0.0483 |
| 180 | 120 | 0.0312 | 0.4907 | 0.1514 | 0.2783 | 0.0483 |
| 240 | 120 | 0.0320 | 0.4899 | 0.1514 | 0.2783 | 0.0483 |

## Lectura del analisis

- **Sensibilidad de N1**: estrechar la ventana N1 de 120s a 60s reduce `anotaciones_N1` en -52.7% (de 1283 a 607). Esas anotaciones se reasignan a N2 — el sesgo sub-reporta-N1 reaparece. Ampliar de 120s a 180s agrega solo +2.5% (saturacion por la mezcla del corpus: el 25% de anotaciones de lectura inicial cae mayoritariamente dentro de los primeros 120s).
- **Sensibilidad de N4**: ampliar la ventana N4 de 60s a 120s aumenta `anotaciones_N4` en +9.1% (de 1745 a 1903). La ventana baseline 60s es conservadora — anotaciones reflexivas con latencia 60-120s post `tutor_respondio` quedan etiquetadas N2 en el baseline.
- **El ratio total de tiempo por nivel es relativamente insensible** a la eleccion de ventanas porque las anotaciones suelen ser una fraccion pequena del total de eventos por episodio. El override afecta principalmente a la distribucion de `anotaciones` entre niveles, no a la composicion global del tiempo del episodio.

**Conclusion para el ADR-023**: las constantes baseline (120s / 60s) son razonables como operacionalizacion conservadora declarable. La sensibilidad no es despreciable — la decision de ventana mueve la asignacion de anotaciones entre N1 y N2 (y entre N4 y N2) en magnitudes que el reporte empirico debe declarar. El override completo via clasificacion semantica (G14, ADR-017) cierra esta sensibilidad a costa de introducir dependencia del modelo de embeddings — agenda Eje B post-defensa.

## Notas metodologicas

- **Corpus sintetico, no datos reales del piloto**. Distribucion de eventos generada con seed=42 y mezcla declarada en `_generate_episode` (25% lectura inicial, 30% post-tutor, 45% otros). Los porcentajes deltas dependen de esa mezcla — el analisis se debe recomputar contra el corpus real del piloto-1 al cierre del cuatrimestre.
- **El generador NO emite `lectura_enunciado`** — para aislar el efecto del override sobre `anotacion_creada` puro. En el corpus real, `lectura_enunciado` aporta a N1 independientemente del override.
- **El generador no emite `intento_adverso_detectado` ni `episodio_abandonado`** — el override no aplica a esos eventos.
