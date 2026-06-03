-- ==============================================================================
-- SISTEM GESTIONARE IDENTITATE DIGITALA SI DREPTURI CALATORII - TRANSPORT FEROVIAR
-- Schema PostgreSQL - Versiunea completă cu constrângeri și integritate referențială
-- ==============================================================================

-- Drop existing tables if they exist (pentru reșetare ușoară)
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
DROP TABLE IF EXISTS auth_methods CASCADE;
DROP TABLE IF EXISTS digital_identities CASCADE;
DROP TABLE IF EXISTS university_students CASCADE;
DROP TABLE IF EXISTS universities CASCADE;
DROP TABLE IF EXISTS users CASCADE;


-- ==============================================================================
-- 0. UNIVERSITĂȚI PARTENERE
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

COMMENT ON TABLE universities IS 'Universități partenere cu agenți verificatori pentru facilități studențești';


-- ==============================================================================
-- 0b. BAZA DE DATE STUDENȚI (per universitate)
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

COMMENT ON TABLE university_students IS 'Baza de date a studenților înscriși - folosită de agenți la validarea facilităților';


-- ==============================================================================
-- 1. UTILIZATORI
-- ==============================================================================
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(500) NOT NULL,
    phone VARCHAR(20),
    date_of_birth DATE,
    role VARCHAR(50) NOT NULL DEFAULT 'passenger'
        CHECK (role IN ('passenger', 'conductor', 'admin', 'university_agent')),
    university_id INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (university_id) REFERENCES universities(university_id) ON DELETE SET NULL
);

-- Index pentru email (se caută frecvent)
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_university_id ON users(university_id);

COMMENT ON TABLE users IS 'Entitatea centrală - toți utilizatorii sistemului';
COMMENT ON COLUMN users.role IS 'passenger: utilizator normal, conductor: controlor de tren, admin: administrator, university_agent: agent verificator universitar';
COMMENT ON COLUMN users.university_id IS 'Universitatea la care aparține utilizatorul (studenți și agenți universitari)';


-- ==============================================================================
-- 2. IDENTITATI DIGITALE
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

COMMENT ON TABLE digital_identities IS 'Identitatea digitală unică pentru fiecare utilizator';


