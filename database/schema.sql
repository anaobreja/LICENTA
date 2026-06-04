-- ==============================================================================
-- SISTEM GESTIONARE IDENTITATE DIGITALA SI DREPTURI CALATORII - TRANSPORT FEROVIAR
-- Schema PostgreSQL — single source of truth pentru aplicatie
--
-- Aceasta schema este executata de container-ul PostgreSQL la prima pornire
-- (vezi docker-compose.yml -> volume mount /docker-entrypoint-initdb.d/01_schema.sql).
-- Aplicatia NU mai creeaza tabele ad-hoc la runtime: toate definitiile sunt aici.
--
-- Convenții:
--   * SERIAL PRIMARY KEY pentru toate tabelele (compatibil PG <=12, simplu)
--   * FOREIGN KEY ... ON DELETE CASCADE sau RESTRICT explicit la fiecare relatie
--   * CHECK constraints pe coloanele de status / enum
--   * Index pe coloane folosite frecvent in WHERE / JOIN
--   * TIMESTAMP fara TZ (aplicatia normalizeaza la UTC in Python)
-- ==============================================================================

-- ==============================================================================
-- DROP ORDER: dinspre dependinte spre tabele de baza
-- ==============================================================================
DROP VIEW IF EXISTS v_user_credentials_active CASCADE;
DROP VIEW IF EXISTS v_validations_summary CASCADE;
DROP VIEW IF EXISTS active_travel_entitlements CASCADE;
DROP VIEW IF EXISTS user_travel_summary CASCADE;
DROP VIEW IF EXISTS validation_history_detailed CASCADE;
DROP VIEW IF EXISTS pending_student_benefits CASCADE;
DROP VIEW IF EXISTS university_agent_summary CASCADE;

DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS validations CASCADE;
DROP TABLE IF EXISTS qr_tokens CASCADE;
DROP TABLE IF EXISTS travel_entitlements CASCADE;
DROP TABLE IF EXISTS user_benefits CASCADE;
DROP TABLE IF EXISTS benefit_types CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;
DROP TABLE IF EXISTS trains CASCADE;
DROP TABLE IF EXISTS route_stops CASCADE;
DROP TABLE IF EXISTS routes CASCADE;
DROP TABLE IF EXISTS stations CASCADE;
DROP TABLE IF EXISTS railway_operators CASCADE;

-- Identity-layer tables (aplicatie reala)
DROP TABLE IF EXISTS card_verifications CASCADE;
DROP TABLE IF EXISTS card_presentations CASCADE;
DROP TABLE IF EXISTS digital_cards CASCADE;
DROP TABLE IF EXISTS user_credentials CASCADE;
DROP TABLE IF EXISTS document_reviews CASCADE;
DROP TABLE IF EXISTS source_documents CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS issuers CASCADE;

-- Legacy / conceptual identity tables (raman in schema pentru ER complet)
DROP TABLE IF EXISTS auth_methods CASCADE;
DROP TABLE IF EXISTS digital_identities CASCADE;

DROP TABLE IF EXISTS university_students CASCADE;
DROP TABLE IF EXISTS universities CASCADE;
DROP TABLE IF EXISTS users CASCADE;


-- ==============================================================================
-- 0. UNIVERSITATI PARTENERE
-- ==============================================================================
CREATE TABLE universities (
    university_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    short_name VARCHAR(50) NOT NULL UNIQUE,
    city VARCHAR(100) NOT NULL,
    email_domain VARCHAR(100) UNIQUE,
    contact_email VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_universities_short_name ON universities(short_name);
CREATE INDEX idx_universities_email_domain ON universities(email_domain);

COMMENT ON TABLE universities IS 'Universitati partenere cu agenti verificatori pentru facilitati studentesti';


-- ==============================================================================
-- 0b. STUDENTI INSCRISI (per universitate) — folosit la verificarea legitimatiei
-- ==============================================================================
CREATE TABLE university_students (
    enrollment_id SERIAL PRIMARY KEY,
    university_id INTEGER NOT NULL,
    student_number VARCHAR(100) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    faculty VARCHAR(255),
    study_program VARCHAR(255),
    year_of_study INTEGER CHECK (year_of_study BETWEEN 1 AND 6),
    enrollment_status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (enrollment_status IN ('active', 'inactive', 'graduated', 'expelled')),
    enrollment_date DATE NOT NULL,
    expected_graduation DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, student_number),
    FOREIGN KEY (university_id) REFERENCES universities(university_id) ON DELETE CASCADE
);

