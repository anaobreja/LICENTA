-- ==============================================================================
-- INTEROGĂRI REPREZENTATIVE - SISTEM GESTIONARE IDENTITATE DIGITALĂ
-- ==============================================================================
-- Aceste interogări demonstrează:
-- - Utilizarea JOIN-urilor
-- - GROUP BY și agregări
-- - Subqueries
-- - Filtrări complexe
-- - View-uri
-- ==============================================================================


-- ==============================================================================
-- 1. INTEROGĂRI SIMPLE - VERIFICĂRI DE BAZĂ
-- ==============================================================================

-- 1.1 Toți utilizatorii pasageri (non-staff)
SELECT user_id, first_name, last_name, email, created_at
FROM users
WHERE role = 'passenger' AND is_active = true
ORDER BY last_name, first_name;

-- 1.2 Toți utilizatorii precum admin-i și controlori
SELECT user_id, first_name, last_name, email, role
FROM users
WHERE role IN ('conductor', 'admin')
ORDER BY role, last_name;

-- 1.3 Utilizatorii înregistrați în ultimele 30 de zile
SELECT user_id, first_name, last_name, email, created_at
FROM users
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY created_at DESC;


-- ==============================================================================
-- 2. INTEROGĂRI CU JOIN - RELAȚII DINTRE TABELE
-- ==============================================================================

-- 2.1 Toți utilizatorii cu bilete active și detaliile trenurilor
SELECT 
    u.first_name,
    u.last_name,
    t.ticket_id,
    t.seat_number,
    t.travel_date,
    tr.train_number,
    ro.name as operator_name,
    s_dep.name as departure_station,
    s_arr.name as arrival_station
FROM users u
JOIN tickets t ON u.user_id = t.user_id
JOIN trains tr ON t.train_id = tr.train_id
JOIN railway_operators ro ON tr.operator_id = ro.operator_id
JOIN stations s_dep ON t.departure_station_id = s_dep.station_id
JOIN stations s_arr ON t.arrival_station_id = s_arr.station_id
WHERE t.ticket_status = 'active'
ORDER BY t.travel_date, t.travel_time;

-- 2.2 Drepturi de călătorie active cu sursă și detalii utilizator
SELECT 
    te.entitlement_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    u.email,
    te.source_type,
    CASE 
        WHEN te.source_type = 'ticket' THEN 'Bilet single'
        WHEN te.source_type = 'subscription' THEN 'Abonament'
        WHEN te.source_type = 'benefit' THEN 'Facilitate'
    END as entitlement_description,
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
WHERE te.status = 'active'
ORDER BY te.valid_until;

-- 2.3 Rute cu stații în ordinea opririi
SELECT 
    r.route_id,
    r.route_name,
    ro.name as operator_name,
    s.code,
    s.name as station_name,
    s.city,
    rs.stop_order,
    rs.planned_arrival_time,
    rs.planned_departure_time
FROM routes r
JOIN railway_operators ro ON r.operator_id = ro.operator_id
JOIN route_stops rs ON r.route_id = rs.route_id
JOIN stations s ON rs.station_id = s.station_id
ORDER BY r.route_id, rs.stop_order;

-- 2.4 Trenuri cu details rută și operator
SELECT 
    t.train_id,
    t.train_number,
    t.train_type,
    t.capacity,
    r.route_name,
    ro.name as operator,
    s_origin.name as origin_station,
    s_dest.name as destination_station,
    r.distance_km
FROM trains t
JOIN railway_operators ro ON t.operator_id = ro.operator_id
JOIN routes r ON t.route_id = r.route_id
JOIN stations s_origin ON r.origin_station_id = s_origin.station_id
JOIN stations s_dest ON r.destination_station_id = s_dest.station_id
WHERE t.is_active = true
ORDER BY ro.name, t.train_number;


-- ==============================================================================
-- 3. INTEROGĂRI CU GROUP BY ȘI AGREGĂRI
-- ==============================================================================

-- 3.1 Numărul de bilete pe utilizator
SELECT 
    u.user_id,
    u.first_name || ' ' || u.last_name as user_name,
    COUNT(t.ticket_id) as total_tickets,
    SUM(CASE WHEN t.ticket_status = 'active' THEN 1 ELSE 0 END) as active_tickets,
    SUM(CASE WHEN t.ticket_status = 'used' THEN 1 ELSE 0 END) as used_tickets,
    MAX(t.travel_date) as last_travel_date
