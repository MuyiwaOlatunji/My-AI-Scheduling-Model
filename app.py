from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_mail import Mail, Message
import sqlite3
import pandas as pd
import numpy as np
import os
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import joblib
<<<<<<< HEAD
from sklearn.preprocessing import LabelEncoder
import random
=======
>>>>>>> redesign
import re

# Load environment variables
load_dotenv()

# Initialize Flask app
<<<<<<< HEAD
app = Flask(__name__, static_folder='static')
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")
=======
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secure_secret_key_here")  # Ensure a secure key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Optional: set session lifetime
>>>>>>> redesign

# Flask-Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER")
mail = Mail(app)

# Logging configuration
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Authentication decorator
def login_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            print(f"login_required - Session: {session}, Path: {request.path}, Roles: {roles}")  # Debug
            if 'user_id' not in session:
                flash("Please log in first.", "danger")
                return redirect(url_for('hospital_admin_login' if 'hospital_admin' in roles else 'patient_login'))
            user_role = query_db("SELECT role FROM users WHERE id = ?", (session['user_id'],), one=True)['role']
            if user_role not in roles:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Database configuration
def get_sqlite_conn():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

<<<<<<< HEAD
# Database initialization
def init_db():
    conn = get_sqlite_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS hospitals 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, location TEXT, 
                  subscription_status TEXT DEFAULT 'pending', subscription_expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, phone TEXT, password TEXT, 
                  role TEXT, age INTEGER, location TEXT, gender TEXT, marriage_status TEXT, occupation TEXT, 
                  hospital_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS departments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, name TEXT,
                  FOREIGN KEY (hospital_id) REFERENCES hospitals(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS doctors 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, department_id INTEGER, name TEXT, 
                  schedule TEXT, gender TEXT, FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                  FOREIGN KEY (department_id) REFERENCES departments(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, hospital_id INTEGER, 
                  department_id INTEGER, doctor_id INTEGER, slot_time TEXT, date TEXT, booking_date TEXT, 
                  no_show_prob REAL, reschedule_prob REAL, status TEXT, health_challenge TEXT,
                  FOREIGN KEY (patient_id) REFERENCES users(id),
                  FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                  FOREIGN KEY (department_id) REFERENCES departments(id),
                  FOREIGN KEY (doctor_id) REFERENCES doctors(id))''')

    if not query_db("SELECT COUNT(*) FROM users", one=True)['COUNT(*)']:
        hospitals = [
            ("Lagos General Hospital", "Lagos", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
            ("Abuja Medical Center", "Abuja", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
        ]
        c.executemany("INSERT INTO hospitals (name, location, subscription_status, subscription_expiry_date) VALUES (?, ?, ?, ?)", hospitals)
        
        admin_email = "admin@example.com"
        admin_password = generate_password_hash("adminpassword")
        patient_email = "patient@example.com"
        patient_password = generate_password_hash("patientpassword")
        c.execute("INSERT INTO users (name, email, phone, password, role, age) VALUES (?, ?, ?, ?, ?, ?)",
                  ("Super Admin", admin_email, "1234567890", admin_password, "super_admin", 30))
        c.execute("INSERT INTO users (name, email, phone, password, role, age, location, gender, marriage_status, occupation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  ("Test Patient", patient_email, "0987654321", patient_password, "patient", 25, "Lagos", "M", "Single", "Engineer"))
        
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (1, "Cardiology"))
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (2, "Neurology"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (1, 1, "Dr. Jane Smith", "F", "mon-fri 9-17"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (2, 2, "Dr. John Brown", "M", "mon-fri 10-18"))
        conn.commit()

    conn.close()

# Database query helper
=======
>>>>>>> redesign
def query_db(query, args=(), one=False, commit=False, return_id=False):
    conn = get_sqlite_conn()
    try:
        c = conn.cursor()
        c.execute(query, args)
        if commit:
            conn.commit()
            if return_id:
                return c.lastrowid
        else:
            rv = c.fetchall()
            if rv:
                columns = [desc[0] for desc in c.description]
                rv = [dict(zip(columns, row)) for row in rv]
                return rv[0] if one else rv
            return None if one else []
    except sqlite3.IntegrityError as e:
        if commit:
            conn.rollback()
            raise e
        return None if one else []
    finally:
        conn.close()

# Database initialization
def init_db():
    conn = get_sqlite_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS hospitals 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, location TEXT, 
                  subscription_status TEXT DEFAULT 'pending', subscription_expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, 
                  password TEXT NOT NULL, role TEXT NOT NULL, age INTEGER, location TEXT, 
                  gender TEXT, marriage_status TEXT, occupation TEXT, hospital_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS departments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, name TEXT,
                  FOREIGN KEY (hospital_id) REFERENCES hospitals(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS doctors 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, department_id INTEGER, name TEXT, 
                  schedule TEXT, gender TEXT, FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                  FOREIGN KEY (department_id) REFERENCES departments(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, hospital_id INTEGER, 
                  department_id INTEGER, doctor_id INTEGER, slot_time TEXT, date TEXT, booking_date TEXT, 
                  no_show_prob REAL, reschedule_prob REAL, status TEXT, health_challenge TEXT,
                  FOREIGN KEY (patient_id) REFERENCES users(id),
                  FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                  FOREIGN KEY (department_id) REFERENCES departments(id),
                  FOREIGN KEY (doctor_id) REFERENCES doctors(id))''')

    # Seed initial data only if no super admin exists
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'super_admin'")
    if c.fetchone()[0] == 0:
        hospitals = [
            ("Lagos General Hospital", "Lagos", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
            ("Abuja Medical Center", "Abuja", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
        ]
        c.executemany("INSERT INTO hospitals (name, location, subscription_status, subscription_expiry_date) VALUES (?, ?, ?, ?)", hospitals)
        c.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                  ("Admin", "admin@example.com", generate_password_hash("admin123"), "super_admin"))
        c.execute("INSERT INTO users (name, email, password, role, age, location, gender, marriage_status, occupation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  ("Test Patient", "patient@example.com", generate_password_hash("patient123"), "patient", 25, "Lagos", "M", "Single", "Engineer"))
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (1, "Cardiology"))
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (2, "Neurology"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (1, 1, "Dr. Jane Smith", "F", "mon-fri 9-17"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (2, 2, "Dr. John Brown", "M", "mon-fri 10-18"))
        conn.commit()
    conn.close()

# Normalize schedule format
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

# Check doctor availability
def is_doctor_available(doctor_id, date, time_slot):
    doctor = query_db("SELECT schedule FROM doctors WHERE id = ?", (doctor_id,), one=True)
    if not doctor:
        return False
    schedule = doctor['schedule'].lower()
    try:
        match = re.match(r'^([a-z]{3})-([a-z]{3})\s+([\d:apm]+)-([\d:apm]+)$', schedule)
        if not match:
            raise ValueError(f"Invalid schedule format: {schedule}")
        start_day, end_day, start_time_str, end_time_str = match.groups()
        
        start_hour = int(normalize_schedule_time(start_time_str))
        end_hour = int(normalize_schedule_time(end_time_str))
        
        days_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        start_day_idx = days_map.get(start_day)
        end_day_idx = days_map.get(end_day)
        if start_day_idx is None or end_day_idx is None:
            app.logger.error(f"Invalid days in schedule: {start_day}-{end_day}")
            return False
        
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        day_idx = date_obj.weekday()
        if not (start_day_idx <= day_idx <= end_day_idx):
            return False
        
        slot_time = datetime.strptime(time_slot, '%I:%M %p')
        slot_hour = slot_time.hour
        
        if not (start_hour <= slot_hour < end_hour):
            return False
    
    except ValueError as e:
        app.logger.error(f"Error parsing schedule for doctor_id {doctor_id}: {e}")
        return False
    
<<<<<<< HEAD
    cursor.execute("SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status NOT IN ('cancelled', 'closed')",
                  (doctor_id, date, time_slot))
    if cursor.fetchone():
        return False
    
    return True

# Find available slot for rescheduling
def find_available_slot(doctor_id, current_date, patient_id, max_attempts=7):
    all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
    current_date_dt = pd.to_datetime(current_date)
    for days_ahead in range(1, max_attempts + 1):
        new_date = (current_date_dt + pd.Timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        if not is_doctor_available(doctor_id, new_date, all_slots[0]):
            continue
        existing_appts = query_db(
            "SELECT slot_time FROM appointments WHERE doctor_id = ? AND date = ? AND status != 'closed'",
            (doctor_id, new_date)
        )
        booked_slots = [appt['slot_time'] for appt in existing_appts]
        for slot in all_slots:
            if slot not in booked_slots and is_doctor_available(doctor_id, new_date, slot):
                return new_date, slot
    return None, None

# Simulate appointments for prediction (not training)
def simulate_appointments(num_appointments):
    appointments = []
    current_date = datetime.now()
    for _ in range(num_appointments):
        patient_id = random.randint(1, 100)
        hospital_id = random.choice([1, 2])
        department_id = random.choice([1, 2])
        doctor_id = random.choice([1, 2])
        appt_date = (current_date + timedelta(days=random.randint(1, 60))).strftime('%Y-%m-%d')
        slot_time = random.choice(['09:00 AM', '10:00 AM', '11:00 AM', '02:00 PM', '03:00 PM'])
        booking_date = current_date.strftime('%Y-%m-%d')
        status = random.choice(['scheduled', 'attended', 'no-show', 'cancelled', 'rescheduled'])
        lead_time = random.randint(1, 30)
        location = random.choice(['Lagos', 'Abuja'])  # Added location
        distance = random.choice([0, 1])
        time_of_day = 1 if 'AM' in slot_time else 0
        is_weekday = 0 if datetime.strptime(appt_date, '%Y-%m-%d').weekday() < 5 else 1
        age = random.randint(18, 70)
        doctor_gender = random.choice(['M', 'F'])
        patient_gender = random.choice(['M', 'F', 'Other'])
        marriage_status = random.choice(['Single', 'Married', 'Divorced', 'Widowed'])
        has_occupation = random.choice([0, 1])
        health_challenge = "Sample challenge" if random.random() > 0.5 else ""
        health_challenge_length = len(health_challenge) if health_challenge else 0
        previous_no_shows = random.randint(0, 5)

        appointments.append({
            'patient_id': patient_id, 'hospital_id': hospital_id, 'department_id': department_id,
            'doctor_id': doctor_id, 'slot_time': slot_time, 'date': appt_date, 'booking_date': booking_date,
            'status': status, 'lead_time': lead_time, 'distance': distance, 'time_of_day': time_of_day,
            'is_weekday': is_weekday, 'age': age, 'doctor_gender': doctor_gender, 'patient_gender': patient_gender,
            'marriage_status': marriage_status, 'has_occupation': has_occupation, 
            'health_challenge': health_challenge, 'health_challenge_length': health_challenge_length,
            'previous_no_shows': previous_no_shows, 'location': location
        })
    df = pd.DataFrame(appointments)
    df['no_show'] = df['status'].apply(lambda x: 1 if x == 'no-show' else 0)
    df['reschedule'] = df['status'].apply(lambda x: 1 if x == 'rescheduled' else 0)
    return df

# Check no-shows and reschedule
def check_no_shows_and_reschedule():
    with app.app_context():
        today = date.today()
        yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        query = """
        SELECT a.id, a.patient_id, a.hospital_id, a.department_id, a.doctor_id, a.slot_time, a.date, a.status,
               u.email, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name
        FROM appointments a
        JOIN users u ON a.patient_id = u.id
        JOIN hospitals h ON a.hospital_id = h.id
        JOIN departments d ON a.department_id = d.id
        JOIN doctors doc ON a.doctor_id = doc.id
        WHERE a.date = ? AND a.status IN ('scheduled', 'rescheduled')
        """
        potential_no_shows = query_db(query, (yesterday,))
        for appt in potential_no_shows:
            appt_id = appt['id']
            patient_id = appt['patient_id']
            doctor_id = appt['doctor_id']
            current_date = appt['date']
            query = "UPDATE appointments SET status = 'no_show' WHERE id = ?"
            query_db(query, (appt_id,), commit=True)
            new_date, new_time = find_available_slot(doctor_id, current_date, patient_id)
            if new_date and new_time:
                appointment_date = pd.to_datetime(new_date)
                current_date_dt = pd.to_datetime(today)
                max_date = current_date_dt + relativedelta(years=1)
                if appointment_date < current_date_dt or appointment_date > max_date:
                    continue
                past_appointments = query_db(
                    "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
                    (patient_id, new_date)
                )
                previous_no_shows = sum(1 for a in past_appointments if a['status'] == 'no_show')
                hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (appt['hospital_id'],), one=True)['location']
                patient = query_db("SELECT * FROM users WHERE id = ?", (patient_id,), one=True)
                lead_time = (appointment_date - current_date_dt).days
                distance = 0 if patient['location'] == hospital_location else 1
                time_of_day = 1 if 'AM' in new_time.upper() else 0
                is_weekday = 0 if appointment_date.weekday() < 5 else 1
                user_age = patient['age']
                doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (doctor_id,), one=True)['gender']
                doctor_gender_val = 0 if doctor_gender == 'M' else 1
                patient_gender = {'M': 0, 'F': 1, 'Other': 2}.get(patient['gender'], 2)
                marriage_status = {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}.get(patient['marriage_status'], 0)
                has_occupation = 1 if patient['occupation'] and patient['occupation'].strip() else 0
                health_challenge = appt.get('health_challenge', '')
                health_challenge_length = len(health_challenge) if health_challenge else 0
                features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, user_age, doctor_gender_val,
                            patient_gender, marriage_status, has_occupation, health_challenge_length]
                no_show_prob = predict_no_show(features)
                reschedule_prob = predict_reschedule(features)
                query = """
                UPDATE appointments 
                SET date = ?, slot_time = ?, booking_date = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? 
                WHERE id = ?
                """
                booking_date = today.strftime('%Y-%m-%d')
                query_db(query, (new_date, new_time, booking_date, no_show_prob, reschedule_prob, appt_id), commit=True)
                appointment_details = {
                    'hospital_name': appt['hospital_name'],
                    'department_name': appt['department_name'],
                    'doctor_name': appt['doctor_name'],
                    'date': new_date,
                    'slot_time': new_time
                }
                send_reschedule_notification(appt['email'], appointment_details)
                flash(f"Appointment ID {appt_id} rescheduled to {new_date} at {new_time}.", "success")
