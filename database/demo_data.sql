-- ==============================================================================
-- GAME DEMO DATA - Pentru dezvoltare și testare
-- ==============================================================================

-- Resetare ID sequences
ALTER SEQUENCE universities_university_id_seq RESTART;
ALTER SEQUENCE university_students_enrollment_id_seq RESTART;
ALTER SEQUENCE users_user_id_seq RESTART;
ALTER SEQUENCE railway_operators_operator_id_seq RESTART;
ALTER SEQUENCE stations_station_id_seq RESTART;
ALTER SEQUENCE routes_route_id_seq RESTART;
ALTER SEQUENCE trains_train_id_seq RESTART;
ALTER SEQUENCE tickets_ticket_id_seq RESTART;
ALTER SEQUENCE subscriptions_subscription_id_seq RESTART;
ALTER SEQUENCE route_stops_route_stop_id_seq RESTART;


-- ==============================================================================
-- 0. UNIVERSITĂȚI DEMO
-- ==============================================================================

INSERT INTO universities (name, short_name, city, email_domain, contact_email) VALUES
    ('Universitatea Politehnica București', 'UPB',   'București', 'stud.acs.upb.ro', 'secretariat@upb.ro'),
    ('Academia de Studii Economice',        'ASE',   'București', 'stud.ase.ro',     'secretariat@ase.ro'),
    ('Universitatea din București',         'UNIBUC','București', 'student.unibuc.ro','secretariat@unibuc.ro');


-- ==============================================================================
-- 0b. BAZA DE DATE STUDENȚI (înregistrări per universitate)
-- ==============================================================================

INSERT INTO university_students
    (university_id, student_number, first_name, last_name, faculty, study_program,
     year_of_study, enrollment_status, enrollment_date, expected_graduation)
VALUES
    (1, 'UPB2002001', 'Andrei',    'Ionescu', 'Facultatea de Automatică și Calculatoare',
     'Calculatoare', 3, 'active', '2022-10-01', '2026-07-01'),
    (1, 'UPB2001002', 'Alexandra', 'Popescu', 'Facultatea de Electronică',
     'Electronică Aplicată', 4, 'active', '2021-10-01', '2025-07-01'),
    (2, 'ASE2003003', 'Elena',     'Stancu',  'Facultatea de Contabilitate',
     'Contabilitate și Informatică de Gestiune', 2, 'active', '2023-10-01', '2027-07-01'),
    (3, 'UNIBUC2000004', 'Radu',   'Marin',   'Facultatea de Drept',
     'Drept', 5, 'active', '2020-10-01', '2025-07-01');


-- ==============================================================================
-- 1. UTILIZATORI DEMO
-- ==============================================================================

-- Utilizator 1: Pasager normal cu bilete
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role)
VALUES (
    'Alexandra', 'Popescu',
    'alexandra.popescu@email.com',
    '$2b$12$demo_hash_alexandra_popescu_12345678901234567890123456789',
    '+40721234567',
    '1995-03-15',
    'passenger'
);

-- Utilizator 2: Student cu facilități
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role)
VALUES (
    'Andrei', 'Ionescu',
    'andrei.ionescu@email.com',
    '$2b$12$demo_hash_andrei_ionescu_12345678901234567890123456789',
    '+40722334455',
    '2002-07-22',
    'passenger'
);

-- Utilizator 3: Pensionar
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role)
VALUES (
    'Ioan', 'Vasile',
    'ioan.vasile@email.com',
    '$2b$12$demo_hash_ioan_vasile_12345678901234567890123456789',
    '+40723445566',
    '1955-12-10',
    'passenger'
);

-- Utilizator 4: Pasager cu abonament lunar
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role)
VALUES (
    'Maria', 'Dumitru',
    'maria.dumitru@email.com',
    '$2b$12$demo_hash_maria_dumitru_12345678901234567890123456789',
    '+40724556677',
    '1988-05-18',
    'passenger'
);

-- Utilizator 5: Controlor de tren
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role)
VALUES (
    'George', 'Constantinescu',
    'george.constantinescu@email.com',
    '$2b$12$demo_hash_george_constantinescu_123456789012345678901234',
    '+40725667788',
    '1978-01-09',
    'conductor'
);

