-- =============================================================================
--  Migrare 06: Vagoane, locuri, rezervari temporare si lifecycle bilet
-- =============================================================================
--
--  Adauga:
--    1. train_cars       — vagoanele unui tren (numar, capacitate, clasa)
--    2. seats            — fiecare loc dintr-un vagon
--    3. seat_reservations— hold-uri temporare de 5 minute pe locuri (UX flow)
--    4. ticket_seats     — locuri vandute, legate de un ticket activ
--    5. tickets coloane noi pentru: cancel, refund, reschedule chain
--
--  Configuratie vagoane per train_type (decizie design):
--    Regio  / R              => 3 vagoane x 60 locuri = 180 locuri
--    IR     / InterRegio     => 5 vagoane x 60 locuri = 300 locuri
--    IC     / InterCity      => 7 vagoane x 60 locuri = 420 locuri
--    default                 => 4 vagoane x 60 locuri = 240 locuri
--
--  Fiecare vagon are layout 2+2 (60 locuri = 15 randuri x 4 locuri A/B/C/D).
--  Vagonul 1 din fiecare tren e CLASA 1 (cu pret +50%), restul clasa 2.
--
--  Idempotent: foloseste IF NOT EXISTS / IF EXISTS peste tot.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
--  1. train_cars  (vagoane)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS train_cars (
    train_car_id    SERIAL PRIMARY KEY,
    train_id        INT NOT NULL REFERENCES trains(train_id) ON DELETE CASCADE,
    car_number      INT NOT NULL,                  -- 1, 2, 3...
    car_class       INT NOT NULL DEFAULT 2,        -- 1 sau 2
    total_seats     INT NOT NULL DEFAULT 60,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_train_cars_train_number UNIQUE (train_id, car_number),
    CONSTRAINT ck_car_number_positive CHECK (car_number > 0),
    CONSTRAINT ck_car_class_valid CHECK (car_class IN (1, 2)),
    CONSTRAINT ck_total_seats_positive CHECK (total_seats > 0)
);

CREATE INDEX IF NOT EXISTS idx_train_cars_train_id ON train_cars(train_id);

COMMENT ON TABLE train_cars IS
    'Vagoane per tren. Numarul de vagoane depinde de train_type. Vagonul 1 = clasa 1.';


-- ---------------------------------------------------------------------------
--  2. seats  (locuri individuale)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seats (
    seat_id         SERIAL PRIMARY KEY,
    train_car_id    INT NOT NULL REFERENCES train_cars(train_car_id) ON DELETE CASCADE,
    seat_row        INT NOT NULL,                  -- 1..15
    seat_letter     CHAR(1) NOT NULL,              -- A, B, C, D
    seat_label      VARCHAR(8) NOT NULL,           -- '1A', '15D' — afisat in UI
    is_window       BOOLEAN NOT NULL DEFAULT FALSE,-- A, D = window
    is_aisle        BOOLEAN NOT NULL DEFAULT FALSE,-- B, C = aisle
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_seats_car_label UNIQUE (train_car_id, seat_label),
    CONSTRAINT ck_seat_letter_valid CHECK (seat_letter IN ('A', 'B', 'C', 'D'))
);

CREATE INDEX IF NOT EXISTS idx_seats_train_car_id ON seats(train_car_id);

COMMENT ON TABLE seats IS
    'Locurile individuale dintr-un vagon. Layout 2+2 cu 15 randuri (A,B | C,D).';


-- ---------------------------------------------------------------------------
--  3. seat_reservations  (hold-uri temporare, max 5 minute)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seat_reservations (
    reservation_id  SERIAL PRIMARY KEY,
    seat_id         INT NOT NULL REFERENCES seats(seat_id) ON DELETE CASCADE,
    user_id         INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    train_id        INT NOT NULL REFERENCES trains(train_id) ON DELETE CASCADE,
    travel_date     DATE NOT NULL,                 -- holdul e specific zilei
    held_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,          -- held_at + INTERVAL '5 minutes'
    -- Un singur hold activ pe (seat, travel_date) — daca expira, e curatat
    CONSTRAINT uq_seat_reservation_active UNIQUE (seat_id, travel_date)
);

CREATE INDEX IF NOT EXISTS idx_seat_reservations_user
    ON seat_reservations(user_id);
CREATE INDEX IF NOT EXISTS idx_seat_reservations_expires
    ON seat_reservations(expires_at);
CREATE INDEX IF NOT EXISTS idx_seat_reservations_train_date
    ON seat_reservations(train_id, travel_date);

COMMENT ON TABLE seat_reservations IS
    'Hold-uri temporare pe locuri (5 min). Cleanup lazy la fiecare GET /trains/seats.';


-- ---------------------------------------------------------------------------
--  4. ticket_seats  (locuri vandute, legate de un ticket activ)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_seats (
    ticket_seat_id  SERIAL PRIMARY KEY,
    ticket_id       INT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    seat_id         INT NOT NULL REFERENCES seats(seat_id) ON DELETE RESTRICT,
    travel_date     DATE NOT NULL,                 -- denormalizat pentru constraint
    sold_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Un loc poate fi vandut o singura data per data calatorie (cat timp e activ)
    -- Daca tichet anulat, ticket_seats e sters -> locul redevine liber
    CONSTRAINT uq_ticket_seats_seat_date UNIQUE (seat_id, travel_date)
);