=======
    existing = query_db(
        "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status NOT IN ('cancelled', 'closed')",
        (doctor_id, date, time_slot), one=True
    )
    return not bool(existing)
>>>>>>> redesign

# Prediction functions using trained models
def predict_no_show(features):
    try:
<<<<<<< HEAD
        rf_model = joblib.load('model/rf_no_show_model.pkl')
        xgb_model = joblib.load('model/xgb_no_show_model.pkl')
        feature_cols = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender',
                        'patient_gender', 'marriage_status', 'has_occupation', 'health_challenge_length']
        features_df = pd.DataFrame([features], columns=feature_cols)
        rf_prob = rf_model.predict_proba(features_df)[0][1]
        xgb_prob = xgb_model.predict_proba(features_df)[0][1]
        ensemble_prob = (rf_prob + xgb_prob) / 2 * 100
        return ensemble_prob
=======
        model = joblib.load('model/rf_no_show_model.pkl')
        feature_cols = [
            'previous_no_shows', 'lead_time', 'distance', 'time_of_day', 
            'is_weekday', 'age', 'doctor_gender', 'patient_gender', 
            'marriage_status', 'has_occupation', 'health_challenge_length'
        ]
        features_df = pd.DataFrame([features], columns=feature_cols)
        prob = model.predict_proba(features_df)[0][1] * 100
        return prob