CREATE INDEX idx_university_students_univ ON university_students(university_id);
CREATE INDEX idx_university_students_number ON university_students(student_number);
CREATE INDEX idx_university_students_status ON university_students(enrollment_status);

COMMENT ON TABLE university_students IS 'Baza de date a studentilor inscrisi - folosita de agenti la validarea facilitatilor';


-- ==============================================================================
-- 1. UTILIZATORI
-- ==============================================================================
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(500) NOT NULL,
    phone VARCHAR(30),
    date_of_birth DATE,
    role VARCHAR(50) NOT NULL DEFAULT 'passenger'
        CHECK (role IN ('passenger', 'conductor', 'admin', 'university_agent')),
    university_id INTEGER,
    -- denormalizat: numele textual al universitatii pentru flow-urile in care
    -- agent_university != user_university (folosit la legitimatii)
    university_name VARCHAR(255),
    profile_photo_path VARCHAR(500),
    -- MFA (TOTP)
    mfa_secret VARCHAR(500),
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    -- Issuer link (pentru agentii universitari: catre tabela issuers daca emit credentiale)
    issuer_id INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (university_id) REFERENCES universities(university_id) ON DELETE SET NULL
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_university_id ON users(university_id);

COMMENT ON TABLE users IS 'Entitate centrala - toti utilizatorii sistemului (pasageri, conductori, agenti universitari, admini)';
COMMENT ON COLUMN users.mfa_enabled IS 'Daca TOTP MFA este activ pentru cont';
COMMENT ON COLUMN users.university_name IS 'Numele textual al universitatii (denormalizat pentru legitimatii)';


-- ==============================================================================
-- 2. IDENTITATI DIGITALE (concept — ramane pentru ER conceptual)
-- ==============================================================================
CREATE TABLE digital_identities (
    identity_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    identity_code VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'expired', 'revoked')),
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_digital_identities_user_id ON digital_identities(user_id);
CREATE INDEX idx_digital_identities_status ON digital_identities(status);


