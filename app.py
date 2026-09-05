import os
import random
import string
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
import pymysql
import pymysql.cursors
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

import astar

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "parkvoice_ai_super_secret_key_2026")

# Database Configuration
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "parkvoice_ai")


def get_db_connection(use_database=True):
    """Create a connection to the MySQL/MariaDB server."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME if use_database else None,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        charset="utf8mb4"
    )


def init_database_if_needed():
    """Ensure database and all required tables exist on application startup."""
    try:
        # Check server connection without database first
        conn = get_db_connection(use_database=False)
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4;")
        conn.close()

        # Connect with database and verify tables
        conn = get_db_connection(use_database=True)
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE 'parking_slots';")
            result = cursor.fetchone()
            if not result:
                print("[ParkVoice AI] Initializing schema from database.sql...")
                sql_path = os.path.join(os.path.dirname(__file__), "database.sql")
                if os.path.exists(sql_path):
                    with open(sql_path, "r", encoding="utf-8") as f:
                        sql_commands = f.read()
                    for statement in sql_commands.split(";"):
                        stmt = statement.strip()
                        if stmt:
                            cursor.execute(stmt)
                    conn.commit()
                    print("[ParkVoice AI] Database schema initialized successfully.")
        conn.close()
    except Exception as e:
        print(f"[ParkVoice AI] Database connection/init warning: {e}")


# Run initial DB verification
init_database_if_needed()


# ---------------------------------------------------------
# AUTHENTICATION DECORATORS & HELPERS
# ---------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required", "status": 401}), 401
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Admin privileges required", "status": 403}), 403
            flash("Admin authentication required.", "danger")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


def generate_booking_code():
    """Generate a unique human-friendly booking code, e.g., 'PV-4892'."""
    suffix = "".join(random.choices(string.digits, k=4))
    return f"PV-{suffix}"


# ---------------------------------------------------------
# FRONTEND TEMPLATE ROUTES
# ---------------------------------------------------------

@app.route("/")
def index():
    """Landing page with live preview and system highlights."""
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login with email and password."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html")

        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, full_name, email, password_hash FROM users WHERE email = %s",
                    (email,)
                )
                user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                session["user_email"] = user["email"]
                session["is_admin"] = False
                flash(f"Welcome back, {user['full_name']}!", "success")
                next_page = request.args.get("next")
                return redirect(next_page or url_for("dashboard"))
            else:
                flash("Invalid email or password. Please check your credentials.", "danger")
        except Exception as e:
            flash(f"Database error: {str(e)}", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration with secure password hashing."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip()
        vehicle_plate = request.form.get("vehicle_plate", "").strip().upper()
        vehicle_type = request.form.get("vehicle_type", "Car")
        vehicle_model = request.form.get("vehicle_model", "").strip()

        # Validation
        if not full_name or not email or not password:
            flash("Name, email, and password are required.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("register.html")

        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Check email existence
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    flash("An account with this email already exists.", "danger")
                    return render_template("register.html")

                # Insert user
                cursor.execute(
                    "INSERT INTO users (full_name, email, password_hash, phone) VALUES (%s, %s, %s, %s)",
                    (full_name, email, hashed_pw, phone or None)
                )
                user_id = cursor.lastrowid

                # Optional initial vehicle
                if vehicle_plate and vehicle_model:
                    cursor.execute(
                        "INSERT INTO vehicles (user_id, plate_number, vehicle_type, model, is_default) "
                        "VALUES (%s, %s, %s, %s, 1)",
                        (user_id, vehicle_plate, vehicle_type, vehicle_model)
                    )

                conn.commit()

            session["user_id"] = user_id
            session["user_name"] = full_name
            session["user_email"] = email
            session["is_admin"] = False
            flash("Account registered successfully! Welcome to ParkVoice AI.", "success")
            return redirect(url_for("dashboard"))
        except Exception as e:
            conn.rollback()
            flash(f"Registration failed: {str(e)}", "danger")
        finally:
            if 'conn' in locals() and conn and getattr(conn, 'open', False):
                conn.close()

    return render_template("register.html")


@app.route("/logout")
def logout():
    """User logout."""
    session.clear()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Interactive visual parking dashboard."""
    return render_template("dashboard.html", user_name=session.get("user_name"))


@app.route("/booking")
@login_required
def booking():
    """Booking management page."""
    return render_template("booking.html")


@app.route("/vehicles")
@login_required
def vehicles():
    """Vehicle management page."""
    return render_template("vehicles.html")


@app.route("/history")
@login_required
def history():
    """User parking history page."""
    return render_template("history.html")