-- ==============================================================================
-- 3. METODE DE AUTENTIFICARE
-- ==============================================================================
CREATE TABLE auth_methods (
    auth_method_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    method_type VARCHAR(50) NOT NULL
        CHECK (method_type IN ('password', 'totp', 'email_otp', 'biometric')),
    secret_value VARCHAR(500),
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_auth_methods_user_id ON auth_methods(user_id);
CREATE INDEX idx_auth_methods_enabled ON auth_methods(is_enabled);

COMMENT ON TABLE auth_methods IS 'Metodele de autentificare disponibile pentru utilizator (MFA)';


-- ==============================================================================
-- 4. OPERATORI FEROVIARI
-- ==============================================================================
CREATE TABLE railway_operators (
    operator_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    country VARCHAR(100),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_railway_operators_code ON railway_operators(code);

COMMENT ON TABLE railway_operators IS 'Operatorii de transport feroviar (CFR, private, etc.)';


-- ==============================================================================
-- 5. STATII FEROVIARE
-- ==============================================================================
CREATE TABLE stations (
    station_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stations_code ON stations(code);
CREATE INDEX idx_stations_city ON stations(city);

COMMENT ON TABLE stations IS 'Stații feroviare disponibile în sistem';


-- ==============================================================================
-- 6. RUTE FEROVIARE
-- ==============================================================================
CREATE TABLE routes (
    route_id SERIAL PRIMARY KEY,
    operator_id INTEGER NOT NULL,
    route_name VARCHAR(255) NOT NULL,
    origin_station_id INTEGER NOT NULL,
    destination_station_id INTEGER NOT NULL,
    distance_km DECIMAL(10, 2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id),
    FOREIGN KEY (origin_station_id) REFERENCES stations(station_id),
    FOREIGN KEY (destination_station_id) REFERENCES stations(station_id)
);

CREATE INDEX idx_routes_operator_id ON routes(operator_id);
CREATE INDEX idx_routes_origin ON routes(origin_station_id);
CREATE INDEX idx_routes_destination ON routes(destination_station_id);

COMMENT ON TABLE routes IS 'Rute definite de operatori (ex: București-Cluj)';


-- ==============================================================================
-- 7. OPRIRI IN TRASEU (Relație N:M între rute și stații)
-- ==============================================================================
CREATE TABLE route_stops (
    route_stop_id SERIAL PRIMARY KEY,
    route_id INTEGER NOT NULL,
    station_id INTEGER NOT NULL,
    stop_order INTEGER NOT NULL,
    planned_arrival_time TIME,
    planned_departure_time TIME,
    FOREIGN KEY (route_id) REFERENCES routes(route_id) ON DELETE CASCADE,
    FOREIGN KEY (station_id) REFERENCES stations(station_id),
    UNIQUE(route_id, stop_order)
);

CREATE INDEX idx_route_stops_route_id ON route_stops(route_id);
CREATE INDEX idx_route_stops_station_id ON route_stops(station_id);

COMMENT ON TABLE route_stops IS 'Ordine și detalii ale opririi la fiecare stație din rută';


-- ==============================================================================
-- 8. TRENURI
-- ==============================================================================
CREATE TABLE trains (
    train_id SERIAL PRIMARY KEY,
    operator_id INTEGER NOT NULL,
    route_id INTEGER NOT NULL,
    train_number VARCHAR(50) NOT NULL,
    train_type VARCHAR(50) NOT NULL
        CHECK (train_type IN ('regional', 'intercity', 'express', 'highspeed')),
    capacity INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id),
    FOREIGN KEY (route_id) REFERENCES routes(route_id)
);

CREATE INDEX idx_trains_operator_id ON trains(operator_id);
CREATE INDEX idx_trains_route_id ON trains(route_id);
CREATE INDEX idx_trains_number ON trains(train_number);

COMMENT ON TABLE trains IS 'Trenuri concrete (cu identificator, tip, capacitate)';


-- ==============================================================================
-- 9. BILETE INDIVIDUALE
-- ==============================================================================
CREATE TABLE tickets (
    ticket_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    train_id INTEGER NOT NULL,
    departure_station_id INTEGER NOT NULL,
    arrival_station_id INTEGER NOT NULL,
    travel_date DATE NOT NULL,
    travel_time TIME,
    seat_number VARCHAR(10),
    ticket_type VARCHAR(50) NOT NULL
        CHECK (ticket_type IN ('single', 'round_trip', 'group', 'promotional')),
    ticket_status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (ticket_status IN ('active', 'used', 'cancelled', 'expired')),
    price DECIMAL(10, 2) NOT NULL,
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (train_id) REFERENCES trains(train_id),
    FOREIGN KEY (departure_station_id) REFERENCES stations(station_id),
    FOREIGN KEY (arrival_station_id) REFERENCES stations(station_id)
);

CREATE INDEX idx_tickets_user_id ON tickets(user_id);
CREATE INDEX idx_tickets_train_id ON tickets(train_id);
CREATE INDEX idx_tickets_travel_date ON tickets(travel_date);
CREATE INDEX idx_tickets_status ON tickets(ticket_status);

COMMENT ON TABLE tickets IS 'Bilete individuale pentru utilizatori';


-- ==============================================================================
-- 10. ABONAMENTE
-- ==============================================================================
CREATE TABLE subscriptions (
    subscription_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    subscription_type VARCHAR(50) NOT NULL
        CHECK (subscription_type IN ('monthly', 'quarterly', 'annual', 'unlimited_route', 'unlimited_operator')),
    operator_id INTEGER,
    route_id INTEGER,
    valid_from DATE NOT NULL,
    valid_until DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'expired', 'suspended')),
    price DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (operator_id) REFERENCES railway_operators(operator_id),
    FOREIGN KEY (route_id) REFERENCES routes(route_id),
    CHECK (valid_until >= valid_from)
);

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_valid_until ON subscriptions(valid_until);

COMMENT ON TABLE subscriptions IS 'Abonamente active - ofer acces periodic';


-- ==============================================================================
-- 11. TIPURI DE FACILITĂȚI
-- ==============================================================================
CREATE TABLE benefit_types (
    benefit_type_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    discount_percent DECIMAL(5, 2) NOT NULL DEFAULT 0
        CHECK (discount_percent >= 0 AND discount_percent <= 100),
    requires_proof BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE benefit_types IS 'Tipuri de facilități (student, pensionar, veteran, etc.)';


-- ==============================================================================
-- 12. FACILITĂȚI ACORDATE UTILIZATORULUI
-- ==============================================================================
CREATE TABLE user_benefits (
    user_benefit_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    benefit_type_id INTEGER NOT NULL,
    document_number VARCHAR(255) NOT NULL,
    valid_from DATE NOT NULL,
    valid_until DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'revoked')),
    university_id INTEGER,
    verified_enrollment_id INTEGER,
    approved_by INTEGER,
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (benefit_type_id) REFERENCES benefit_types(benefit_type_id),
    FOREIGN KEY (university_id) REFERENCES universities(university_id) ON DELETE SET NULL,
    FOREIGN KEY (verified_enrollment_id) REFERENCES university_students(enrollment_id) ON DELETE SET NULL,
    FOREIGN KEY (approved_by) REFERENCES users(user_id) ON DELETE SET NULL,
    CHECK (valid_until >= valid_from)
);

