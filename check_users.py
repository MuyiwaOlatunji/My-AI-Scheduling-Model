import sqlite3

conn = sqlite3.connect("database.db")
c = conn.cursor()
c.execute("SELECT * FROM users")
users = c.fetchall()
for user in users:
    print(user)
conn.close()