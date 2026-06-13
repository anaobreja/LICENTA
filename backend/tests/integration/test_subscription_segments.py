"""
Teste pentru aplicarea abonamentului pe SEGMENTE ale rutei.

Acopera fixul P2: abonament Faurei <-> Bucuresti (de exemplu) acopera si
biletele cumparate pentru sub-segmente sau leg-uri ale unei calatorii cu
schimbare (ex: Faurei -> Buzau, Buzau -> Bucuresti).

Reutilizam fixture-ul seed_segment_infrastructure din test_personal_route_segments
care creeaza:
  - Ruta directa Iasi -> Bacau -> Bucuresti
  - Doua rute care formeaza un transfer Faurei -> Buzau -> Bucuresti
  - O statie off-route (Constanta)
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.core.database import engine as _global_engine
from app.services.subscription_business import find_active_subscription_for_route


def _engine():
    return _global_engine


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _find_sub(*, user_id, from_station_id, to_station_id, travel_date):
    """
    Wrapper care apeleaza find_active_subscription_for_route folosind o conexiune
    inchisa corect dupa apel.

    Bug istoric: apelul direct `find_active_subscription_for_route(db=_engine().connect(), ...)`
    crea o conexiune fara `with`, deci niciodata inchisa. Cursor-ul ramanea cu
    AccessShareLock pe subscriptions, iar `DELETE FROM subscriptions` din `finally`
    astepta la infinit -> hang in pytest. pg_terminate_backend nu ajuta pentru ca
    sesiunea nu era 'idle in transaction'.
    """
    with _engine().connect() as conn:
        return find_active_subscription_for_route(
            db=conn,
            user_id=user_id,
            from_station_id=from_station_id,
            to_station_id=to_station_id,
            travel_date=travel_date,
        )


# Reutilizam fixture-ul de infrastructura din celalalt fisier
from tests.integration.test_personal_route_segments import (  # noqa: F401
    seed_segment_infrastructure,
)


@pytest.fixture()
def user_with_subscription_faurei_buc(seed_segment_infrastructure):
    """
    Creeaza un user de test cu un abonament Faurei <-> Bucuresti activ pentru
    luna curenta. Returneaza dict cu user_id, subscription_id si station ids.
    """
    s = seed_segment_infrastructure
    today = date.today()
    valid_from = today - timedelta(days=5)
    valid_until = today + timedelta(days=25)

    with _engine().begin() as conn:
        # Insereaza user
        email = _unique("subseg") + "@test.example"
        user_id = conn.execute(text("""
            INSERT INTO users (first_name, last_name, email, password_hash,
                               role)
            VALUES ('Sub', 'Seg Test', :email, 'x', 'passenger')
            RETURNING user_id
        """), {"email": email}).scalar()

        # Operator pentru abonament
        op_id = conn.execute(text(
            "SELECT operator_id FROM railway_operators ORDER BY operator_id LIMIT 1"
        )).scalar()

        # Insereaza abonament route-scope Faurei <-> Bucuresti
        sub_id = conn.execute(text("""
            INSERT INTO subscriptions (
                user_id, subscription_type, operator_id,
                valid_from, valid_until, price, status,
                subscription_scope, from_station_id, to_station_id
            )
            VALUES (
                :uid, 'monthly', :op, :vf, :vu, 200, 'active',
                'route', :s_from, :s_to
            )
            RETURNING subscription_id
        """), {
            "uid": user_id,
            "op": op_id,
            "vf": valid_from,
            "vu": valid_until,
            "s_from": s["faurei"],
            "s_to": s["buc"],
        }).scalar()

    yield {
        "user_id": user_id,
        "subscription_id": sub_id,
        "stations": s,
        "today": today,
    }

    # NU facem cleanup manual aici. Fixture-ul `client` (function-scope, in
    # conftest.py) apeleaza _truncate_transactional_tables la INCEPUTUL fiecarui
    # test, care goleste users + subscriptions oricum.
    #
    # Daca facem DELETE aici si testul urmator e deja in setup (TRUNCATE),
    # Postgres detecteaza DEADLOCK: noi tinem RowExclusiveLock pe users (DELETE),
    # iar TRUNCATE-ul concurent vrea AccessExclusiveLock pe acelasi tabel.
    # Vezi commit-ul care a corectat acest hang.


class TestSubscriptionSegmentMatch:
    """Verifica ca find_active_subscription_for_route gaseste abonamentul si
    pe segmente, nu doar pe perechea exacta."""

    def test_endpoint_exact_match(self, user_with_subscription_faurei_buc):
        """Perechea exacta {Faurei, Bucuresti} - cazul vechi, tot trebuie sa mearga."""
        u = user_with_subscription_faurei_buc
        result = _find_sub(
            user_id=u["user_id"],
            from_station_id=u["stations"]["faurei"],
            to_station_id=u["stations"]["buc"],
            travel_date=u["today"],
        )
        assert result is not None
        assert result["subscription_id"] == u["subscription_id"]
        assert result["match_kind"] == "endpoint"

    def test_endpoint_reverse_match(self, user_with_subscription_faurei_buc):
        """Sens invers: Bucuresti -> Faurei (acelasi abonament)."""
        u = user_with_subscription_faurei_buc
        result = _find_sub(
            user_id=u["user_id"],
            from_station_id=u["stations"]["buc"],
            to_station_id=u["stations"]["faurei"],
            travel_date=u["today"],
        )
        assert result is not None
        assert result["subscription_id"] == u["subscription_id"]

    def test_segment_first_leg_faurei_buzau(self, user_with_subscription_faurei_buc):
        """
        Faurei -> Buzau (primul leg al calatoriei Faurei -> Bucuresti cu
        schimbare in Buzau). Abonamentul Faurei-Bucuresti TREBUIE sa acopere.
        Acesta e cazul P2 fixat.
        """
        u = user_with_subscription_faurei_buc
        result = _find_sub(
            user_id=u["user_id"],
            from_station_id=u["stations"]["faurei"],
            to_station_id=u["stations"]["buzau"],
            travel_date=u["today"],
        )
        assert result is not None, (
            "Abonament Faurei-Bucuresti ar trebui sa acopere si segmentul "
            "Faurei -> Buzau (primul leg al calatoriei cu schimbare)"
        )
        assert result["match_kind"] == "segment"

    def test_segment_second_leg_buzau_bucuresti(self, user_with_subscription_faurei_buc):
        """
        Buzau -> Bucuresti (al doilea leg). Abonamentul TREBUIE sa acopere.
        """
        u = user_with_subscription_faurei_buc
        result = _find_sub(
            user_id=u["user_id"],
            from_station_id=u["stations"]["buzau"],
            to_station_id=u["stations"]["buc"],
            travel_date=u["today"],
        )
        assert result is not None
        assert result["match_kind"] == "segment"

    def test_off_route_no_match(self, user_with_subscription_faurei_buc):
        """
        Faurei -> Constanta: Constanta NU e pe traseul Faurei-Bucuresti.
        Abonamentul NU trebuie sa acopere.
        """
        u = user_with_subscription_faurei_buc
        result = _find_sub(
            user_id=u["user_id"],
            from_station_id=u["stations"]["faurei"],
            to_station_id=u["stations"]["constanta"],
            travel_date=u["today"],
        )
        assert result is None

    def test_user_without_subscription_returns_none(self, seed_segment_infrastructure):
        """User fara abonament -> None"""
        # User nou, fara abonament
        with _engine().begin() as conn:
            uid = conn.execute(text("""
                INSERT INTO users (first_name, last_name, email, password_hash, role)
                VALUES ('No', 'Sub', :em, 'x', 'passenger')
                RETURNING user_id
            """), {"em": _unique("nosub") + "@t.ex"}).scalar()
        result = _find_sub(
            user_id=uid,
            from_station_id=seed_segment_infrastructure["faurei"],
            to_station_id=seed_segment_infrastructure["buzau"],
            travel_date=date.today(),
        )
        assert result is None
        # Cleanup-ul tabelei `users` se face de fixture-ul `client` la testul
        # urmator (TRUNCATE in conftest). NU facem DELETE manual aici ->
        # ar putea provoca deadlock cu TRUNCATE-ul concurent (vezi user_with_subscription_faurei_buc).

    def test_subscription_expired_does_not_match(self, seed_segment_infrastructure):
        """Abonament expirat (status='expired') -> nu match chiar daca e in interval"""
        s = seed_segment_infrastructure
        with _engine().begin() as conn:
            op_id = conn.execute(text(
                "SELECT operator_id FROM railway_operators ORDER BY operator_id LIMIT 1"
            )).scalar()
            uid = conn.execute(text("""
                INSERT INTO users (first_name, last_name, email, password_hash, role)
                VALUES ('Exp', 'Sub', :em, 'x', 'passenger')
                RETURNING user_id
            """), {"em": _unique("expsub") + "@t.ex"}).scalar()
            sub_id = conn.execute(text("""
                INSERT INTO subscriptions (
                    user_id, subscription_type, operator_id,
                    valid_from, valid_until, price, status,
                    subscription_scope, from_station_id, to_station_id
                )
                VALUES (
                    :uid, 'monthly', :op,
                    :vf, :vu, 200, 'expired',
                    'route', :a, :b
                )
                RETURNING subscription_id
            """), {
                "uid": uid, "op": op_id,
                "vf": date.today() - timedelta(days=10),
                "vu": date.today() + timedelta(days=10),
                "a": s["faurei"], "b": s["buc"],
            }).scalar()
        result = _find_sub(
            user_id=uid,
            from_station_id=s["faurei"],
            to_station_id=s["buzau"],
            travel_date=date.today(),
        )
        assert result is None, "Abonament expirat nu trebuie sa fie returnat"
        # Cleanup automat la testul urmator (vezi nota din test_user_without_subscription_returns_none).
