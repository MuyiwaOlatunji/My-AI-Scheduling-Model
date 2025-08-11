import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database.db')
c = conn.cursor()
c.execute("""
INSERT OR IGNORE INTO users (name, email, phone, password, role, age, location, gender, marriage_status, occupation, hospital_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", ("Hospital Admin", "hospitaladmin@example.com", "08022222222", generate_password_hash("adminpassword"), "hospital_admin", 45, "Lagos", "M", "Married", "Administrator", 1))
conn.commit()
conn.close()
print("Hospital admin user created.")