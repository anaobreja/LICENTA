"""
Teste pentru aplicarea reducerii student pe SEGMENTE ale rutei personale
(home <-> universitate), conform OUG 11/2024.

Acopera:
  - Segment direct: studentul cumpara bilet pentru o portiune din ruta unica
    home -> uni (ex: Iasi -> Bacau, ca parte din ruta Iasi -> Bucuresti).
  - Segment pe ruta cu transfer: studentul cumpara unul din cele 2 legs al
    unei calatorii cu schimbare (ex: Buzau -> Bucuresti dintr-o calatorie
    Faurei -> Buzau -> Bucuresti).
  - Off-route: segment care NU face parte din traseul home <-> uni
    -> nu se aplica reducere.
"""
import uuid
import pytest
from sqlalchemy import text
from app.core.database import engine as _global_engine


def _engine():
    return _global_engine


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Fixtures pentru seedarea infrastructurii necesara testelor de segmente
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seed_segment_infrastructure():
    """
    Seed:
      - Statia "Bacau Test" intre Iasi si Bucuresti, pe ruta Iasi-Bucuresti
        (ca sa avem 3 stops: Iasi -> Bacau -> Bucuresti).
      - Ruta "Faurei Test - Buzau Test" + tren
      - Ruta "Buzau Test - Bucuresti Nord" + tren
      - O stație "Constanta Test" care NU e pe traseu (pentru off-route)

    Idempotent: foloseste ON CONFLICT.
    """
    with _engine().begin() as conn:
        op_id = conn.execute(text(
            "SELECT operator_id FROM railway_operators ORDER BY operator_id LIMIT 1"
        )).scalar()
        if op_id is None:
            pytest.skip("Niciun operator in DB - test imposibil")

        # Statia "Iași" si "București Nord" (deja seedate de conftest)
        s_iasi = conn.execute(text(
            "SELECT station_id FROM stations WHERE name = 'Iași' OR name = 'Iaşi' LIMIT 1"
        )).scalar()
        s_buc = conn.execute(text(
            "SELECT station_id FROM stations "
            "WHERE name LIKE 'Bucure%ti Nord%' LIMIT 1"
        )).scalar()
        if s_iasi is None or s_buc is None:
            pytest.skip("Iasi sau BUC Nord lipsesc din DB de test")

        # Stații noi
        s_bacau = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES ('BC_SEGTEST', 'Bacau SegTest', 'Bacau', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """)).scalar()
        s_faurei = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES ('FR_SEGTEST', 'Faurei SegTest', 'Faurei', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """)).scalar()
        s_buzau = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES ('BZ_SEGTEST', 'Buzau SegTest', 'Buzau', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """)).scalar()
        s_constanta = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES ('CT_SEGTEST', 'Constanta SegTest', 'Constanta', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """)).scalar()

        # ---- Ruta 1: Iasi -> Bacau -> Bucuresti Nord (directa, cu stop intermediar) ----
        r1 = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES ('Iasi-Bacau-Bucuresti TEST', 'IS-BC-BN-SEG',
                    :op, :s_iasi, :s_buc, 400)
            ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {"op": op_id, "s_iasi": s_iasi, "s_buc": s_buc}).scalar()
        # Insereaza/upsert route_stops
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES
                (:r, :s1, 1, NULL,          '08:00'::TIME, 0),
                (:r, :s2, 2, '10:30'::TIME, '10:35'::TIME, 200),
                (:r, :s3, 3, '14:00'::TIME, NULL,          400)
            ON CONFLICT (route_id, stop_order) DO UPDATE SET
                arrival_time = EXCLUDED.arrival_time,
                departure_time = EXCLUDED.departure_time,
                distance_from_origin_km = EXCLUDED.distance_from_origin_km,
                station_id = EXCLUDED.station_id
        """), {"r": r1, "s1": s_iasi, "s2": s_bacau, "s3": s_buc})
        conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, 'IR-SEG-1', 'interregio', 200, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE
                SET is_active = TRUE
        """), {"op": op_id, "rt": r1})

        # ---- Ruta 2: Faurei -> Buzau (primul leg) ----
        r2 = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES ('Faurei-Buzau TEST', 'FR-BZ-SEG',
                    :op, :s1, :s2, 60)
            ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {"op": op_id, "s1": s_faurei, "s2": s_buzau}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES
                (:r, :s1, 1, NULL,          '07:00'::TIME, 0),
                (:r, :s2, 2, '08:00'::TIME, NULL,          60)
            ON CONFLICT (route_id, stop_order) DO UPDATE SET
                arrival_time = EXCLUDED.arrival_time,
                departure_time = EXCLUDED.departure_time,
                distance_from_origin_km = EXCLUDED.distance_from_origin_km,
                station_id = EXCLUDED.station_id
        """), {"r": r2, "s1": s_faurei, "s2": s_buzau})
        conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, 'R-SEG-2', 'regio', 120, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE
                SET is_active = TRUE
        """), {"op": op_id, "rt": r2})

        # ---- Ruta 3: Buzau -> Bucuresti Nord (al doilea leg) ----
        r3 = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES ('Buzau-Bucuresti TEST', 'BZ-BN-SEG',
                    :op, :s1, :s2, 130)
            ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {"op": op_id, "s1": s_buzau, "s2": s_buc}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES
                (:r, :s1, 1, NULL,          '08:30'::TIME, 0),
                (:r, :s2, 2, '10:15'::TIME, NULL,          130)
            ON CONFLICT (route_id, stop_order) DO UPDATE SET
                arrival_time = EXCLUDED.arrival_time,
                departure_time = EXCLUDED.departure_time,
                distance_from_origin_km = EXCLUDED.distance_from_origin_km,
                station_id = EXCLUDED.station_id
        """), {"r": r3, "s1": s_buzau, "s2": s_buc})
        conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, 'IR-SEG-3', 'interregio', 200, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE
                SET is_active = TRUE
        """), {"op": op_id, "rt": r3})

    return {
        "iasi": s_iasi,
        "buc": s_buc,
        "bacau": s_bacau,
        "faurei": s_faurei,
        "buzau": s_buzau,
        "constanta": s_constanta,
    }