CREATE INDEX IF NOT EXISTS idx_ticket_seats_ticket ON ticket_seats(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_seats_seat   ON ticket_seats(seat_id);

COMMENT ON TABLE ticket_seats IS
    'Locuri vandute. Stergem randul la cancel/reschedule -> loc liber instant.';


-- ---------------------------------------------------------------------------
--  5. Coloane noi pe tickets pentru lifecycle (cancel, refund, reschedule)
-- ---------------------------------------------------------------------------
ALTER TABLE tickets
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancel_refund_amount NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS rescheduled_from_ticket_id INT
        REFERENCES tickets(ticket_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rescheduled_to_ticket_id INT
        REFERENCES tickets(ticket_id) ON DELETE SET NULL;

-- Extindem CHECK-ul existent pe ticket_status (avea: active, used, expired, cancelled).
-- Acum adaugam si 'rescheduled' pentru clarificarea ca biletul vechi a fost mutat.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.constraint_column_usage
        WHERE table_name = 'tickets' AND constraint_name LIKE '%ticket_status%'
    ) THEN
        ALTER TABLE tickets DROP CONSTRAINT IF EXISTS tickets_ticket_status_check;
    END IF;
END $$;

ALTER TABLE tickets
    ADD CONSTRAINT tickets_ticket_status_check
    CHECK (ticket_status IN ('active','used','expired','cancelled','rescheduled'));

CREATE INDEX IF NOT EXISTS idx_tickets_cancelled_at ON tickets(cancelled_at);
CREATE INDEX IF NOT EXISTS idx_tickets_rescheduled_from
    ON tickets(rescheduled_from_ticket_id) WHERE rescheduled_from_ticket_id IS NOT NULL;


-- ---------------------------------------------------------------------------
--  6. Functii utility — generare layout vagoane
-- ---------------------------------------------------------------------------

-- Returneaza numarul de vagoane pentru un train_type dat.
CREATE OR REPLACE FUNCTION cars_for_train_type(p_train_type TEXT)
RETURNS INT AS $$
BEGIN
    -- Acceptam atat abrevierile CFR clasice (R/IR/IC) cat si numele lungi
    -- impuse de check constraint-ul trains.train_type (regio/interregio/...)
    RETURN CASE
        WHEN LOWER(p_train_type) IN ('r', 'regio', 'reg')             THEN 3
        WHEN LOWER(p_train_type) IN ('ir', 'interregio', 'inter_regio') THEN 5
        WHEN LOWER(p_train_type) IN ('ic', 'intercity', 'inter_city')   THEN 7
        WHEN LOWER(p_train_type) IN ('express', 'high_speed', 'icn')   THEN 7
        ELSE 4   -- IRN, S, Special, Tur, EX si altele
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- Genereaza vagoane + locuri pentru un tren.
-- Daca trenul are deja vagoane, nu face nimic.
CREATE OR REPLACE FUNCTION generate_train_layout(p_train_id INT)
RETURNS INT AS $$
DECLARE
    v_train_type TEXT;
    v_cars INT;
    v_car_number INT;
    v_car_id INT;
    v_row INT;
    v_letter CHAR(1);
    v_is_window BOOLEAN;
    v_is_aisle BOOLEAN;
    v_total_created INT := 0;
BEGIN
    -- Skip daca exista deja
    IF EXISTS (SELECT 1 FROM train_cars WHERE train_id = p_train_id) THEN
        RETURN 0;
    END IF;

    SELECT train_type INTO v_train_type FROM trains WHERE train_id = p_train_id;
    IF v_train_type IS NULL THEN
        RAISE EXCEPTION 'Train % not found', p_train_id;
    END IF;

    v_cars := cars_for_train_type(v_train_type);

    FOR v_car_number IN 1..v_cars LOOP
        INSERT INTO train_cars (train_id, car_number, car_class, total_seats)
        VALUES (
            p_train_id,
            v_car_number,
            CASE WHEN v_car_number = 1 THEN 1 ELSE 2 END,
            60
        )
        RETURNING train_car_id INTO v_car_id;

        -- 15 randuri x 4 locuri (A, B, C, D)
        FOR v_row IN 1..15 LOOP
            FOREACH v_letter IN ARRAY ARRAY['A','B','C','D'] LOOP
                v_is_window := v_letter IN ('A', 'D');
                v_is_aisle  := v_letter IN ('B', 'C');
                INSERT INTO seats (
                    train_car_id, seat_row, seat_letter, seat_label,
                    is_window, is_aisle
                ) VALUES (
                    v_car_id,
                    v_row,
                    v_letter,
                    v_row::TEXT || v_letter,
                    v_is_window,
                    v_is_aisle
                );
                v_total_created := v_total_created + 1;
            END LOOP;
        END LOOP;
    END LOOP;

    RETURN v_total_created;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
--  7. Backfill pentru toate trenurile existente
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    n INT;
    total_trains INT := 0;
    total_seats INT := 0;
BEGIN
    FOR r IN SELECT train_id FROM trains LOOP
        n := generate_train_layout(r.train_id);
        IF n > 0 THEN
            total_trains := total_trains + 1;
            total_seats := total_seats + n;
        END IF;
    END LOOP;
    RAISE NOTICE 'Backfill: generated layout for % trains, % seats total',
        total_trains, total_seats;
END $$;


-- ---------------------------------------------------------------------------
--  8. Functie utility — cleanup lazy al rezervarilor expirate
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION release_expired_reservations()
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM seat_reservations WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION release_expired_reservations() IS
    'Sterge hold-urile expirate. Apelat lazy la GET /trains/seats si la POST /seats/hold.';

COMMIT;

-- =============================================================================
-- Verificare rapida post-migrare:
--   SELECT COUNT(*) FROM train_cars;
--   SELECT COUNT(*) FROM seats;
--   SELECT t.train_number, t.train_type, COUNT(tc.train_car_id) AS cars
--     FROM trains t LEFT JOIN train_cars tc ON tc.train_id = t.train_id
--     GROUP BY t.train_id ORDER BY t.train_id LIMIT 10;
-- =============================================================================