-- Utilizator 6: Admin
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role)
VALUES (
    'Administrator', 'System',
    'admin@railway.gov.ro',
    '$2b$12$demo_hash_admin_system_1234567890123456789012345678901234',
    '+40726778899',
    '1980-06-20',
    'admin'
);

-- Utilizator 7: Agent verificator universitar (UPB)
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role, university_id)
VALUES (
    'Mihai', 'Radu',
    'agent.verificator@upb.ro',
    '$2b$12$demo_hash_agent_upb_123456789012345678901234567890123456',
    '+40727889900',
    '1982-09-14',
    'university_agent',
    1  -- UPB
);

-- Utilizator 8: Agent verificator universitar (ASE)
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role, university_id)
VALUES (
    'Ioana', 'Constantin',
    'agent.verificator@ase.ro',
    '$2b$12$demo_hash_agent_ase_123456789012345678901234567890123456',
    '+40728990011',
    '1990-03-22',
    'university_agent',
    2  -- ASE
);

-- Link studenți la universități (university_id pe contul de utilizator)
UPDATE users SET university_id = 1 WHERE email = 'andrei.ionescu@email.com';    -- UPB
UPDATE users SET university_id = 1 WHERE email = 'alexandra.popescu@email.com'; -- UPB


-- ==============================================================================
-- 2. IDENTITĂȚI DIGITALE
-- ==============================================================================

INSERT INTO digital_identities (user_id, identity_code, status, issued_at, expires_at)
VALUES 
    (1, 'DI_2026_00001_APOPESCU', 'active', '2025-01-15', '2027-01-15'),
    (2, 'DI_2026_00002_AIONESCU', 'active', '2025-02-01', '2027-02-01'),
    (3, 'DI_2026_00003_IVASILE', 'active', '2024-12-01', '2026-12-01'),
    (4, 'DI_2026_00004_MDUMITRU', 'active', '2025-01-20', '2027-01-20'),
    (5, 'DI_2026_00005_GCONSTANTINESCU', 'active', '2025-01-10', '2027-01-10');


-- ==============================================================================
-- 3. METODE DE AUTENTIFICARE
-- ==============================================================================

INSERT INTO auth_methods (user_id, method_type, secret_value, is_enabled)
VALUES
    (1, 'password', NULL, true),
    (1, 'totp', 'JBSWY3DPEBLW64TMMQ======', true),  -- Secret TOTP pentru MFA
    (2, 'password', NULL, true),
    (3, 'password', NULL, true),
    (4, 'password', NULL, true),
    (5, 'password', NULL, true),
    (6, 'password', NULL, true),
    (7, 'password', NULL, true),  -- Agent UPB
    (8, 'password', NULL, true);  -- Agent ASE


-- ==============================================================================
-- 4. OPERATORI FEROVIARI
-- ==============================================================================

INSERT INTO railway_operators (name, code, country, contact_email, contact_phone)
VALUES
    ('Căi Ferate Române', 'CFR', 'Romania', 'contact@cfr.ro', '+40213160000'),
    ('Astra Trains', 'ASTRA', 'Romania', 'info@astratrains.ro', '+40213254567'),
    ('TrainExpress', 'TEXPRESS', 'Romania', 'support@trainexpress.ro', '+40213125678');


-- ==============================================================================
-- 5. STAȚII FEROVIARE
-- ==============================================================================

INSERT INTO stations (name, city, code, latitude, longitude)
VALUES
    ('Bucharest Central', 'Bucharest', 'BUH_C', 44.4268, 26.0970),
    ('Bucharest North', 'Bucharest', 'BUH_N', 44.4612, 26.0733),
    ('Cluj Central', 'Cluj-Napoca', 'CLJ_C', 46.7712, 23.6236),
    ('Timișoara Central', 'Timișoara', 'TIM_C', 45.7613, 21.2246),
    ('Brașov Central', 'Brașov', 'BRA_C', 45.6371, 25.5951),
    ('Constanța Central', 'Constanța', 'CNS_C', 44.1598, 28.6648),
    ('Iași Central', 'Iași', 'IAS_C', 47.1667, 27.5833),
    ('Sibiu Central', 'Sibiu', 'SIB_C', 45.7979, 24.1486);


