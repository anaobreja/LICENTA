-- DEPRECATED / no-op safety net
--
-- Coloanele GPS + indecsii (latitude, longitude, is_university_hub,
-- student_count, universities_count, notes) sunt acum definite direct
-- in schema.sql, asa cum cere review-ul coordonatorului
-- ("schema unica, fara ALTER TABLE la runtime").
--
-- Fisierul este pastrat doar pentru compatibilitate cu baze de date
-- vechi care au fost initializate cu schema veche. Pe orice deploy
-- nou (test DB, Render, Docker) nu mai este necesar.
ALTER TABLE stations
  ADD COLUMN IF NOT EXISTS latitude  NUMERIC(9, 6),
  ADD COLUMN IF NOT EXISTS longitude NUMERIC(9, 6),
  ADD COLUMN IF NOT EXISTS is_university_hub BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS student_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS universities_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS notes TEXT;

CREATE INDEX IF NOT EXISTS idx_stations_geo
  ON stations(latitude, longitude)
  WHERE latitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_stations_university_hub
  ON stations(is_university_hub)
  WHERE is_university_hub = TRUE;
