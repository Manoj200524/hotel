import os
import csv
import io
import hashlib
import secrets
from datetime import datetime, date

from flask import Flask, request, jsonify, session, Response
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "hotel-secret-key-change-me")

CORS(
    app,
    origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5501"
    ],
    supports_credentials=True
)

# ==================================================
# DATABASE
# ==================================================

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3307")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", "manoj2005@123"),
        database=os.getenv("MYSQL_DATABASE", "hotel_management")
    )


def password_hash(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000
    ).hex()
    return salt + ":" + hashed


def password_verify(password, stored):
    if not stored:
        return False

    if ":" not in stored:
        return password == stored

    salt, hashed = stored.split(":", 1)

    calculated = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000
    ).hex()

    return calculated == hashed


def db_execute(sql, params=(), fetch=False):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(sql, params)

        result = cursor.fetchall() if fetch else None
        conn.commit()

        return result

    finally:
        cursor.close()
        conn.close()


def db_insert(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.lastrowid

    finally:
        cursor.close()
        conn.close()


# ==================================================
# INITIALIZE DATABASE
# ==================================================

def initialize_database():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room_number VARCHAR(30) UNIQUE NOT NULL,
            type VARCHAR(100) NOT NULL,
            price DECIMAL(10,2) NOT NULL,
            status VARCHAR(30) DEFAULT 'Available'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            phone VARCHAR(30) NOT NULL,
            email VARCHAR(150),
            room_id INT,
            room_type VARCHAR(100),
            check_in DATE NOT NULL,
            check_out DATE NOT NULL,
            status VARCHAR(30) DEFAULT 'Booked',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            phone VARCHAR(30) NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            phone VARCHAR(30),
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(30) DEFAULT 'staff'
        )
    """)

    # ADD MISSING COLUMNS TO OLD TABLES

    migrations = {
        "rooms": {
            "room_number": "VARCHAR(30)",
            "type": "VARCHAR(100)",
            "price": "DECIMAL(10,2)",
            "status": "VARCHAR(30) DEFAULT 'Available'"
        },
        "bookings": {
            "name": "VARCHAR(150)",
            "phone": "VARCHAR(30)",
            "email": "VARCHAR(150)",
            "room_id": "INT",
            "room_type": "VARCHAR(100)",
            "check_in": "DATE",
            "check_out": "DATE",
            "status": "VARCHAR(30) DEFAULT 'Booked'",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        },
        "customers": {
            "name": "VARCHAR(150)",
            "phone": "VARCHAR(30)",
            "email": "VARCHAR(150)",
            "password": "VARCHAR(255)"
        },
        "staff": {
            "name": "VARCHAR(150)",
            "phone": "VARCHAR(30)",
            "username": "VARCHAR(100)",
            "password": "VARCHAR(255)",
            "role": "VARCHAR(30) DEFAULT 'staff'"
        }
    }

    for table, columns in migrations.items():

        cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        current_columns = {
            row[0] for row in cursor.fetchall()
        }

        for column, definition in columns.items():

            if column not in current_columns:

                cursor.execute(
                    f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}"
                )

    conn.commit()

    # INSERT ROOMS ONLY IF EMPTY

    cursor.execute("SELECT COUNT(*) FROM rooms")
    count = cursor.fetchone()[0]

    if count == 0:

        rooms = [
            ("101", "Single", 1500),
            ("102", "Single", 1500),
            ("201", "Double", 2500),
            ("202", "Double", 2500),
            ("301", "Deluxe", 4000),
            ("302", "Deluxe", 4000)
        ]

        cursor.executemany("""
            INSERT INTO rooms (room_number, type, price, status)
            VALUES (%s, %s, %s, 'Available')
        """, rooms)

    # CREATE ADMIN IF NOT EXISTS

    cursor.execute("""
        SELECT id FROM staff WHERE username = 'admin'
    """)

    if not cursor.fetchone():

        cursor.execute("""
            INSERT INTO staff (name, phone, username, password, role)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "Admin",
            "0000000000",
            "admin",
            password_hash("Admin@12345"),
            "admin"
        ))

    conn.commit()
    cursor.close()
    conn.close()

    print("Database initialized successfully!")


# ==================================================
# HOME
# ==================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "message": "Hotel Management System Backend is Running",
        "status": "success"
    })


@app.route("/api", methods=["GET"])
def api_home():

    return jsonify({
        "message": "Hotel Management System API is Running"
    })