-- ==============================================================================
-- 6. RUTE FEROVIARE
-- ==============================================================================

INSERT INTO routes (operator_id, route_name, origin_station_id, destination_station_id, distance_km)
VALUES
    (1, 'Bucharest - Cluj', 1, 3, 445),
    (1, 'Bucharest - Constanta', 1, 6, 236),
    (1, 'Cluj - Timisoara', 3, 4, 198),
    (2, 'Bucharest - Brasov', 2, 5, 164),
    (2, 'Brasov - Sibiu', 5, 8, 140),
    (3, 'Iasi - Bucharest', 7, 1, 480);


-- ==============================================================================
-- 7. OPRIRI ÎN TRASEU
-- ==============================================================================

-- Ruta 1: Bucharest - Cluj (cu oprire la Sibiu)
INSERT INTO route_stops (route_id, station_id, stop_order, planned_arrival_time, planned_departure_time)
VALUES
    (1, 1, 1, NULL, '08:00:00'),
    (1, 8, 2, '17:00:00', '17:15:00'),
    (1, 3, 3, '20:30:00', NULL);

-- Ruta 2: Bucharest - Constanta
INSERT INTO route_stops (route_id, station_id, stop_order, planned_arrival_time, planned_departure_time)
VALUES
    (2, 1, 1, NULL, '09:00:00'),
    (2, 6, 2, '12:45:00', NULL);

-- Ruta 3: Cluj - Timisoara
INSERT INTO route_stops (route_id, station_id, stop_order, planned_arrival_time, planned_departure_time)
VALUES
    (3, 3, 1, NULL, '10:00:00'),
    (3, 4, 2, '14:30:00', NULL);

-- Ruta 4: Bucharest - Brasov
INSERT INTO route_stops (route_id, station_id, stop_order, planned_arrival_time, planned_departure_time)
VALUES
    (4, 2, 1, NULL, '07:30:00'),
    (4, 5, 2, '09:30:00', NULL);

-- Ruta 5: Brasov - Sibiu
INSERT INTO route_stops (route_id, station_id, stop_order, planned_arrival_time, planned_departure_time)
VALUES
    (5, 5, 1, NULL, '12:00:00'),
    (5, 8, 2, '14:20:00', NULL);

-- Ruta 6: Iasi - Bucharest
INSERT INTO route_stops (route_id, station_id, stop_order, planned_arrival_time, planned_departure_time)
VALUES
    (6, 7, 1, NULL, '14:00:00'),
    (6, 1, 2, '22:30:00', NULL);


-- ==============================================================================
-- 8. TRENURI
-- ==============================================================================

INSERT INTO trains (operator_id, route_id, train_number, train_type, capacity)
VALUES
    (1, 1, 'R2400', 'intercity', 300),
    (1, 2, 'R2401', 'regional', 200),
    (1, 3, 'R2350', 'intercity', 280),
    (2, 4, 'R2100', 'intercity', 250),
    (2, 5, 'R2101', 'regional', 180),
    (3, 6, 'R2500', 'express', 320);


-- ==============================================================================
-- 9. BILETE
-- ==============================================================================

-- Bilet activ pentru utilizator 1
INSERT INTO tickets (user_id, train_id, departure_station_id, arrival_station_id, travel_date, travel_time, seat_number, ticket_type, ticket_status, price, issued_at)
VALUES
    (1, 1, 1, 3, '2026-04-10', '08:00:00', '12A', 'single', 'active', 189.99, '2026-03-30'),
    (1, 2, 1, 6, '2026-04-15', '09:00:00', '5B', 'single', 'active', 75.50, '2026-03-28');

