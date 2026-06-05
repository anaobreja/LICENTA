-- SEED DEMO DATA — Railway Digital Identity Platform
--
-- Acest fisier este executat de PostgreSQL la prima pornire dupa schema.sql.
-- Toate parolele demo sunt hash-uri bcrypt reale pentru parola "demo2026".
--
-- Conturi demo:
--   alexandra.popescu@email.com       / demo2026  (passenger)
--   andrei.ionescu@email.com          / demo2026  (passenger)
--   ioan.vasile@email.com             / demo2026  (passenger)
--   maria.dumitru@email.com           / demo2026  (passenger)
--   george.constantinescu@email.com   / demo2026  (conductor)
--   admin@railway.gov.ro              / demo2026  (admin)
--   user.demo@railwaydemo.com         / demo2026  (passenger demo principal)
--   agent.train@railwaydemo.com       / demo2026  (conductor demo)
--   agent.upb@railwaydemo.com         / demo2026  (university_agent UPB)
--   agent.ase@railwaydemo.com         / demo2026  (university_agent ASE)
--   agent.unibuc@railwaydemo.com      / demo2026  (university_agent UB)
-- 1. UNIVERSITATI PARTENERE
INSERT INTO universities (name, short_name, city, email_domain, contact_email) VALUES
('Universitatea Politehnica Bucuresti (UPB)',          'UPB',    'Bucuresti', 'upb.ro',    'contact@upb.ro'),
('Academia de Studii Economice (ASE)',                 'ASE',    'Bucuresti', 'ase.ro',    'contact@ase.ro'),
('Universitatea din Bucuresti (UB)',                   'UNIBUC', 'Bucuresti', 'unibuc.ro', 'contact@unibuc.ro');
-- 2. EMITENTI (issuers)
INSERT INTO issuers (name, issuer_type) VALUES
('Railway Digital Identity Authority',                 'transport'),
('Universitatea Politehnica Bucuresti (UPB)',          'university'),
('Academia de Studii Economice (ASE)',                 'university'),
('Universitatea din Bucuresti (UB)',                   'university');
-- 3. UTILIZATORI DEMO
--    Hash bcrypt pentru parola "demo2026":
--    $2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO
-- Passengers
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role, university_id) VALUES
('Alexandra',    'Popescu',         'alexandra.popescu@email.com',     '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40721234567', '1995-03-15', 'passenger', NULL),
('Andrei',       'Ionescu',         'andrei.ionescu@email.com',        '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40722334455', '2002-07-22', 'passenger', (SELECT university_id FROM universities WHERE short_name = 'UPB')),
('Ioan',         'Vasile',          'ioan.vasile@email.com',           '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40723445566', '1955-12-10', 'passenger', NULL),
('Maria',        'Dumitru',         'maria.dumitru@email.com',         '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40724556677', '1988-05-18', 'passenger', NULL),
('Demo',         'User',            'user.demo@railwaydemo.com',       '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40720000001', '1999-01-01', 'passenger', (SELECT university_id FROM universities WHERE short_name = 'UPB'));

-- Conductors (validators)
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role, university_id) VALUES
('George',       'Constantinescu',  'george.constantinescu@email.com', '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40725667788', '1978-01-09', 'conductor', NULL),
('Demo',         'Train',           'agent.train@railwaydemo.com',     '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40720000003', '1985-01-01', 'conductor', NULL);

-- Admin
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role) VALUES
('Administrator', 'System',         'admin@railway.gov.ro',            '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40726778899', '1980-06-20', 'admin');

-- University agents (legati de universitate + issuer corespunzator)
INSERT INTO users (first_name, last_name, email, password_hash, phone, date_of_birth, role, university_id, issuer_id) VALUES
('Agent', 'UPB',     'agent.upb@railwaydemo.com',    '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40720000004', '1985-01-01', 'university_agent',
    (SELECT university_id FROM universities WHERE short_name = 'UPB'),
    (SELECT id FROM issuers WHERE name = 'Universitatea Politehnica Bucuresti (UPB)')),
('Agent', 'ASE',     'agent.ase@railwaydemo.com',    '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40720000005', '1986-01-01', 'university_agent',
    (SELECT university_id FROM universities WHERE short_name = 'ASE'),
    (SELECT id FROM issuers WHERE name = 'Academia de Studii Economice (ASE)')),
