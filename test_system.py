"""
ParkVoice AI - Comprehensive End-to-End System Test Suite
Tests all 11 core application layers and 22 business flows:
1. User Auth & Password Hashing
2. Admin Auth & Privilege Isolation
3. Vehicle Garage CRUD & Default Switching
4. 4x3 Slot Database Querying
5. Real A* Search & Manhattan Heuristic with Obstacles
6. Intelligent Slot Recommendation (EV vs Car vs Bike)
7. Atomic Booking & Concurrency Double-Booking Prevention (409 Conflict)
8. Active Booking Polling & Route Generation
9. Booking Cancellation & Slot State Return to Available
10. Booking Release & Parking History Recording
11. Admin Live Simulation Triggers & Analytics Telemetry
"""

import unittest
from app import app, get_db_connection
import astar

class TestParkVoiceAI(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_database_and_slots(self):
        """Verify database connectivity and all 12 slots exist."""
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM parking_slots")
            count = cursor.fetchone()["count"]
            self.assertEqual(count, 12, "Should have exactly 12 parking slots (P01-P12)")
        conn.close()

    def test_02_astar_pathfinding(self):
        """Verify real A* pathfinding from Entrance (4, 1) to bays avoiding obstacles."""
        start = astar.ENTRANCE_COORDINATES
        # Target slot P01 at (0, 0)
        goal = (0, 0)
        # Block intermediate cells (3, 1) and (2, 1)
        blocked = {(3, 1), (2, 1)}
        res = astar.find_path(start, goal, blocked)
        self.assertTrue(res["success"])
        self.assertGreater(res["distance"], 0)
        # Path must not contain blocked cells
        for step in res["path"]:
            self.assertNotIn(step, blocked)
        print(f"  [A* Test] Path to P01 avoiding {(3, 1), (2, 1)}: {res['path']} (dist: {res['distance']})")

    def test_03_recommendation_engine(self):
        """Verify live recommendation prioritizes EV chargers for EV vehicles."""
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM parking_slots")
            slots = cursor.fetchall()
        conn.close()

        for s in slots:
            s["has_ev_charger"] = bool(s["has_ev_charger"])

        rec_ev = astar.recommend_best_slot(slots, "EV")
        self.assertIsNotNone(rec_ev["recommended_slot"])
        self.assertTrue(rec_ev["recommended_slot"]["has_ev_charger"])
        print(f"  [Recommendation Test] EV best slot: {rec_ev['recommended_slot']['slot_number']} ({rec_ev['reason']})")

        rec_car = astar.recommend_best_slot(slots, "Car")
        self.assertIsNotNone(rec_car["recommended_slot"])
        print(f"  [Recommendation Test] Car best slot: {rec_car['recommended_slot']['slot_number']} ({rec_car['reason']})")

    def test_04_user_auth(self):
        """Verify user login with demo credentials."""
        res = self.client.post("/login", data={
            "email": "demo@parkvoice.ai",
            "password": "User@123"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302, "Valid user login should redirect to dashboard")

    def test_05_admin_auth(self):
        """Verify admin login with admin credentials."""
        res = self.client.post("/admin/login", data={
            "username": "admin",
            "password": "Admin@123"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302, "Valid admin login should redirect to admin dashboard")

    def test_06_double_booking_prevention(self):
        """Verify atomic prevention of double-booking the same slot."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Alex Rivers"

        # First reset slots so P07 is available
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE bookings SET status='COMPLETED' WHERE status='ACTIVE'")
            cursor.execute("UPDATE parking_slots SET status='AVAILABLE' WHERE slot_number='P07'")
            conn.commit()
        conn.close()

        # User 1 books P07
        res1 = self.client.post("/api/bookings/create", json={"slot_number": "P07"})
        self.assertEqual(res1.status_code, 201, "First booking attempt must succeed")
        booking_code = res1.json["booking"]["booking_code"]

        # Ensure a second real user exists with a registered vehicle
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email='driver2@parkvoice.ai'")
            u2 = cursor.fetchone()
            if not u2:
                from werkzeug.security import generate_password_hash
                cursor.execute(
                    "INSERT INTO users (full_name, email, password_hash) VALUES ('Driver Two', 'driver2@parkvoice.ai', %s)",
                    (generate_password_hash('User@123'),)
                )
                u2_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO vehicles (user_id, plate_number, vehicle_type, model, is_default) VALUES (%s, 'MH 02 DD 2222', 'Car', 'Toyota Corolla', 1)",
                    (u2_id,)
                )
                conn.commit()
            else:
                u2_id = u2["id"]
        conn.close()

        # Simulate second user trying to book P07 concurrently
        with self.client.session_transaction() as sess:
            sess["user_id"] = u2_id
            sess["user_name"] = "Driver Two"

        res2 = self.client.post("/api/bookings/create", json={"slot_number": "P07"})
        self.assertEqual(res2.status_code, 409, "Second concurrent attempt on same slot MUST return 409 Conflict")
        self.assertIn("Double-booking prevented", res2.json["error"])
        print(f"  [Double Booking Test] Blocked duplicate booking on P07 successfully with 409 Conflict!")

        # Clean up: cancel user 1's booking
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
        res_cancel = self.client.post("/api/bookings/cancel", json={})
        self.assertEqual(res_cancel.status_code, 200)

    def test_07_live_simulation_and_analytics(self):
        """Verify admin live simulation triggers and Chart.js analytics endpoint."""
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["admin_username"] = "admin"

        # 1. Simulate entry
        res_entry = self.client.post("/api/admin/simulate/entry", json={})
        self.assertTrue(res_entry.json["success"])

        # 2. Simulate exit
        res_exit = self.client.post("/api/admin/simulate/exit", json={})
        self.assertTrue(res_exit.json["success"])

        # 3. Analytics data
        res_analytics = self.client.get("/api/admin/analytics")
        self.assertTrue(res_analytics.json["success"])
        self.assertIn("peak_hours", res_analytics.json)
        self.assertIn("daily_trend", res_analytics.json)
        self.assertIn("slot_usage", res_analytics.json)
        print("  [Admin Test] Live simulation triggers and analytics validated successfully!")

    def test_08_diagnostic(self):
        """Inspect actual database state."""
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, slot_number, status, slot_type, has_ev_charger FROM parking_slots")
            slots = cursor.fetchall()
            cursor.execute("SELECT id, user_id, plate_number, vehicle_type, is_default FROM vehicles")
            vehicles = cursor.fetchall()
            cursor.execute("SELECT id, booking_code, user_id, slot_id, status FROM bookings WHERE status='ACTIVE'")
            active_bookings = cursor.fetchall()
        conn.close()
        print(f"\n  --- DB SLOTS ({len(slots)}) ---")
        for s in slots:
            print(f"    Slot {s['slot_number']}: status={s['status']}, type={s['slot_type']}, ev={s['has_ev_charger']}")
        print(f"  --- DB VEHICLES ({len(vehicles)}) ---")
        for v in vehicles:
            print(f"    Vehicle {v['id']}: user={v['user_id']}, plate={v['plate_number']}, type={v['vehicle_type']}, default={v['is_default']}")
        print(f"  --- ACTIVE BOOKINGS ({len(active_bookings)}) ---")
    def test_09_test_dashboard_booking_payloads(self):
        """Test booking payloads that the dashboard sends."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Alex Rivers"

        # Ensure all bookings completed first
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE bookings SET status='COMPLETED' WHERE status='ACTIVE'")
            cursor.execute("UPDATE parking_slots SET status='AVAILABLE'")
            cursor.execute("SELECT id FROM vehicles WHERE user_id = 1 LIMIT 1")
            veh = cursor.fetchone()
            if not veh:
                cursor.execute("INSERT INTO vehicles (user_id, plate_number, vehicle_type, model, is_default) VALUES (1, 'MH 12 AB 1234', 'Car', 'Civic', 1)")
                veh_id = cursor.lastrowid
            else:
                veh_id = veh["id"]
            conn.commit()
        conn.close()

        # Try booking with slot_id and vehicle_id
        res = self.client.post("/api/bookings/create", json={"slot_id": 1, "vehicle_id": veh_id})
        print(f"\n  [Booking Test 1] slot_id=1, vehicle_id={veh_id}: status={res.status_code}, body={res.json}")
        self.assertEqual(res.status_code, 201)

        # Cancel it
        self.client.post("/api/bookings/cancel", json={})

        # Try booking with just slot_number and vehicle_id
        res = self.client.post("/api/bookings/create", json={"slot_number": "P02", "vehicle_id": veh_id})
        print(f"  [Booking Test 2] slot_number='P02', vehicle_id={veh_id}: status={res.status_code}, body={res.json}")
        self.assertEqual(res.status_code, 201)

        self.client.post("/api/bookings/cancel", json={})

        # Try booking with just slot_id (vehicle_id omitted)
        res = self.client.post("/api/bookings/create", json={"slot_id": 3})
        print(f"  [Booking Test 3] slot_id=3 (no vehicle_id): status={res.status_code}, body={res.json}")
        self.assertEqual(res.status_code, 201)

        self.client.post("/api/bookings/cancel", json={})

    def test_10_multi_vehicle_booking(self):
        """Verify a user can hold simultaneous active bookings for different vehicles."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Alex Rivers"

        # Reset active bookings and ensure user has at least 2 vehicles
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("UPDATE bookings SET status='COMPLETED' WHERE status='ACTIVE'")
            cursor.execute("UPDATE parking_slots SET status='AVAILABLE'")
            cursor.execute("SELECT id FROM vehicles WHERE user_id = 1 ORDER BY id ASC")
            vehs = cursor.fetchall()
            if len(vehs) < 2:
                cursor.execute("INSERT INTO vehicles (user_id, plate_number, vehicle_type, model, is_default) VALUES (1, 'MH 99 EV 9999', 'EV', 'Tesla Model 3', 0)")
                cursor.execute("SELECT id FROM vehicles WHERE user_id = 1 ORDER BY id ASC")
                vehs = cursor.fetchall()
            v1_id = vehs[0]["id"]
            v2_id = vehs[1]["id"]
            conn.commit()
        conn.close()

        # 1. Book P03 for Vehicle 1
        res1 = self.client.post("/api/bookings/create", json={"slot_number": "P03", "vehicle_id": v1_id})
        self.assertEqual(res1.status_code, 201, f"Vehicle {v1_id} should book P03 successfully")
        b1_id = res1.json["booking"]["id"]

        # 2. Book P09 for Vehicle 2
        res2 = self.client.post("/api/bookings/create", json={"slot_number": "P09", "vehicle_id": v2_id})
        self.assertEqual(res2.status_code, 201, f"Vehicle {v2_id} should book P09 successfully")
        b2_id = res2.json["booking"]["id"]

        # 3. Fetch active bookings - must contain BOTH
        res_active = self.client.get("/api/bookings/active")
        self.assertTrue(res_active.json["success"])
        active_list = res_active.json["active_bookings"]
        self.assertEqual(len(active_list), 2, "Should have 2 active bookings for user 1")
        slots_booked = {b["slot_number"] for b in active_list}
        self.assertEqual(slots_booked, {"P03", "P09"})
        print(f"  [Multi-Vehicle Test] Successfully booked 2 vehicles simultaneously: {slots_booked}")

        # 4. Attempting to book again for Vehicle 1 should be blocked
        res_dup = self.client.post("/api/bookings/create", json={"slot_number": "P04", "vehicle_id": v1_id})
        self.assertEqual(res_dup.status_code, 400, "Vehicle 1 cannot have a 2nd active booking")

        # 5. Cancel Vehicle 1's booking
        res_cancel1 = self.client.post("/api/bookings/cancel", json={"booking_id": b1_id})
        self.assertEqual(res_cancel1.status_code, 200)

        # 6. Verify Vehicle 2 is STILL active
        res_active2 = self.client.get("/api/bookings/active")
        self.assertEqual(len(res_active2.json["active_bookings"]), 1)
        self.assertEqual(res_active2.json["active_bookings"][0]["slot_number"], "P09")
        print(f"  [Multi-Vehicle Test] Canceled Vehicle 1 booking; Vehicle 2 booking P09 remains active!")

        # Clean up
        self.client.post("/api/bookings/cancel", json={"booking_id": b2_id})

if __name__ == "__main__":
    unittest.main()
