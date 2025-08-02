import sqlite3
import pandas as pd
import random
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
try:
    from model.panrpm_model import predict_no_show, predict_reschedule
except FileNotFoundError:
    # Define dummy functions if models are not available
    def predict_no_show(features):
        return random.uniform(0, 100)  # Placeholder: random probability
    def predict_reschedule(features):
        return random.uniform(0, 100)  # Placeholder: random probability

# Database initialization
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, phone TEXT, password TEXT, role TEXT, age INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS hospitals 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, location TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS departments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, name TEXT,
                  FOREIGN KEY (hospital_id) REFERENCES hospitals(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS doctors 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, department_id INTEGER, name TEXT, schedule TEXT, gender TEXT,
                  FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                  FOREIGN KEY (department_id) REFERENCES departments(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, hospital_id INTEGER, department_id INTEGER, 
                  doctor_id INTEGER, slot_time TEXT, date TEXT, booking_date TEXT, no_show_prob REAL, reschedule_prob REAL, status TEXT,
                  FOREIGN KEY (patient_id) REFERENCES users(id),
                  FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                  FOREIGN KEY (department_id) REFERENCES departments(id),
                  FOREIGN KEY (doctor_id) REFERENCES doctors(id))''')
    conn.commit()
    conn.close()
    print("Database initialized with tables.")

# Clear existing appointments
def clear_appointments():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM appointments")
    conn.commit()
    conn.close()

# Seed users
def seed_users():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    users = [
        ("John Doe", "john@example.com", "08012345678", "password123", "patient", 30),
        ("Jane Smith", "jane@example.com", "08098765432", "password123", "patient", 25),
        ("Alice Johnson", "alice@example.com", "08055555555", "password123", "patient", 40),
        ("Bob Brown", "bob@example.com", "08044444444", "password123", "patient", 35)
    ]
    c.executemany("INSERT OR IGNORE INTO users (name, email, phone, password, role, age) VALUES (?, ?, ?, ?, ?, ?)", users)
    conn.commit()
    conn.close()

# Seed hospitals
def seed_hospitals():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    hospitals = [
        ("Lagos General Hospital", "Lagos"), 
        ("Abuja Medical Center", "Abuja"), 
        ("Kano Health Clinic", "Kano"),
        ("Ibadan Community Hospital", "Ibadan")
    ]
    c.executemany("INSERT OR IGNORE INTO hospitals (name, location) VALUES (?, ?)", hospitals)
    conn.commit()
    conn.close()

# Seed departments
def seed_departments():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    hospital_ids = [row[0] for row in c.execute("SELECT id FROM hospitals").fetchall()]
    department_names = ["Cardiology", "Pediatrics", "Orthopedics", "Neurology"]
    for hospital_id in hospital_ids:
        for dept_name in department_names:
            c.execute("INSERT OR IGNORE INTO departments (hospital_id, name) VALUES (?, ?)", (hospital_id, dept_name))
    conn.commit()
    conn.close()

# Seed doctors
def seed_doctors():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    doctor_names = ["Dr. Adebayo", "Dr. Bello", "Dr. Okon", "Dr. Musa"]
    schedules = ["Mon-Fri 08:00-16:00", "Mon-Wed 09:00-15:00", "Tue-Thu 10:00-18:00"]
    genders = ["M", "F"]
    for dept in c.execute("SELECT id, hospital_id FROM departments").fetchall():
        dept_id = dept[0]
        hospital_id = dept[1]
        for i in range(2):
            doc_name = doctor_names[i % len(doctor_names)]
            schedule = random.choice(schedules)
            gender = random.choice(genders)
            c.execute("INSERT OR IGNORE INTO doctors (hospital_id, department_id, name, schedule, gender) VALUES (?, ?, ?, ?, ?)",
                      (hospital_id, dept_id, doc_name, schedule, gender))
    conn.commit()
    conn.close()

# Parse doctor's schedule to get valid hours
def parse_schedule(schedule):
    try:
        days, times = schedule.split()
        start_time, end_time = times.split('-')
        start_hour = int(start_time.split(':')[0])
        end_hour = int(end_time.split(':')[0])
        if start_hour >= end_hour:
            end_hour += 12 if end_hour < 12 else 0
        return start_hour, end_hour
    except (ValueError, AttributeError):
        return 8, 18  # Default to 8 AM - 6 PM

# Generate simulated appointments
def generate_appointments(num_appointments=100):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    # Fetch necessary data
    patients = c.execute("SELECT id, age FROM users WHERE role = 'patient'").fetchall()
    doctors = c.execute("SELECT id, hospital_id, department_id, schedule, gender FROM doctors").fetchall()
    hospitals = c.execute("SELECT id, location FROM hospitals").fetchall()
    statuses = ['scheduled', 'no_show', 'attended', 'rescheduled']
    
    current_date = datetime.now().date()
    for _ in range(num_appointments):
        patient = random.choice(patients)
        patient_id, patient_age = patient[0], patient[1]
        doctor = random.choice(doctors)
        doctor_id, hospital_id, department_id, schedule, doctor_gender = doctor[0], doctor[1], doctor[2], doctor[3], doctor[4]
        
        # Generate random past date (up to 1 year ago)
        days_back = random.randint(1, 365)
        appt_date = (current_date - timedelta(days=days_back)).strftime('%Y-%m-%d')
        booking_date = (pd.to_datetime(appt_date) - timedelta(days=random.randint(1, 30))).strftime('%Y-%m-%d')
        
        # Parse doctor's schedule for valid time slots
        start_hour, end_hour = parse_schedule(schedule)
        if start_hour >= end_hour:
            end_hour = start_hour + 8  # Default to 8-hour workday
        hour = random.randint(start_hour, end_hour - 1)
        slot_time = f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}"
        
        # Calculate features for predictions
        past_appointments = c.execute(
            "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
            (patient_id, appt_date)
        ).fetchall()
        previous_no_shows = sum(1 for appt in past_appointments if appt[0] == 'no_show')
        hospital_location = next(h[1] for h in hospitals if h[0] == hospital_id)
        lead_time = (pd.to_datetime(appt_date) - pd.to_datetime(booking_date)).days
        distance = 0 if 'Lagos' in hospital_location else 1
        time_of_day = 1 if 'AM' in slot_time.upper() else 0
        is_weekday = 0 if pd.to_datetime(appt_date).weekday() < 5 else 1
        doctor_gender_val = 0 if doctor_gender == 'M' else 1
        
        features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, patient_age, doctor_gender_val]
        
        # Use predictions if models exist, otherwise use placeholders
        model_files = [
            'model/rf_no_show_model.pkl', 'model/xgb_no_show_model.pkl',
            'model/rf_reschedule_model.pkl', 'model/xgb_reschedule_model.pkl'
        ]
        models_exist = all(os.path.exists(f) for f in model_files)
        if models_exist:
            no_show_prob = predict_no_show(features)
            reschedule_prob = predict_reschedule(features)
        else:
            no_show_prob = random.uniform(0, 100)  # Placeholder
            reschedule_prob = random.uniform(0, 100)  # Placeholder
        
        status = random.choice(statuses)
        
        # Insert appointment
        c.execute('''
            INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, booking_date, no_show_prob, reschedule_prob, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (patient_id, hospital_id, department_id, doctor_id, slot_time, appt_date, booking_date, no_show_prob, reschedule_prob, status))
    
    conn.commit()
    conn.close()
    print(f"Generated {num_appointments} simulated appointments.")

# Main execution
if __name__ == "__main__":
    # Initialize database and seed data
    init_db()
    print("Database initialized with tables and seed data.")
    clear_appointments()
    seed_users()
    seed_hospitals()
    seed_departments()
    seed_doctors()
    generate_appointments(100)