-- ==============================================================================
-- 3. METODE DE AUTENTIFICARE (legate de identity)
-- ==============================================================================
CREATE TABLE auth_methods (
    method_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    method_type VARCHAR(50) NOT NULL
        CHECK (method_type IN ('password', 'totp', 'sms_otp', 'email_otp', 'biometric')),
    method_value VARCHAR(500),
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_auth_methods_user_id ON auth_methods(user_id);
CREATE INDEX idx_auth_methods_enabled ON auth_methods(is_enabled);


-- ==============================================================================
-- 4. EMITENTI (issuers) — universitati, autoritate transport
-- ==============================================================================
CREATE TABLE issuers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    issuer_type VARCHAR(50) NOT NULL
        CHECK (issuer_type IN ('university', 'transport', 'government', 'demo')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_issuers_type ON issuers(issuer_type);

COMMENT ON TABLE issuers IS 'Autoritati care emit credentiale digitale (universitati, autoritate feroviara)';

-- FK delayed pentru users.issuer_id (issuers nu existau la create users)
ALTER TABLE users
    ADD CONSTRAINT fk_users_issuer
    FOREIGN KEY (issuer_id) REFERENCES issuers(id) ON DELETE SET NULL;


-- ==============================================================================
-- 5. DOCUMENTE SURSA — CI / legitimatii incarcate de pasageri
-- ==============================================================================
CREATE TABLE source_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    document_type VARCHAR(50) NOT NULL
        CHECK (document_type IN ('national_id', 'identity_card', 'student_card', 'student_id', 'pupil_card', 'elev_card', 'school_id', 'passport')),
    document_number_masked VARCHAR(100) NOT NULL,
    document_image_path VARCHAR(500),
    document_image_path_verso VARCHAR(500),
    status VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- denormalizat: pentru filtrarea pe universitate fara JOIN
    university_name VARCHAR(255),
    year_of_study INTEGER CHECK (year_of_study IS NULL OR year_of_study BETWEEN 1 AND 6),
    -- date extrase din CI prin OCR/MRZ
    ci_number VARCHAR(100),
    ci_name VARCHAR(255),
    ci_date_of_birth VARCHAR(20),
    ci_sex VARCHAR(10),
    ci_address VARCHAR(500),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_source_documents_user_id ON source_documents(user_id);
CREATE INDEX idx_source_documents_status ON source_documents(status);
CREATE INDEX idx_source_documents_university ON source_documents(university_name);
CREATE INDEX idx_source_documents_type ON source_documents(document_type);

COMMENT ON TABLE source_documents IS 'Documente fizice/digitale incarcate pentru aprobare (CI, legitimatie student/elev)';


-- ==============================================================================
-- 6. REVIZUIRI DOCUMENTE — log aprobari/respingeri de catre agentii universitari
-- ==============================================================================
CREATE TABLE document_reviews (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,
    decision VARCHAR(20) NOT NULL
        CHECK (decision IN ('approved', 'rejected')),
    notes TEXT,
    reviewed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES source_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_id) REFERENCES users(user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_document_reviews_document_id ON document_reviews(document_id);
CREATE INDEX idx_document_reviews_reviewer_id ON document_reviews(reviewer_id);


-- ==============================================================================
-- 7. CREDENTIALE UTILIZATOR — claim-uri active emise (ex: student la UPB)
-- ==============================================================================
CREATE TABLE user_credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    credential_type VARCHAR(50) NOT NULL
        CHECK (credential_type IN ('national_id', 'identity_verified', 'student', 'student_verified', 'pupil', 'elev_verified', 'passenger', 'conductor')),
    claim_value VARCHAR(500) NOT NULL,
    issuer_id INTEGER,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked', 'expired')),
    issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (issuer_id) REFERENCES issuers(id) ON DELETE SET NULL
);

CREATE INDEX idx_user_credentials_user_id ON user_credentials(user_id);
CREATE INDEX idx_user_credentials_status ON user_credentials(status);
CREATE INDEX idx_user_credentials_type ON user_credentials(credential_type);
CREATE INDEX idx_user_credentials_valid_until ON user_credentials(valid_until);


-- ==============================================================================
-- 8. CARDURI DIGITALE — cardul efectiv emis pentru un user (1:1)
-- ==============================================================================
CREATE TABLE digital_cards (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    issuer_id INTEGER NOT NULL,
    card_identifier VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked', 'expired')),
    issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (issuer_id) REFERENCES issuers(id) ON DELETE RESTRICT
);

CREATE INDEX idx_digital_cards_user_id ON digital_cards(user_id);
CREATE INDEX idx_digital_cards_status ON digital_cards(status);
CREATE INDEX idx_digital_cards_valid_until ON digital_cards(valid_until);


-- ==============================================================================
-- 9. PREZENTARI CARD — token QR generat de pasager pentru identitate
-- ==============================================================================
CREATE TABLE card_presentations (
    id SERIAL PRIMARY KEY,
    card_id INTEGER NOT NULL,
    token_value VARCHAR(500) NOT NULL UNIQUE,
    issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'used', 'expired', 'revoked')),
    used_at TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES digital_cards(id) ON DELETE CASCADE
);

CREATE INDEX idx_card_presentations_card_id ON card_presentations(card_id);
CREATE INDEX idx_card_presentations_token ON card_presentations(token_value);
CREATE INDEX idx_card_presentations_status ON card_presentations(status);
CREATE INDEX idx_card_presentations_expires_at ON card_presentations(expires_at);

COMMENT ON TABLE card_presentations IS 'QR tokens generate de pasager pentru a-si prezenta identitatea (single-use)';
COMMENT ON COLUMN card_presentations.used_at IS 'Timestamp prima validare reusita - anti-replay';


