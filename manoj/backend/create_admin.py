import mysql.connector
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
import os

load_dotenv()

db = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", "3307")),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", "manoj2005@123"),
    database=os.getenv("MYSQL_DATABASE", "hotel_management")
)

cursor = db.cursor()

username = "admin"
name = "Administrator"
password = input("Enter Admin password: ")

hashed_password = generate_password_hash(password)

cursor.execute(
    "SELECT id FROM staff WHERE username=%s",
    (username,)
)

existing = cursor.fetchone()

if existing:
    cursor.execute("""
        UPDATE staff
        SET password=%s, role='Admin', name=%s
        WHERE username=%s
    """, (hashed_password, name, username))

    print("Existing Admin password updated.")

else:
    cursor.execute("""
        INSERT INTO staff (name, phone, username, password, role)
        VALUES (%s, %s, %s, %s, %s)
    """, (name, "0000000000", username, hashed_password, "Admin"))

    print("Admin account created.")

db.commit()
cursor.close()
db.close()

print("Admin setup completed.")