CREATE INDEX idx_user_benefits_user_id ON user_benefits(user_id);
CREATE INDEX idx_user_benefits_status ON user_benefits(status);
CREATE INDEX idx_user_benefits_benefit_type_id ON user_benefits(benefit_type_id);
CREATE INDEX idx_user_benefits_university_id ON user_benefits(university_id);

COMMENT ON TABLE user_benefits IS 'Facilitățile concrete acordate utilizatorilor (ex: card student validat)';
COMMENT ON COLUMN user_benefits.university_id IS 'Universitatea responsabilă de verificarea acestei facilități';
COMMENT ON COLUMN user_benefits.verified_enrollment_id IS 'Referință la înregistrarea din baza universității care a confirmat statutul de student';
COMMENT ON COLUMN user_benefits.rejection_reason IS 'Motivul respingerii, completat de agentul universitar';


-- ==============================================================================
-- 13. DREPTURI DE CĂLĂTORIE UNIFICATE
-- ==============================================================================
CREATE TABLE travel_entitlements (
    entitlement_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    source_type VARCHAR(50) NOT NULL
        CHECK (source_type IN ('ticket', 'subscription', 'benefit')),
    ticket_id INTEGER,
    subscription_id INTEGER,
    user_benefit_id INTEGER,
    valid_from DATE NOT NULL,
    valid_until DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'expired', 'used')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE SET NULL,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id) ON DELETE SET NULL,
    FOREIGN KEY (user_benefit_id) REFERENCES user_benefits(user_benefit_id) ON DELETE SET NULL,
    CHECK (valid_until >= valid_from),
    CHECK (
        (source_type = 'ticket' AND ticket_id IS NOT NULL) OR
        (source_type = 'subscription' AND subscription_id IS NOT NULL) OR
        (source_type = 'benefit' AND user_benefit_id IS NOT NULL)
    )
);

CREATE INDEX idx_travel_entitlements_user_id ON travel_entitlements(user_id);
CREATE INDEX idx_travel_entitlements_source_type ON travel_entitlements(source_type);
CREATE INDEX idx_travel_entitlements_status ON travel_entitlements(status);
CREATE INDEX idx_travel_entitlements_valid_until ON travel_entitlements(valid_until);

COMMENT ON TABLE travel_entitlements IS 'Tabel unificator pentru toate drepturile de călătorie - permite validare uniformă';


-- ==============================================================================
-- 14. TOKENURI QR PENTRU VALIDARE
-- ==============================================================================
CREATE TABLE qr_tokens (
    qr_token_id SERIAL PRIMARY KEY,
    entitlement_id INTEGER NOT NULL,
    token_value VARCHAR(500) NOT NULL UNIQUE,
    token_hash VARCHAR(500) NOT NULL UNIQUE,
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'used', 'cancelled', 'expired')),
    used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entitlement_id) REFERENCES travel_entitlements(entitlement_id) ON DELETE CASCADE,
    CHECK (expires_at > issued_at)
);

CREATE INDEX idx_qr_tokens_entitlement_id ON qr_tokens(entitlement_id);
CREATE INDEX idx_qr_tokens_status ON qr_tokens(status);
CREATE INDEX idx_qr_tokens_expires_at ON qr_tokens(expires_at);

COMMENT ON TABLE qr_tokens IS 'Tokenuri QR cu validitate limitată. Token_hash e stocat din motive de securitate';


-- ==============================================================================
-- 15. VALIDĂRI - ISTORICUL PENTRU FIECARE SCANARE
-- ==============================================================================
CREATE TABLE validations (
    validation_id SERIAL PRIMARY KEY,
    qr_token_id INTEGER NOT NULL,
    conductor_id INTEGER NOT NULL,
    validation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    validation_result VARCHAR(50) NOT NULL
        CHECK (validation_result IN ('valid', 'already_used', 'expired', 'invalid_token', 'not_found')),
    location_station_id INTEGER,
    device_id VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (qr_token_id) REFERENCES qr_tokens(qr_token_id) ON DELETE CASCADE,
    FOREIGN KEY (conductor_id) REFERENCES users(user_id),
    FOREIGN KEY (location_station_id) REFERENCES stations(station_id)
);