-- ==============================================================================
-- 10. VERIFICARI CARD — log scanari de catre conductori
-- ==============================================================================
CREATE TABLE card_verifications (
    id SERIAL PRIMARY KEY,
    card_presentation_id INTEGER NOT NULL,
    verifier_user_id INTEGER NOT NULL,
    verification_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    result VARCHAR(50) NOT NULL
        CHECK (result IN ('valid', 'invalid', 'accepted', 'rejected', 'expired', 'already_used')),
    notes TEXT,
    FOREIGN KEY (card_presentation_id) REFERENCES card_presentations(id) ON DELETE CASCADE,
    FOREIGN KEY (verifier_user_id) REFERENCES users(user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_card_verifications_pres_id ON card_verifications(card_presentation_id);
CREATE INDEX idx_card_verifications_verifier ON card_verifications(verifier_user_id);
CREATE INDEX idx_card_verifications_time ON card_verifications(verification_time);


-- ==============================================================================
-- 11. NOTIFICARI — in-app pentru pasageri
-- ==============================================================================
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    category VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_is_read ON notifications(is_read);
CREATE INDEX idx_notifications_created_at ON notifications(created_at);


-- ==============================================================================
-- 12. OPERATORI FEROVIARI
-- ==============================================================================
CREATE TABLE railway_operators (
    operator_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(20) NOT NULL UNIQUE,
    country VARCHAR(100) DEFAULT 'Romania',
    contact_email VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_railway_operators_code ON railway_operators(code);


-- ==============================================================================
-- 13. STATII
-- ==============================================================================
CREATE TABLE stations (
    station_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(20) NOT NULL UNIQUE,
    city VARCHAR(100) NOT NULL,
    country VARCHAR(100) DEFAULT 'Romania',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stations_code ON stations(code);
CREATE INDEX idx_stations_city ON stations(city);


-- ==============================================================================
-- 14. RUTE
-- ==============================================================================
CREATE TABLE routes (
    route_id SERIAL PRIMARY KEY,
    operator_id INTEGER NOT NULL,
    route_name VARCHAR(255) NOT NULL,
    route_code VARCHAR(50) NOT NULL UNIQUE,
    origin_station_id INTEGER NOT NULL,
    destination_station_id INTEGER NOT NULL,
    total_distance_km NUMERIC(8, 2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id) ON DELETE RESTRICT,
    FOREIGN KEY (origin_station_id) REFERENCES stations(station_id) ON DELETE RESTRICT,
    FOREIGN KEY (destination_station_id) REFERENCES stations(station_id) ON DELETE RESTRICT,
    CHECK (origin_station_id <> destination_station_id)
);

CREATE INDEX idx_routes_operator_id ON routes(operator_id);
CREATE INDEX idx_routes_origin ON routes(origin_station_id);
CREATE INDEX idx_routes_destination ON routes(destination_station_id);


-- ==============================================================================
-- 15. STATII PE RUTA (ordine + km)
-- ==============================================================================
CREATE TABLE route_stops (
    route_stop_id SERIAL PRIMARY KEY,
    route_id INTEGER NOT NULL,
    station_id INTEGER NOT NULL,
    stop_order INTEGER NOT NULL,
    distance_from_origin_km NUMERIC(8, 2),
    arrival_time TIME,
    departure_time TIME,
    UNIQUE(route_id, stop_order),
    FOREIGN KEY (route_id) REFERENCES routes(route_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id) REFERENCES stations(station_id) ON DELETE RESTRICT
);

CREATE INDEX idx_route_stops_route_id ON route_stops(route_id);
CREATE INDEX idx_route_stops_station_id ON route_stops(station_id);


-- ==============================================================================
-- 16. TRENURI
-- ==============================================================================
CREATE TABLE trains (
    train_id SERIAL PRIMARY KEY,
    operator_id INTEGER NOT NULL,
    route_id INTEGER NOT NULL,
    train_number VARCHAR(50) NOT NULL UNIQUE,
    train_type VARCHAR(50) NOT NULL
        CHECK (train_type IN ('regio', 'interregio', 'intercity', 'express', 'high_speed')),
    capacity_seats INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id) ON DELETE RESTRICT,
    FOREIGN KEY (route_id) REFERENCES routes(route_id) ON DELETE RESTRICT
);

CREATE INDEX idx_trains_operator_id ON trains(operator_id);
CREATE INDEX idx_trains_route_id ON trains(route_id);
CREATE INDEX idx_trains_number ON trains(train_number);


-- ==============================================================================
-- 17. BILETE
-- ==============================================================================
CREATE TABLE tickets (
    ticket_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    train_id INTEGER NOT NULL,
    departure_station_id INTEGER NOT NULL,
    arrival_station_id INTEGER NOT NULL,
    travel_date DATE NOT NULL,
    ticket_type VARCHAR(50) NOT NULL
        CHECK (ticket_type IN ('single', 'return', 'group')),
    ticket_status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (ticket_status IN ('active', 'used', 'cancelled', 'refunded', 'expired')),
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    discount_applied NUMERIC(5, 2) DEFAULT 0 CHECK (discount_applied >= 0 AND discount_applied <= 100),
    purchase_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (train_id) REFERENCES trains(train_id) ON DELETE RESTRICT,
    FOREIGN KEY (departure_station_id) REFERENCES stations(station_id) ON DELETE RESTRICT,
    FOREIGN KEY (arrival_station_id) REFERENCES stations(station_id) ON DELETE RESTRICT,
    CHECK (departure_station_id <> arrival_station_id)
);

CREATE INDEX idx_tickets_user_id ON tickets(user_id);
CREATE INDEX idx_tickets_train_id ON tickets(train_id);
CREATE INDEX idx_tickets_travel_date ON tickets(travel_date);
CREATE INDEX idx_tickets_status ON tickets(ticket_status);


-- ==============================================================================
-- 18. ABONAMENTE
-- ==============================================================================
CREATE TABLE subscriptions (
    subscription_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    subscription_type VARCHAR(50) NOT NULL
        CHECK (subscription_type IN ('monthly', 'semester', 'annual', 'weekly')),
    operator_id INTEGER,
    valid_from DATE NOT NULL,
    valid_until DATE NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    discount_applied NUMERIC(5, 2) DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'cancelled', 'suspended')),
    purchase_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id) ON DELETE SET NULL,
    CHECK (valid_until >= valid_from)
);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_valid_until ON subscriptions(valid_until);


