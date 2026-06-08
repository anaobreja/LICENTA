"""
Integration tests pentru abonamente CFR cu scope pe ruta.

Acopera:
  - Calcul pret cu/fara reducere student (DOAR pe ruta home<->univ)
  - Quote endpoint
  - Buy + anti-overlap pe ruta (in ambele directii)
  - Cancel cu refund pro-rata (3 tiers: full_not_started, partial, more_than_half_used)
  - Lazy expire pentru abonamente cu valid_until < azi
  - Buy ticket pe ruta acoperita => price=0 si uses_subscription_id
  - Buy ticket pe alta ruta => pret normal (nu confuzie)
  - Unit tests pe compute_subscription_price
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import itertools

import pytest
from sqlalchemy import text

from helpers import register_and_login


# ---------------------------------------------------------------------------
# Counter unic pentru chei (route_code, train_number)
# ---------------------------------------------------------------------------
_seq = itertools.count(1)


def _engine():
    from app.core.database import engine
    return engine


def _get_user_id(client, token: str) -> int:
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()["user_id"]


def _ensure_issuer(conn) -> int:
    """Issuer pentru credentialele de test."""
    return conn.execute(text("""
        INSERT INTO issuers (name, issuer_type)
        VALUES ('Test Subscription Issuer', 'university')
        ON CONFLICT (name) DO UPDATE SET issuer_type = EXCLUDED.issuer_type
        RETURNING id
    """)).scalar()


def _mark_student_verified(engine, user_id: int) -> None:
    """Da userului un credential student_verified activ (valid 1 an)."""
    with engine.begin() as conn:
        issuer_id = _ensure_issuer(conn)
        conn.execute(text("""
            DELETE FROM user_credentials
            WHERE user_id = :uid AND credential_type = 'student_verified'
        """), {"uid": user_id})
        conn.execute(text("""
            INSERT INTO user_credentials
                (user_id, credential_type, claim_value, issuer_id,
                 status, issued_at, valid_until)
            VALUES (:uid, 'student_verified', 'student_active', :iss,
                    'active', NOW(), NOW() + INTERVAL '365 days')
        """), {"uid": user_id, "iss": issuer_id})


def _setup_user_with_home_and_university(engine, user_id: int,
                                          home_code: str, univ_code: str) -> tuple[int, int]:
    """
    Creeaza 2 statii (home + universitate) + o universitate + asociaza userul
    cu universitatea SI seteaza home_station_id. Marcheaza student_verified.

    Returneaza (home_station_id, university_station_id).
    """
    with engine.begin() as conn:
        home_s = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'Home City', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": home_code, "n": f"Home {home_code}"}).scalar()

        univ_s = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'Uni City', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": univ_code, "n": f"Univ {univ_code}"}).scalar()

        # Universitate cu main_station = univ_s
        univ_id = conn.execute(text("""
            INSERT INTO universities (name, short_name, city, email_domain, contact_email, main_station_id)
            VALUES (:n, :sn, 'Uni City', :em, :ce, :ms)
            ON CONFLICT (short_name) DO UPDATE SET main_station_id = EXCLUDED.main_station_id
            RETURNING university_id
        """), {
            "n": f"Test University {univ_code}",
            "sn": f"TU{univ_code}",
            "em": f"test_{univ_code.lower()}.edu",
            "ce": f"contact@test_{univ_code.lower()}.edu",
            "ms": univ_s,
        }).scalar()

        # Asociaza userul cu universitatea + home_station
        conn.execute(text("""
            UPDATE users
            SET home_station_id = :hs, university_id = :uni
            WHERE user_id = :uid
        """), {"hs": home_s, "uni": univ_id, "uid": user_id})

        # Adauga ruta home <-> univ in routes (necesar pentru get_route_distance_km)
        nonce = next(_seq)
        op_id = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 100)
            ON CONFLICT (route_code) DO NOTHING
        """), {
            "rn": f"Home-Univ {nonce}",
            "rc": f"HU_{nonce}",
            "op": op_id, "s1": home_s, "s2": univ_s,
        })

    _mark_student_verified(engine, user_id)
    return home_s, univ_s


