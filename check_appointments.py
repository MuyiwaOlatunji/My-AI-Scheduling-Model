import sqlite3

conn = sqlite3.connect("database.db")
c = conn.cursor()
c.execute("SELECT * FROM appointments WHERE id = 1")
appt = c.fetchone()
print(appt)
c.execute("SELECT * FROM appointments WHERE no_show_prob > 0.5 AND status = 'booked'")
eligible_appts = c.fetchall()
print(eligible_appts)
conn.close()