-- ==============================================================================
-- 19. DREPTURI DE CALATORIE (unificare ticket + subscription)
-- ==============================================================================
CREATE TABLE travel_entitlements (
    entitlement_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    source_type VARCHAR(50) NOT NULL
        CHECK (source_type IN ('ticket', 'subscription', 'benefit')),
    ticket_id INTEGER,
    subscription_id INTEGER,
    valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'used', 'expired', 'revoked')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id) ON DELETE CASCADE,
    -- exact una din ticket_id / subscription_id e populata
    CHECK (
        (source_type = 'ticket' AND ticket_id IS NOT NULL AND subscription_id IS NULL) OR
        (source_type = 'subscription' AND subscription_id IS NOT NULL AND ticket_id IS NULL) OR
        (source_type = 'benefit' AND ticket_id IS NULL AND subscription_id IS NULL)
    )
);

CREATE INDEX idx_travel_entitlements_user_id ON travel_entitlements(user_id);
CREATE INDEX idx_travel_entitlements_status ON travel_entitlements(status);
CREATE INDEX idx_travel_entitlements_valid_until ON travel_entitlements(valid_until);


-- ==============================================================================
-- 20. QR TOKENS pentru bilete / abonamente (single-use)
-- ==============================================================================
CREATE TABLE qr_tokens (
    qr_token_id SERIAL PRIMARY KEY,
    entitlement_id INTEGER NOT NULL,
    token_value VARCHAR(500) NOT NULL UNIQUE,
    token_hash VARCHAR(500) NOT NULL,
    issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'used', 'expired', 'revoked')),
    FOREIGN KEY (entitlement_id) REFERENCES travel_entitlements(entitlement_id) ON DELETE CASCADE
);

CREATE INDEX idx_qr_tokens_entitlement_id ON qr_tokens(entitlement_id);
CREATE INDEX idx_qr_tokens_status ON qr_tokens(status);
CREATE INDEX idx_qr_tokens_expires_at ON qr_tokens(expires_at);


