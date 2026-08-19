-- Consultas de solo lectura del almacen de la bitacora (filas 3 a 7 de la Tabla IV).
--
-- Uso:
--     psql "$CTR_STORE_URL" -f scripts/volumen-almacen.sql
--
-- Son SOLO LECTURA: no hay INSERT, UPDATE ni DELETE. La bitacora es append-only
-- y estas consultas no la tocan.
--
-- Complementan a `scripts/bench-tabla-iv.py`, que mide las filas de computo.
-- Juntos cubren la Tabla IV entera.
--
-- IMPORTANTE sobre unidades: `pg_size_pretty` y `pg_total_relation_size` usan
-- potencias de 1024. Si el paper publica "MB", tiene que declarar que son MiB;
-- con MB decimales la columna entera se corre ~4,6 %.

\echo ''
\echo '== FECHA DE CORTE Y VOLUMEN =============================================='
-- El paper debe declarar esta fecha junto a la tabla: el almacen crece, y sin
-- corte declarado un revisor que consulte despues ve otros numeros.
SELECT
    now()                                   AS medido_en,
    (SELECT count(*) FROM events)           AS eventos,
    (SELECT count(*) FROM episodes)         AS episodios,
    (SELECT count(DISTINCT comision_id) FROM episodes) AS comisiones,
    round((SELECT count(*) FROM events)::numeric
          / NULLIF((SELECT count(*) FROM episodes), 0), 1) AS eventos_por_episodio;

\echo ''
\echo '== FILA 4: TAMANO EN DISCO ==============================================='
SELECT
    pg_size_pretty(pg_total_relation_size('events'))   AS eventos_total,
    pg_size_pretty(pg_relation_size('events'))         AS eventos_tabla,
    pg_size_pretty(pg_total_relation_size('episodes')) AS episodios_total,
    pg_size_pretty(
        pg_total_relation_size('events') + pg_total_relation_size('episodes')
    ) AS almacen_total;

\echo ''
\echo '== FILA 3: BYTES POR EVENTO EN DISCO ====================================='
-- Cociente disco/eventos. OJO: no es lo mismo que el tamano canonico que mide
-- el banco de pruebas — ese es el buffer que se hashea, este incluye indices y
-- overhead de fila. Publicarlos en la misma celda exige aclarar que son dos
-- poblaciones distintas.
SELECT
    round(pg_total_relation_size('events')::numeric
          / NULLIF((SELECT count(*) FROM events), 0), 1) AS bytes_por_evento_disco;

\echo ''
\echo '== FILA 5: COPIAS DE ESTADO (snapshots de codigo) ========================'
-- La unica fila que exige de verdad una consulta: no se deriva por aritmetica
-- de las otras. Es el campo que domina el almacenamiento.
SELECT
    count(*) FILTER (WHERE payload ? 'snapshot')            AS eventos_con_snapshot,
    pg_size_pretty(sum(octet_length(payload->>'snapshot'))) AS bytes_snapshot,
    round(100.0 * sum(octet_length(payload->>'snapshot'))
          / NULLIF(pg_total_relation_size('events'), 0), 1) AS pct_del_disco,
    round(100.0 * sum(octet_length(payload->>'snapshot'))
          / NULLIF(sum(octet_length(payload::text)), 0), 1) AS pct_del_payload
FROM events;

\echo ''
\echo '== FILA 6: SOBRECOSTO DE DIGESTS ========================================='
-- Los tres hashes del encadenamiento, que es lo que el paper reporta...
SELECT
    pg_size_pretty(sum(octet_length(self_hash)
                     + octet_length(chain_hash)
                     + octet_length(prev_chain_hash))) AS hashes_de_cadena,
    round(100.0 * sum(octet_length(self_hash)
                    + octet_length(chain_hash)
                    + octet_length(prev_chain_hash))
          / NULLIF(pg_total_relation_size('events'), 0), 1) AS pct_del_disco
FROM events;

-- ...y los dos de versionado, que el paper NO cuenta en esa fila aunque
-- tambien son sobrecosto estructural de una propiedad del nucleo.
SELECT
    pg_size_pretty(sum(octet_length(prompt_system_hash)
                     + octet_length(classifier_config_hash))) AS hashes_de_versionado,
    round(100.0 * sum(octet_length(prompt_system_hash)
                    + octet_length(classifier_config_hash))
          / NULLIF(pg_total_relation_size('events'), 0), 1) AS pct_del_disco
FROM events;

\echo ''
\echo '== FILA 7: LINEALIDAD DEL CRECIMIENTO ===================================='
-- Bytes acumulados cada 10.000 eventos, en orden de insercion. La pendiente de
-- esta serie es el "MB por cada 1000 eventos" que publica el paper, y su R2 es
-- la evidencia de linealidad. Con estos puntos se puede reajustar la regresion.
WITH ordenados AS (
    SELECT
        row_number() OVER (ORDER BY persisted_at, id) AS n,
        octet_length(payload::text)
          + octet_length(self_hash) + octet_length(chain_hash)
          + octet_length(prev_chain_hash) + octet_length(prompt_system_hash)
          + octet_length(classifier_config_hash) + 120 AS bytes_fila
    FROM events
)
SELECT
    (n / 10000) * 10000                            AS hasta_evento,
    pg_size_pretty(sum(sum(bytes_fila)) OVER (ORDER BY n / 10000)) AS acumulado
FROM ordenados
GROUP BY n / 10000
ORDER BY 1;

\echo ''
\echo '== CONTROL: INTEGRIDAD DECLARADA ========================================'
-- No es de la Tabla IV, pero si algun episodio figura comprometido, cualquier
-- numero de arriba se lee distinto. Tiene que dar 0.
SELECT count(*) FILTER (WHERE integrity_compromised) AS episodios_comprometidos,
       count(*)                                      AS episodios_totales
FROM episodes;
\echo ''
