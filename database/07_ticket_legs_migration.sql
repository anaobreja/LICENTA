-- =============================================================================
--  Migrare 07: ticket_legs — segmente individuale ale unui bilet multi-leg
-- =============================================================================
--
--  Structura:
--    tickets       = containerul unui journey (1 tren sau mai multe)
--    ticket_legs   = un segment de tren din journey (1:N cu tickets)
--
--  Pentru bilete single-leg: 1 ticket + 1 ticket_leg
--  Pentru bilete multi-leg:  1 ticket + N ticket_legs (N = 2 sau 3)
--
--  tickets.train_id / departure_station_id / arrival_station_id continuă să
--  existe pentru compatibilitate cu codul existent (populat cu primul/ultimul leg).
--  Sursa de adevăr pentru legs este tabelul ticket_legs.
--
--  Câmpuri cheie ticket_legs:
--    leg_order      — ordinea în journey (1, 2, 3)
--    qr_token       — tokenul QR unic al acestui segment (string random, SHA-256 stocat separat)
--    qr_token_hash  — SHA-256(qr_token), folosit la validare (nu expunem tokenul brut)
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS ticket_legs (
    leg_id                  SERIAL PRIMARY KEY,
    ticket_id               INTEGER NOT NULL
                                REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    leg_order               SMALLINT NOT NULL DEFAULT 1
                                CHECK (leg_order > 0),
    train_id                INTEGER NOT NULL REFERENCES trains(train_id),
    departure_station_id    INTEGER NOT NULL REFERENCES stations(station_id),
    arrival_station_id      INTEGER NOT NULL REFERENCES stations(station_id),
    travel_date             DATE NOT NULL,
    seat_id                 INTEGER REFERENCES seats(seat_id),
    price                   NUMERIC(8,2) NOT NULL DEFAULT 0,
    discount_applied        NUMERIC(8,2) NOT NULL DEFAULT 0,
    qr_token                TEXT,           -- token brut, afișat ca QR
    qr_token_hash           TEXT,           -- SHA-256 pentru validare
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ticket_legs_order UNIQUE (ticket_id, leg_order)
);

CREATE INDEX IF NOT EXISTS idx_ticket_legs_ticket
    ON ticket_legs(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_legs_train_date
    ON ticket_legs(train_id, travel_date);
CREATE INDEX IF NOT EXISTS idx_ticket_legs_qr_hash
    ON ticket_legs(qr_token_hash)
    WHERE qr_token_hash IS NOT NULL;

COMMENT ON TABLE ticket_legs IS
    'Segmentele individuale ale unui bilet. Single-leg: 1 row. Multi-leg (cu schimbare): 2-3 rows.';

COMMIT;