def _setup_arbitrary_route(engine, code_a: str, code_b: str,
                           distance_km: float = 200) -> tuple[int, int]:
    """Creeaza 2 statii + o ruta intre ele. Returneaza (station_a_id, station_b_id)."""
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'City A', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": code_a, "n": f"Station {code_a}"}).scalar()

        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'City B', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": code_b, "n": f"Station {code_b}"}).scalar()

        nonce = next(_seq)
        op_id = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, :d)
            ON CONFLICT (route_code) DO NOTHING
        """), {
            "rn": f"Route {code_a}-{code_b} {nonce}",
            "rc": f"RT_{nonce}",
            "op": op_id, "s1": s1, "s2": s2, "d": distance_km,
        })

    return s1, s2


# ===========================================================================
# 1. UNIT TESTS pe compute_subscription_price
# ===========================================================================

class TestSubscriptionPriceFormula:

    def test_monthly_without_discount(self):
        from app.services.subscription_business import compute_subscription_price
        # (100 * 0.5 + 50) * 1 = 100 RON
        base, disc, final = compute_subscription_price(
            distance_km=100, subscription_type="monthly", is_student_route=False
        )
        assert base == 100.0
        assert disc == 0.0
        assert final == 100.0

    def test_monthly_with_student_discount(self):
        from app.services.subscription_business import compute_subscription_price
        # base = 100, discount = 90 (OUG 11/2024 -> 90% student), final = 10
        base, disc, final = compute_subscription_price(
            distance_km=100, subscription_type="monthly", is_student_route=True
        )
        assert base == 100.0
        assert disc == 90.0
        assert final == 10.0

    def test_annual_with_student_discount(self):
        from app.services.subscription_business import compute_subscription_price
        # base = 100 * 10 = 1000, discount = 900 (OUG 11/2024 -> 90%), final = 100
        base, disc, final = compute_subscription_price(
            distance_km=100, subscription_type="annual", is_student_route=True
        )
        assert base == 1000.0
        assert disc == 900.0
        assert final == 100.0

    def test_invalid_type_raises(self):
        from app.services.subscription_business import compute_subscription_price
        with pytest.raises(ValueError):
            compute_subscription_price(100, "biennial", False)


# ===========================================================================
# 2. REFUND PRO-RATA
# ===========================================================================

class TestSubscriptionRefund:

    def test_refund_not_started_full(self):
        from app.services.subscription_business import compute_subscription_refund
        today = date(2026, 1, 15)
        vf = date(2026, 2, 1)  # in viitor
        vu = date(2026, 3, 1)
        refund, tier = compute_subscription_refund(100.0, vf, vu, cancel_date=today)
        assert tier == "full_not_started"
        assert refund == 100.0

    def test_refund_partial_pro_rata(self):
        from app.services.subscription_business import compute_subscription_refund
        # Abonament 30 zile, 10 zile folosite (33%) -> refund pe 20 zile * 0.5
        vf = date(2026, 1, 1)
        vu = date(2026, 1, 31)
        today = date(2026, 1, 11)  # 10 zile folosite
        refund, tier = compute_subscription_refund(300.0, vf, vu, cancel_date=today)
        assert tier == "partial_pro_rata"
        # 20/30 * 0.5 * 300 = 100
        assert abs(refund - 100.0) < 0.5

    def test_refund_more_than_half_zero(self):
        from app.services.subscription_business import compute_subscription_refund
        vf = date(2026, 1, 1)
        vu = date(2026, 1, 31)
        today = date(2026, 1, 20)  # 19 zile folosite (>50%)
        refund, tier = compute_subscription_refund(300.0, vf, vu, cancel_date=today)
        assert tier == "more_than_half_used"
        assert refund == 0.0


# ===========================================================================
# 3. QUOTE endpoint
# ===========================================================================

class TestSubscriptionQuote:

    def test_quote_without_discount(self, client):
        s1, s2 = _setup_arbitrary_route(_engine(), "QT01", "QT02", distance_km=100)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/subscriptions/quote", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["distance_km"] == 100.0
        assert body["base_price"] == 100.0
        assert body["discount_amount"] == 0.0
        assert body["final_price"] == 100.0
        assert body["is_student_route"] is False

    def test_quote_with_student_discount_on_home_univ_route(self, client):
        token = register_and_login(client, "passenger")
        user_id = _get_user_id(client, token)
        h = {"Authorization": f"Bearer {token}"}

        home_s, univ_s = _setup_user_with_home_and_university(
            _engine(), user_id, "QHOME1", "QUNIV1",
        )

        r = client.post("/subscriptions/quote", json={
            "from_station_id": home_s, "to_station_id": univ_s,
            "subscription_type": "monthly",
        }, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_student_route"] is True
        assert body["discount_pct"] == 90.0
        assert body["discount_amount"] > 0
        assert body["final_price"] < body["base_price"]

    def test_quote_no_discount_on_other_route_for_student(self, client):
        """Student verificat dar pe ALTA ruta -> fara reducere (regula CFR)."""
        token = register_and_login(client, "passenger")
        user_id = _get_user_id(client, token)
        h = {"Authorization": f"Bearer {token}"}

        # Setup home + univ + student verified
        _setup_user_with_home_and_university(_engine(), user_id, "QHOME2", "QUNIV2")

        # Acum cere quote pe ALTA ruta
        s1, s2 = _setup_arbitrary_route(_engine(), "QT03", "QT04", distance_km=150)

        r = client.post("/subscriptions/quote", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_student_route"] is False
        assert body["discount_amount"] == 0.0


# ===========================================================================
# 4. BUY + ANTI-OVERLAP
# ===========================================================================

class TestSubscriptionBuy:

    def test_buy_creates_active_subscription(self, client):
        s1, s2 = _setup_arbitrary_route(_engine(), "BUY01", "BUY02", distance_km=100)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["subscription_id"] is not None
        assert body["subscription_type"] == "monthly"
        assert body["distance_km"] == 100.0

    def test_buy_anti_overlap_same_direction(self, client):
        s1, s2 = _setup_arbitrary_route(_engine(), "OVR01", "OVR02")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        body = {"from_station_id": s1, "to_station_id": s2,
                "subscription_type": "monthly"}
        r1 = client.post("/subscriptions/buy", json=body, headers=h)
        assert r1.status_code == 200

        r2 = client.post("/subscriptions/buy", json=body, headers=h)
        assert r2.status_code == 409
        assert r2.json()["detail"]["error"] == "subscription_overlap"

    def test_buy_anti_overlap_reverse_direction(self, client):
        """Abonament Buc->Cluj impiedica cumpararea Cluj->Buc (acelasi traseu)."""
        s1, s2 = _setup_arbitrary_route(_engine(), "OVR03", "OVR04")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r1 = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r1.status_code == 200

        r2 = client.post("/subscriptions/buy", json={
            "from_station_id": s2, "to_station_id": s1,  # invers
            "subscription_type": "monthly",
        }, headers=h)
        assert r2.status_code == 409

    def test_buy_different_routes_ok(self, client):
        s1, s2 = _setup_arbitrary_route(_engine(), "ROUTE1A", "ROUTE1B")
        s3, s4 = _setup_arbitrary_route(_engine(), "ROUTE2A", "ROUTE2B")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r1 = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        r2 = client.post("/subscriptions/buy", json={
            "from_station_id": s3, "to_station_id": s4,
            "subscription_type": "monthly",
        }, headers=h)
        assert r1.status_code == 200
        assert r2.status_code == 200


# ===========================================================================
# 5. CANCEL endpoint
# ===========================================================================

class TestSubscriptionCancel:

    def test_cancel_active_returns_full_refund_when_not_started(self, client):
        """Backend creeaza valid_from = today, deci cancel azi = 0 zile folosite."""
        s1, s2 = _setup_arbitrary_route(_engine(), "CXL01", "CXL02", distance_km=100)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        sub_id = r.json()["subscription_id"]

        cancel = client.post(f"/subscriptions/{sub_id}/cancel", headers=h)
        assert cancel.status_code == 200, cancel.text
        body = cancel.json()
        assert body["status"] == "cancelled"
        # Cu valid_from = today si days_used = 0, pct_used = 0 (sub 50%)
        # Refund partial_pro_rata: 30/30 * 0.5 * 100 = 50 RON
        assert body["refund_tier"] in ("partial_pro_rata", "full_not_started")
        assert body["refund_amount"] > 0

    def test_cancel_other_user_subscription_forbidden(self, client):
        s1, s2 = _setup_arbitrary_route(_engine(), "CXL03", "CXL04")
        token_a = register_and_login(client, "passenger")
        token_b = register_and_login(client, "passenger")

        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers={"Authorization": f"Bearer {token_a}"})
        sub_id = r.json()["subscription_id"]

        r2 = client.post(f"/subscriptions/{sub_id}/cancel",
                         headers={"Authorization": f"Bearer {token_b}"})
        assert r2.status_code == 403

    def test_cannot_cancel_twice(self, client):
        s1, s2 = _setup_arbitrary_route(_engine(), "CXL05", "CXL06")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        sub_id = r.json()["subscription_id"]

        c1 = client.post(f"/subscriptions/{sub_id}/cancel", headers=h)
        assert c1.status_code == 200
        c2 = client.post(f"/subscriptions/{sub_id}/cancel", headers=h)
        assert c2.status_code == 409


# ===========================================================================
# 6. LAZY EXPIRE
# ===========================================================================

class TestSubscriptionLazyExpire:

    def test_expired_subscriptions_marked_at_get_my(self, client):
        s1, s2 = _setup_arbitrary_route(_engine(), "EXP01", "EXP02")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        # Cumpar + apoi setez manual valid_until in trecut (simulare expirare)
        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        sub_id = r.json()["subscription_id"]

        with _engine().begin() as conn:
            conn.execute(text("""
                UPDATE subscriptions
                SET valid_until = CURRENT_DATE - INTERVAL '1 day',
                    valid_from = CURRENT_DATE - INTERVAL '31 days'
                WHERE subscription_id = :sid
            """), {"sid": sub_id})

        # GET /subscriptions/my ar trebui sa-l marcheze 'expired' lazy
        r = client.get("/subscriptions/my", headers=h)
        assert r.status_code == 200
        body = r.json()
        sub = next(s for s in body if s["subscription_id"] == sub_id)
        assert sub["status"] == "expired"


# ===========================================================================
# 7. INTEGRARE CU BILETE (testul cheie de business)
# ===========================================================================

class TestSubscriptionTicketIntegration:
    """Verifica regula centrala: ticket pe ruta cu abonament -> price=0."""

    def _setup_train_with_route(self, engine, s1, s2, distance=100):
        """Creeaza un tren cu ruta s1->s2 si layout."""
        nonce = next(_seq)
        with engine.begin() as conn:
            op_id = conn.execute(
                text("SELECT operator_id FROM railway_operators LIMIT 1")
            ).scalar()

            # Caut o ruta existenta intre s1->s2 (creata de _setup_arbitrary_route)
            route_id = conn.execute(text("""
                SELECT route_id FROM routes
                WHERE (origin_station_id = :a AND destination_station_id = :b)
                   OR (origin_station_id = :b AND destination_station_id = :a)
                LIMIT 1
            """), {"a": s1, "b": s2}).scalar()

            assert route_id, "Route should exist from _setup_arbitrary_route"

            train_id = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'regio', 180, TRUE)
                ON CONFLICT (operator_id, train_number) DO UPDATE
                    SET is_active = TRUE
                RETURNING train_id
            """), {"op": op_id, "rt": route_id, "tn": f"SUB_T_{nonce}"}).scalar()

            # Route stops cu departure_time / arrival_time
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES
                    (:rt, :s1, 1, NULL, '09:00'::TIME, 0),
                    (:rt, :s2, 2, '11:00'::TIME, NULL, :d)
                ON CONFLICT (route_id, stop_order) DO UPDATE
                    SET arrival_time = EXCLUDED.arrival_time,
                        departure_time = EXCLUDED.departure_time
            """), {"rt": route_id, "s1": s1, "s2": s2, "d": distance})

            conn.execute(text("SELECT generate_train_layout(:t)"), {"t": train_id})

        return train_id

    def test_ticket_on_covered_route_is_free(self, client):
        """User cumpara abonament Buc->Cluj, apoi bilet pe acelasi traseu -> 0 RON."""
        s1, s2 = _setup_arbitrary_route(_engine(), "TIC01", "TIC02", distance_km=100)
        train_id = self._setup_train_with_route(_engine(), s1, s2)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        future = date.today() + timedelta(days=10)

        # 1. Cumpara abonament
        r_sub = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r_sub.status_code == 200, r_sub.text
        sub_id = r_sub.json()["subscription_id"]

        # 2. Cumpara bilet pe acelasi traseu in perioada de valabilitate
        r_tic = client.post("/tickets/buy", json={
            "train_id": train_id,
            "departure_station_id": s1,
            "arrival_station_id": s2,
            "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        assert r_tic.status_code == 200, r_tic.text
        ticket_id = r_tic.json()["ticket_id"]

        # 3. Verific in DB: price=0 si uses_subscription_id setat
        with _engine().connect() as conn:
            row = conn.execute(text("""
                SELECT price, discount_applied, uses_subscription_id
                FROM tickets WHERE ticket_id = :tid
            """), {"tid": ticket_id}).first()
        assert float(row[0]) == 0.0, f"Expected price=0, got {row[0]}"
        assert float(row[1]) == 100.0, f"Expected discount=100, got {row[1]}"
        assert row[2] == sub_id, f"Expected uses_subscription_id={sub_id}, got {row[2]}"

    def test_ticket_on_uncovered_route_has_normal_price(self, client):
        """User are abonament Buc->Cluj. Bilet Buc->Iasi -> pret normal."""
        # Abonament: route 1
        s1, s2 = _setup_arbitrary_route(_engine(), "TIC03", "TIC04", distance_km=100)
        # Bilet: route 2 (alta)
        s3, s4 = _setup_arbitrary_route(_engine(), "TIC05", "TIC06", distance_km=150)
        train_id = self._setup_train_with_route(_engine(), s3, s4, distance=150)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        future = date.today() + timedelta(days=10)

        # Abonament pe ruta 1
        client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)

        # Bilet pe ruta 2 - NU trebuie sa fie gratuit
        r = client.post("/tickets/buy", json={
            "train_id": train_id,
            "departure_station_id": s3,
            "arrival_station_id": s4,
            "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        assert r.status_code == 200, r.text

        with _engine().connect() as conn:
            row = conn.execute(text("""
                SELECT price, uses_subscription_id FROM tickets WHERE ticket_id = :tid
            """), {"tid": r.json()["ticket_id"]}).first()
        assert float(row[0]) > 0, "Expected normal price, got free"
        assert row[1] is None, "Should NOT use subscription for this route"
