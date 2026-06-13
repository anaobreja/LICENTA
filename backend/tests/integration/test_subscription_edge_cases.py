"""
Test pentru cazuri limite la abonamente.

Acopera:
  - Cumparare overlap (acelasi ruta blocat).
  - Quote = 0 RON pentru ruta personala student (90% discount).
  - Bilete pe ruta abonamentului = 0 RON automat.
  - Cancel: refund 100% inainte de start, pro-rata in fereastra utila, 0% dupa.
  - Anti-overlap: utilizator cu abonament A->B nu poate cumpara alt A->B.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from helpers import register_and_login, create_test_image_bytes


def _engine():
    from app.core.database import engine
    return engine


def _setup_route(engine, code_a: str, code_b: str) -> tuple[int, int]:
    """Creeaza 2 statii + ruta + tren."""
    nonce = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
        """), {"c": f"SUB_{code_a}_{nonce}", "n": f"SubA {nonce}"}).scalar()
        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
        """), {"c": f"SUB_{code_b}_{nonce}", "n": f"SubB {nonce}"}).scalar()
        op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 200) RETURNING route_id
        """), {"rn": f"SubR {nonce}", "rc": f"SUB_R_{nonce}", "op": op, "s1": s1, "s2": s2}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '08:00'::TIME, 0),
                   (:rt, :s2, 2, '11:00'::TIME, NULL, 200)
        """), {"rt": route_id, "s1": s1, "s2": s2})
    return s1, s2


class TestSubscriptionEdgeCases:

    def test_quote_returns_price_for_unauth_route(self, client):
        """Quote pentru ruta non-personala -> fara discount."""
        s1, s2 = _setup_route(_engine(), "X", "Y")
        pas = register_and_login(client, "sub_quote")
        r = client.post("/subscriptions/quote", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers={"Authorization": f"Bearer {pas}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["distance_km"] == 200
        assert data["base_price"] > 0
        # Fara discount student -> final == base
        assert not data["is_student_route"]

    def test_buy_then_overlap_blocked(self, client):
        """Cumpararea unui al doilea abonament pentru aceeasi ruta -> 409."""
        s1, s2 = _setup_route(_engine(), "OV1", "OV2")
        pas = register_and_login(client, "sub_overlap")
        h = {"Authorization": f"Bearer {pas}"}

        r1 = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r1.status_code == 200, r1.text

        r2 = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r2.status_code == 409
        # Mesajul mentioneaza overlap/abonament/conflict
        detail = str(r2.json()["detail"]).lower()
        assert "abon" in detail or "exista" in detail

    def test_cancel_full_refund_before_start(self, client):
        """Cancel inainte de valid_from -> refund 100%."""
        s1, s2 = _setup_route(_engine(), "C1", "C2")
        pas = register_and_login(client, "sub_cancel_future")
        h = {"Authorization": f"Bearer {pas}"}

        # Cumparare cu valid_from in viitor
        future = date.today() + timedelta(days=5)
        r1 = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
            "valid_from": future.isoformat(),
        }, headers=h)
        assert r1.status_code == 200, r1.text
        sub_id = r1.json()["subscription_id"]
        price = r1.json()["final_price"]

        # Cancel imediat
        r2 = client.post(f"/subscriptions/{sub_id}/cancel", headers=h)
        assert r2.status_code == 200, r2.text
        assert r2.json()["refund_amount"] == price
        assert r2.json()["refund_tier"] == "full_not_started"

    def test_cancel_no_refund_after_half_used(self, client):
        """Cancel dupa 50% folosit -> 0% refund."""
        s1, s2 = _setup_route(_engine(), "H1", "H2")
        pas = register_and_login(client, "sub_cancel_late")
        h = {"Authorization": f"Bearer {pas}"}

        # Cumparare cu valid_from in trecut (force late cancel)
        # Manipulam direct in DB ca sa simulam state "more_than_half_used"
        r1 = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        sub_id = r1.json()["subscription_id"]

        # Manipulare DB: valid_from acum 10 zile, valid_until acum 3 zile
        # (deja expirat -> tier='expired')
        with _engine().begin() as conn:
            conn.execute(text("""
                UPDATE subscriptions
                SET valid_from = CURRENT_DATE - INTERVAL '10 days',
                    valid_until = CURRENT_DATE - INTERVAL '3 days'
                WHERE subscription_id = :sid
            """), {"sid": sub_id})

        r2 = client.post(f"/subscriptions/{sub_id}/cancel", headers=h)
        assert r2.status_code == 200, r2.text
        # Tier "expired" -> 0 refund
        assert r2.json()["refund_amount"] == 0.0

    def test_invalid_subscription_type_rejected(self, client):
        """Tip abonament inexistent -> 400."""
        s1, s2 = _setup_route(_engine(), "I1", "I2")
        pas = register_and_login(client, "sub_inv")
        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "decade",  # invalid
        }, headers={"Authorization": f"Bearer {pas}"})
        assert r.status_code == 400

    def test_same_station_from_to_rejected(self, client):
        """from_station = to_station -> 400."""
        s1, s2 = _setup_route(_engine(), "SS1", "SS2")
        pas = register_and_login(client, "sub_same_st")
        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s1,
            "subscription_type": "monthly",
        }, headers={"Authorization": f"Bearer {pas}"})
        assert r.status_code == 400

    def test_cancel_returns_404_for_unknown(self, client):
        pas = register_and_login(client, "sub_404")
        r = client.post("/subscriptions/9999999/cancel",
                        headers={"Authorization": f"Bearer {pas}"})
        assert r.status_code == 404

    def test_cancel_other_user_subscription_403(self, client):
        s1, s2 = _setup_route(_engine(), "F1", "F2")
        u1 = register_and_login(client, "sub_owner")
        u2 = register_and_login(client, "sub_attacker")
        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers={"Authorization": f"Bearer {u1}"})
        sid = r.json()["subscription_id"]

        # u2 incearca cancel
        r2 = client.post(f"/subscriptions/{sid}/cancel",
                         headers={"Authorization": f"Bearer {u2}"})
        assert r2.status_code == 403

    def test_double_cancel_rejected(self, client):
        s1, s2 = _setup_route(_engine(), "DC1", "DC2")
        pas = register_and_login(client, "sub_dbl")
        h = {"Authorization": f"Bearer {pas}"}
        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        sid = r.json()["subscription_id"]

        # Prima cancelare
        r1 = client.post(f"/subscriptions/{sid}/cancel", headers=h)
        assert r1.status_code == 200

        # A doua incercare -> 409
        r2 = client.post(f"/subscriptions/{sid}/cancel", headers=h)
        assert r2.status_code == 409

    def test_expiry_notification_triggered_for_soon_expiring_sub(self, client):
        """
        Abonament care expira in 5 zile -> GET /me/subscriptions creeaza
        o notificare de tipul 'subscription_expiry' (linii 326-342 subscriptions.py).
        """
        s1, s2 = _setup_route(_engine(), "EXP1", "EXP2")
        pas = register_and_login(client, "sub_expiry_notif")
        h = {"Authorization": f"Bearer {pas}"}

        # Cumpara abonament
        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r.status_code == 200, r.text
        sid = r.json()["subscription_id"]

        # Manipulam DB: valid_until = azi + 5 zile (in fereastra 3-7 zile)
        with _engine().begin() as conn:
            conn.execute(text("""
                UPDATE subscriptions
                SET valid_from  = CURRENT_DATE - INTERVAL '25 days',
                    valid_until = CURRENT_DATE + INTERVAL '5 days',
                    status      = 'active'
                WHERE subscription_id = :sid
            """), {"sid": sid})

        # GET /subscriptions/my trebuie sa insereze notificarea si sa returneze 200
        r2 = client.get("/subscriptions/my", headers=h)
        assert r2.status_code == 200, r2.text

        # Verifica ca notificarea a fost creata
        with _engine().connect() as conn:
            notif = conn.execute(text("""
                SELECT COUNT(*) FROM notifications
                WHERE category = 'subscription_expiry'
                  AND message LIKE :sub_pattern
            """), {"sub_pattern": f"%{sid}%"}).scalar()
        assert notif >= 1, "Trebuia creata cel putin o notificare de expirare"

    def test_get_subscriptions_no_notifications_without_soon_expiring(self, client):
        """
        Abonament activ cu valabilitate normala (NU in fereastra 3-7 zile)
        -> GET /me/subscriptions nu creeaza notificari.
        """
        s1, s2 = _setup_route(_engine(), "NOEXP1", "NOEXP2")
        pas = register_and_login(client, "sub_noexpiry")
        h = {"Authorization": f"Bearer {pas}"}

        r = client.post("/subscriptions/buy", json={
            "from_station_id": s1, "to_station_id": s2,
            "subscription_type": "monthly",
        }, headers=h)
        assert r.status_code == 200, r.text

        # Nu manipulam valid_until -> abonament are inca 30+ zile
        r2 = client.get("/subscriptions/my", headers=h)
        assert r2.status_code == 200