@app.route("/api/db-test", methods=["GET"])
def db_test():

    try:
        conn = get_connection()
        conn.close()

        return jsonify({
            "message": "MySQL connected successfully"
        }), 200

    except Exception as e:

        return jsonify({
            "message": "MySQL connection failed",
            "error": str(e)
        }), 500


# ==================================================
# ROOMS
# ==================================================

@app.route("/api/rooms", methods=["GET"])
def get_rooms():

    try:

        rooms = db_execute(
            "SELECT * FROM rooms ORDER BY room_number",
            fetch=True
        )

        return jsonify(rooms), 200

    except Exception as e:

        return jsonify({
            "message": "Room loading failed",
            "error": str(e)
        }), 500


@app.route("/api/available-rooms", methods=["GET"])
def get_available_rooms():

    check_in = request.args.get("check_in")
    check_out = request.args.get("check_out")

    if not check_in or not check_out:

        return jsonify({
            "message": "Enter check-in and check-out dates"
        }), 400

    try:

        start = datetime.strptime(check_in, "%Y-%m-%d").date()
        end = datetime.strptime(check_out, "%Y-%m-%d").date()

        if end <= start:

            return jsonify({
                "message": "Check-out must be after check-in"
            }), 400

        rooms = db_execute("""
            SELECT r.*
            FROM rooms r
            WHERE r.id NOT IN (
                SELECT b.room_id
                FROM bookings b
                WHERE b.status NOT IN ('Cancelled', 'Canceled')
                AND b.check_in < %s
                AND b.check_out > %s
            )
            ORDER BY r.room_number
        """, (end, start), fetch=True)

        return jsonify(rooms), 200

    except Exception as e:

        return jsonify({
            "message": "Failed to check rooms",
            "error": str(e)
        }), 500


# ==================================================
# BOOKING
# ==================================================

@app.route("/api/bookings", methods=["POST"])
def create_booking():

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    email = str(data.get("email", "")).strip()
    room_type = str(data.get("room_type", "")).strip()
    check_in = str(data.get("check_in", "")).strip()
    check_out = str(data.get("check_out", "")).strip()

    if not all([name, phone, room_type, check_in, check_out]):

        return jsonify({
            "message": "Please fill all required details"
        }), 400

    try:

        start = datetime.strptime(check_in, "%Y-%m-%d").date()
        end = datetime.strptime(check_out, "%Y-%m-%d").date()

        if start < date.today():

            return jsonify({
                "message": "Check-in date cannot be in the past"
            }), 400

        if end <= start:

            return jsonify({
                "message": "Check-out must be after check-in"
            }), 400

    except ValueError:

        return jsonify({
            "message": "Invalid date format"
        }), 400

    conn = None
    cursor = None

    try:

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT r.*
            FROM rooms r
            WHERE r.type = %s
            AND r.id NOT IN (
                SELECT b.room_id
                FROM bookings b
                WHERE b.status NOT IN ('Cancelled', 'Canceled')
                AND b.check_in < %s
                AND b.check_out > %s
            )
            ORDER BY r.room_number
            LIMIT 1
        """, (room_type, end, start))

        room = cursor.fetchone()

        if not room:

            return jsonify({
                "message": "No room available for these dates"
            }), 400

        cursor.execute("""
            INSERT INTO bookings (
                name, phone, email, room_id,
                room_type, check_in, check_out, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            name,
            phone,
            email,
            room["id"],
            room["type"],
            start,
            end,
            "Booked"
        ))

        booking_id = cursor.lastrowid
        conn.commit()

        return jsonify({
            "message": "Booking successful",
            "booking_id": booking_id,
            "room_number": room["room_number"]
        }), 201

    except Exception as e:

        if conn:
            conn.rollback()

        return jsonify({
            "message": "Booking failed",
            "error": str(e)
        }), 500

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# ==================================================
# BOOKING HISTORY
# ==================================================

@app.route("/api/history", methods=["GET"])
def history():

    phone = request.args.get("phone", "").strip()

    if not phone:

        return jsonify({
            "message": "Phone number required"
        }), 400

    try:

        bookings = db_execute("""
            SELECT b.*, r.room_number, r.price
            FROM bookings b
            LEFT JOIN rooms r ON b.room_id = r.id
            WHERE b.phone = %s
            ORDER BY b.id DESC
        """, (phone,), fetch=True)

        return jsonify(bookings), 200

    except Exception as e:

        return jsonify({
            "message": "History loading failed",
            "error": str(e)
        }), 500