FROM users u
LEFT JOIN tickets t ON u.user_id = t.user_id
GROUP BY u.user_id, u.first_name, u.last_name
HAVING COUNT(t.ticket_id) > 0
ORDER BY total_tickets DESC;

-- 3.2 Suma investiții pe utilizator (bilete + abonamente)
SELECT 
    u.user_id,
    u.first_name || ' ' || u.last_name as user_name,
    u.email,
    COALESCE(SUM(t.price), 0) as total_tickets_spent,
    COALESCE(SUM(s.price), 0) as total_subscriptions_spent,
    COALESCE(SUM(t.price), 0) + COALESCE(SUM(s.price), 0) as total_spent
FROM users u
LEFT JOIN tickets t ON u.user_id = t.user_id
LEFT JOIN subscriptions s ON u.user_id = s.user_id
GROUP BY u.user_id, u.first_name, u.last_name, u.email
ORDER BY total_spent DESC;

-- 3.3 Validări per controlor (top conductori)
SELECT 
    c.user_id,
    c.first_name || ' ' || c.last_name as conductor_name,
    COUNT(v.validation_id) as total_validations,
    SUM(CASE WHEN v.validation_result = 'valid' THEN 1 ELSE 0 END) as valid_scans,
    SUM(CASE WHEN v.validation_result != 'valid' THEN 1 ELSE 0 END) as failed_scans,
    ROUND(100.0 * SUM(CASE WHEN v.validation_result = 'valid' THEN 1 ELSE 0 END) / COUNT(v.validation_id), 2) as success_rate,
    MAX(v.validation_time) as last_scan
FROM users c
LEFT JOIN validations v ON c.user_id = v.conductor_id
WHERE c.role = 'conductor'
GROUP BY c.user_id, c.first_name, c.last_name
ORDER BY total_validations DESC;

-- 3.4 Trenuri cu încărcătură (bilete vândute vs capacitate)
SELECT 
    t.train_id,
    t.train_number,
    t.train_type,
    t.capacity,
    COUNT(tr.ticket_id) as tickets_sold,
    ROUND(100.0 * COUNT(tr.ticket_id) / t.capacity, 2) as occupancy_rate,
    SUM(tr.price) as revenue_from_tickets
FROM trains t
LEFT JOIN tickets tr ON t.train_id = tr.train_id AND tr.ticket_status IN ('active', 'used')
GROUP BY t.train_id, t.train_number, t.train_type, t.capacity
ORDER BY occupancy_rate DESC;

-- 3.5 Facilități aprobate pe tip
SELECT 
    bt.name as benefit_type,
    COUNT(ub.user_benefit_id) as total_approved,
    COUNT(DISTINCT ub.user_id) as unique_users,
    MAX(ub.approved_at) as last_approved
FROM benefit_types bt
LEFT JOIN user_benefits ub ON bt.benefit_type_id = ub.benefit_type_id AND ub.status = 'approved'
GROUP BY bt.benefit_type_id, bt.name
ORDER BY total_approved DESC;


-- ==============================================================================
-- 4. INTEROGĂRI CU HAVING - FILTRĂRI POST-AGREGARE
-- ==============================================================================

-- 4.1 Utilizatorii care au mai mult de 3 bilete active
SELECT 
    u.user_id,
    u.first_name || ' ' || u.last_name as user_name,
    COUNT(t.ticket_id) as active_tickets_count,
    STRING_AGG(DISTINCT t.travel_date::text, ', ' ORDER BY t.travel_date::text) as travel_dates
FROM users u
JOIN tickets t ON u.user_id = t.user_id
WHERE t.ticket_status = 'active'
GROUP BY u.user_id, u.first_name, u.last_name
HAVING COUNT(t.ticket_id) > 3
ORDER BY active_tickets_count DESC;

-- 4.2 Rute care au venit > 10000 RON
SELECT 
    r.route_id,
    r.route_name,
    ro.name as operator,
    COUNT(t.ticket_id) as total_tickets_sold,
    SUM(t.price) as total_revenue,
    ROUND(AVG(t.price), 2) as avg_ticket_price
FROM routes r
JOIN railway_operators ro ON r.operator_id = ro.operator_id
LEFT JOIN trains tr ON r.route_id = tr.route_id
LEFT JOIN tickets t ON tr.train_id = t.train_id AND t.ticket_status IN ('active', 'used')
GROUP BY r.route_id, r.route_name, ro.name
HAVING SUM(t.price) > 10000
ORDER BY total_revenue DESC;