CREATE INDEX idx_validations_qr_token_id ON validations(qr_token_id);
CREATE INDEX idx_validations_conductor_id ON validations(conductor_id);
CREATE INDEX idx_validations_validation_time ON validations(validation_time);
CREATE INDEX idx_validations_result ON validations(validation_result);

COMMENT ON TABLE validations IS 'Istoricul complet al validărilor - cui, cand, unde, cu ce rezultat';


-- ==============================================================================
-- 16. AUDIT LOG - Trasabilitate completă
-- ==============================================================================
CREATE TABLE audit_logs (
    audit_log_id SERIAL PRIMARY KEY,
    actor_user_id INTEGER,
    action_type VARCHAR(100) NOT NULL,
    target_table VARCHAR(100) NOT NULL,
    target_id INTEGER,
    action_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    user_agent TEXT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (actor_user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_logs_action_type ON audit_logs(action_type);
CREATE INDEX idx_audit_logs_target_table ON audit_logs(target_table);
CREATE INDEX idx_audit_logs_action_timestamp ON audit_logs(action_timestamp);

COMMENT ON TABLE audit_logs IS 'Jurnal de audit - all operații importante pentru trata GDPR și securitate';


-- ==============================================================================
-- VIEW-URI PENTRU REZULTATE UTILE
-- ==============================================================================

-- View: Drepturi de călătorie active
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
        WHEN CURRENT_DATE > te.valid_until THEN 'EXPIRED'
        WHEN CURRENT_DATE >= te.valid_from THEN 'ACTIVE'
        ELSE 'NOT_YET_VALID'
    END as computed_status
FROM travel_entitlements te
JOIN users u ON te.user_id = u.user_id
WHERE te.status = 'active';

COMMENT ON VIEW active_travel_entitlements IS 'Vizualizare drepturi de călătorie valide în timp real';


-- View: Rezumat profil utilizator
CREATE VIEW user_travel_summary AS
SELECT 
    u.user_id,
    u.first_name,
    u.last_name,
    u.email,
    COUNT(DISTINCT CASE WHEN t.ticket_status = 'active' THEN t.ticket_id END) as active_tickets,
    COUNT(DISTINCT CASE WHEN s.status = 'active' THEN s.subscription_id END) as active_subscriptions,
    COUNT(DISTINCT CASE WHEN ub.status = 'approved' THEN ub.user_benefit_id END) as active_benefits,
    COUNT(DISTINCT v.validation_id) as total_validations
FROM users u
LEFT JOIN tickets t ON u.user_id = t.user_id
LEFT JOIN subscriptions s ON u.user_id = s.user_id
LEFT JOIN user_benefits ub ON u.user_id = ub.user_id
LEFT JOIN travel_entitlements te ON u.user_id = te.user_id
LEFT JOIN qr_tokens qt ON te.entitlement_id = qt.entitlement_id
LEFT JOIN validations v ON qt.qr_token_id = v.qr_token_id
GROUP BY u.user_id, u.first_name, u.last_name, u.email;

COMMENT ON VIEW user_travel_summary IS 'Rezumat activități pentru fiecare utilizator';


-- View: Istoricul validărilor cu detalii complete
CREATE VIEW validation_history_detailed AS
SELECT 
    v.validation_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    c.first_name || ' ' || c.last_name as conductor_name,
    s.name as station_name,
    v.validation_time,
    v.validation_result,
    te.source_type,
    te.valid_until,
    v.notes
FROM validations v
JOIN qr_tokens qt ON v.qr_token_id = qt.qr_token_id
JOIN travel_entitlements te ON qt.entitlement_id = te.entitlement_id
JOIN users u ON te.user_id = u.user_id
JOIN users c ON v.conductor_id = c.user_id
LEFT JOIN stations s ON v.location_station_id = s.station_id
ORDER BY v.validation_time DESC;

COMMENT ON VIEW validation_history_detailed IS 'Istoricul validărilor cu toate detaliile relevante';


-- ==============================================================================
-- TRIGGER: Marcă QR ca "used" după validare reușită
-- ==============================================================================
CREATE OR REPLACE FUNCTION mark_qr_as_used()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.validation_result = 'valid' THEN
        UPDATE qr_tokens 
        SET status = 'used', used_at = CURRENT_TIMESTAMP
        WHERE qr_token_id = NEW.qr_token_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mark_qr_used
AFTER INSERT ON validations
FOR EACH ROW
EXECUTE FUNCTION mark_qr_as_used();


-- ==============================================================================
-- FUNCȚII: Verificare drept de călătorie
-- ==============================================================================
CREATE OR REPLACE FUNCTION check_travel_entitlement(p_entitlement_id INTEGER)
RETURNS TABLE(is_valid BOOLEAN, reason VARCHAR) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        CASE 
            WHEN te.status != 'active' THEN false
            WHEN CURRENT_DATE < te.valid_from THEN false
            WHEN CURRENT_DATE > te.valid_until THEN false
            ELSE true
        END as is_valid,
        CASE 
            WHEN te.status != 'active' THEN 'Status not active'
            WHEN CURRENT_DATE < te.valid_from THEN 'Not yet valid'
            WHEN CURRENT_DATE > te.valid_until THEN 'Expired'
            ELSE 'Valid'
        END as reason
    FROM travel_entitlements te
    WHERE te.entitlement_id = p_entitlement_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION check_travel_entitlement IS 'Verifică în timp real dacă un drept de călătorie este valid';


-- ==============================================================================
-- FUNCȚIE: Număr validări pe controlor într-o perioadă
-- ==============================================================================
CREATE OR REPLACE FUNCTION conductor_validations_count(
    p_conductor_id INTEGER,
    p_start_date DATE,
    p_end_date DATE
)
RETURNS INTEGER AS $$
DECLARE
    count_validations INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO count_validations
    FROM validations
    WHERE conductor_id = p_conductor_id
        AND DATE(validation_time) BETWEEN p_start_date AND p_end_date
        AND validation_result = 'valid';
    
    RETURN COALESCE(count_validations, 0);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION conductor_validations_count IS 'Calculează numărul de validări reușite ale unui controlor';


-- ==============================================================================
-- INSERARE DATE INIȚIALE - Tipuri de facilități
-- ==============================================================================
INSERT INTO benefit_types (name, description, discount_percent, requires_proof)
VALUES 
    ('Student', 'Reducere pentru studenți valizi', 25.00, true),
    ('Pensioner', 'Reducere pentru persoane în vârstă', 35.00, true),
    ('Disability', 'Gratuit pentru persoane cu dizabilități', 100.00, true),
    ('Family Group', 'Reducere grup familial', 20.00, false),
    ('Early Bird', 'Reducere bilete cu 7 zile înainte', 10.00, false);

COMMENT ON TABLE benefit_types IS 'Inițializate tipurile principale de facilități';


-- ==============================================================================
-- VIEW: Facilități studențești în așteptare (pentru dashboard agent universitar)
-- ==============================================================================
CREATE VIEW pending_student_benefits AS
SELECT
    ub.user_benefit_id,
    ub.university_id,
    univ.short_name          AS university_short_name,
    univ.name                AS university_name,
    u.first_name || ' ' || u.last_name AS student_name,
    u.email                  AS student_email,
    ub.document_number,
    ub.valid_from,
    ub.valid_until,
    ub.status,
    ub.created_at            AS applied_at
FROM user_benefits ub
JOIN users u           ON ub.user_id = u.user_id
JOIN universities univ ON ub.university_id = univ.university_id
JOIN benefit_types bt  ON ub.benefit_type_id = bt.benefit_type_id
WHERE bt.name = 'Student'
  AND ub.status = 'pending'
ORDER BY ub.created_at ASC;

COMMENT ON VIEW pending_student_benefits IS 'Cereri de facilitate student în așteptarea verificării de agentul universitar';


-- ==============================================================================
-- VIEW: Sumar activitate agenți universitari
-- ==============================================================================
CREATE VIEW university_agent_summary AS
SELECT
    univ.university_id,
    univ.short_name,
    univ.name                AS university_name,
    COUNT(CASE WHEN ub.status = 'pending'  THEN 1 END) AS pending_count,
    COUNT(CASE WHEN ub.status = 'approved' THEN 1 END) AS approved_count,
    COUNT(CASE WHEN ub.status = 'rejected' THEN 1 END) AS rejected_count,
    COUNT(ua.user_id)                                   AS agents_count
FROM universities univ
LEFT JOIN user_benefits ub ON ub.university_id = univ.university_id
LEFT JOIN users ua ON ua.university_id = univ.university_id AND ua.role = 'university_agent'
GROUP BY univ.university_id, univ.short_name, univ.name;

COMMENT ON VIEW university_agent_summary IS 'Statistici per universitate: cereri pendente, aprobate, respinse și număr agenți';


-- ==============================================================================
-- TRIGGER: Asignare automată universitate la cerere facilitate student
-- ==============================================================================
CREATE OR REPLACE FUNCTION auto_assign_university_to_benefit()
RETURNS TRIGGER AS $$
DECLARE
    v_benefit_name   VARCHAR;
    v_university_id  INTEGER;
BEGIN
    SELECT bt.name INTO v_benefit_name
    FROM benefit_types bt
    WHERE bt.benefit_type_id = NEW.benefit_type_id;

    IF v_benefit_name = 'Student' THEN
        SELECT u.university_id INTO v_university_id
        FROM users u
        WHERE u.user_id = NEW.user_id;

        IF v_university_id IS NOT NULL THEN
            NEW.university_id := v_university_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auto_assign_university
BEFORE INSERT ON user_benefits
FOR EACH ROW
EXECUTE FUNCTION auto_assign_university_to_benefit();

COMMENT ON FUNCTION auto_assign_university_to_benefit IS
'La depunerea unei cereri de tip Student, preia university_id din profilul utilizatorului';


-- ==============================================================================
-- TRIGGER: Creare automată travel_entitlement la aprobarea unui beneficiu
-- ==============================================================================
CREATE OR REPLACE FUNCTION create_entitlement_on_benefit_approval()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'approved' AND OLD.status <> 'approved' THEN
        INSERT INTO travel_entitlements
            (user_id, source_type, user_benefit_id, valid_from, valid_until, status)
        VALUES
            (NEW.user_id, 'benefit', NEW.user_benefit_id, NEW.valid_from, NEW.valid_until, 'active');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_create_entitlement_on_approval
AFTER UPDATE ON user_benefits
FOR EACH ROW
EXECUTE FUNCTION create_entitlement_on_benefit_approval();

COMMENT ON FUNCTION create_entitlement_on_benefit_approval IS
'La aprobarea unui beneficiu de agentul universitar, creează automat dreptul de călătorie corespunzător';


-- ==============================================================================
-- FUNCȚIE: Verificare student în baza universității
-- ==============================================================================
CREATE OR REPLACE FUNCTION verify_student_enrollment(
    p_user_benefit_id INTEGER,
    p_student_number  VARCHAR
)
RETURNS TABLE(found BOOLEAN, enrollment_id INTEGER, enrollment_status VARCHAR) AS $$
DECLARE
    v_university_id INTEGER;
BEGIN
    SELECT ub.university_id INTO v_university_id
    FROM user_benefits ub
    WHERE ub.user_benefit_id = p_user_benefit_id;

    RETURN QUERY
    SELECT
        TRUE                    AS found,
        us.enrollment_id,
        us.enrollment_status
    FROM university_students us
    WHERE us.university_id  = v_university_id
      AND us.student_number = p_student_number
      AND us.enrollment_status = 'active'
    UNION ALL
    SELECT FALSE, NULL, NULL
    WHERE NOT EXISTS (
        SELECT 1 FROM university_students us
        WHERE us.university_id  = v_university_id
          AND us.student_number = p_student_number
          AND us.enrollment_status = 'active'
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION verify_student_enrollment IS
'Verifică dacă numărul matricol există în baza universității responsabile de cererea dată';


-- ==============================================================================
-- FUNCȚIE: Statistici rapide pentru agentul universitar (dashboard)
-- ==============================================================================
CREATE OR REPLACE FUNCTION university_agent_stats(p_university_id INTEGER)
RETURNS TABLE(
    pending_count    INTEGER,
    approved_today   INTEGER,
    rejected_today   INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(CASE WHEN ub.status = 'pending' THEN 1 END)::INTEGER,
        COUNT(CASE WHEN ub.status = 'approved'
                    AND DATE(ub.approved_at) = CURRENT_DATE THEN 1 END)::INTEGER,
        COUNT(CASE WHEN ub.status = 'rejected'
                    AND DATE(ub.approved_at) = CURRENT_DATE THEN 1 END)::INTEGER
    FROM user_benefits ub
    WHERE ub.university_id = p_university_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION university_agent_stats IS
'Returnează statisticile zilnice pentru dashboardul agentului universitar';


-- ==============================================================================
-- GRANT PERMISIUNI (dacă e necesar)
-- ==============================================================================
-- Descomentează dacă ai un utilizator PostgreSQL specific pentru aplicație:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

