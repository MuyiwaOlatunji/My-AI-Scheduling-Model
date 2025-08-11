import sqlite3
from datetime import datetime
import re

conn = sqlite3.connect("database.db")
c = conn.cursor()

# Fetch all appointments
c.execute("SELECT id, date FROM appointments")
appointments = c.fetchall()

for appt in appointments:
    appt_id, date_str = appt
    try:
        # Try parsing as MM/DD/YYYY or other common formats
        for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y']:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                new_date_str = date_obj.strftime('%Y-%m-%d')
                if new_date_str != date_str:
                    # Update the database
                    c.execute("UPDATE appointments SET date = ? WHERE id = ?", (new_date_str, appt_id))
                    print(f"Updated appointment ID {appt_id}: {date_str} -> {new_date_str}")
                break
            except ValueError:
                continue
        else:
            print(f"Skipping appointment ID {appt_id}: Unrecognized date format {date_str}")
    except Exception as e:
        print(f"Error processing appointment ID {appt_id}: {e}")

# Normalize doctor schedules
c.execute("SELECT id, schedule FROM doctors")
doctors = c.fetchall()

for doc in doctors:
    doc_id, schedule = doc
    try:
        # Parse schedule (e.g., 'tue-sun 8:00am-5:00pm' or 'mon-fri 9-17')
        match = re.match(r'^([a-z]{3})-([a-z]{3})\s+([\d:apm]+)-([\d:apm]+)$', schedule.lower())
        if not match:
            print(f"Skipping doctor ID {doc_id}: Invalid schedule format {schedule}")
            continue
        # Define normalize_schedule_time function (same as in app.py)
        def normalize_schedule_time(time_str):
            time_str = time_str.lower().strip()
            match = re.match(r'^(\d{1,2})(?::\d{2})?(am|pm)?$', time_str)
            if not match:
                raise ValueError(f"Invalid time format: {time_str}")
            hour, period = match.groups()
            hour = int(hour)
            if period:
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0
            return str(hour)

        start_day, end_day, start_time_str, end_time_str = match.groups()
        # Normalize times
        start_hour = normalize_schedule_time(start_time_str)
        end_hour = normalize_schedule_time(end_time_str)
        new_schedule = f"{start_day}-{end_day} {start_hour}-{end_hour}"
        if new_schedule != schedule:
            c.execute("UPDATE doctors SET schedule = ? WHERE id = ?", (new_schedule, doc_id))
            print(f"Updated doctor ID {doc_id}: {schedule} -> {new_schedule}")
    except Exception as e:
        print(f"Error processing doctor ID {doc_id}: {e}")

conn.commit()
conn.close()