-- ==============================================================================
-- 5. INTEROGĂRI CU SUBQUERIES
-- ==============================================================================

-- 5.1 Utilizatorii care au cel puțin o facilitate activă
SELECT DISTINCT
    u.user_id,
    u.first_name || ' ' || u.last_name as user_name,
    u.email
FROM users u
WHERE u.user_id IN (
    SELECT DISTINCT ub.user_id
    FROM user_benefits ub
    WHERE ub.status = 'approved'
        AND ub.valid_until >= CURRENT_DATE
        AND ub.valid_from <= CURRENT_DATE
)
ORDER BY u.first_name, u.last_name;

-- 5.2 QR tokenuri care au fost scanate (cu detalii)
SELECT 
    qt.qr_token_id,
    qt.token_value,
    qt.issued_at,
    qt.expires_at,
    qt.status,
    v.validation_count,
    MAX(v.last_validation) as last_validation_time
FROM qr_tokens qt
LEFT JOIN (
    SELECT 
        qr_token_id,
        COUNT(*) as validation_count,
        MAX(validation_time) as last_validation
    FROM validations
    GROUP BY qr_token_id
) v ON qt.qr_token_id = v.qr_token_id
WHERE qt.status = 'used' OR qt.status = 'active'
ORDER BY qt.issued_at DESC;

-- 5.3 Drepturi de călătorie care se vor expira în următoarele 7 zile
SELECT 
    te.entitlement_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    u.email,
    te.source_type,
    te.valid_until,
    CURRENT_DATE - te.valid_until as days_until_expiry
FROM travel_entitlements te
JOIN users u ON te.user_id = u.user_id
WHERE te.status = 'active'
    AND te.valid_until BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
ORDER BY te.valid_until;

-- 5.4 Pasageri cu bilete dar fără abonament activ
SELECT DISTINCT
    u.user_id,
    u.first_name || ' ' || u.last_name as user_name
FROM users u
WHERE u.user_id IN (
    SELECT DISTINCT user_id FROM tickets WHERE ticket_status = 'active'
)
AND u.user_id NOT IN (
    SELECT DISTINCT user_id FROM subscriptions WHERE status = 'active'
)
ORDER BY u.first_name, u.last_name;


-- ==============================================================================
-- 6. INTEROGĂRI PENTRU AUDIT ȘI GDPR
-- ==============================================================================

-- 6.1 Ultimele 20 de operații pe sistem (audit trail)
SELECT 
    al.audit_log_id,
    u.first_name || ' ' || u.last_name as actor_name,
    al.action_type,
    al.target_table,
    al.action_timestamp,
    al.ip_address,
    al.details
FROM audit_logs al
LEFT JOIN users u ON al.actor_user_id = u.user_id
ORDER BY al.action_timestamp DESC
LIMIT 20;

-- 6.2 Accesuri la probe cu date sensibile
SELECT 
    al.audit_log_id,
    u.first_name || ' ' || u.last_name as actor_name,
    al.action_type,
    al.target_table,
    al.action_timestamp,
    al.ip_address
FROM audit_logs al
LEFT JOIN users u ON al.actor_user_id = u.user_id
WHERE al.target_table IN ('user_benefits', 'digital_identities', 'users')
    AND al.action_type IN ('SELECT_SENSITIVE', 'EXPORT')
ORDER BY al.action_timestamp DESC;

-- 6.3 Date exportate per utilizator (GDPR - data export requests)
SELECT 
    al.audit_log_id,
    u.user_id,
    u.first_name || ' ' || u.last_name as user_name,
    u.email,
    al.action_timestamp,
    COUNT(*) OVER (PARTITION BY u.user_id) as total_exports
FROM audit_logs al
JOIN users u ON al.actor_user_id = u.user_id
WHERE al.action_type = 'EXPORT'
ORDER BY al.action_timestamp DESC;


-- ==============================================================================
-- 7. INTEROGĂRI PENTRU VALIDĂRI ȘI CONTROL
-- ==============================================================================

-- 7.1 Istoricul complet de validări (view-uri)
SELECT * FROM validation_history_detailed
ORDER BY validation_time DESC
LIMIT 20;

