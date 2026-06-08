-- ============================================================================
-- Migration 05 — Ruta personala (home_station + main_station)
-- ============================================================================
-- Adauga suportul pentru:
--   * users.home_station_id   = statia de domiciliu declarata de pasager
--   * universities.main_station_id = statia centrului universitar
--
-- Folosit de routerul de bilete pentru a aplica reducerea de 90% (OUG 11/2024)
-- DOAR pe ruta personala home_station <-> university.main_station. Pe alte
-- rute se aplica tariful intreg, conform legii.
--
-- Idempotent — poate fi rulat de mai multe ori fara probleme.
-- Pe deploy curat, schema.sql contine deja aceste coloane si FK-uri.
-- Acest fisier exista pentru a putea fi rulat pe DB-uri EXISTENTE
-- care au fost initializate cu o versiune mai veche a schemei.
-- ============================================================================

-- 1. users.home_station_id
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS home_station_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_home_station'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_home_station
            FOREIGN KEY (home_station_id) REFERENCES stations(station_id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_home_station
    ON users(home_station_id) WHERE home_station_id IS NOT NULL;

-- 2. universities.main_station_id
ALTER TABLE universities
    ADD COLUMN IF NOT EXISTS main_station_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_universities_main_station'
    ) THEN
        ALTER TABLE universities
            ADD CONSTRAINT fk_universities_main_station
            FOREIGN KEY (main_station_id) REFERENCES stations(station_id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_universities_main_station
    ON universities(main_station_id) WHERE main_station_id IS NOT NULL;

-- 3. Populez statia centrului universitar pentru cele 3 universitati demo
-- (toate sunt in Bucuresti, deci main_station = Bucuresti Nord Gr.A)
UPDATE universities
SET main_station_id = (
    SELECT station_id FROM stations WHERE name = 'Bucureşti Nord Gr.A' LIMIT 1
)
WHERE short_name IN ('UPB', 'ASE', 'UNIBUC')
  AND main_station_id IS NULL;
