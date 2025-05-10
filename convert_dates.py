import sqlite3
from datetime import datetime

conn = sqlite3.connect("database.db")
c = conn.cursor()

# Fetch all appointments
c.execute("SELECT id, date FROM appointments")
appointments = c.fetchall()

for appt in appointments:
    appt_id, date_str = appt
    try:
        # Try parsing as MM/DD/YYYY
        date_obj = datetime.strptime(date_str, '%m/%d/%Y')
        new_date_str = date_obj.strftime('%Y-%m-%d')
        # Update the database
        c.execute("UPDATE appointments SET date = ? WHERE id = ?", (new_date_str, appt_id))
        print(f"Updated appointment ID {appt_id}: {date_str} -> {new_date_str}")
    except ValueError:
        # Already in YYYY-MM-DD format or another format
        continue

conn.commit()
conn.close()