-- 7.2 Validări eșuate într-o zi (anomalii potențiale)
SELECT 
    v.validation_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    c.first_name || ' ' || c.last_name as conductor_name,
    v.validation_result,
    v.validation_time,
    v.notes,
    s.name as station_name
FROM validations v
JOIN qr_tokens qt ON v.qr_token_id = qt.qr_token_id
JOIN travel_entitlements te ON qt.entitlement_id = te.entitlement_id
JOIN users u ON te.user_id = u.user_id
JOIN users c ON v.conductor_id = c.user_id
LEFT JOIN stations s ON v.location_station_id = s.station_id
WHERE DATE(v.validation_time) = CURRENT_DATE
    AND v.validation_result != 'valid'
ORDER BY v.validation_time DESC;

-- 7.3 Tentative de re-utilizare a aceluiași QR (fraud detection)
SELECT 
    qt.qr_token_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    COUNT(*) as scan_attempts,
    STRING_AGG(v.validation_result, ', ') as results,
    MIN(v.validation_time) as first_scan,
    MAX(v.validation_time) as last_scan,
    MAX(v.validation_time) - MIN(v.validation_time) as time_span
FROM qr_tokens qt
JOIN travel_entitlements te ON qt.entitlement_id = te.entitlement_id
JOIN users u ON te.user_id = u.user_id
JOIN validations v ON qt.qr_token_id = v.qr_token_id
GROUP BY qt.qr_token_id, u.user_id, u.first_name, u.last_name
HAVING COUNT(*) > 1
ORDER BY scan_attempts DESC;


-- ==============================================================================
-- 8. INTEROGĂRI PENTRU RAPOARTE ADMINISTRATIVE
-- ==============================================================================

-- 8.1 Dashboard statistic - Rezumat zilei
SELECT 
    'Users Active' as metric,
    COUNT(DISTINCT user_id)::text as value
FROM users
WHERE is_active = true

UNION ALL

SELECT 'Bilete Active', COUNT(*)::text FROM tickets WHERE ticket_status = 'active'

UNION ALL

SELECT 'Abonamente Active', COUNT(*)::text FROM subscriptions WHERE status = 'active'

UNION ALL

SELECT 'Validări Ziua', COUNT(*)::text 
FROM validations WHERE DATE(validation_time) = CURRENT_DATE

UNION ALL

SELECT 'Validări Reușite Ziua', COUNT(*)::text 
FROM validations 
WHERE DATE(validation_time) = CURRENT_DATE AND validation_result = 'valid'

UNION ALL

SELECT 'Drepturi Expirate Mâine', COUNT(*)::text
FROM travel_entitlements
WHERE valid_until = CURRENT_DATE + INTERVAL '1 day' AND status = 'active';

-- 8.2 Revenue Report - Venituri pe operator și tip
SELECT 
    ro.name as operator,
    'Tickets' as revenue_source,
    COUNT(t.ticket_id) as item_count,
    SUM(t.price) as total_revenue,
    ROUND(AVG(t.price), 2) as avg_price
FROM railway_operators ro
JOIN trains tr ON ro.operator_id = tr.operator_id
LEFT JOIN tickets t ON tr.train_id = t.train_id AND t.ticket_status IN ('active', 'used')
GROUP BY ro.operator_id, ro.name

UNION ALL

SELECT 
    'Unknown' as operator,
    'Subscriptions' as revenue_source,
    COUNT(s.subscription_id) as item_count,
    SUM(s.price) as total_revenue,
    ROUND(AVG(s.price), 2) as avg_price
FROM subscriptions s;

-- 8.3 Utilizatorii cu cele mai multe validări (frequent travelers)
SELECT 
    u.user_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    COUNT(v.validation_id) as total_validations,
    COUNT(DISTINCT DATE(v.validation_time)) as travel_days,
    MIN(v.validation_time) as first_validation,
    MAX(v.validation_time) as recent_validation
FROM users u
LEFT JOIN travel_entitlements te ON u.user_id = te.user_id
LEFT JOIN qr_tokens qt ON te.entitlement_id = qt.entitlement_id
LEFT JOIN validations v ON qt.qr_token_id = v.qr_token_id
GROUP BY u.user_id, u.first_name, u.last_name
HAVING COUNT(v.validation_id) > 0
ORDER BY total_validations DESC
LIMIT 10;