# ==================================================
# STAFF / ADMIN AUTH
# ==================================================

@app.route("/api/staff/login", methods=["POST"])
def staff_login():

    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not username or not password:

        return jsonify({
            "message": "Username and password required"
        }), 400

    try:

        staff_list = db_execute("""
            SELECT * FROM staff WHERE username = %s
        """, (username,), fetch=True)

        if not staff_list:

            return jsonify({
                "message": "Invalid username or password"
            }), 401

        staff = staff_list[0]

        if not password_verify(password, staff["password"]):

            return jsonify({
                "message": "Invalid username or password"
            }), 401

        # Convert legacy plain password to hash
        if ":" not in staff["password"]:

            db_execute("""
                UPDATE staff SET password = %s
                WHERE id = %s
            """, (password_hash(password), staff["id"]))

        session["staff_id"] = staff["id"]
        session["staff_role"] = staff["role"]
        session["staff_username"] = staff["username"]

        return jsonify({
            "message": "Login successful",
            "staff": {
                "id": staff["id"],
                "name": staff["name"],
                "username": staff["username"],
                "role": staff["role"]
            }
        }), 200

    except Exception as e:

        return jsonify({
            "message": "Login failed",
            "error": str(e)
        }), 500


@app.route("/api/staff/logout", methods=["POST"])
def staff_logout():

    session.clear()

    return jsonify({
        "message": "Logout successful"
    }), 200


@app.route("/api/staff/me", methods=["GET"])
def staff_me():

    if "staff_id" not in session:

        return jsonify({
            "logged_in": False
        }), 200

    return jsonify({
        "logged_in": True,
        "id": session["staff_id"],
        "username": session["staff_username"],
        "role": session["staff_role"]
    }), 200


# ==================================================
# ALL BOOKINGS (STAFF)
# ==================================================

@app.route("/api/bookings", methods=["GET"])
def get_bookings():

    if "staff_id" not in session:

        return jsonify({
            "message": "Login required"
        }), 401

    try:

        bookings = db_execute("""
            SELECT b.*, r.room_number, r.price
            FROM bookings b
            LEFT JOIN rooms r ON b.room_id = r.id
            ORDER BY b.id DESC
        """, fetch=True)

        return jsonify(bookings), 200

    except Exception as e:

        return jsonify({
            "message": "Failed to load bookings",
            "error": str(e)
        }), 500


# ==================================================
# UPDATE BOOKING
# ==================================================

@app.route("/api/bookings/<int:booking_id>", methods=["PUT"])
def update_booking(booking_id):

    if "staff_id" not in session:

        return jsonify({
            "message": "Login required"
        }), 401

    data = request.get_json(silent=True) or {}
    status = data.get("status")

    allowed = [
        "Booked",
        "Confirmed",
        "Checked In",
        "Checked Out",
        "Cancelled"
    ]

    if status not in allowed:

        return jsonify({
            "message": "Invalid status"
        }), 400

    try:

        db_execute("""
            UPDATE bookings SET status = %s
            WHERE id = %s
        """, (status, booking_id))

        return jsonify({
            "message": "Booking updated"
        }), 200

    except Exception as e:

        return jsonify({
            "message": "Update failed",
            "error": str(e)
        }), 500


# ==================================================
# DELETE BOOKING
# ==================================================

@app.route("/api/bookings/<int:booking_id>", methods=["DELETE"])
def delete_booking(booking_id):

    if "staff_id" not in session:

        return jsonify({
            "message": "Login required"
        }), 401

    try:

        db_execute("""
            DELETE FROM bookings WHERE id = %s
        """, (booking_id,))

        return jsonify({
            "message": "Booking deleted"
        }), 200

    except Exception as e:

        return jsonify({
            "message": "Delete failed",
            "error": str(e)
        }), 500


# ==================================================
# CUSTOMER REGISTER
# ==================================================

@app.route("/api/customer/register", methods=["POST"])
def customer_register():

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not name or not phone or not email or not password:

        return jsonify({
            "message": "All fields required"
        }), 400

    try:

        db_insert("""
            INSERT INTO customers (name, phone, email, password)
            VALUES (%s, %s, %s, %s)
        """, (name, phone, email, password_hash(password)))

        return jsonify({
            "message": "Registration successful"
        }), 201

    except Error as e:

        if e.errno == 1062:

            return jsonify({
                "message": "Email already exists"
            }), 400

        return jsonify({
            "message": "Registration failed",
            "error": str(e)
        }), 500


