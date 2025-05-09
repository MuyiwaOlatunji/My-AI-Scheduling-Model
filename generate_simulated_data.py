import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import random
import numpy as np

# Connect to the database
conn = sqlite3.connect("database.db")
c = conn.cursor()

# Clear existing appointments to start fresh
c.execute("DELETE FROM appointments")
conn.commit()

# Clear existing patients (to start fresh)
c.execute("DELETE FROM users WHERE role = 'patient'")
conn.commit()

# Get hospital, department, and doctor IDs from the database
hospitals = c.execute("SELECT id FROM hospitals").fetchall()
departments = c.execute("SELECT id, hospital_id FROM departments").fetchall()
doctors = c.execute("SELECT id, hospital_id, department_id FROM doctors").fetchall()

# Generate more patients (100 patients)
patients = []
for i in range(1, 101):
    c.execute("INSERT INTO users (name, email, phone, password, role) VALUES (?, ?, ?, ?, ?)",
              (f"Patient{i}", f"patient{i}@example.com", f"080{i:07d}", "password", "patient"))
patients = c.execute("SELECT id FROM users WHERE role = 'patient'").fetchall()
conn.commit()

# Generate simulated appointments (5000 records)
appointments = []
start_date = datetime(2024, 1, 1)
current_date = datetime(2025, 5, 8)  # Current date for simulation
target_appointments = 5000

while len(appointments) < target_appointments:
    patient_id = random.choice(patients)[0]
    hospital_id = random.choice(hospitals)[0]
    dept = random.choice([d for d in departments if d[1] == hospital_id])
    department_id = dept[0]
    
    # Filter doctors for the selected hospital and department
    matching_doctors = [d for d in doctors if d[1] == hospital_id and d[2] == department_id]
    if not matching_doctors:
        print(f"No doctors found for hospital_id={hospital_id}, department_id={department_id}. Skipping appointment.")
        continue  # Skip this appointment if no doctors are available
    
    doc = random.choice(matching_doctors)
    doctor_id = doc[0]
    
    # Appointment date (between Jan 2024 and May 2025)
    days_offset = random.randint(0, (current_date - start_date).days)
    date = (start_date + timedelta(days=days_offset)).strftime('%Y-%m-%d')
    
    # Slot time (between 8 AM and 5 PM)
    hour = random.randint(8, 17)
    slot_time = f"{hour}:00 {'AM' if hour < 12 else 'PM'}"
    
    # Simulate status based on realistic no-show rates (42% as per your study)
    status = random.choices(['scheduled', 'attended', 'closed'], weights=[42, 50, 8])[0]
    
    appointments.append((patient_id, hospital_id, department_id, doctor_id, slot_time, date, 0.0, status))

# Insert into database
c.executemany("INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", appointments)
conn.commit()
conn.close()

print(f"Generated {len(appointments)} simulated appointments with {len(patients)} patients.")