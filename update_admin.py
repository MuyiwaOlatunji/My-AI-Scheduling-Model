import sqlite3

# Connect to the database
conn = sqlite3.connect("database.db")
c = conn.cursor()

# Update the existing user to be an admin
try:
    c.execute("UPDATE users SET role = ?, name = ?, phone = ?, password = ? WHERE email = ?",
              ('admin', 'Muyiwa Olatunji', '08100225774', 'admin123', 'lrdmuyi85@gmail.com'))
    conn.commit()
    print("User updated to admin successfully.")
except sqlite3.Error as e:
    print(f"Error updating user to admin: {e}")
finally:
    conn.close()