>>>>>>> redesign
    except Exception as e:
        app.logger.error(f"Error predicting no-show: {e}")
        return 10.0

def predict_reschedule(features):
    try:
<<<<<<< HEAD
        rf_model = joblib.load('model/rf_reschedule_model.pkl')
        xgb_model = joblib.load('model/xgb_reschedule_model.pkl')
        feature_cols = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender',
                        'patient_gender', 'marriage_status', 'has_occupation', 'health_challenge_length']
        features_df = pd.DataFrame([features], columns=feature_cols)
        rf_prob = rf_model.predict_proba(features_df)[0][1]
        xgb_prob = xgb_model.predict_proba(features_df)[0][1]
        ensemble_prob = (rf_prob + xgb_prob) / 2 * 100
        return ensemble_prob
    except Exception as e:
        app.logger.error(f"Error predicting reschedule: {e}")
        return 10.0
=======
        model = joblib.load('model/rf_reschedule_model.pkl')
        feature_cols = [
            'previous_no_shows', 'lead_time', 'distance', 'time_of_day', 
            'is_weekday', 'age', 'doctor_gender', 'patient_gender', 
            'marriage_status', 'has_occupation', 'health_challenge_length'
        ]
        features_df = pd.DataFrame([features], columns=feature_cols)
        prob = model.predict_proba(features_df)[0][1] * 100
        return prob
    except Exception as e:
        app.logger.error(f"Error predicting reschedule: {e}")
        return 10.0

