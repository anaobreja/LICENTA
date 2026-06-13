-- ============================================================================
-- Migrare 09: View pentru monitorizarea calitatii GPS-urilor stațiilor.
-- ============================================================================
-- Context: dupa rularea geocode_stations_v2.py, fiecare statie are
-- coloana `gps_source` care indica de unde provin coordonatele (manual,
-- interpolated, osm-exact, osm-bbox, nominatim, NULL, blacklisted).
--
-- View-ul `v_stations_gps_quality` ofera o vedere consolidata pentru
-- demonstratia de licenta si pentru debug-ul re-geocodarilor viitoare.
-- ============================================================================

-- Coloana gps_source poate sa existe deja (creata de scriptul Python).
-- Idempotent:
ALTER TABLE stations
    ADD COLUMN IF NOT EXISTS gps_source TEXT;

COMMENT ON COLUMN stations.gps_source IS
    'Sursa coordonatelor GPS: manual | interpolated | osm-exact | '
    'osm-shorter | osm-firstword-unique | osm-firstword_bbox | '
    'osm-substring_bbox | nominatim | blacklisted | NULL';

-- ----------------------------------------------------------------------------
-- View principal: distributia sursei + numar de rute afectate
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_stations_gps_quality AS
WITH base AS (
    SELECT
        s.station_id,
        s.name,
        s.code,
        s.city,
        s.latitude,
        s.longitude,
        s.gps_source,
        s.latitude IS NOT NULL AS has_gps,
        EXISTS (
            SELECT 1 FROM route_stops rs
            WHERE rs.station_id = s.station_id
              AND rs.is_commercial_stop = TRUE
        ) AS is_commercial_anywhere,
        (SELECT COUNT(*) FROM route_stops rs
            WHERE rs.station_id = s.station_id) AS appearances_on_routes
    FROM stations s
    WHERE s.code LIKE 'CFR-%'
)
SELECT
    station_id,
    name,
    code,
    city,
    latitude,
    longitude,
    gps_source,
    has_gps,
    is_commercial_anywhere,
    appearances_on_routes,
    CASE
        WHEN has_gps AND gps_source = 'manual'         THEN 'A: manual (verificat)'
        WHEN has_gps AND gps_source LIKE 'osm-exact%'  THEN 'B: OSM exact name'
        WHEN has_gps AND gps_source LIKE 'osm-shorter%' THEN 'B: OSM exact name'
        WHEN has_gps AND gps_source LIKE 'osm-firstword-unique%' THEN 'B: OSM exact name'
        WHEN has_gps AND gps_source LIKE 'osm-%bbox'   THEN 'C: OSM + route bbox'
        WHEN has_gps AND gps_source = 'interpolated'   THEN 'D: interpolated from neighbours'
        WHEN has_gps AND gps_source = 'nominatim'      THEN 'E: Nominatim search'
        WHEN has_gps AND gps_source IS NULL            THEN 'F: legacy (pre-v2 import)'
        WHEN NOT has_gps AND gps_source = 'blacklisted' THEN 'X: blacklisted (bad name match)'
        WHEN NOT has_gps                               THEN 'X: no GPS'
        ELSE 'Z: unknown'
    END AS quality_tier
FROM base;

COMMENT ON VIEW v_stations_gps_quality IS
    'Pivot pe stations: tier-uri A-F dupa increderea in GPS. '
    'A=manual, B=match exact OSM, C=OSM cu validare bbox de ruta, '
    'D=interpolare din vecini, E=Nominatim, F=geocodificare initiala. '
    'X=fara GPS sau blacklisted.';

-- ----------------------------------------------------------------------------
-- Quick summary view: raport agregat pentru dashboard / demo
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_stations_gps_summary AS
SELECT
    COUNT(*)                                         AS total_stations,
    COUNT(*) FILTER (WHERE has_gps)                  AS with_gps,
    COUNT(*) FILTER (WHERE NOT has_gps)              AS without_gps,
    ROUND(100.0 * COUNT(*) FILTER (WHERE has_gps) / COUNT(*), 1) AS coverage_pct,
    COUNT(*) FILTER (WHERE NOT has_gps AND is_commercial_anywhere) AS commercial_without_gps,
    COUNT(*) FILTER (WHERE has_gps AND gps_source = 'manual')      AS tier_a_manual,
    COUNT(*) FILTER (WHERE has_gps AND (
            gps_source LIKE 'osm-exact%' 
         OR gps_source LIKE 'osm-shorter%' 
         OR gps_source LIKE 'osm-firstword-unique%'
    )) AS tier_b_osm_exact,
    COUNT(*) FILTER (WHERE has_gps AND gps_source LIKE 'osm-%bbox') AS tier_c_osm_bbox,
    COUNT(*) FILTER (WHERE has_gps AND gps_source = 'interpolated') AS tier_d_interpolated,
    COUNT(*) FILTER (WHERE has_gps AND gps_source = 'nominatim')    AS tier_e_nominatim,
    COUNT(*) FILTER (WHERE has_gps AND gps_source IS NULL)          AS tier_f_legacy,
    COUNT(*) FILTER (WHERE gps_source = 'blacklisted')              AS blacklisted
FROM v_stations_gps_quality;

COMMENT ON VIEW v_stations_gps_summary IS
    'Sumar global: % acoperire GPS, distributie pe tier-uri de incredere.';

-- ----------------------------------------------------------------------------
-- Verificare: lista stațiilor problematice ramase (pentru demo)
-- ----------------------------------------------------------------------------
-- SELECT * FROM v_stations_gps_summary;
-- SELECT name, code, gps_source, appearances_on_routes
--   FROM v_stations_gps_quality
--  WHERE NOT has_gps AND is_commercial_anywhere
--  ORDER BY appearances_on_routes DESC;