-- Bilet pentru utilizator 2 (student)
INSERT INTO tickets (user_id, train_id, departure_station_id, arrival_station_id, travel_date, travel_time, seat_number, ticket_type, ticket_status, price, issued_at)
VALUES
    (2, 4, 2, 5, '2026-04-08', '07:30:00', '8C', 'single', 'active', 49.99, '2026-03-25');

-- Bilet expirat
INSERT INTO tickets (user_id, train_id, departure_station_id, arrival_station_id, travel_date, travel_time, seat_number, ticket_type, ticket_status, price, issued_at)
VALUES
    (3, 2, 1, 6, '2026-02-10', '09:00:00', '15D', 'single', 'expired', 75.50, '2026-02-01');

-- Bilet deja folosit
INSERT INTO tickets (user_id, train_id, departure_station_id, arrival_station_id, travel_date, travel_time, seat_number, ticket_type, ticket_status, price, issued_at)
VALUES
    (4, 1, 1, 3, '2026-03-25', '08:00:00', '22E', 'single', 'used', 189.99, '2026-03-20');


-- ==============================================================================
-- 10. ABONAMENTE
-- ==============================================================================

-- Abonament lunar activ
INSERT INTO subscriptions (user_id, subscription_type, operator_id, valid_from, valid_until, status, price)
VALUES
    (4, 'monthly', 1, '2026-03-01', '2026-03-31', 'active', 299.99);

-- Abonament anual expirat
INSERT INTO subscriptions (user_id, subscription_type, operator_id, valid_from, valid_until, status, price)
VALUES
    (3, 'annual', 1, '2025-01-01', '2025-12-31', 'expired', 2500.00);

-- Abonament pe rută disponibil pentru utilizator 2
INSERT INTO subscriptions (user_id, subscription_type, route_id, valid_from, valid_until, status, price)
VALUES
    (2, 'monthly', NULL, '2026-04-01', '2026-04-30', 'active', 199.99);


-- ==============================================================================
-- 11. FACILITĂȚI UTILIZATOR
-- ==============================================================================

-- Facilitate student aprobată pentru Andrei (UPB) - aprobată de agentul UPB (user 7)
-- university_id=1 (UPB), verified_enrollment_id=1 (înregistrarea UPB2002001)
INSERT INTO user_benefits
    (user_id, benefit_type_id, document_number, valid_from, valid_until,
     status, university_id, verified_enrollment_id, approved_by, approved_at)
VALUES
    (2, 1, 'UPB2002001', '2026-01-01', '2026-09-30',
     'approved', 1, 1, 7, '2026-01-15');

-- Facilitate pensionar pentru Ioan (nu necesită universitate)
INSERT INTO user_benefits (user_id, benefit_type_id, document_number, valid_from, valid_until, status, approved_by, approved_at)
VALUES
    (3, 2, 'PEN_2026_00012', '2025-01-01', '2026-12-31', 'approved', 6, '2025-12-20');

-- Facilitate student pendentă pentru Alexandra (UPB) - așteptând verificarea agentului UPB
-- university_id=1 asignat automat de trigger din users.university_id
INSERT INTO user_benefits
    (user_id, benefit_type_id, document_number, valid_from, valid_until,
     status, university_id)
VALUES
    (1, 1, 'UPB2001002', '2026-02-01', '2026-09-30', 'pending', 1);

-- Facilitate student respinsă (număr matricol invalid, demonstrează workflow-ul de respingere)
INSERT INTO user_benefits
    (user_id, benefit_type_id, document_number, valid_from, valid_until,
     status, university_id, approved_by, approved_at, rejection_reason)
VALUES
    (1, 1, 'INVALID_999', '2025-09-01', '2026-01-31',
     'rejected', 1, 7, '2026-01-10',
     'Numărul matricol nu a fost găsit în baza de date a universității');


-- ==============================================================================
-- 12. DREPTURI DE CĂLĂTORIE UNIFICATE
-- ==============================================================================

-- Drept din bilet activ pentru utilizator 1
INSERT INTO travel_entitlements (user_id, source_type, ticket_id, valid_from, valid_until, status)
VALUES
    (1, 'ticket', 1, '2026-04-10', '2026-04-10', 'active');