# Check no-shows and reschedule
def check_no_shows_and_reschedule():
    with app.app_context():
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        potential_no_shows = query_db("""
            SELECT a.id, a.patient_id, a.doctor_id, a.date, u.email, h.name AS hospital_name, 
                   d.name AS department_name, doc.name AS doctor_name
            FROM appointments a
            JOIN users u ON a.patient_id = u.id
            JOIN hospitals h ON a.hospital_id = h.id
            JOIN departments d ON a.department_id = d.id
            JOIN doctors doc ON a.doctor_id = doc.id
            WHERE a.date = ? AND a.status IN ('scheduled', 'rescheduled')
        """, (yesterday,))
        
        for appt in potential_no_shows:
            query_db("UPDATE appointments SET status = 'no_show' WHERE id = ?", (appt['id'],), commit=True)
            
            # Get patient and appointment details for prediction
            patient = query_db("SELECT * FROM users WHERE id = ?", (appt['patient_id'],), one=True)
            hospital = query_db("SELECT location FROM hospitals WHERE id = ?", (query_db("SELECT hospital_id FROM appointments WHERE id = ?", (appt['id'],), one=True)['hospital_id'],), one=True)

            # Prepare features for prediction
            features = [
                query_db("SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND status = 'no_show'", 
                        (appt['patient_id'],), one=True)['COUNT(*)'],  # previous_no_shows
                1,  # lead_time (1 day for reschedule)
                0 if patient['location'] == hospital['location'] else 1,  # distance
                1 if 'AM' in appt['slot_time'].upper() else 0,  # time_of_day
                0 if datetime.strptime(appt['date'], '%Y-%m-%d').weekday() < 5 else 1,  # is_weekday
                patient['age'],  # age
                0 if query_db("SELECT gender FROM doctors WHERE id = ?", (appt['doctor_id'],), one=True)['gender'] == 'M' else 1,  # doctor_gender
                {'M': 0, 'F': 1, 'Other': 2}[patient['gender']],  # patient_gender
                {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}[patient['marriage_status']],  # marriage_status
                1 if patient['occupation'].strip() else 0,  # has_occupation
                len(query_db("SELECT health_challenge FROM appointments WHERE id = ?", (appt['id'],), one=True)['health_challenge'] or '')  # health_challenge_length
            ]
            
            no_show_prob = predict_no_show(features)
            reschedule_prob = predict_reschedule(features)
            
            # Find next available slot
            all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
            current_date = datetime.strptime(appt['date'], '%Y-%m-%d')
            
            for days_ahead in range(1, 8):
                new_date = (current_date + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
                existing_appts = query_db(
                    "SELECT slot_time FROM appointments WHERE doctor_id = ? AND date = ? AND status != 'closed'",
                    (appt['doctor_id'], new_date)
                )
                booked_slots = [a['slot_time'] for a in existing_appts]
                
                for slot in all_slots:
                    if slot not in booked_slots and is_doctor_available(appt['doctor_id'], new_date, slot):
                        query_db("""
                            UPDATE appointments 
                            SET date = ?, slot_time = ?, booking_date = ?, status = 'rescheduled', 
                                no_show_prob = ?, reschedule_prob = ? 
                            WHERE id = ?
                        """, (new_date, slot, date.today().strftime('%Y-%m-%d'), no_show_prob, reschedule_prob, appt['id']), commit=True)
                        
                        # Send notification
                        msg = Message(
                            "Your Appointment Has Been Rescheduled",
                            recipients=[appt['email']],
                            body=f"""
                            Dear Patient,
                            
                            Your appointment has been rescheduled:
                            Hospital: {appt['hospital_name']}
                            Department: {appt['department_name']}
                            Doctor: {appt['doctor_name']}
                            New Date: {new_date}
                            New Time: {slot}
                            
                            Thank you.
                            """
                        )
                        mail.send(msg)
                        break
>>>>>>> redesign

# Routes
@app.route('/')
def index():
    print(f"Index - Session: {session}")  # Debug
    if 'user_id' in session:
        user_role = query_db("SELECT role FROM users WHERE id = ?", (session['user_id'],), one=True)['role']
        if user_role == 'hospital_admin':
            return redirect(url_for('hospital_admin_dashboard'))
        elif user_role == 'patient':
            return redirect(url_for('patient_dashboard'))
        elif user_role == 'super_admin':
            return redirect(url_for('super_admin'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            user_data = {
                'name': request.form['name'],
                'email': request.form['email'],
                'phone': request.form['phone'],
                'password': generate_password_hash(request.form['password']),
                'role': 'patient',
                'age': int(request.form.get('age', 30)),
                'location': request.form['location'],
                'gender': request.form['gender'],
                'marriage_status': request.form['marriage_status'],
                'occupation': request.form['occupation']
            }
            query_db(
                "INSERT INTO users (name, email, phone, password, role, age, location, gender, marriage_status, occupation) "
                "VALUES (:name, :email, :phone, :password, :role, :age, :location, :gender, :marriage_status, :occupation)",
                user_data, commit=True
            )
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('patient_login'))
        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")
    return render_template('register.html')

@app.route('/patient_login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if not email or not password:
            flash('Please provide both email and password', 'danger')
            return redirect(url_for('patient_login'))
        
        user = query_db("SELECT * FROM users WHERE email = ? AND role = 'patient'", (email,), one=True)
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash('Logged in successfully', 'success')
            return redirect(url_for('patient_dashboard'))
        
        flash('Invalid credentials', 'danger')
    return render_template('patient_login.html')

@app.route('/hospital_admin_login', methods=['GET', 'POST'])
def hospital_admin_login():
    print(f"hospital_admin_login - Session: {session}")  # Debug
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = query_db("SELECT * FROM users WHERE email = ? AND role = 'hospital_admin'", (email,), one=True)
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash("Logged in successfully.", "success")
            return redirect(url_for('hospital_admin_dashboard'))
        
        flash("Invalid credentials or not a hospital admin.", "danger")
    return render_template('hospital_admin_login.html')  # Changed to correct template

@app.route('/super_admin_login', methods=['GET', 'POST'])
def super_admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if not email or not password:
            flash('Please provide both email and password', 'danger')
            return redirect(url_for('super_admin_login'))
        
        user = query_db("SELECT * FROM users WHERE email = ? AND role = 'super_admin'", (email,), one=True)
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash("Logged in successfully.", "success")
            return redirect(url_for('super_admin'))
        
        flash("Invalid credentials or not a super admin.", "danger")
        return redirect(url_for('super_admin_login'))
    
    return render_template('super_admin_login.html')

@app.route('/cancel_appointment/<int:appt_id>', methods=['GET'])
def cancel_appointment(appt_id):
    app.logger.info(f"Attempting to cancel appointment with ID: {appt_id}")
    if 'user_id' not in session:
        flash('Please log in to cancel an appointment.', 'danger')
        return redirect(url_for('login'))
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE appointments SET status = ? WHERE id = ? AND patient_id = ?', ('canceled', appt_id, session['user_id']))
        conn.commit()
        if cursor.rowcount == 0:
            flash('Appointment not found or you do not have permission to cancel it.', 'danger')
        else:
            flash('Appointment canceled successfully.', 'success')
    except sqlite3.Error as e:
        flash(f'Database error: {e}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('patient_dashboard'))

@app.route('/patient')
<<<<<<< HEAD
def patient_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT a.id, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name, a.date, a.slot_time, a.status, a.doctor_id '
                   'FROM appointments a '
                   'JOIN hospitals h ON a.hospital_id = h.id '
                   'JOIN departments d ON a.department_id = d.id '
                   'JOIN doctors doc ON a.doctor_id = doc.id '
                   'WHERE a.patient_id = ?', (session['user_id'],))
    appointments = cursor.fetchall()
    appointments = [{'id': row[0], 'name': row[1], 'name_1': row[2], 'name_2': row[3], 'date': row[4], 'slot_time': row[5], 'status': row[6], 'doctor_id': row[7]} for row in appointments]
    
    current_date = datetime.now()
    for appt in appointments:
        appointment_date = datetime.strptime(appt['date'], '%Y-%m-%d')
        appt['lead_time'] = (appointment_date - current_date).days
    
    conn.close()
    return render_template('patient.html', appointments=appointments)
=======
@login_required(['patient'])
def patient_dashboard():
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')
    if sort_by not in ['date', 'status']:
        sort_by = 'date'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    user = query_db("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
    appointments = query_db(f"""
        SELECT a.id, h.name AS hospital, d.name AS department, doc.name AS doctor, 
               a.date, a.slot_time, a.status, a.no_show_prob, a.reschedule_prob
        FROM appointments a
        JOIN hospitals h ON a.hospital_id = h.id
        JOIN departments d ON a.department_id = d.id
        JOIN doctors doc ON a.doctor_id = doc.id
        WHERE a.patient_id = ?
        ORDER BY {sort_by} {sort_order}
    """, (session['user_id'],))

    return render_template('patient.html', appointments=appointments, user=user)

@app.route('/update_profile', methods=['POST'])
@login_required(['patient'])
def update_profile():
    if request.method == 'POST':
        try:
            query_db(
                "UPDATE users SET occupation = ?, location = ?, age = ? WHERE id = ?",
                (request.form['occupation'], request.form['location'], int(request.form['age']), session['user_id']),
                commit=True
            )
            flash("Profile updated successfully", "success")
        except Exception as e:
            app.logger.error(f"Error updating profile: {e}")
            flash("Error updating profile", "danger")
    return redirect(url_for('patient_dashboard'))
>>>>>>> redesign

@app.route('/book', methods=['GET', 'POST'])
@login_required(['patient'])
def book_appointment():
    if request.method == 'POST':
<<<<<<< HEAD
        patient_id = session['user_id']
        hospital_id = request.form['hospital']
        department_id = request.form['department']
        doctor_id = request.form['doctor']
        date_str = request.form['date']
        slot_time = request.form['time']
        health_challenge = request.form['health_challenge']
        booking_date = date.today().strftime('%Y-%m-%d')
        patient = query_db("SELECT * FROM users WHERE id = ?", (patient_id,), one=True)

        if not is_doctor_available(doctor_id, date_str, slot_time):
            flash("Selected doctor is not available at this time.", "danger")
            return redirect(url_for('book_appointment'))

        appointment_date = pd.to_datetime(date_str)
        current_date = pd.to_datetime(date.today())
        max_date = current_date + relativedelta(years=1)
        if appointment_date < current_date or appointment_date > max_date:
            flash("Invalid date range.", "danger")
            return redirect(url_for('book_appointment'))

        existing = query_db(
            "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'closed'",
            (doctor_id, date_str, slot_time), one=True
        )
        if existing:
            flash("Selected slot is already booked.", "danger")
            return redirect(url_for('book_appointment'))

        past_appointments = query_db("SELECT status FROM appointments WHERE patient_id = ? AND date < ?", (patient_id, date_str))
        previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')
        hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)['location']
        lead_time = (appointment_date - current_date).days
        distance = 0 if patient['location'] == hospital_location else 1
        time_of_day = 1 if 'AM' in slot_time.upper() else 0
        is_weekday = 0 if appointment_date.weekday() < 5 else 1
        doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (doctor_id,), one=True)['gender']
        doctor_gender_val = 0 if doctor_gender == 'M' else 1
        patient_gender = {'M': 0, 'F': 1, 'Other': 2}.get(patient['gender'], 2)
        marriage_status = {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}.get(patient['marriage_status'], 0)
        has_occupation = 1 if patient['occupation'] and patient['occupation'].strip() else 0
        health_challenge_length = len(health_challenge) if health_challenge else 0
        features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, patient['age'], doctor_gender_val,
                    patient_gender, marriage_status, has_occupation, health_challenge_length]
        no_show_prob = predict_no_show(features)
        reschedule_prob = predict_reschedule(features)

        query = """
        INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, booking_date, no_show_prob, reschedule_prob, status, health_challenge)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        query_db(query, (patient_id, hospital_id, department_id, doctor_id, slot_time, date_str, booking_date, no_show_prob, reschedule_prob, 'scheduled', health_challenge), commit=True)
        flash("Appointment booked successfully.", "success")
        return redirect(url_for('patient_dashboard'))
=======
        try:
            hospital_id = request.form['hospital']
            department_id = request.form['department']
            doctor_id = request.form['doctor']
            date_str = request.form['date']
            slot_time = request.form['time']
            health_challenge = request.form['health_challenge']
            
            if not is_doctor_available(doctor_id, date_str, slot_time):
                flash("Selected slot is not available", "danger")
                return redirect(url_for('book_appointment'))
            
            patient = query_db("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
            hospital = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
            
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d')
            booking_date = datetime.now()
            lead_time = (appointment_date - booking_date).days
            
            features = [
                query_db("SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND status = 'no-show'", 
                        (session['user_id'],), one=True)['COUNT(*)'],
                lead_time,
                0 if patient['location'] == hospital['location'] else 1,
                1 if 'AM' in slot_time.upper() else 0,
                0 if appointment_date.weekday() < 5 else 1,
                patient['age'],
                0 if query_db("SELECT gender FROM doctors WHERE id = ?", (doctor_id,), one=True)['gender'] == 'M' else 1,
                {'M': 0, 'F': 1, 'Other': 2}[patient['gender']],
                {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}[patient['marriage_status']],
                1 if patient['occupation'].strip() else 0,
                len(health_challenge)
            ]
            
            no_show_prob = predict_no_show(features)
            reschedule_prob = predict_reschedule(features)
            
            query_db("""
                INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, 
                booking_date, no_show_prob, reschedule_prob, status, health_challenge)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session['user_id'], hospital_id, department_id, doctor_id, slot_time, date_str,
                  booking_date.strftime('%Y-%m-%d'), no_show_prob, reschedule_prob, 'scheduled', health_challenge),
                commit=True)
            
            flash("Appointment booked successfully!", "success")
            return redirect(url_for('patient_dashboard'))
        except Exception as e:
            app.logger.error(f"Error booking appointment: {e}")
            flash("Error booking appointment", "danger")
    
    hospitals = query_db("SELECT * FROM hospitals WHERE subscription_status = 'active'")