# ---------------------------------------------------------
# ADMIN AUTHENTICATION & VIEWS
# ---------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin portal login."""
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter both username/email and password.", "danger")
            return render_template("admin_login.html")

        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, email, password_hash, role FROM admins "
                    "WHERE username = %s OR email = %s",
                    (username, username)
                )
                admin = cursor.fetchone()
            conn.close()

            if admin and check_password_hash(admin["password_hash"], password):
                session["admin_id"] = admin["id"]
                session["admin_username"] = admin["username"]
                session["admin_role"] = admin["role"]
                session["is_admin"] = True
                flash("Admin authenticated successfully.", "success")
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Invalid admin credentials.", "danger")
        except Exception as e:
            flash(f"Database error: {str(e)}", "danger")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Admin logout."""
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    session.pop("admin_role", None)
    session.pop("is_admin", None)
    flash("Admin session closed.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    """Admin dashboard with Live Simulation controls and analytics."""
    return render_template("admin.html", admin_user=session.get("admin_username"))


# ---------------------------------------------------------
# REST API: VEHICLES
# ---------------------------------------------------------

@app.route("/api/vehicles", methods=["GET"])
@login_required
def api_get_vehicles():
    """Retrieve all vehicles belonging to the logged-in user."""
    user_id = session["user_id"]
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, plate_number, vehicle_type, model, is_default, created_at "
                "FROM vehicles WHERE user_id = %s ORDER BY is_default DESC, id DESC",
                (user_id,)
            )
            vehicles = cursor.fetchall()
        conn.close()
        return jsonify({"success": True, "vehicles": vehicles})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/vehicles", methods=["POST"])
@login_required
def api_add_vehicle():
    """Add a new vehicle for the logged-in user."""
    user_id = session["user_id"]
    data = request.get_json() or {}
    plate_number = data.get("plate_number", "").strip().upper()
    vehicle_type = data.get("vehicle_type", "Car")
    model = data.get("model", "").strip()
    is_default = 1 if data.get("is_default") else 0

    if not plate_number or not model:
        return jsonify({"success": False, "error": "Plate number and vehicle model are required."}), 400

    if vehicle_type not in ("Car", "SUV", "Bike", "EV"):
        vehicle_type = "Car"

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check unique plate
            cursor.execute("SELECT id FROM vehicles WHERE plate_number = %s", (plate_number,))
            if cursor.fetchone():
                return jsonify({"success": False, "error": f"Plate number '{plate_number}' is already registered."}), 400

            # If marked default, remove default from user's other vehicles
            if is_default:
                cursor.execute("UPDATE vehicles SET is_default = 0 WHERE user_id = %s", (user_id,))
            else:
                # If this is their first vehicle, make it default automatically
                cursor.execute("SELECT COUNT(*) as count FROM vehicles WHERE user_id = %s", (user_id,))
                if cursor.fetchone()["count"] == 0:
                    is_default = 1

            cursor.execute(
                "INSERT INTO vehicles (user_id, plate_number, vehicle_type, model, is_default) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user_id, plate_number, vehicle_type, model, is_default)
            )
            new_id = cursor.lastrowid
            conn.commit()

        return jsonify({
            "success": True,
            "message": "Vehicle added successfully.",
            "vehicle": {
                "id": new_id,
                "plate_number": plate_number,
                "vehicle_type": vehicle_type,
                "model": model,
                "is_default": is_default
            }
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/vehicles/<int:vehicle_id>", methods=["PUT"])
@login_required
def api_update_vehicle(vehicle_id):
    """Update vehicle details or set as default."""
    user_id = session["user_id"]
    data = request.get_json() or {}

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM vehicles WHERE id = %s AND user_id = %s", (vehicle_id, user_id))
            if not cursor.fetchone():
                return jsonify({"success": False, "error": "Vehicle not found."}), 404

            if "is_default" in data and data["is_default"]:
                cursor.execute("UPDATE vehicles SET is_default = 0 WHERE user_id = %s", (user_id,))
                cursor.execute("UPDATE vehicles SET is_default = 1 WHERE id = %s", (vehicle_id,))

            if "model" in data and data["model"].strip():
                cursor.execute("UPDATE vehicles SET model = %s WHERE id = %s", (data["model"].strip(), vehicle_id))

            if "vehicle_type" in data and data["vehicle_type"] in ("Car", "SUV", "Bike", "EV"):
                cursor.execute("UPDATE vehicles SET vehicle_type = %s WHERE id = %s", (data["vehicle_type"], vehicle_id))

            conn.commit()

        return jsonify({"success": True, "message": "Vehicle updated successfully."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/vehicles/<int:vehicle_id>/set-default", methods=["POST"])
@login_required
def api_set_default_vehicle(vehicle_id):
    """Set the specified vehicle as default for active recommendation and route focus."""
    user_id = session["user_id"]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, vehicle_type, plate_number FROM vehicles WHERE id = %s AND user_id = %s", (vehicle_id, user_id))
            veh = cursor.fetchone()
            if not veh:
                return jsonify({"success": False, "error": "Vehicle not found."}), 404

            cursor.execute("UPDATE vehicles SET is_default = 0 WHERE user_id = %s", (user_id,))
            cursor.execute("UPDATE vehicles SET is_default = 1 WHERE id = %s AND user_id = %s", (vehicle_id, user_id))
            conn.commit()

        return jsonify({
            "success": True,
            "message": f"Active vehicle switched to {veh['plate_number']} ({veh['vehicle_type']}).",
            "vehicle": veh
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/vehicles/<int:vehicle_id>", methods=["DELETE"])
@login_required
def api_delete_vehicle(vehicle_id):
    """Delete a vehicle."""
    user_id = session["user_id"]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, is_default FROM vehicles WHERE id = %s AND user_id = %s", (vehicle_id, user_id))
            veh = cursor.fetchone()
            if not veh:
                return jsonify({"success": False, "error": "Vehicle not found."}), 404

            # Prevent deleting vehicle if linked to an active booking
            cursor.execute(
                "SELECT id FROM bookings WHERE vehicle_id = %s AND status = 'ACTIVE'",
                (vehicle_id,)
            )
            if cursor.fetchone():
                return jsonify({"success": False, "error": "Cannot delete vehicle with an active parking booking."}), 400

            cursor.execute("DELETE FROM vehicles WHERE id = %s", (vehicle_id,))

            # If default vehicle was deleted, promote another
            if veh["is_default"]:
                cursor.execute(
                    "UPDATE vehicles SET is_default = 1 WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                    (user_id,)
                )

            conn.commit()
        return jsonify({"success": True, "message": "Vehicle removed."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------
# REST API: PARKING SLOTS & A* RECOMMENDATION
# ---------------------------------------------------------

@app.route("/api/parking/slots", methods=["GET"])
def api_get_slots():
    """Retrieve all 12 parking slots with live status and metadata."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT s.id, s.slot_number, s.row_index, s.col_index, s.slot_type, "
                "       s.has_ev_charger, s.status, s.price_per_hour, "
                "       b.booking_code, b.user_id as booked_by_user_id, "
                "       u.full_name as booked_by_name, v.plate_number, v.vehicle_type "
                "FROM parking_slots s "
                "LEFT JOIN bookings b ON s.id = b.slot_id AND b.status = 'ACTIVE' "
                "LEFT JOIN users u ON b.user_id = u.id "
                "LEFT JOIN vehicles v ON b.vehicle_id = v.id "
                "ORDER BY s.slot_number ASC"
            )
            slots = cursor.fetchall()
        conn.close()

        # Format booleans/decimals
        for s in slots:
            s["has_ev_charger"] = bool(s["has_ev_charger"])
            s["price_per_hour"] = float(s["price_per_hour"])

        return jsonify({
            "success": True,
            "entrance": {
                "label": "ENTRANCE",
                "coordinates": list(astar.ENTRANCE_COORDINATES)
            },
            "slots": slots
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/parking/find-parking", methods=["POST"])
@login_required
def api_find_parking():
    """
    Run real A* search and intelligent recommendation for the user's vehicle.
    Returns:
        - Recommended slot
        - Real A* path coordinates from Entrance
        - Distance and estimated travel time
        - AI reasoning string
    """
    user_id = session["user_id"]
    data = request.get_json() or {}

    vehicle_id = data.get("vehicle_id")
    vehicle_type = data.get("vehicle_type")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Determine vehicle type (explicit vehicle_type takes precedence if specified, e.g. from voice)
            if not vehicle_type:
                if vehicle_id:
                    cursor.execute(
                        "SELECT vehicle_type, plate_number, model FROM vehicles WHERE id = %s AND user_id = %s",
                        (vehicle_id, user_id)
                    )
                    veh = cursor.fetchone()
                    if veh:
                        vehicle_type = veh["vehicle_type"]
                if not vehicle_type:
                    cursor.execute(
                        "SELECT vehicle_type, plate_number, model FROM vehicles WHERE user_id = %s ORDER BY is_default DESC LIMIT 1",
                        (user_id,)
                    )
                    veh = cursor.fetchone()
                    if veh:
                        vehicle_type = veh["vehicle_type"]
                    else:
                        vehicle_type = "Car"

            # Fetch live slots
            cursor.execute(
                "SELECT id, slot_number, row_index, col_index, slot_type, has_ev_charger, status, price_per_hour "
                "FROM parking_slots ORDER BY slot_number ASC"
            )
            slots = cursor.fetchall()

        conn.close()

        for s in slots:
            s["has_ev_charger"] = bool(s["has_ev_charger"])
            s["price_per_hour"] = float(s["price_per_hour"])

        # Execute A* recommendation engine
        recommendation = astar.recommend_best_slot(
            slots=slots,
            vehicle_type=vehicle_type or "Car"
        )

        return jsonify({
            "success": True,
            "vehicle_type": vehicle_type,
            "entrance": list(astar.ENTRANCE_COORDINATES),
            "recommendation": recommendation
        })

    except Exception as e:
        if 'conn' in locals() and conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/parking/path", methods=["POST"])
def api_get_path():
    """
    Calculate real A* path from Entrance (or specified start) to a target slot.
    Returns path, distance, and explored nodes.
    """
    data = request.get_json() or {}
    slot_number = data.get("slot_number")
    start = tuple(data.get("start", astar.ENTRANCE_COORDINATES))

    if not slot_number or slot_number not in astar.SLOT_COORDINATES:
        return jsonify({"success": False, "error": "Invalid or missing slot_number."}), 400

    goal = astar.SLOT_COORDINATES[slot_number]

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT row_index, col_index, status FROM parking_slots")
            slots = cursor.fetchall()
        conn.close()

        blocked_cells = {
            (s["row_index"], s["col_index"])
            for s in slots
            if s["status"] in ("OCCUPIED", "RESERVED")
        }

        result = astar.find_path(start, goal, blocked_cells)

        return jsonify({
            "success": result["success"],
            "slot_number": slot_number,
            "start": list(start),
            "goal": list(goal),
            "path": result["path"],
            "distance": result["distance"],
            "explored_nodes": result["explored_nodes"],
            "status": result["status"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------
# REST API: BOOKINGS & DOUBLE-BOOKING PREVENTION
# ---------------------------------------------------------

@app.route("/api/bookings/create", methods=["POST"])
@login_required
def api_create_booking():
    """
    Create a parking reservation atomically.
    Guarantees double-booking prevention via transaction locking and slot status re-check.
    """
    user_id = session["user_id"]
    data = request.get_json() or {}

    slot_id = data.get("slot_id")
    slot_number = data.get("slot_number")
    vehicle_id = data.get("vehicle_id")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verify or resolve vehicle first
            if not vehicle_id:
                cursor.execute(
                    "SELECT id FROM vehicles WHERE user_id = %s ORDER BY is_default DESC LIMIT 1",
                    (user_id,)
                )
                v_res = cursor.fetchone()
                if not v_res:
                    return jsonify({
                        "success": False,
                        "error": "Please add a vehicle to your garage before making a booking."
                    }), 400
                vehicle_id = v_res["id"]
            else:
                cursor.execute("SELECT id FROM vehicles WHERE id = %s AND user_id = %s", (vehicle_id, user_id))
                if not cursor.fetchone():
                    return jsonify({"success": False, "error": "Invalid vehicle specified."}), 400

            # 2. Prevent multiple active bookings FOR THIS VEHICLE
            # (Allows a user to hold active reservations for multiple vehicles simultaneously)
            cursor.execute(
                "SELECT id, booking_code, slot_id FROM bookings WHERE vehicle_id = %s AND status = 'ACTIVE'",
                (vehicle_id,)
            )
            existing_booking = cursor.fetchone()
            if existing_booking:
                return jsonify({
                    "success": False,
                    "error": f"This vehicle already has an active booking ({existing_booking['booking_code']}). "
                             f"Please complete or cancel it before booking another slot."
                }), 400

            # 3. ATOMIC DOUBLE-BOOKING PREVENTION
            # Acquire exclusive row lock using FOR UPDATE
            if slot_id:
                cursor.execute(
                    "SELECT id, slot_number, status, price_per_hour, row_index, col_index "
                    "FROM parking_slots WHERE id = %s FOR UPDATE",
                    (slot_id,)
                )
            elif slot_number:
                cursor.execute(
                    "SELECT id, slot_number, status, price_per_hour, row_index, col_index "
                    "FROM parking_slots WHERE slot_number = %s FOR UPDATE",
                    (slot_number,)
                )
            else:
                return jsonify({"success": False, "error": "Must specify slot_id or slot_number."}), 400

            slot = cursor.fetchone()

            if not slot:
                conn.rollback()
                return jsonify({"success": False, "error": "Parking slot not found."}), 404

            # Verify availability in database transaction
            if slot["status"] != "AVAILABLE":
                conn.rollback()
                return jsonify({
                    "success": False,
                    "error": f"Slot {slot['slot_number']} is currently {slot['status'].lower()}. "
                             f"Double-booking prevented. Please select another slot.",
                    "status_code": 409
                }), 409

            # 4. Mark slot RESERVED
            cursor.execute(
                "UPDATE parking_slots SET status = 'RESERVED' WHERE id = %s",
                (slot["id"],)
            )

            # 5. Insert Booking
            booking_code = generate_booking_code()
            price = float(slot["price_per_hour"])

            cursor.execute(
                "INSERT INTO bookings (booking_code, user_id, vehicle_id, slot_id, start_time, status, total_amount) "
                "VALUES (%s, %s, %s, %s, NOW(), 'ACTIVE', %s)",
                (booking_code, user_id, vehicle_id, slot["id"], price)
            )
            booking_id = cursor.lastrowid

            # Commit the atomic transaction
            conn.commit()

        # Calculate navigation route
        target_coords = (slot["row_index"], slot["col_index"])
        astar_res = astar.find_path(astar.ENTRANCE_COORDINATES, target_coords, set())

        return jsonify({
            "success": True,
            "message": f"Successfully reserved slot {slot['slot_number']}!",
            "booking": {
                "id": booking_id,
                "booking_code": booking_code,
                "slot_number": slot["slot_number"],
                "slot_id": slot["id"],
                "start_time": datetime.now().isoformat(),
                "status": "ACTIVE",
                "price_per_hour": price,
                "path": astar_res.get("path", []),
                "distance": astar_res.get("distance", 0)
            }
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


@app.route("/api/bookings/active", methods=["GET"])
@login_required
def api_get_active_booking():
    """Retrieve all active bookings for the current user (supporting multi-vehicle bookings)."""
    user_id = session["user_id"]
    req_vehicle_id = request.args.get("vehicle_id")
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT b.id, b.booking_code, b.start_time, b.status, b.total_amount, "
                "       s.id as slot_id, s.slot_number, s.row_index, s.col_index, s.price_per_hour, s.has_ev_charger, "
                "       v.id as vehicle_id, v.plate_number, v.vehicle_type, v.model "
                "FROM bookings b "
                "JOIN parking_slots s ON b.slot_id = s.id "
                "JOIN vehicles v ON b.vehicle_id = v.id "
                "WHERE b.user_id = %s AND b.status = 'ACTIVE' "
                "ORDER BY b.id DESC",
                (user_id,)
            )
            raw_bookings = cursor.fetchall()
        conn.close()

        formatted_bookings = []
        matching_booking = None

        for b in raw_bookings:
            item = dict(b)
            item["price_per_hour"] = float(item["price_per_hour"])
            item["has_ev_charger"] = bool(item["has_ev_charger"])
            item["start_time"] = item["start_time"].isoformat()

            # Compute A* route from entrance to active slot
            target_coords = (item["row_index"], item["col_index"])
            astar_res = astar.find_path(astar.ENTRANCE_COORDINATES, target_coords, set())
            item["path"] = astar_res.get("path", [])
            item["distance"] = astar_res.get("distance", 0)

            formatted_bookings.append(item)

            if req_vehicle_id and str(item["vehicle_id"]) == str(req_vehicle_id):
                matching_booking = item

        primary_booking = matching_booking or (formatted_bookings[0] if formatted_bookings else None)

        return jsonify({
            "success": True,
            "active_bookings": formatted_bookings,
            "active_booking": primary_booking
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/bookings/cancel", methods=["POST"])
@login_required
def api_cancel_booking():
    """Cancel active booking and return slot to AVAILABLE."""
    user_id = session["user_id"]
    data = request.get_json() or {}
    booking_id = data.get("booking_id")
    vehicle_id = data.get("vehicle_id")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if booking_id:
                cursor.execute(
                    "SELECT id, slot_id, booking_code, vehicle_id FROM bookings "
                    "WHERE id = %s AND user_id = %s AND status = 'ACTIVE' FOR UPDATE",
                    (booking_id, user_id)
                )
            elif vehicle_id:
                cursor.execute(
                    "SELECT id, slot_id, booking_code, vehicle_id FROM bookings "
                    "WHERE vehicle_id = %s AND user_id = %s AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1 FOR UPDATE",
                    (vehicle_id, user_id)
                )
            else:
                cursor.execute(
                    "SELECT id, slot_id, booking_code, vehicle_id FROM bookings "
                    "WHERE user_id = %s AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1 FOR UPDATE",
                    (user_id,)
                )
            booking = cursor.fetchone()

            if not booking:
                conn.rollback()
                return jsonify({"success": False, "error": "No active booking found to cancel."}), 404

            # Update booking status
            cursor.execute(
                "UPDATE bookings SET status = 'CANCELLED', end_time = NOW() WHERE id = %s",
                (booking["id"],)
            )

            # Re-release slot to AVAILABLE
            cursor.execute(
                "UPDATE parking_slots SET status = 'AVAILABLE' WHERE id = %s",
                (booking["slot_id"],)
            )

            conn.commit()

        return jsonify({
            "success": True,
            "message": f"Booking {booking['booking_code']} cancelled. Parking slot is now free."
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


@app.route("/api/bookings/release", methods=["POST"])
@login_required
def api_release_booking():
    """Complete an active parking session (simulate car departure)."""
    user_id = session["user_id"]
    data = request.get_json() or {}
    booking_id = data.get("booking_id")
    vehicle_id = data.get("vehicle_id")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if booking_id:
                cursor.execute(
                    "SELECT id, slot_id, vehicle_id, start_time, total_amount, booking_code "
                    "FROM bookings WHERE id = %s AND user_id = %s AND status = 'ACTIVE' FOR UPDATE",
                    (booking_id, user_id)
                )
            elif vehicle_id:
                cursor.execute(
                    "SELECT id, slot_id, vehicle_id, start_time, total_amount, booking_code "
                    "FROM bookings WHERE vehicle_id = %s AND user_id = %s AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1 FOR UPDATE",
                    (vehicle_id, user_id)
                )
            else:
                cursor.execute(
                    "SELECT id, slot_id, vehicle_id, start_time, total_amount, booking_code "
                    "FROM bookings WHERE user_id = %s AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1 FOR UPDATE",
                    (user_id,)
                )
            booking = cursor.fetchone()

            if not booking:
                conn.rollback()
                return jsonify({"success": False, "error": "No active booking found to release."}), 404

            # Calculate duration and fee
            check_in = booking["start_time"]
            check_out = datetime.now()
            duration_minutes = max(1, int((check_out - check_in).total_seconds() / 60))
            hours = max(1.0, duration_minutes / 60.0)
            fee = round(hours * float(booking["total_amount"]), 2)

            # Mark booking COMPLETED
            cursor.execute(
                "UPDATE bookings SET status = 'COMPLETED', end_time = NOW(), total_amount = %s WHERE id = %s",
                (fee, booking["id"])
            )

            # Return slot to AVAILABLE
            cursor.execute(
                "UPDATE parking_slots SET status = 'AVAILABLE' WHERE id = %s",
                (booking["slot_id"],)
            )

            # Record in parking_history
            cursor.execute(
                "INSERT INTO parking_history (booking_id, user_id, vehicle_id, slot_id, check_in, check_out, duration_minutes, fee_paid, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'COMPLETED')",
                (booking["id"], user_id, booking["vehicle_id"], booking["slot_id"], check_in, check_out, duration_minutes, fee)
            )

            conn.commit()

        return jsonify({
            "success": True,
            "message": f"Parking session completed for {booking['booking_code']}. Duration: {duration_minutes} min, Fee: ${fee:.2f}.",
            "duration_minutes": duration_minutes,
            "fee_paid": fee
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


# ---------------------------------------------------------
# REST API: PARKING HISTORY & FILTERS
# ---------------------------------------------------------

@app.route("/api/history", methods=["GET"])
@login_required
def api_get_history():
    """
    Retrieve parking history with date filter (today, week, month, all).
    """
    user_id = session["user_id"]
    time_filter = request.args.get("filter", "all").lower()

    date_condition = ""
    if time_filter == "today":
        date_condition = "AND b.created_at >= CURDATE()"
    elif time_filter == "week":
        date_condition = "AND b.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
    elif time_filter == "month":
        date_condition = "AND b.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"

    query = f"""
        SELECT b.id, b.booking_code, b.start_time, b.end_time, b.status, b.total_amount, b.created_at,
               s.slot_number, s.slot_type, s.has_ev_charger,
               v.plate_number, v.vehicle_type, v.model,
               h.duration_minutes, h.fee_paid
        FROM bookings b
        JOIN parking_slots s ON b.slot_id = s.id
        JOIN vehicles v ON b.vehicle_id = v.id
        LEFT JOIN parking_history h ON b.id = h.booking_id
        WHERE b.user_id = %s {date_condition}
        ORDER BY b.id DESC
    """

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, (user_id,))
            records = cursor.fetchall()
        conn.close()

        for r in records:
            r["has_ev_charger"] = bool(r["has_ev_charger"])
            r["total_amount"] = float(r["total_amount"])
            r["start_time"] = r["start_time"].strftime("%Y-%m-%d %H:%M") if r["start_time"] else None
            r["end_time"] = r["end_time"].strftime("%Y-%m-%d %H:%M") if r["end_time"] else None
            r["fee_paid"] = float(r["fee_paid"]) if r.get("fee_paid") is not None else r["total_amount"]

        return jsonify({"success": True, "history": records, "filter": time_filter})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------
# REST API: ADMIN & LIVE SIMULATION MODE
# ---------------------------------------------------------

@app.route("/api/admin/stats", methods=["GET"])
@admin_required
def api_admin_stats():
    """Retrieve parking lot operational metrics and live counts."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "  COUNT(*) as total_slots, "
                "  SUM(CASE WHEN status = 'AVAILABLE' THEN 1 ELSE 0 END) as available_slots, "
                "  SUM(CASE WHEN status = 'OCCUPIED' THEN 1 ELSE 0 END) as occupied_slots, "
                "  SUM(CASE WHEN status = 'RESERVED' THEN 1 ELSE 0 END) as reserved_slots "
                "FROM parking_slots"
            )
            slot_stats = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) as total_users FROM users")
            user_count = cursor.fetchone()["total_users"]

            cursor.execute(
                "SELECT COUNT(*) as today_bookings FROM bookings WHERE created_at >= CURDATE()"
            )
            today_bookings = cursor.fetchone()["today_bookings"]

            cursor.execute(
                "SELECT COUNT(*) as active_bookings FROM bookings WHERE status = 'ACTIVE'"
            )
            active_bookings = cursor.fetchone()["active_bookings"]

        conn.close()

        return jsonify({
            "success": True,
            "stats": {
                "total_slots": slot_stats["total_slots"] or 12,
                "available": slot_stats["available_slots"] or 0,
                "occupied": slot_stats["occupied_slots"] or 0,
                "reserved": slot_stats["reserved_slots"] or 0,
                "total_users": user_count,
                "today_bookings": today_bookings,
                "active_bookings": active_bookings
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/simulate/entry", methods=["POST"])
@admin_required
def api_simulate_entry():
    """
    Live Simulation: simulate a vehicle arriving and occupying an available slot.
    """
    data = request.get_json() or {}
    slot_number = data.get("slot_number")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if slot_number:
                cursor.execute(
                    "SELECT id, slot_number, status FROM parking_slots WHERE slot_number = %s FOR UPDATE",
                    (slot_number,)
                )
            else:
                cursor.execute(
                    "SELECT id, slot_number, status FROM parking_slots WHERE status = 'AVAILABLE' "
                    "ORDER BY slot_number ASC LIMIT 1 FOR UPDATE"
                )
            slot = cursor.fetchone()

            if not slot:
                conn.rollback()
                return jsonify({"success": False, "error": "No available slots found to simulate entry."}), 400

            cursor.execute(
                "UPDATE parking_slots SET status = 'OCCUPIED' WHERE id = %s",
                (slot["id"],)
            )
            conn.commit()

        return jsonify({
            "success": True,
            "message": f"LIVE SIMULATION: Car entered and parked at slot {slot['slot_number']}.",
            "slot_number": slot["slot_number"],
            "new_status": "OCCUPIED"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


@app.route("/api/admin/simulate/exit", methods=["POST"])
@admin_required
def api_simulate_exit():
    """
    Live Simulation: simulate a vehicle leaving, turning slot back to AVAILABLE.
    """
    data = request.get_json() or {}
    slot_number = data.get("slot_number")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if slot_number:
                cursor.execute(
                    "SELECT id, slot_number, status FROM parking_slots WHERE slot_number = %s FOR UPDATE",
                    (slot_number,)
                )
            else:
                cursor.execute(
                    "SELECT id, slot_number, status FROM parking_slots WHERE status IN ('OCCUPIED', 'RESERVED') "
                    "ORDER BY slot_number DESC LIMIT 1 FOR UPDATE"
                )
            slot = cursor.fetchone()

            if not slot:
                conn.rollback()
                return jsonify({"success": False, "error": "No occupied or reserved slots found to simulate exit."}), 400

            # Complete any associated active booking
            cursor.execute(
                "UPDATE bookings SET status = 'COMPLETED', end_time = NOW() WHERE slot_id = %s AND status = 'ACTIVE'",
                (slot["id"],)
            )

            # Set slot back to AVAILABLE
            cursor.execute(
                "UPDATE parking_slots SET status = 'AVAILABLE' WHERE id = %s",
                (slot["id"],)
            )
            conn.commit()

        return jsonify({
            "success": True,
            "message": f"LIVE SIMULATION: Car departed from slot {slot['slot_number']}. Slot is now AVAILABLE.",
            "slot_number": slot["slot_number"],
            "new_status": "AVAILABLE"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


@app.route("/api/admin/simulate/toggle-slot", methods=["POST"])
@admin_required
def api_admin_toggle_slot():
    """Directly toggle a slot's status (AVAILABLE <-> OCCUPIED <-> RESERVED)."""
    data = request.get_json() or {}
    slot_number = data.get("slot_number")
    target_status = data.get("status", "").upper()

    if target_status not in ("AVAILABLE", "OCCUPIED", "RESERVED"):
        return jsonify({"success": False, "error": "Invalid status."}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM parking_slots WHERE slot_number = %s", (slot_number,))
            slot = cursor.fetchone()
            if not slot:
                return jsonify({"success": False, "error": "Slot not found."}), 404

            cursor.execute(
                "UPDATE parking_slots SET status = %s WHERE id = %s",
                (target_status, slot["id"])
            )
            if target_status == "AVAILABLE":
                cursor.execute(
                    "UPDATE bookings SET status = 'COMPLETED', end_time = NOW() WHERE slot_id = %s AND status = 'ACTIVE'",
                    (slot["id"],)
                )
            conn.commit()

        return jsonify({
            "success": True,
            "message": f"Slot {slot_number} status set to {target_status}.",
            "slot_number": slot_number,
            "new_status": target_status
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


@app.route("/api/admin/simulate/reset", methods=["POST"])
@admin_required
def api_admin_reset():
    """Reset all 12 parking slots to AVAILABLE and complete any active bookings."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE bookings SET status = 'COMPLETED', end_time = NOW() WHERE status = 'ACTIVE'")
            cursor.execute("UPDATE parking_slots SET status = 'AVAILABLE'")
            conn.commit()
        return jsonify({"success": True, "message": "All slots reset to AVAILABLE."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


@app.route("/api/admin/simulate/generate-booking", methods=["POST"])
@admin_required
def api_admin_generate_booking():
    """Simulation helper: Automatically generates a demo booking for a random available slot."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, slot_number, price_per_hour FROM parking_slots WHERE status = 'AVAILABLE' ORDER BY RAND() LIMIT 1 FOR UPDATE"
            )
            slot = cursor.fetchone()
            if not slot:
                conn.rollback()
                return jsonify({"success": False, "error": "No available slots to generate a booking."}), 400

            cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            u = cursor.fetchone()
            user_id = u["id"] if u else 1

            cursor.execute("SELECT id FROM vehicles WHERE user_id = %s LIMIT 1", (user_id,))
            v = cursor.fetchone()
            veh_id = v["id"] if v else 1

            booking_code = generate_booking_code()
            cursor.execute(
                "UPDATE parking_slots SET status = 'RESERVED' WHERE id = %s",
                (slot["id"],)
            )
            cursor.execute(
                "INSERT INTO bookings (booking_code, user_id, vehicle_id, slot_id, start_time, status, total_amount) "
                "VALUES (%s, %s, %s, %s, NOW(), 'ACTIVE', %s)",
                (booking_code, user_id, veh_id, slot["id"], float(slot["price_per_hour"]))
            )
            conn.commit()

        return jsonify({
            "success": True,
            "message": f"Generated simulated booking {booking_code} on slot {slot['slot_number']}.",
            "slot_number": slot["slot_number"],
            "booking_code": booking_code
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn and getattr(conn, 'open', False):
            conn.close()


@app.route("/api/admin/analytics", methods=["GET"])
@admin_required
def api_admin_analytics():
    """Provide structured analytics data for Chart.js dashboards."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 1. Slot usage frequency
            cursor.execute(
                "SELECT s.slot_number, COUNT(b.id) as booking_count "
                "FROM parking_slots s "
                "LEFT JOIN bookings b ON s.id = b.slot_id "
                "GROUP BY s.slot_number ORDER BY s.slot_number ASC"
            )
            slot_usage = cursor.fetchall()

            # 2. Daily bookings over past 7 days
            cursor.execute(
                "SELECT DATE(created_at) as date_val, COUNT(*) as count "
                "FROM bookings "
                "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY) "
                "GROUP BY DATE(created_at) ORDER BY date_val ASC"
            )
            daily_data = cursor.fetchall()

            # 3. Peak hours distribution
            cursor.execute(
                "SELECT HOUR(start_time) as hour_val, COUNT(*) as count "
                "FROM bookings "
                "GROUP BY HOUR(start_time) ORDER BY hour_val ASC"
            )
            hourly_data = cursor.fetchall()

            # 4. Cancellation rate
            cursor.execute(
                "SELECT "
                "  COUNT(*) as total, "
                "  SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled, "
                "  SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed, "
                "  SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) as active "
                "FROM bookings"
            )
            cancellation_stats = cursor.fetchone()

        conn.close()

        # Format 7 days timeline
        today = datetime.now().date()
        daily_labels = [(today - timedelta(days=i)).strftime("%b %d") for i in range(6, -1, -1)]
        daily_map = {r["date_val"].strftime("%b %d"): r["count"] for r in daily_data if r["date_val"]}
        daily_counts = [daily_map.get(label, 0) for label in daily_labels]

        # Format 24 hours timeline (focus on 8 AM to 8 PM)
        peak_hours_labels = [f"{h:02d}:00" for h in range(8, 21)]
        hourly_map = {r["hour_val"]: r["count"] for r in hourly_data}
        peak_hours_counts = [hourly_map.get(h, 0) for h in range(8, 21)]

        total_b = cancellation_stats["total"] or 0
        canc_b = cancellation_stats["cancelled"] or 0
        canc_rate = round((canc_b / total_b) * 100, 1) if total_b > 0 else 0.0

        return jsonify({
            "success": True,
            "slot_usage": {
                "labels": [s["slot_number"] for s in slot_usage],
                "counts": [s["booking_count"] for s in slot_usage]
            },
            "daily_trend": {
                "labels": daily_labels,
                "counts": daily_counts
            },
            "peak_hours": {
                "labels": peak_hours_labels,
                "counts": peak_hours_counts
            },
            "cancellation_rate": canc_rate,
            "status_summary": {
                "total": total_b,
                "cancelled": canc_b,
                "completed": cancellation_stats["completed"] or 0,
                "active": cancellation_stats["active"] or 0
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------
# APPLICATION ENTRYPOINT
# ---------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n=======================================================")
    print(f"   PARKVOICE AI - Smart Parking & Navigation System   ")
    print(f"=======================================================")
    print(f" Server running at: http://127.0.0.1:{port}")
    print(f" User Login:        http://127.0.0.1:{port}/login")
    print(f" Admin Portal:      http://127.0.0.1:{port}/admin/login")
    print(f" Default Admin:     admin / Admin@123")
    print(f" Demo User:         demo@parkvoice.ai / User@123")
    print(f"=======================================================\n")
    app.run(host="0.0.0.0", port=port, debug=True)