-- Drept din bilet pentru utilizator 2
INSERT INTO travel_entitlements (user_id, source_type, ticket_id, valid_from, valid_until, status)
VALUES
    (2, 'ticket', 3, '2026-04-08', '2026-04-08', 'active');

-- Drept din abonament pentru utilizator 4
INSERT INTO travel_entitlements (user_id, source_type, subscription_id, valid_from, valid_until, status)
VALUES
    (4, 'subscription', 1, '2026-03-01', '2026-03-31', 'active');

-- Drept din facilitate pentru utilizator 2 (student)
INSERT INTO travel_entitlements (user_id, source_type, user_benefit_id, valid_from, valid_until, status)
VALUES
    (2, 'benefit', 1, '2026-01-01', '2026-09-30', 'active');

-- Drept expirat
INSERT INTO travel_entitlements (user_id, source_type, ticket_id, valid_from, valid_until, status)
VALUES
    (3, 'ticket', 4, '2026-02-10', '2026-02-10', 'expired');


-- ==============================================================================
-- 13. TOKENURI QR PENTRU VALIDARE
-- ==============================================================================

-- Token activ pentru drept 1
INSERT INTO qr_tokens (entitlement_id, token_value, token_hash, issued_at, expires_at, status)
VALUES
    (1, 'QR_TOKEN_ACTIVE_001', 'hash_qr_active_001_sha256_length_64_bytes_0000000000000000000000', '2026-04-09 20:00:00', '2026-04-10 09:00:00', 'active');

-- Token deși folosit
INSERT INTO qr_tokens (entitlement_id, token_value, token_hash, issued_at, expires_at, status, used_at)
VALUES
    (2, 'QR_TOKEN_USED_002', 'hash_qr_used_002_sha256_length_64_bytes_00000000000000000000000', '2026-04-07 15:00:00', '2026-04-08 10:00:00', 'used', '2026-04-08 08:30:00');

-- Token expirat
INSERT INTO qr_tokens (entitlement_id, token_value, token_hash, issued_at, expires_at, status)
VALUES
    (3, 'QR_TOKEN_EXPIRED_003', 'hash_qr_expired_003_sha256_length_64_bytes_0000000000000000000', '2026-02-09 12:00:00', '2026-02-10 08:00:00', 'expired');

-- Token activ pentru student
INSERT INTO qr_tokens (entitlement_id, token_value, token_hash, issued_at, expires_at, status)
VALUES
    (4, 'QR_TOKEN_ACTIVE_004', 'hash_qr_active_004_sha256_length_64_bytes_0000000000000000000000', '2026-04-08 18:00:00', '2026-04-09 10:00:00', 'active');


-- ==============================================================================
-- 14. VALIDĂRI (SCANĂRI)
-- ==============================================================================

-- Validare reușită
INSERT INTO validations (qr_token_id, conductor_id, validation_time, validation_result, location_station_id, device_id, notes)
VALUES
    (2, 5, '2026-04-08 08:35:00', 'valid', 2, 'DEVICE_001', 'Bilet valid - Student cu reducere');

-- Validare eșuată - token expirat
INSERT INTO validations (qr_token_id, conductor_id, validation_time, validation_result, location_station_id, device_id, notes)
VALUES
    (3, 5, '2026-02-10 07:45:00', 'expired', 1, 'DEVICE_001', 'Bilet expirat - reclama recepționată');

-- Validare eșuată - token deja folosit
INSERT INTO validations (qr_token_id, conductor_id, validation_time, validation_result, location_station_id, device_id, notes)
VALUES
    (2, 5, '2026-04-08 15:00:00', 'already_used', 6, 'DEVICE_002', 'Attempt de re-utilizare a aceluiași bilet');

-- Validare reușită - utilizator pensionar
INSERT INTO validations (qr_token_id, conductor_id, validation_time, validation_result, location_station_id, device_id, notes)
VALUES
    (4, 5, '2026-04-08 09:15:00', 'valid', 2, 'DEVICE_001', 'Bilet valid - Student');


-- ==============================================================================
-- 15. AUDIT LOGS (Operații importante)
-- ==============================================================================