# ---------------------------------------------------------------------------
# Test unitar pentru _segment_on_personal_path (apel direct, fara HTTP)
# ---------------------------------------------------------------------------

class TestSegmentOnPersonalPath:
    """Verifica direct funcția pură _segment_on_personal_path."""

    def test_endpoint_exact(self, seed_segment_infrastructure):
        """{dep, arr} == {home, uni}  ->  match kind=endpoint"""
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["iasi"], arr_id=s["buc"],
            )
        assert result["match"] is True
        assert result["match_kind"] == "endpoint"

    def test_endpoint_exact_reverse(self, seed_segment_infrastructure):
        """{dep, arr} == {uni, home}  ->  tot endpoint"""
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["buc"], arr_id=s["iasi"],
            )
        assert result["match"] is True
        assert result["match_kind"] == "endpoint"

    def test_direct_segment_first_half(self, seed_segment_infrastructure):
        """Iasi -> Bacau ca parte din Iasi -> Bucuresti  ->  direct_segment"""
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["iasi"], arr_id=s["bacau"],
            )
        assert result["match"] is True, "Iasi -> Bacau e segment al rutei personale"
        assert result["match_kind"] == "direct_segment"

    def test_direct_segment_second_half(self, seed_segment_infrastructure):
        """Bacau -> Bucuresti ca parte din Iasi -> Bucuresti  ->  direct_segment"""
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["bacau"], arr_id=s["buc"],
            )
        assert result["match"] is True
        assert result["match_kind"] == "direct_segment"

    def test_direct_segment_reverse_direction(self, seed_segment_infrastructure):
        """Bucuresti -> Bacau (sens invers al rutei seedate) - tot pe traseu"""
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["buc"], arr_id=s["bacau"],
            )
        assert result["match"] is True
        assert result["match_kind"] == "direct_segment"

    def test_transfer_segment_first_leg(self, seed_segment_infrastructure):
        """
        Faurei -> Buzau: primul leg al unei calatorii Faurei -> Bucuresti
        cu schimbare in Buzau. home=Faurei, uni=Bucuresti.
        """
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["faurei"], uni_id=s["buc"],
                dep_id=s["faurei"], arr_id=s["buzau"],
            )
        assert result["match"] is True, (
            "Faurei -> Buzau ar trebui sa fie segment al rutei Faurei -> Bucuresti "
            "(cu schimbare in Buzau)"
        )
        # Acceptam orice match_kind != None (poate fi 'direct_segment' daca
        # exista o ruta directa Faurei-Buzau-Buc seedata, sau 'transfer_segment')
        assert result["match_kind"] in ("direct_segment", "transfer_segment")

    def test_transfer_segment_second_leg(self, seed_segment_infrastructure):
        """
        Buzau -> Bucuresti: al doilea leg al unei calatorii Faurei -> Bucuresti
        cu schimbare in Buzau.
        """
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["faurei"], uni_id=s["buc"],
                dep_id=s["buzau"], arr_id=s["buc"],
            )
        assert result["match"] is True
        assert result["match_kind"] in ("direct_segment", "transfer_segment")

    def test_off_route_segment(self, seed_segment_infrastructure):
        """
        Iasi -> Constanta: NU e pe traseul Iasi -> Bucuresti -> NU match.
        """
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["iasi"], arr_id=s["constanta"],
            )
        assert result["match"] is False
        assert result["match_kind"] is None

    def test_unrelated_stations(self, seed_segment_infrastructure):
        """Bacau -> Constanta: niciuna pe traseul home<->uni (Iasi-Bucuresti)
        nu duce la Constanta -> NU match."""
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["bacau"], arr_id=s["constanta"],
            )
        assert result["match"] is False

    def test_same_dep_and_arr(self, seed_segment_infrastructure):
        """dep == arr  ->  fara match (statii identice)"""
        from app.routers.tickets import _segment_on_personal_path
        s = seed_segment_infrastructure
        with _engine().connect() as conn:
            result = _segment_on_personal_path(
                conn, home_id=s["iasi"], uni_id=s["buc"],
                dep_id=s["bacau"], arr_id=s["bacau"],
            )
        assert result["match"] is False