# ==================================================
# CUSTOMER LOGIN
# ==================================================

@app.route("/api/customer/login", methods=["POST"])
def customer_login():

    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or not password:

        return jsonify({
            "message": "Email and password required"
        }), 400

    try:

        customers = db_execute("""
            SELECT * FROM customers WHERE email = %s
        """, (email,), fetch=True)

        if not customers or not password_verify(
            password, customers[0]["password"]
        ):

            return jsonify({
                "message": "Invalid email or password"
            }), 401

        customer = customers[0]

        session["customer_id"] = customer["id"]

        return jsonify({
            "message": "Login successful",
            "customer": {
                "id": customer["id"],
                "name": customer["name"],
                "phone": customer["phone"],
                "email": customer["email"]
            }
        }), 200

    except Exception as e:

        return jsonify({
            "message": "Customer login failed",
            "error": str(e)
        }), 500


@app.route("/api/customer/logout", methods=["POST"])
def customer_logout():

    session.pop("customer_id", None)

    return jsonify({
        "message": "Logout successful"
    }), 200


# ==================================================
# CUSTOMER BOOKINGS
# ==================================================

@app.route("/api/customer/bookings", methods=["GET"])
def customer_bookings():

    if "customer_id" not in session:

        return jsonify({
            "message": "Customer login required"
        }), 401

    try:

        customer = db_execute("""
            SELECT email FROM customers WHERE id = %s
        """, (session["customer_id"],), fetch=True)

        if not customer:

            return jsonify({
                "message": "Customer not found"
            }), 404

        bookings = db_execute("""
            SELECT b.*, r.room_number, r.price
            FROM bookings b
            LEFT JOIN rooms r ON b.room_id = r.id
            WHERE b.email = %s
            ORDER BY b.id DESC
        """, (customer[0]["email"],), fetch=True)

        return jsonify(bookings), 200

    except Exception as e:

        return jsonify({
            "message": "Failed to load bookings",
            "error": str(e)
        }), 500


# ==================================================
# DASHBOARD
# ==================================================

@app.route("/api/stats", methods=["GET"])
def stats():

    if "staff_id" not in session:

        return jsonify({
            "message": "Login required"
        }), 401

    try:

        bookings = db_execute(
            "SELECT COUNT(*) AS total FROM bookings",
            fetch=True
        )

        rooms = db_execute(
            "SELECT COUNT(*) AS total FROM rooms",
            fetch=True
        )

        customers = db_execute(
            "SELECT COUNT(*) AS total FROM customers",
            fetch=True
        )

        active = db_execute("""
            SELECT COUNT(*) AS total FROM bookings
            WHERE status NOT IN ('Cancelled', 'Canceled', 'Checked Out')
        """, fetch=True)

        return jsonify({
            "total_bookings": bookings[0]["total"],
            "total_rooms": rooms[0]["total"],
            "total_customers": customers[0]["total"],
            "active_bookings": active[0]["total"]
        }), 200

    except Exception as e:

        return jsonify({
            "message": "Stats error",
            "error": str(e)
        }), 500


# ==================================================
# ADD ROOM - ADMIN
# ==================================================

@app.route("/api/rooms", methods=["POST"])
def add_room():

    if session.get("staff_role") != "admin":

        return jsonify({
            "message": "Admin access required"
        }), 403

    data = request.get_json(silent=True) or {}

    number = str(data.get("room_number", "")).strip()
    room_type = str(data.get("type", data.get("room_type", ""))).strip()
    price = data.get("price")

    if not number or not room_type or price is None:

        return jsonify({
            "message": "All fields required"
        }), 400

    try:

        price = float(price)

        if price <= 0:

            return jsonify({
                "message": "Price must be positive"
            }), 400

        db_insert("""
            INSERT INTO rooms (room_number, type, price, status)
            VALUES (%s, %s, %s, 'Available')
        """, (number, room_type, price))

        return jsonify({
            "message": "Room added successfully"
        }), 201

    except Error as e:

        if e.errno == 1062:

            return jsonify({
                "message": "Room number already exists"
            }), 400

        return jsonify({
            "message": "Room add failed",
            "error": str(e)
        }), 500


# ==================================================
# DELETE ROOM - ADMIN
# ==================================================