-- Înregistrare utilizator - prima dată
INSERT INTO audit_logs (actor_user_id, action_type, target_table, target_id, ip_address, user_agent, details)
VALUES
    (1, 'CREATE', 'users', 1, '192.168.1.100', 'Mozilla/5.0', 'User registered - alexandra.popescu@email.com');

-- Login reușit
INSERT INTO audit_logs (actor_user_id, action_type, target_table, target_id, ip_address, user_agent, details)
VALUES
    (1, 'LOGIN_SUCCESS', 'users', 1, '192.168.1.100', 'Mozilla/5.0', 'Login successful');

-- Creare bilet
INSERT INTO audit_logs (actor_user_id, action_type, target_table, target_id, ip_address, user_agent, details)
VALUES
    (1, 'CREATE', 'tickets', 1, '192.168.1.100', 'Mozilla/5.0', 'Ticket purchased - Bucharest to Cluj');

-- Generare QR token
INSERT INTO audit_logs (actor_user_id, action_type, target_table, target_id, ip_address, user_agent, details)
VALUES
    (1, 'CREATE', 'qr_tokens', 1, '192.168.1.100', 'Mozilla/5.0', 'QR token generated for travel');

-- Validare QR
INSERT INTO audit_logs (actor_user_id, action_type, target_table, target_id, ip_address, user_agent, details)
VALUES
    (5, 'CREATE', 'validations', 1, '192.168.10.50', 'Custom Android App', 'QR validation successful - conductor 5');

-- Cerere export date
INSERT INTO audit_logs (actor_user_id, action_type, target_table, target_id, ip_address, user_agent, details)
VALUES
    (2, 'EXPORT', 'users', 2, '192.168.1.101', 'Mozilla/5.0', 'User data export requested - GDPR');

-- Admin aprob facilitate
INSERT INTO audit_logs (actor_user_id, action_type, target_table, target_id, ip_address, user_agent, details)
VALUES
    (6, 'UPDATE', 'user_benefits', 1, '192.168.10.100', 'Mozilla/5.0', 'Student benefit approved');


-- ==============================================================================
-- VERIFICARE DATE INSERATE
-- ==============================================================================

SELECT 'Universities' as entity, COUNT(*) as count FROM universities
UNION ALL
SELECT 'University Students', COUNT(*) FROM university_students
UNION ALL
SELECT 'Users' as entity, COUNT(*) FROM users
UNION ALL
SELECT 'Digital Identities', COUNT(*) FROM digital_identities
UNION ALL
SELECT 'Auth Methods', COUNT(*) FROM auth_methods
UNION ALL
SELECT 'Railway Operators', COUNT(*) FROM railway_operators
UNION ALL
SELECT 'Stations', COUNT(*) FROM stations
UNION ALL
SELECT 'Routes', COUNT(*) FROM routes
UNION ALL
SELECT 'Route Stops', COUNT(*) FROM route_stops
UNION ALL
SELECT 'Trains', COUNT(*) FROM trains
UNION ALL
SELECT 'Tickets', COUNT(*) FROM tickets
UNION ALL
SELECT 'Subscriptions', COUNT(*) FROM subscriptions
UNION ALL
SELECT 'User Benefits', COUNT(*) FROM user_benefits
UNION ALL
SELECT 'Travel Entitlements', COUNT(*) FROM travel_entitlements
UNION ALL
SELECT 'QR Tokens', COUNT(*) FROM qr_tokens
UNION ALL
SELECT 'Validations', COUNT(*) FROM validations
UNION ALL
SELECT 'Audit Logs', COUNT(*) FROM audit_logs;

-- Verificare agenți universitari și universitate asociată
SELECT u.first_name || ' ' || u.last_name AS agent_name,
       u.email,
       univ.short_name AS universitate
FROM users u
JOIN universities univ ON u.university_id = univ.university_id
WHERE u.role = 'university_agent';

-- Verificare cereri pendente per universitate
SELECT * FROM pending_student_benefits;

-- Test funcție statistici agent UPB (university_id=1)
SELECT * FROM university_agent_stats(1);