('Agent', 'UNIBUC',  'agent.unibuc@railwaydemo.com', '$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO', '+40720000006', '1987-01-01', 'university_agent',
    (SELECT university_id FROM universities WHERE short_name = 'UNIBUC'),
    (SELECT id FROM issuers WHERE name = 'Universitatea din Bucuresti (UB)'));
-- 4. STUDENTI INSCRISI (demo per universitate)
INSERT INTO university_students (university_id, student_number, first_name, last_name, faculty, study_program, year_of_study, enrollment_date) VALUES
((SELECT university_id FROM universities WHERE short_name = 'UPB'),    'UPB-2024-001', 'Andrei', 'Ionescu', 'Automatica si Calculatoare', 'Calculatoare',         2, '2023-10-01'),
((SELECT university_id FROM universities WHERE short_name = 'UPB'),    'UPB-2024-002', 'Demo',   'User',    'Automatica si Calculatoare', 'Calculatoare',         3, '2022-10-01'),
((SELECT university_id FROM universities WHERE short_name = 'ASE'),    'ASE-2024-001', 'Maria',  'Popa',    'Cibernetica',               'Informatica Economica', 1, '2024-10-01'),
((SELECT university_id FROM universities WHERE short_name = 'UNIBUC'), 'UB-2024-001',  'Vlad',   'Mihai',   'Matematica si Informatica', 'Informatica',          2, '2023-10-01');
-- 5. OPERATORI FEROVIARI
INSERT INTO railway_operators (name, code, country, contact_email) VALUES
('CFR Calatori',     'CFR',  'Romania', 'contact@cfrcalatori.ro'),
('Softrans',         'STR',  'Romania', 'contact@softrans.ro'),
('Astra Trans Carpatic', 'ATC', 'Romania', 'contact@astratranscarpatic.ro');
-- 6. STATII
INSERT INTO stations (name, code, city) VALUES
('Bucuresti Nord',  'BUH', 'Bucuresti'),
('Brasov',          'BRV', 'Brasov'),
('Cluj-Napoca',     'CJN', 'Cluj-Napoca'),
('Timisoara Nord',  'TMN', 'Timisoara'),
('Iasi',            'IAS', 'Iasi'),
('Constanta',       'CTA', 'Constanta'),
('Sibiu',           'SBU', 'Sibiu'),
('Ploiesti Sud',    'PLO', 'Ploiesti');
-- 7. RUTE (cateva exemple)
INSERT INTO routes (operator_id, route_name, route_code, origin_station_id, destination_station_id, total_distance_km) VALUES
((SELECT operator_id FROM railway_operators WHERE code = 'CFR'), 'Bucuresti - Brasov',     'CFR-BUH-BRV', (SELECT station_id FROM stations WHERE code = 'BUH'), (SELECT station_id FROM stations WHERE code = 'BRV'), 166.0),
((SELECT operator_id FROM railway_operators WHERE code = 'CFR'), 'Bucuresti - Cluj-Napoca','CFR-BUH-CJN', (SELECT station_id FROM stations WHERE code = 'BUH'), (SELECT station_id FROM stations WHERE code = 'CJN'), 497.0),
((SELECT operator_id FROM railway_operators WHERE code = 'CFR'), 'Bucuresti - Constanta',  'CFR-BUH-CTA', (SELECT station_id FROM stations WHERE code = 'BUH'), (SELECT station_id FROM stations WHERE code = 'CTA'), 225.0),
((SELECT operator_id FROM railway_operators WHERE code = 'STR'), 'Bucuresti - Timisoara',  'STR-BUH-TMN', (SELECT station_id FROM stations WHERE code = 'BUH'), (SELECT station_id FROM stations WHERE code = 'TMN'), 533.0),
((SELECT operator_id FROM railway_operators WHERE code = 'ATC'), 'Bucuresti - Iasi',       'ATC-BUH-IAS', (SELECT station_id FROM stations WHERE code = 'BUH'), (SELECT station_id FROM stations WHERE code = 'IAS'), 405.0);
-- 8. TRENURI
INSERT INTO trains (operator_id, route_id, train_number, train_type, capacity_seats) VALUES
((SELECT operator_id FROM railway_operators WHERE code = 'CFR'), (SELECT route_id FROM routes WHERE route_code = 'CFR-BUH-BRV'), 'IR-1621', 'interregio', 300),
((SELECT operator_id FROM railway_operators WHERE code = 'CFR'), (SELECT route_id FROM routes WHERE route_code = 'CFR-BUH-CJN'), 'IR-1841', 'interregio', 350),
((SELECT operator_id FROM railway_operators WHERE code = 'CFR'), (SELECT route_id FROM routes WHERE route_code = 'CFR-BUH-CTA'), 'IC-672',  'intercity',  280),
((SELECT operator_id FROM railway_operators WHERE code = 'STR'), (SELECT route_id FROM routes WHERE route_code = 'STR-BUH-TMN'), 'S-100',   'interregio', 250),
((SELECT operator_id FROM railway_operators WHERE code = 'ATC'), (SELECT route_id FROM routes WHERE route_code = 'ATC-BUH-IAS'), 'ATC-201', 'intercity',  220);
-- 9. CARD DIGITAL pentru user.demo (ca sa mearga "Card Digital" out-of-the-box)
INSERT INTO digital_cards (user_id, issuer_id, card_identifier, status, valid_until) VALUES
(
    (SELECT user_id FROM users WHERE email = 'user.demo@railwaydemo.com'),
    (SELECT id FROM issuers WHERE name = 'Railway Digital Identity Authority'),
    'RDC-DEMO-USER',
    'active',
    CURRENT_TIMESTAMP + INTERVAL '365 days'
);
-- 10. CREDENTIAL "student" activ pentru user.demo (UPB, anul 3)
INSERT INTO user_credentials (user_id, credential_type, claim_value, issuer_id, status, valid_until) VALUES
(
    (SELECT user_id FROM users WHERE email = 'user.demo@railwaydemo.com'),
    'student_verified',
    'UPB-2024-002:Calculatoare:An 3',
    (SELECT id FROM issuers WHERE name = 'Universitatea Politehnica Bucuresti (UPB)'),
    'active',
    CURRENT_TIMESTAMP + INTERVAL '300 days'
);