-- ==============================================================================
-- 21. VALIDARI BILETE (controlor scaneaza QR in tren)
-- ==============================================================================
CREATE TABLE validations (
    validation_id SERIAL PRIMARY KEY,
    qr_token_id INTEGER NOT NULL,
    conductor_id INTEGER NOT NULL,
    train_id INTEGER,
    validation_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    validation_result VARCHAR(50) NOT NULL
        CHECK (validation_result IN ('valid', 'invalid', 'expired', 'already_used')),
    device_id VARCHAR(100),
    notes TEXT,
    FOREIGN KEY (qr_token_id) REFERENCES qr_tokens(qr_token_id) ON DELETE CASCADE,
    FOREIGN KEY (conductor_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (train_id) REFERENCES trains(train_id) ON DELETE SET NULL
);

CREATE INDEX idx_validations_qr_token_id ON validations(qr_token_id);
CREATE INDEX idx_validations_conductor_id ON validations(conductor_id);
CREATE INDEX idx_validations_validation_time ON validations(validation_time);


-- ==============================================================================
-- 22. AUDIT LOGS (cross-cutting)
-- ==============================================================================
CREATE TABLE audit_logs (
    audit_log_id SERIAL PRIMARY KEY,
    actor_user_id INTEGER,
    action_type VARCHAR(100) NOT NULL,
    target_table VARCHAR(100),
    target_id INTEGER,
    action_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    details TEXT,
    FOREIGN KEY (actor_user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_logs_action_type ON audit_logs(action_type);
CREATE INDEX idx_audit_logs_target_table ON audit_logs(target_table);
CREATE INDEX idx_audit_logs_action_timestamp ON audit_logs(action_timestamp);


-- ==============================================================================
-- VIEW: drepturi de calatorie active
-- ==============================================================================
CREATE VIEW active_travel_entitlements AS
SELECT
    te.entitlement_id,
    te.user_id,
    u.first_name,
    u.last_name,
    u.email,
    te.source_type,
    te.valid_from,
    te.valid_until,
    te.status,
    CASE
        WHEN te.source_type = 'ticket'       THEN t.ticket_type
        WHEN te.source_type = 'subscription' THEN s.subscription_type
        ELSE 'benefit'
    END AS entitlement_subtype
FROM travel_entitlements te
JOIN users u ON u.user_id = te.user_id
LEFT JOIN tickets t       ON t.ticket_id = te.ticket_id
LEFT JOIN subscriptions s ON s.subscription_id = te.subscription_id
WHERE te.status = 'active'
  AND te.valid_until > CURRENT_TIMESTAMP;


-- ==============================================================================
-- VIEW: credentialele active per user
-- ==============================================================================
CREATE VIEW v_user_credentials_active AS
SELECT
    uc.id,
    uc.user_id,
    u.email,
    u.first_name,
    u.last_name,
    uc.credential_type,
    uc.claim_value,
    uc.valid_until,
    i.name AS issuer_name
FROM user_credentials uc
JOIN users u ON u.user_id = uc.user_id
LEFT JOIN issuers i ON i.id = uc.issuer_id
WHERE uc.status = 'active'
  AND uc.valid_until > CURRENT_TIMESTAMP;


-- ==============================================================================
-- VIEW: istoric validari biletelor (pentru rapoarte)
-- ==============================================================================
CREATE VIEW v_validations_summary AS
SELECT
    v.validation_id,
    v.validation_time,
    v.validation_result,
    qt.token_value,
    te.user_id AS passenger_id,
    pu.first_name AS passenger_first_name,
    pu.last_name AS passenger_last_name,
    v.conductor_id,
    cu.first_name AS conductor_first_name,
    cu.last_name AS conductor_last_name,
    te.source_type
FROM validations v
JOIN qr_tokens qt           ON qt.qr_token_id = v.qr_token_id
JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
JOIN users pu               ON pu.user_id = te.user_id
JOIN users cu               ON cu.user_id = v.conductor_id;


-- ==============================================================================
-- VIEW: rezumat universitate-agent (cereri pending / approved / rejected)
-- ==============================================================================
CREATE VIEW university_agent_summary AS
SELECT
    univ.university_id,
    univ.name                AS university_name,
    COUNT(CASE WHEN sd.status = 'pending'  THEN 1 END) AS pending_count,
    COUNT(CASE WHEN sd.status = 'approved' THEN 1 END) AS approved_count,
    COUNT(CASE WHEN sd.status = 'rejected' THEN 1 END) AS rejected_count
FROM universities univ
LEFT JOIN source_documents sd ON sd.university_name = univ.name
GROUP BY univ.university_id, univ.name;


COMMENT ON VIEW active_travel_entitlements IS 'Drepturi de calatorie valide la momentul interogarii';
COMMENT ON VIEW v_user_credentials_active IS 'Credentiale active per utilizator (claim-uri verificabile)';
COMMENT ON VIEW v_validations_summary IS 'Detalii pentru fiecare validare de bilet';
COMMENT ON VIEW university_agent_summary IS 'KPI per universitate pentru dashboard agent';