>>>>>>> redesign
    return render_template('booking.html', hospitals=hospitals)

@app.route('/get_departments/<int:hospital_id>')
def get_departments(hospital_id):
    departments = query_db("SELECT id, name FROM departments WHERE hospital_id = ?", (hospital_id,))
    return jsonify([{'id': dept['id'], 'name': dept['name']} for dept in departments])

@app.route('/get_doctors/<int:department_id>')
def get_doctors(department_id):
    doctors = query_db("SELECT id, name FROM doctors WHERE department_id = ?", (department_id,))
    return jsonify([{'id': doc['id'], 'name': doc['name']} for doc in doctors])

@app.route('/get_available_slots')
@login_required(['patient'])
def get_available_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    
    if not doctor_id or not date:
        return jsonify({'error': 'Missing parameters'}), 400
    
    all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
    booked_slots = [a['slot_time'] for a in query_db(
        "SELECT slot_time FROM appointments WHERE doctor_id = ? AND date = ? AND status != 'closed'",
        (doctor_id, date)
    )]
    
    available_slots = [slot for slot in all_slots 
                      if slot not in booked_slots and is_doctor_available(doctor_id, date, slot)]
    
    return jsonify(available_slots)

@app.route('/super_admin')
@login_required(['super_admin'])
def super_admin():
    search = request.args.get('search', '')
    query = """
    SELECT h.*, 
           (SELECT COUNT(*) FROM departments d WHERE d.hospital_id = h.id) AS dept_count,
           (SELECT COUNT(*) FROM doctors doc WHERE doc.hospital_id = h.id) AS doc_count
    FROM hospitals h
    """
    args = []
    if search:
        query += " WHERE h.name LIKE ? OR h.location LIKE ?"
        args.extend([f"%{search}%", f"%{search}%"])
    
    hospitals = query_db(query, args)
    for h in hospitals:
        print(f"Hospital ID: {h['id']}, Status: {h['subscription_status']}")  # Debug print
    return render_template('super_admin.html', hospitals=hospitals, search=search)