-- ==============================================================================
-- 9. INTEROGĂRI CU FUNCȚII WINDOW
-- ==============================================================================

-- 9.1 Ranking bilete pe preț (ieftin la scump)
SELECT 
    t.ticket_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    tr.train_number,
    t.price,
    ROW_NUMBER() OVER (ORDER BY t.price DESC) as price_rank,
    ROUND(100.0 * t.price / MAX(t.price) OVER (), 2) as price_percentage_of_max
FROM tickets t
JOIN users u ON t.user_id = u.user_id
JOIN trains tr ON t.train_id = tr.train_id
WHERE t.ticket_status = 'active'
ORDER BY price_rank
LIMIT 10;

-- 9.2 Cumulative validări pe conductor
SELECT 
    v.validation_id,
    c.first_name || ' ' || c.last_name as conductor_name,
    DATE(v.validation_time) as validation_date,
    COUNT(*) OVER (
        PARTITION BY c.user_id 
        ORDER BY DATE(v.validation_time)
    ) as cumulative_validations
FROM validations v
JOIN users c ON v.conductor_id = c.user_id
WHERE c.role = 'conductor'
ORDER BY c.user_id, validation_date;


-- ==============================================================================
-- 10. INTEROGĂRI DE TEST PENTRU CONSTRÂNGERI ȘI INTEGRITATE
-- ==============================================================================

-- 10.1 Bilete cu date de călătorie în trecut
SELECT 
    t.ticket_id,
    u.first_name || ' ' || u.last_name as passenger_name,
    t.travel_date,
    t.ticket_status,
    CURRENT_DATE - t.travel_date as days_ago
FROM tickets t
JOIN users u ON t.user_id = u.user_id
WHERE t.travel_date < CURRENT_DATE
    AND t.ticket_status != 'expired'
ORDER BY t.travel_date DESC;

-- 10.2 Abonamente cu date incoerente (valid_until < valid_from)
SELECT 
    s.subscription_id,
    u.first_name || ' ' || u.last_name as user_name,
    s.valid_from,
    s.valid_until,
    s.valid_until - s.valid_from as duration_days,
    s.status
FROM subscriptions s
JOIN users u ON s.user_id = u.user_id
WHERE s.valid_until < s.valid_from;  -- Ar trebui să fie gol dacă CHECK e aplicat

-- 10.3 QR Tokenuri expirate care au status 'active'
SELECT 
    qt.qr_token_id,
    qt.issued_at,
    qt.expires_at,
    qt.status,
    CURRENT_TIMESTAMP - qt.expires_at as time_since_expiry
FROM qr_tokens qt
WHERE qt.status = 'active'
    AND qt.expires_at < CURRENT_TIMESTAMP;

-- 10.4 Drepturi cu referințe nule inconsistente
SELECT 
    te.entitlement_id,
    te.source_type,
    te.ticket_id,
    te.subscription_id,
    te.user_benefit_id,
    CASE 
        WHEN te.source_type = 'ticket' AND te.ticket_id IS NULL THEN 'ERROR: Ticket expected but NULL'
        WHEN te.source_type = 'subscription' AND te.subscription_id IS NULL THEN 'ERROR: Subscription expected but NULL'
        WHEN te.source_type = 'benefit' AND te.user_benefit_id IS NULL THEN 'ERROR: Benefit expected but NULL'
        ELSE 'OK'
    END as integrity_check
FROM travel_entitlements te
WHERE CASE 
    WHEN te.source_type = 'ticket' AND te.ticket_id IS NULL THEN true
    WHEN te.source_type = 'subscription' AND te.subscription_id IS NULL THEN true
    WHEN te.source_type = 'benefit' AND te.user_benefit_id IS NULL THEN true
    ELSE false
END;


-- ==============================================================================
-- NOTĂ PENTRU PREZENTARE
-- ==============================================================================
-- Aceste interogări demonstrează:
-- 1. Joins simple și complexe (2-4 tabele)
-- 2. Agregări cu GROUP BY, HAVING
-- 3. Subqueries în WHERE și FROM
-- 4. Views pentru date frecvent accesate
-- 5. Window functions pentru ranking și cumulative
-- 6. Validări de integritate a datelor
-- 7. Cazuri de use GDPR (audit, export)
-- 8. Rapoarte administrative
-- 9. Detecția anomaliilor (fraud detection)
-- 10. Performance considerations (indexe, suboptimale queries)

