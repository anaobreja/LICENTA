-- =============================================================================
--  Migrare 07: Abonamente cu scope pe ruta + integrare cu bilete gratuite
-- =============================================================================
--
--  Adauga:
--    1. subscriptions.from_station_id, to_station_id (FK -> stations)
--       Pentru scope='route', identifica ruta exacta acoperita.
--    2. subscriptions.subscription_scope ('network' | 'route')
--       'route' = ruta exacta origin->destination (CFR-style abonamente regionale)
--       'network' = orice tren al operatorului (CFR Senior)
--       Default 'route' (cazul realist pentru studenti/naveta).
--    3. subscriptions.route_distance_km
--       Cache pentru calcul rapid de pret (evita JOIN cu routes la fiecare quote).
--    4. tickets.uses_subscription_id (FK -> subscriptions)
--       Marcheaza biletele cumparate gratuit via abonament activ.
--    5. Index compus pentru lookup rapid (anti-overlap pe ruta + lookup la bilet).
--
--  Constraint logic:
--    - Daca scope='route' => from_station_id si to_station_id NOT NULL si diferite.
--    - Daca scope='network' => from/to pot fi NULL.
--    - Pentru aceeasi (user_id, from, to, scope='route'), nu pot exista 2
--      abonamente 'active' simultan (anti-overlap pe ruta).
--
--  Idempotent: IF NOT EXISTS peste tot.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Coloane noi pe subscriptions
-- ---------------------------------------------------------------------------
ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS from_station_id    INT REFERENCES stations(station_id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS to_station_id      INT REFERENCES stations(station_id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS subscription_scope VARCHAR(20) NOT NULL DEFAULT 'route',
    ADD COLUMN IF NOT EXISTS route_distance_km  NUMERIC(8,2);

-- Constraint pentru scope valid
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'subscriptions_scope_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_scope_check
            CHECK (subscription_scope IN ('network', 'route'));
    END IF;
END $$;

-- Constraint: pentru scope=route, from/to obligatorii si diferite
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'subscriptions_route_endpoints_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_route_endpoints_check
            CHECK (
                subscription_scope != 'route'
                OR (
                    from_station_id IS NOT NULL
                    AND to_station_id IS NOT NULL
                    AND from_station_id != to_station_id
                )
            );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Index-uri pentru lookup rapid
-- ---------------------------------------------------------------------------
-- Pentru anti-overlap (verifica daca user are deja abonament activ pe ruta)
CREATE INDEX IF NOT EXISTS idx_subscriptions_route_lookup
    ON subscriptions(user_id, from_station_id, to_station_id, status)
    WHERE subscription_scope = 'route';

-- Pentru gasire rapida la cumparare bilet (verifica daca exista abonament
-- activ care acopera ruta in data calatoriei)
CREATE INDEX IF NOT EXISTS idx_subscriptions_active_dates
    ON subscriptions(valid_until, status) WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 3. Coloana noua pe tickets pentru a marca biletele cumparate gratis via abonament
-- ---------------------------------------------------------------------------
ALTER TABLE tickets
    ADD COLUMN IF NOT EXISTS uses_subscription_id INT
        REFERENCES subscriptions(subscription_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tickets_uses_subscription
    ON tickets(uses_subscription_id) WHERE uses_subscription_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. Functie utility: cleanup lazy abonamente expirate
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION expire_old_subscriptions()
RETURNS INT AS $$
DECLARE
    expired_count INT;
BEGIN
    UPDATE subscriptions
    SET status = 'expired'
    WHERE status = 'active'
      AND valid_until < CURRENT_DATE;
    GET DIAGNOSTICS expired_count = ROW_COUNT;
    RETURN expired_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION expire_old_subscriptions() IS
    'Marcheaza ca expired abonamentele cu valid_until < azi. Apelat lazy la GET /subscriptions/my.';

COMMIT;

-- =============================================================================
-- Verificare:
--   SELECT column_name, data_type, is_nullable FROM information_schema.columns
--     WHERE table_name='subscriptions' ORDER BY ordinal_position;
--   SELECT count(*) FROM subscriptions; -- nu trebuie sa creasca, doar coloane noi
-- =============================================================================