@app.route('/search_appointments')
@login_required(['hospital_admin'])
<<<<<<< HEAD
def search_appointments():
    user_id = session['user_id']
    hospital = query_db("SELECT hospital_id, name FROM hospitals WHERE id = (SELECT hospital_id FROM users WHERE id = ?)", (user_id,), one=True)
    if not hospital:
        return jsonify({'error': 'Hospital not found'}), 404
    search_query = request.args.get('search', '').strip()
    search_type = request.args.get('search_type', 'name')
    if not search_query:
        return jsonify([])
    
    query = """
        SELECT a.id, a.patient_name, a.date 
        FROM appointments a
        JOIN users u ON a.user_id = u.id
        WHERE a.hospital_id = ? AND 
    """
    params = [hospital['hospital_id']]
    if search_type == 'name':
        query += "a.patient_name LIKE ?"
        params.append(f"%{search_query}%")
    elif search_type == 'email':
        query += "u.email LIKE ?"
        params.append(f"%{search_query}%")
    elif search_type == 'department':
        query += "a.department_id IN (SELECT id FROM departments WHERE name LIKE ?)"
        params.append(f"%{search_query}%")
    elif search_type == 'doctor':
        query += "a.doctor_id IN (SELECT id FROM doctors WHERE name LIKE ?)"
        params.append(f"%{search_query}%")
    else:
        return jsonify([])

    appointments = query_db(query, params)
    return jsonify(appointments)
=======
def hospital_admin_dashboard():
    hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
    
    search = request.args.get('search', '')
    search_type = request.args.get('search_type', 'name')
    
    query = """
    SELECT a.id, u.name AS patient_name, u.email, d.name AS department, doc.name AS doctor, 
           a.slot_time, a.date, a.no_show_prob, a.reschedule_prob, a.status
    FROM appointments a
    JOIN users u ON a.patient_id = u.id
    JOIN departments d ON a.department_id = d.id
    JOIN doctors doc ON a.doctor_id = doc.id
    WHERE a.hospital_id = ?
    """
    args = [hospital_id]
    
    if search:
        if search_type == 'name':
            query += " AND u.name LIKE ?"
        elif search_type == 'email':
            query += " AND u.email LIKE ?"
        elif search_type == 'department':
            query += " AND d.name LIKE ?"
        elif search_type == 'doctor':
            query += " AND doc.name LIKE ?"
        args.append(f"%{search}%")
    
    appointments = query_db(query, args)
    return render_template('hospital_admin.html', appointments=appointments, search=search, search_type=search_type)
>>>>>>> redesign

@app.route('/hospital_register', methods=['GET', 'POST'])
@login_required(['super_admin'])
def hospital_register():
    if request.method == 'POST':
        try:
            hospital_id = query_db(
                "INSERT INTO hospitals (name, location, subscription_status) VALUES (?, ?, ?)",
                (request.form['hospital_name'], request.form['location'], 'suspended'),
                commit=True, return_id=True
            )
            query_db(
                "INSERT INTO users (name, email, password, role, hospital_id) VALUES (?, ?, ?, ?, ?)",
                (request.form['admin_name'], request.form['admin_email'], 
                 generate_password_hash(request.form['admin_password']), 'hospital_admin', hospital_id),
                commit=True
            )
            flash("Hospital registered successfully and set to suspended status.", "success")
            return redirect(url_for('super_admin'))
        except Exception as e:
            flash(f"Error registering hospital: {str(e)}", "danger")
    return render_template('hospital_register.html')

<<<<<<< HEAD
@app.route('/hospital_admin')
@login_required(['hospital_admin'])
def hospital_admin():
    user_id = session['user_id']
    hospital = query_db("SELECT hospital_id, name FROM hospitals WHERE id = (SELECT hospital_id FROM users WHERE id = ?)", (user_id,), one=True)
    if not hospital:
        return redirect(url_for('index'))
    appointments = query_db("""
        SELECT a.id, a.patient_name, u.email, d.name as dept_name, doc.name as doc_name, a.time, a.date, a.no_show_prob, a.reschedule_prob, a.status
        FROM appointments a
        JOIN users u ON a.user_id = u.id
        JOIN departments d ON a.department_id = d.id
        JOIN doctors doc ON a.doctor_id = doc.id
        WHERE a.hospital_id = ?
        ORDER BY a.date DESC
    """, (hospital['hospital_id'],))
    return render_template('hospital_admin.html', appointments=appointments, hospital_name=hospital['name'])

