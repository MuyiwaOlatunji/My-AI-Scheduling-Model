import sqlite3

# Connect to the database
conn = sqlite3.connect("database.db")
c = conn.cursor()

# Insert admin user
try:
    c.execute("INSERT INTO users (name, email, phone, password, role) VALUES (?, ?, ?, ?, ?)",
              ('Muyiwa Olatunji', 'lrdmuyi85@gmail.com', '08100225774', 'admin123', 'admin'))
    conn.commit()
    print("Admin user inserted successfully.")
except sqlite3.Error as e:
    print(f"Error inserting admin user: {e}")
finally:
    conn.close()
    