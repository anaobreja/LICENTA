# Test Matrix — Acoperire teste pe funcționalități

Statisticele rulate la sfârșitul auditului (2026-06-09 04:00).

---

## Sumar global

| Suite | Teste | Trec | Skip | Coverage |
|---|---|---|---|---|
| Backend integration | ~340 | 100% | 0% | 76% |
| Backend unit | ~40 | 100% | 0% | acoperit prin integration |
| Frontend smoke | 14 | 100% | 0% | n/a (smoke) |
| **TOTAL** | **~395** | **~99%** | **~0%** | **76%** |

---

## Acoperire pe modul / feature

### Auth & users

| Feature | Test file | Test count | Status |
|---|---|---|---|
| Register passenger | `test_auth.py` | ~8 | ✅ |
| Login bcrypt + JWT | `test_auth.py` | ~6 | ✅ |
| MFA TOTP setup/disable | `test_auth_mfa.py` | ~15 | ✅ |
| Profile update (frozen fields) | `test_profile_freeze.py` | ~12 | ✅ |
| Change password | `test_users_endpoints.py` | ~5 | ✅ |
| Delete account / GDPR export | `test_users_endpoints.py` | ~8 | ✅ |
| **JWT tampering** | `test_security_inputs.py` | 5 | ✅ NOU |
| **Role enforcement** | `test_security_inputs.py` | 2 | ✅ NOU |

### Identity / documents

| Feature | Test file | Test count | Status |
|---|---|---|---|
| Submit validation request | `test_identity.py` | ~10 | ✅ |
| Photo upload + OCR mock | `test_identity.py` | ~6 | ✅ |
| Issuer approve / reject | `test_identity.py` | ~12 | ✅ |
| Document expiry / renewal | `test_identity.py` | ~5 | ✅ |
| Card presentation flow | `test_offline_presentation.py` | ~8 | ✅ |
| **Cross-university security** | `test_cross_university_security.py` | 5 | ✅ NOU |
| **Home station sync** | `test_home_station_contract.py` | 3 | ✅ |
| **DOB format sync (5 formate)** | `test_dob_sync.py` | 6 | ✅ NOU |

### Tickets

| Feature | Test file | Test count | Status |
|---|---|---|---|
| Buy ticket simple | `test_tickets.py` | ~8 | ✅ |
| Buy with seat | `test_tickets.py` | ~5 | ✅ |
| Quote / pricing | `test_tickets_contract.py` | ~12 | ✅ |
| Personal route discount | `test_personal_route.py` | ~10 | ✅ |
| Cancel + refund tiers | `test_ticket_lifecycle_edges.py` | ~8 | ✅ |
| **Refund matrix** | `test_refund_matrix.py` | 11 | ✅ NOU |
| Reschedule same route | `test_ticket_lifecycle_edges.py` | ~6 | ✅ |
| Validate QR (single-use) | `test_ticket_validation.py` | ~8 | ✅ |
| **QR lifecycle complet** | `test_qr_lifecycle.py` | 9 | ✅ NOU |
| **Multi-pasager E2E** | `test_multi_passenger_e2e.py` | 7 | ✅ NOU |
| Anti-overlap | `test_tickets.py` | ~4 | ✅ |

### Seats

| Feature | Test file | Test count | Status |
|---|---|---|---|
| Layout endpoint | `test_seats.py` | ~6 | ✅ |
| Hold seat | `test_seats.py` | ~5 | ✅ |
| Release seat | `test_seats.py` | ~3 | ✅ |
| **Concurrency / race** | `test_seat_concurrency.py` | 6 | ✅ NOU |
| Expired hold cleanup | `test_seats.py` | ~3 | ✅ |
| Confirm seats for ticket | `test_seats.py` | ~4 | ✅ |

### Subscriptions

| Feature | Test file | Test count | Status |
|---|---|---|---|
| Quote + buy | `test_subscriptions.py` | ~8 | ✅ |
| Anti-overlap | `test_subscription_edge_cases.py` | 1 | ✅ NOU |
| Cancel + refund pro-rata | `test_subscription_edge_cases.py` | 2 | ✅ NOU |
| **Edge cases (9 scenarios)** | `test_subscription_edge_cases.py` | 9 | ✅ NOU |
| Auto-discount pe bilete | `test_subscriptions.py` | ~3 | ✅ |
| Lazy expire | `test_subscriptions.py` | ~2 | ✅ |

### Map

| Feature | Test file | Test count | Status |
|---|---|---|---|
| Stations + GPS | `test_map.py` | ~5 | ✅ |
| Connections + filtere | `test_map.py` | ~3 | ✅ |
| Operators | `test_map_endpoints.py` | ~2 | ✅ |
| Train simulate position | `test_map_endpoints.py` | ~3 | ✅ |

### Performance

| Feature | Test file | Status |
|---|---|---|
| **N+1 detection** | `test_performance_smoke.py` | ✅ NOU |
| **Response time** | `test_performance_smoke.py` | ✅ NOU |

### Security

| Feature | Test file | Status |
|---|---|---|
| **SQL injection prevention** | `test_security_inputs.py` | ✅ NOU |
| **XSS stored as text** | `test_security_inputs.py` | ✅ NOU |
| **Input length limits** | `test_security_inputs.py` | ✅ NOU |
| **Auth header validation** | `test_security_inputs.py` | ✅ NOU |

---

## Frontend

| Page | Test file | Tests | Status |
|---|---|---|---|
| MyTickets | `MyTickets.test.jsx` | 7 (cu QR) | ✅ |
| BuyTicket | `BuyTicket.test.jsx` | 4 | ✅ |
| Documents | `Documents.test.jsx` | 3 | ✅ |

---

## Coverage details per fișier

| Fișier | Coverage | Lipsuri |
|---|---|---|
| `core/config.py` | 100% | — |
| `core/security.py` | 100% | — |
| `core/roles.py` | 100% | — |
| `core/identity_status.py` | 93% | 3 error paths |
| `core/signing.py` | 84% | edge cases verify |
| `core/uploads.py` | 90% | error paths |
| `core/database.py` | 59% | startup/shutdown |
| `routers/auth.py` | 87% | MFA edge cases |
| `routers/crypto_keys.py` | 100% | — |
| `routers/identity.py` | ~60% | renewal, exotic flows |
| `routers/map.py` | 80% | error paths |
| `routers/seats.py` | 90% | — |
| `routers/subscriptions.py` | ~80% | renewal flow |
| `routers/tickets.py` | ~80% | reschedule edge cases |
| `routers/users.py` | 83% | GDPR delete flow |
| `services/subscription_business.py` | 82% | — |
| `services/ticket_business.py` | 87% | — |

**TOTAL**: 76% pe tot codul de business.

---

## Ce NU e acoperit (decizii deliberate)

1. **`run.py`** — entry point, no tests
2. **`proxy_server.py`** — proxy DEV, no tests
3. **`database/import_cfr.py`** — import script, manual
4. **`main.py` startup** — testat indirect prin client fixture
5. **Frontend `App.jsx` / `Router`** — testat indirect prin smoke tests
6. **`signing.py` key rotation** — manual

---

## Recapitulare

✅ **Toate fluxurile critice de business sunt testate**
✅ **Toate bug-urile cunoscute fixate au teste anti-regresie**
✅ **Coverage > 75% pe codul de business**

Aplicația e gata pentru demo licență.