@app.route('/manage_departments', methods=['GET', 'POST'])
@login_required(['hospital_admin'])
def manage_departments():
    user_id = session['user_id']
    hospital = query_db("SELECT hospital_id FROM users WHERE id = ?", (user_id,), one=True)
    hospital_id = hospital['hospital_id']
    
    if request.method == 'POST':
        if 'delete_dept' in request.form:
            dept_id = request.form['dept_id']
            doctors = query_db("SELECT id FROM doctors WHERE department_id = ?", (dept_id,))
            appointments = query_db("SELECT id FROM appointments WHERE department_id = ?", (dept_id,))
            if doctors or appointments:
                return jsonify({'success': False, 'message': 'Cannot delete department with existing doctors or appointments.'})
            query_db("DELETE FROM departments WHERE id = ? AND hospital_id = ?", (dept_id, hospital_id), commit=True)
            return jsonify({'success': True, 'message': 'Department deleted successfully.'})
        
        if 'add_doctor' in request.form:
            dept_id = request.form['dept_id']
            doctor_name = request.form['doctor_name']
            doctor_gender = request.form['doctor_gender']
            start_day = request.form['start_day'].lower()
            end_day = request.form['end_day'].lower()
            start_time = request.form['start_time'].lower()
            end_time = request.form['end_time'].lower()
            try:
                start_hour = normalize_schedule_time(start_time)
                end_hour = normalize_schedule_time(end_time)
                schedule = f"{start_day}-{end_day} {start_hour}-{end_hour}"
            except ValueError as e:
                return jsonify({'success': False, 'message': f"Invalid time format: {e}"})
            query_db(
                "INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                (hospital_id, dept_id, doctor_name, doctor_gender, schedule), commit=True
            )
            return jsonify({'success': True, 'message': 'Doctor added successfully.'})
        
        if 'edit_doctor' in request.form:
            doctor_id = request.form['doctor_id']
            doctor_name = request.form['doctor_name']
            doctor_gender = request.form['doctor_gender']
            start_day = request.form['start_day'].lower()
            end_day = request.form['end_day'].lower()
            start_time = request.form['start_time'].lower()
            end_time = request.form['end_time'].lower()
            try:
                start_hour = normalize_schedule_time(start_time)
                end_hour = normalize_schedule_time(end_time)
                schedule = f"{start_day}-{end_day} {start_hour}-{end_hour}"
            except ValueError as e:
                return jsonify({'success': False, 'message': f"Invalid time format: {e}"})
            query_db(
                "UPDATE doctors SET name = ?, gender = ?, schedule = ? WHERE id = ? AND hospital_id = ?",
                (doctor_name, doctor_gender, schedule, doctor_id, hospital_id), commit=True
            )
            return jsonify({'success': True, 'message': 'Doctor updated successfully.'})
        
        if 'delete_doctor' in request.form:
            doctor_id = request.form['doctor_id']
            appointments = query_db("SELECT id FROM appointments WHERE doctor_id = ?", (doctor_id,))
            if appointments:
                return jsonify({'success': False, 'message': 'Cannot delete doctor with existing appointments.'})
            query_db("DELETE FROM doctors WHERE id = ? AND hospital_id = ?", (doctor_id, hospital_id), commit=True)
            return jsonify({'success': True, 'message': 'Doctor deleted successfully.'})
    
=======
@app.route('/manage_departments', methods=['GET', 'POST'])
@login_required(['hospital_admin'])
def manage_departments():
    hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
    if request.method == 'POST':
        if 'add_department' in request.form:
            query_db("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", 
                     (hospital_id, request.form['name']), commit=True)
            flash("Department added successfully", "success")
            return redirect(url_for('manage_departments'))
        # Other POST logic (delete_department, add_doctor, delete_doctor)
>>>>>>> redesign
    departments = query_db("SELECT id, name FROM departments WHERE hospital_id = ?", (hospital_id,))
    dept_doctors = {dept['id']: query_db("SELECT id, name, gender, schedule FROM doctors WHERE department_id = ?", (dept['id'],)) for dept in departments}
    return render_template('manage_departments.html', departments=departments, dept_doctors=dept_doctors)

@app.route('/suspend_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def suspend_hospital(hospital_id):
    query_db("UPDATE hospitals SET subscription_status = 'suspended' WHERE id = ?", (hospital_id,), commit=True)
    flash("Hospital suspended", "success")
    return redirect(url_for('super_admin'))

@app.route('/activate_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def activate_hospital(hospital_id):
    expiry_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
    query_db("UPDATE hospitals SET subscription_status = 'active', subscription_expiry_date = ? WHERE id = ?", 
             (expiry_date, hospital_id), commit=True)
    flash("Hospital activated", "success")
    return redirect(url_for('super_admin'))

@app.route('/delete_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def delete_hospital(hospital_id):
    has_users = query_db("SELECT COUNT(*) as count FROM users WHERE hospital_id = ?", (hospital_id,), one=True)['count'] > 0
    has_departments = query_db("SELECT COUNT(*) as count FROM departments WHERE hospital_id = ?", (hospital_id,), one=True)['count'] > 0
    has_doctors = query_db("SELECT COUNT(*) as count FROM doctors WHERE hospital_id = ?", (hospital_id,), one=True)['count'] > 0
    has_appointments = query_db("SELECT COUNT(*) as count FROM appointments WHERE hospital_id = ?", (hospital_id,), one=True)['count'] > 0

    if has_users or has_departments or has_doctors or has_appointments:
        flash("Cannot delete hospital with associated users, departments, doctors, or appointments.", "danger")
    else:
        query_db("DELETE FROM hospitals WHERE id = ?", (hospital_id,), commit=True)
        flash("Hospital deleted successfully.", "success")
    return redirect(url_for('super_admin'))

@app.route('/reschedule_patient/<int:appt_id>', methods=['POST'])
@login_required(['patient'])
def reschedule_patient(appt_id):
    appointment = query_db("SELECT * FROM appointments WHERE id = ? AND patient_id = ?", 
                          (appt_id, session['user_id']), one=True)
    if not appointment:
        flash("Appointment not found", "danger")
        return redirect(url_for('patient_dashboard'))
    
    new_date = request.form['date']
    new_time = request.form['time']
    
    if not is_doctor_available(appointment['doctor_id'], new_date, new_time):
        flash("Slot not available", "danger")
        return redirect(url_for('patient_dashboard'))
<<<<<<< HEAD
    existing = query_db(
        "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'closed'",
        (appointment['doctor_id'], new_date, new_time), one=True
    )
    if existing:
        flash("Selected slot is already booked.", "danger")
        return redirect(url_for('patient_dashboard'))
    patient = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (appointment['hospital_id'],), one=True)['location']
    appointment_date = pd.to_datetime(new_date)
    current_date = pd.to_datetime(date.today())
    lead_time = (appointment_date - current_date).days
    distance = 0 if patient['location'] == hospital_location else 1
    time_of_day = 1 if 'AM' in new_time.upper() else 0
    is_weekday = 0 if appointment_date.weekday() < 5 else 1
    patient_gender = {'M': 0, 'F': 1, 'Other': 2}.get(patient['gender'], 2)
    marriage_status = {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}.get(patient['marriage_status'], 0)
    has_occupation = 1 if patient['occupation'] and patient['occupation'].strip() else 0
    doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (appointment['doctor_id'],), one=True)['gender']
    doctor_gender_val = 0 if doctor_gender == 'M' else 1
    health_challenge = appointment['health_challenge'] or ''
    health_challenge_length = len(health_challenge) if health_challenge else 0
    past_appointments = query_db("SELECT status FROM appointments WHERE patient_id = ? AND date < ?", (user_id, new_date))
    previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')
    features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, patient['age'], doctor_gender_val,
                patient_gender, marriage_status, has_occupation, health_challenge_length]
    no_show_prob = predict_no_show(features)
    reschedule_prob = predict_reschedule(features)
    query = "UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? WHERE id = ?"
    query_db(query, (new_date, new_time, no_show_prob, reschedule_prob, appt_id), commit=True)
    flash("Appointment rescheduled successfully.", "success")
    return redirect(url_for('patient_dashboard'))