@app.route("/api/rooms/<int:room_id>", methods=["DELETE"])
def remove_room(room_id):

    if session.get("staff_role") != "admin":

        return jsonify({
            "message": "Admin access required"
        }), 403

    try:

        bookings = db_execute("""
            SELECT COUNT(*) AS total FROM bookings
            WHERE room_id = %s
        """, (room_id,), fetch=True)

        if bookings[0]["total"] > 0:

            return jsonify({
                "message": "Room has booking history and cannot be deleted"
            }), 400

        db_execute(
            "DELETE FROM rooms WHERE id = %s",
            (room_id,)
        )

        return jsonify({
            "message": "Room deleted successfully"
        }), 200

    except Exception as e:

        return jsonify({
            "message": "Room deletion failed",
            "error": str(e)
        }), 500


# ==================================================
# STAFF LIST - ADMIN
# ==================================================

@app.route("/api/staff", methods=["GET"])
def staff_list():

    if session.get("staff_role") != "admin":

        return jsonify({
            "message": "Admin access required"
        }), 403

    try:

        staff = db_execute("""
            SELECT id, name, phone, username, role
            FROM staff ORDER BY id
        """, fetch=True)

        return jsonify(staff), 200

    except Exception as e:

        return jsonify({
            "message": "Staff loading failed",
            "error": str(e)
        }), 500


# ==================================================
# ADD STAFF - ADMIN
# ==================================================

@app.route("/api/staff", methods=["POST"])
def staff_add():

    if session.get("staff_role") != "admin":

        return jsonify({
            "message": "Admin access required"
        }), 403

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = str(data.get("role", "staff")).lower().strip()

    if not name or not username or not password:

        return jsonify({
            "message": "Name, username and password required"
        }), 400

    if role not in ["staff", "admin"]:

        return jsonify({
            "message": "Invalid role"
        }), 400

    try:

        db_insert("""
            INSERT INTO staff (name, phone, username, password, role)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, phone, username, password_hash(password), role))

        return jsonify({
            "message": "Staff added successfully"
        }), 201

    except Error as e:

        if e.errno == 1062:

            return jsonify({
                "message": "Username already exists"
            }), 400

        return jsonify({
            "message": "Staff creation failed",
            "error": str(e)
        }), 500


# ==================================================
# DELETE STAFF - ADMIN
# ==================================================

@app.route("/api/staff/<int:staff_id>", methods=["DELETE"])
def staff_delete(staff_id):

    if session.get("staff_role") != "admin":

        return jsonify({
            "message": "Admin access required"
        }), 403

    if staff_id == session.get("staff_id"):

        return jsonify({
            "message": "Cannot delete your own account"
        }), 400

    try:

        db_execute(
            "DELETE FROM staff WHERE id = %s",
            (staff_id,)
        )

        return jsonify({
            "message": "Staff deleted"
        }), 200

    except Exception as e:

        return jsonify({
            "message": "Staff deletion failed",
            "error": str(e)
        }), 500


# ==================================================
# CSV EXPORT
# ==================================================

@app.route("/api/export", methods=["GET"])
def export_csv():

    if "staff_id" not in session:

        return jsonify({
            "message": "Login required"
        }), 401

    try:

        bookings = db_execute("""
            SELECT b.id, b.name, b.phone, b.email,
                   r.room_number, b.room_type,
                   b.check_in, b.check_out, b.status,
                   r.price, b.created_at
            FROM bookings b
            LEFT JOIN rooms r ON b.room_id = r.id
            ORDER BY b.id DESC
        """, fetch=True)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "ID", "Name", "Phone", "Email",
            "Room", "Room Type", "Check In",
            "Check Out", "Status", "Price", "Created"
        ])

        for b in bookings:

            writer.writerow([
                b["id"], b["name"], b["phone"],
                b["email"], b["room_number"],
                b["room_type"], b["check_in"],
                b["check_out"], b["status"],
                b["price"], b["created_at"]
            ])

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                "attachment; filename=hotel_bookings.csv"
            }
        )

    except Exception as e:

        return jsonify({
            "message": "Export failed",
            "error": str(e)
        }), 500


# ==================================================
# RUN
# ==================================================

if __name__ == "__main__":

    try:

        initialize_database()

        print("\n====================================")
        print("HOTEL MANAGEMENT SYSTEM")
        print("Backend: http://127.0.0.1:5000")
        print("Admin username: admin")
        print("Admin password: Admin@12345")
        print("====================================\n")

        app.run(
            host="127.0.0.1",
            port=5000,
            debug=True
        )

    except Exception as e:

        print("STARTUP ERROR:", e)