-- ==============================================================================
-- 11. TARIFE PE TREPTE (Tariful 100 CFR — aproximare clasa II 2025)
-- ==============================================================================
-- Regio (R), clasa II — preturile de baza
INSERT INTO tariff_brackets (train_category, train_class, km_from, km_to, price_ron) VALUES
('R',  2,   0,   10,  5.00),
('R',  2,  11,   25,  9.00),
('R',  2,  26,   50, 15.00),
('R',  2,  51,   75, 22.00),
('R',  2,  76,  100, 30.00),
('R',  2, 101,  150, 38.00),
('R',  2, 151,  200, 48.00),
('R',  2, 201,  300, 60.00),
('R',  2, 301,  400, 75.00),
('R',  2, 401,  500, 90.00),
('R',  2, 501,  700,108.00),
('R',  2, 701, 9999,128.00);

-- InterRegio (IR), clasa II — base + supliment IR + rezervare
INSERT INTO tariff_brackets (train_category, train_class, km_from, km_to, price_ron) VALUES
('IR', 2,   0,   10, 12.00),
('IR', 2,  11,   25, 18.00),
('IR', 2,  26,   50, 27.00),
('IR', 2,  51,   75, 38.00),
('IR', 2,  76,  100, 48.00),
('IR', 2, 101,  150, 56.00),
('IR', 2, 151,  200, 67.00),
('IR', 2, 201,  300, 82.00),
('IR', 2, 301,  400,103.00),
('IR', 2, 401,  500,127.00),
('IR', 2, 501,  700,156.00),
('IR', 2, 701, 9999,180.00);

-- InterCity (IC), clasa II — base + supliment IC + rezervare obligatorie
INSERT INTO tariff_brackets (train_category, train_class, km_from, km_to, price_ron) VALUES
('IC', 2,   0,   50, 35.00),
('IC', 2,  51,  100, 55.00),
('IC', 2, 101,  150, 68.00),
('IC', 2, 151,  200, 75.00),
('IC', 2, 201,  300, 95.00),
('IC', 2, 301,  500,135.00),
('IC', 2, 501, 9999,180.00);

-- Clasa I — supliment ~35% peste clasa II
INSERT INTO tariff_brackets (train_category, train_class, km_from, km_to, price_ron) VALUES
('R',  1,   0,  100, 42.00),
('R',  1, 101,  300, 81.00),
('R',  1, 301, 9999,140.00),
('IR', 1,   0,  100, 65.00),
('IR', 1, 101,  300,111.00),
('IR', 1, 301,  500,170.00),
('IR', 1, 501, 9999,235.00),
('IC', 1,   0,  200,101.00),
('IC', 1, 201,  500,180.00),
('IC', 1, 501, 9999,240.00);