@app.route('/update_profile', methods=['POST'])
@login_required(['patient'])
def update_profile():
    user_id = session['user_id']
    occupation = request.form['occupation']
    location = request.form['location']
    age = int(request.form['age'])
    query = "UPDATE users SET occupation = ?, location = ?, age = ? WHERE id = ?"
    query_db(query, (occupation, location, age, user_id), commit=True)
    flash("Profile updated successfully.", "success")
=======
    
    query_db("UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled' WHERE id = ?", 
             (new_date, new_time, appt_id), commit=True)
    flash("Appointment rescheduled", "success")
>>>>>>> redesign
    return redirect(url_for('patient_dashboard'))

@app.route('/mark_attended/<int:appt_id>', methods=['POST'])
@login_required(['hospital_admin'])
def mark_attended(appt_id):
    query_db("UPDATE appointments SET status = 'attended' WHERE id = ?", (appt_id,), commit=True)
    flash("Appointment marked as attended", "success")
    return redirect(url_for('hospital_admin_dashboard'))

<<<<<<< HEAD
@app.route('/reschedule/<int:appt_id>', methods=['POST'])
@login_required(['hospital_admin'])
def reschedule(appt_id):
    appointment = query_db("SELECT * FROM appointments WHERE id = ?", (appt_id,), one=True)
    if not appointment:
        flash("Appointment not found.", "danger")
        return redirect(url_for('hospital_admin_dashboard'))
    new_date = request.form['date']
    new_time = request.form['time']
    if not is_doctor_available(appointment['doctor_id'], new_date, new_time):
        flash("Selected doctor is not available at this time.", "danger")
        return redirect(url_for('hospital_admin_dashboard'))
    existing = query_db(
        "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'closed'",
        (appointment['doctor_id'], new_date, new_time), one=True
    )
    if existing:
        flash("Selected slot is already booked.", "danger")
        return redirect(url_for('hospital_admin_dashboard'))
    patient = query_db("SELECT * FROM users WHERE id = ?", (appointment['patient_id'],), one=True)
    hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (appointment['hospital_id'],), one=True)['location']
    appointment_date = pd.to_datetime(new_date)
    current_date = pd.to_datetime(date.today())
    lead_time = (appointment_date - current_date).days
    distance = 0 if patient['location'] == hospital_location else 1
    time_of_day = 1 if 'AM' in new_time.upper() else 0
    is_weekday = 0 if appointment_date.weekday() < 5 else 1
    doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (appointment['doctor_id'],), one=True)['gender']
    doctor_gender_val = 0 if doctor_gender == 'M' else 1
    patient_gender = {'M': 0, 'F': 1, 'Other': 2}.get(patient['gender'], 2)
    marriage_status = {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}.get(patient['marriage_status'], 0)
    has_occupation = 1 if patient['occupation'] and patient['occupation'].strip() else 0
    health_challenge = appointment['health_challenge'] or ''
    health_challenge_length = len(health_challenge) if health_challenge else 0
    past_appointments = query_db("SELECT status FROM appointments WHERE patient_id = ? AND date < ?", (appointment['patient_id'], new_date))
    previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')
    features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, patient['age'], doctor_gender_val,
                patient_gender, marriage_status, has_occupation, health_challenge_length]
    no_show_prob = predict_no_show(features)
    reschedule_prob = predict_reschedule(features)
    query = "UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? WHERE id = ?"
    query_db(query, (new_date, new_time, no_show_prob, reschedule_prob, appt_id), commit=True)
    appointment_details = {
        'hospital_name': query_db("SELECT name FROM hospitals WHERE id = ?", (appointment['hospital_id'],), one=True)['name'],
        'department_name': query_db("SELECT name FROM departments WHERE id = ?", (appointment['department_id'],), one=True)['name'],
        'doctor_name': query_db("SELECT name FROM doctors WHERE id = ?", (appointment['doctor_id'],), one=True)['name'],
        'date': new_date,
        'slot_time': new_time
    }
    send_reschedule_notification(patient['email'], appointment_details)
    flash("Appointment rescheduled successfully.", "success")
    return redirect(url_for('hospital_admin_dashboard'))

# Function to send reschedule notification email
def send_reschedule_notification(email, appointment_details):
    subject = "Your Appointment Has Been Rescheduled"
    body = (
        f"Dear Patient,\n\n"
        f"Your appointment has been rescheduled.\n"
        f"Hospital: {appointment_details.get('hospital_name', '')}\n"
        f"Department: {appointment_details.get('department_name', '')}\n"
        f"Doctor: {appointment_details.get('doctor_name', '')}\n"
        f"Date: {appointment_details.get('date', '')}\n"
        f"Time: {appointment_details.get('slot_time', '')}\n\n"
        f"Thank you."
    )
    try:
        msg = Message(subject, recipients=[email], body=body)
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Failed to send reschedule notification: {e}")
=======
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for('index'))
>>>>>>> redesign

if __name__ == '__main__':
    init_db()
    scheduler = BackgroundScheduler()
<<<<<<< HEAD
    scheduler.add_job(check_no_shows_and_reschedule, 'cron', hour=8, minute=0)
=======
    scheduler.add_job(check_no_shows_and_reschedule, 'cron', hour=8)
>>>>>>> redesign
    scheduler.start()
    app.run(debug=True, use_reloader=False)