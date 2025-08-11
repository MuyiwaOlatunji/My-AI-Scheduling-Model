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
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
import re

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Flask-Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME", "lrdmuyi85@gmail.com")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD", "fjqdyzjlfudatoky")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER", "lrdmuyi85@gmail.com")
mail = Mail(app)

# Logging configuration
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Authentication decorator
def login_required(roles=None):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not session.get('user_id'):
                flash("Please log in to access this page.", "danger")
                return redirect(url_for('login'))
            if roles and session.get('role') not in roles:
                flash("You do not have permission to access this page.", "danger")
                if session.get('role') == 'patient':
                    return redirect(url_for('patient_dashboard'))
                elif session.get('role') == 'hospital_admin':
                    return redirect(url_for('hospital_admin_dashboard'))
                elif session.get('role') == 'super_admin':
                    return redirect(url_for('super_admin_dashboard'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

# Database configuration
def get_sqlite_conn():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

# Database initialization
def init_db():
    conn = get_sqlite_conn()
    c = conn.cursor()
    # Create tables if they don't exist
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

    # Seed initial data only if no users exist
    if not query_db("SELECT COUNT(*) FROM users", one=True)['COUNT(*)']:
        # Seed hospitals with subscription data
        hospitals = [
            ("Lagos General Hospital", "Lagos", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
            ("Abuja Medical Center", "Abuja", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
        ]
        c.executemany("INSERT INTO hospitals (name, location, subscription_status, subscription_expiry_date) VALUES (?, ?, ?, ?)", hospitals)
        
        # Seed super admin and patient
        admin_email = "admin@example.com"
        admin_password = generate_password_hash("adminpassword")
        patient_email = "patient@example.com"
        patient_password = generate_password_hash("patientpassword")
        c.execute("INSERT INTO users (name, email, phone, password, role, age) VALUES (?, ?, ?, ?, ?, ?)",
                  ("Super Admin", admin_email, "1234567890", admin_password, "super_admin", 30))
        c.execute("INSERT INTO users (name, email, phone, password, role, age, location, gender, marriage_status, occupation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  ("Test Patient", patient_email, "0987654321", patient_password, "patient", 25, "Lagos", "M", "Single", "Engineer"))
        
        # Seed sample departments and doctors
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (1, "Cardiology"))
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (2, "Neurology"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (1, 1, "Dr. Jane Smith", "F", "mon-fri 9-17"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (2, 2, "Dr. John Brown", "M", "mon-fri 10-18"))
        conn.commit()

    conn.close()

# Database query helper
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

# Normalize schedule format (e.g., '8:00am' -> '8', '5:00pm' -> '17')
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

# Check doctor availability based on schedule
def is_doctor_available(doctor_id, date, time_slot):
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT schedule FROM doctors WHERE id = ?", (doctor_id,))
    schedule = cursor.fetchone()
    if not schedule:
        return False
    
    schedule = schedule[0].lower()
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
            app.logger.info(f"Doctor not available on {date_obj.strftime('%a')} for schedule {schedule}")
            return False
        
        slot_time = datetime.strptime(time_slot, '%I:%M %p')
        slot_hour = slot_time.hour
        slot_minute = slot_time.minute
        
        if not (start_hour <= slot_hour < end_hour):
            app.logger.info(f"Slot {time_slot} (hour {slot_hour}:{slot_minute:02d}) outside doctor's hours {start_hour}-{end_hour}")
            return False
    
    except ValueError as e:
        app.logger.error(f"Error parsing schedule for doctor_id {doctor_id}: {e}")
        return False
    
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
                lead_time = (appointment_date - current_date_dt).days
                distance = 0 if 'Lagos' in hospital_location else 1
                time_of_day = 1 if 'AM' in new_time.upper() else 0
                is_weekday = 0 if appointment_date.weekday() < 5 else 1
                user_age = query_db("SELECT age FROM users WHERE id = ?", (patient_id,), one=True)['age']
                doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (doctor_id,), one=True)['gender']
                doctor_gender_val = 0 if doctor_gender == 'M' else 1
                features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, user_age, doctor_gender_val]
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

# Retrain the model with patient inputs
def retrain_model():
    with app.app_context():
        today = date.today().strftime('%Y-%m-%d')
        query = """
        SELECT a.*, u.age, h.location, doc.gender, a.health_challenge
        FROM appointments a
        JOIN users u ON a.patient_id = u.id
        JOIN hospitals h ON a.hospital_id = h.id
        JOIN doctors doc ON a.doctor_id = doc.id
        WHERE a.date < ? AND a.status IN ('attended', 'no_show')
        """
        past_appts = query_db(query, (today,))
        if not past_appts:
            app.logger.info("No past appointments to retrain the model.")
            return

        data = pd.DataFrame(past_appts)
        data['booking_date'] = pd.to_datetime(data['booking_date'])
        data['appointment_date'] = pd.to_datetime(data['date'])
        data['lead_time'] = (data['appointment_date'] - data['booking_date']).dt.days
        data['distance'] = data['location'].apply(lambda x: 0 if 'Lagos' in x else 1)
        data['time_of_day'] = data['slot_time'].apply(lambda x: 1 if 'AM' in x.upper() else 0)
        data['is_weekday'] = data['appointment_date'].dt.weekday.apply(lambda x: 0 if x < 5 else 1)
        data['doctor_gender'] = data['gender'].map({'M': 0, 'F': 1})
        data['no_show'] = data['status'].apply(lambda x: 1 if x == 'no_show' else 0)
        data['health_challenge_length'] = data['health_challenge'].apply(lambda x: len(x) if x else 0)

        features = ['lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender', 'health_challenge_length']
        X = data[features].fillna(0)
        y_no_show = data['no_show']

        # Retrain RandomForest for no-show
        rf_ns = RandomForestClassifier(n_estimators=100, random_state=42)
        rf_ns.fit(X, y_no_show)
        joblib.dump(rf_ns, 'model/rf_no_show_model.pkl')

        # Retrain XGBoost for no-show
        xgb_ns = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42)
        xgb_ns.fit(X, y_no_show)
        joblib.dump(xgb_ns, 'model/xgb_no_show_model.pkl')

        app.logger.info("Models retrained successfully.")

# Prediction functions using trained models
def predict_no_show(features):
    try:
        rf_model = joblib.load('model/rf_no_show_model.pkl')
        xgb_model = joblib.load('model/xgb_no_show_model.pkl')
        # Expected features based on training (adjust if needed)
        feature_cols = ['lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender']
        features_df = pd.DataFrame([features[:6]], columns=feature_cols)  # Use only common features
        rf_prob = rf_model.predict_proba(features_df)[0][1]
        xgb_prob = xgb_model.predict_proba(features_df)[0][1]
        ensemble_prob = (rf_prob + xgb_prob) / 2 * 100  # Scale to 0-100
        return ensemble_prob
    except Exception as e:
        app.logger.error(f"Error predicting no-show: {e}")
        return 10.0  # Fallback value

def predict_reschedule(features):
    try:
        rf_model = joblib.load('model/rf_reschedule_model.pkl')
        xgb_model = joblib.load('model/xgb_reschedule_model.pkl')
        # Expected features based on training (adjust if needed)
        feature_cols = ['lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender']
        features_df = pd.DataFrame([features[:6]], columns=feature_cols)  # Use only common features
        rf_prob = rf_model.predict_proba(features_df)[0][1]
        xgb_prob = xgb_model.predict_proba(features_df)[0][1]
        ensemble_prob = (rf_prob + xgb_prob) / 2 * 100  # Scale to 0-100
        return ensemble_prob
    except Exception as e:
        app.logger.error(f"Error predicting reschedule: {e}")
        return 10.0  # Fallback value

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        age = int(request.form.get('age', 30))
        location = request.form['location']
        gender = request.form['gender']
        marriage_status = request.form['marriage_status']
        occupation = request.form['occupation']
        password_hash = generate_password_hash(password)
        query = "INSERT INTO users (name, email, phone, password, role, age, location, gender, marriage_status, occupation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        try:
            query_db(query, (name, email, phone, password_hash, 'patient', age, location, gender, marriage_status, occupation), commit=True)
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = query_db("SELECT * FROM users WHERE email = ? AND role = 'patient'", (email,), one=True)
        app.logger.info(f"Login attempt for email: {email}, user found: {bool(user)}")
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash("Logged in successfully.", "success")
            return redirect(url_for('patient_dashboard'))
        flash("Invalid credentials or not a patient.", "danger")
    return render_template('login.html', title="Patient Login")

@app.route('/super_admin_login', methods=['GET', 'POST'])
def super_admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = query_db("SELECT * FROM users WHERE email = ? AND role = 'super_admin'", (email,), one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash("Logged in successfully.", "success")
            return redirect(url_for('super_admin_dashboard'))
        flash("Invalid credentials or not a super admin.", "danger")
    return render_template('login.html', title="Super Admin Login")

@app.route('/hospital_admin_login', methods=['GET', 'POST'])
def hospital_admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = query_db("SELECT * FROM users WHERE email = ? AND role = 'hospital_admin'", (email,), one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            hospital = query_db("SELECT subscription_status FROM hospitals WHERE id = ?", (user['hospital_id'],), one=True)
            if hospital and hospital['subscription_status'] != 'active':
                flash("Your hospital's subscription is not active. Contact support.", "danger")
                return redirect(url_for('logout'))
            flash("Logged in successfully.", "success")
            return redirect(url_for('hospital_admin_dashboard'))
        flash("Invalid credentials or not a hospital admin.", "danger")
    return render_template('login.html', title="Hospital Admin Login")

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('index'))

@app.route('/patient')
@login_required('patient')
def patient_dashboard():
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')
    if sort_by not in ['date', 'status']:
        sort_by = 'date'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
    app.logger.info(f"Fetching appointments for user_id: {session['user_id']}")
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT h.name, d.name, doc.name, a.date, a.slot_time, a.status, a.id
        FROM appointments a
        JOIN hospitals h ON a.hospital_id = h.id
        JOIN departments d ON a.department_id = d.id
        JOIN doctors doc ON a.doctor_id = doc.id
        WHERE a.patient_id = ?
        ORDER BY {} {}
    """.format(sort_by, sort_order), (session['user_id'],))
    appointments = cursor.fetchall()
    conn.close()
    app.logger.info(f"Found {len(appointments)} appointments for user_id: {session['user_id']}")
    
    return render_template('patient.html', appointments=appointments)

@app.route('/book', methods=['GET', 'POST'])
@login_required(['patient'])
def book_appointment():
    hospitals = query_db("SELECT * FROM hospitals WHERE subscription_status = 'active'")
    if request.method == 'POST':
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
        # Use only the features the models expect
        features = [lead_time, distance, time_of_day, is_weekday, patient['age'], doctor_gender_val]
        no_show_prob = predict_no_show(features)
        reschedule_prob = predict_reschedule(features)

        query = """
        INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, booking_date, no_show_prob, reschedule_prob, status, health_challenge)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        query_db(query, (patient_id, hospital_id, department_id, doctor_id, slot_time, date_str, booking_date, no_show_prob, reschedule_prob, 'scheduled', health_challenge), commit=True)
        flash("Appointment booked successfully.", "success")
        return redirect(url_for('patient_dashboard'))
    return render_template('booking.html', hospitals=hospitals)

@app.route('/get_departments/<int:hospital_id>')
def get_departments(hospital_id):
    departments = query_db("SELECT id, name FROM departments WHERE hospital_id = ?", (hospital_id,))
    return jsonify([(dept['id'], dept['name']) for dept in departments])

@app.route('/get_doctors/<int:department_id>')
def get_doctors(department_id):
    doctors = query_db("SELECT id, name FROM doctors WHERE department_id = ?", (department_id,))
    return jsonify([(doc['id'], doc['name']) for doc in doctors])

@app.route('/get_available_slots')
@login_required(['patient'])
def get_available_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    if not doctor_id or not date:
        return jsonify({'error': 'Doctor ID and date are required'})
    
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT schedule FROM doctors WHERE id = ?", (doctor_id,))
    schedule = cursor.fetchone()
    if not schedule:
        return jsonify({'error': 'Doctor not found'})
    
    schedule = schedule[0].lower()
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
            return jsonify({'error': 'Invalid doctor schedule'})
        
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        day_idx = date_obj.weekday()
        if not (start_day_idx <= day_idx <= end_day_idx):
            app.logger.info(f"No available slots for doctor_id {doctor_id} on {date}")
            return jsonify({'error': f'Doctor not available on {date_obj.strftime("%a")}'})
        
        slots = []
        current_time = datetime.strptime(f"{start_hour:02d}:00", "%H:%M")
        end_time = datetime.strptime(f"{end_hour:02d}:00", "%H:%M")
        while current_time < end_time:
            time_str = current_time.strftime("%I:%M %p").lstrip('0')
            if is_doctor_available(doctor_id, date, time_str):
                slots.append(time_str)
            current_time += timedelta(minutes=30)
    
    except ValueError as e:
        app.logger.error(f"Error parsing schedule for doctor_id {doctor_id}: {e}")
        return jsonify({'error': 'Invalid doctor schedule'})
    
    if not slots:
        app.logger.info(f"No available slots for doctor_id {doctor_id} on {date}")
        return jsonify([])
    
    return jsonify(slots)

@app.route('/check_slot')
@login_required(['patient'])
def check_slot():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    time = request.args.get('time')
    if not is_doctor_available(doctor_id, date, time):
        return jsonify({'available': False})
    existing = query_db(
        "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'closed'",
        (doctor_id, date, time), one=True
    )
    return jsonify({'available': not bool(existing)})

@app.route('/super_admin')
@login_required(['super_admin'])
def super_admin_dashboard():
    search_query = request.args.get('search', '')
    query = """
    SELECT h.*, COUNT(d.id) as dept_count, COUNT(doc.id) as doc_count, COUNT(a.id) as appt_count
    FROM hospitals h
    LEFT JOIN departments d ON h.id = d.hospital_id
    LEFT JOIN doctors doc ON h.id = doc.hospital_id
    LEFT JOIN appointments a ON h.id = a.hospital_id
    """
    args = []
    if search_query:
        query += " WHERE h.name LIKE ?"
        args.append(f"%{search_query}%")
    query += " GROUP BY h.id, h.name, h.location, h.subscription_status, h.subscription_expiry_date"
    hospitals = query_db(query, args)
    return render_template('super_admin.html', hospitals=hospitals, search_query=search_query)

@app.route('/hospital_admin')
@login_required(['hospital_admin'])
def hospital_admin_dashboard():
    user_id = session['user_id']
    user = query_db("SELECT hospital_id FROM users WHERE id = ?", (user_id,), one=True)
    hospital_id = user['hospital_id']
    search_query = request.args.get('search', '')
    search_type = request.args.get('search_type', 'name')
    query = """
    SELECT a.id, u.name, u.email, d.name AS department_name, doc.name AS doctor_name, 
           a.slot_time, a.date, a.no_show_prob, a.reschedule_prob, a.status 
    FROM appointments a 
    JOIN users u ON a.patient_id = u.id 
    JOIN departments d ON a.department_id = d.id 
    JOIN doctors doc ON a.doctor_id = doc.id 
    WHERE a.hospital_id = ?
    """
    args = [hospital_id]
    if search_query:
        if search_type == 'name':
            query += " AND u.name LIKE ?"
            args.append(f"%{search_query}%")
        elif search_type == 'email':
            query += " AND u.email LIKE ?"
            args.append(f"%{search_query}%")
        elif search_type == 'department':
            query += " AND d.name LIKE ?"
            args.append(f"%{search_query}%")
        elif search_type == 'doctor':
            query += " AND doc.name LIKE ?"
            args.append(f"%{search_query}%")
    appointments = query_db(query, args)
    formatted_appointments = [
        [appt['id'], appt['name'], appt['email'], appt['department_name'], appt['doctor_name'],
         appt['slot_time'], appt['date'], appt['no_show_prob'], appt['reschedule_prob'], appt['status']]
        for appt in appointments
    ]
    return render_template('hospital_admin.html', appointments=formatted_appointments, search_query=search_query, search_type=search_type)

@app.route('/hospital_register', methods=['GET', 'POST'])
@login_required(['super_admin'])
def hospital_register():
    if request.method == 'POST':
        hospital_name = request.form['hospital_name']
        location = request.form['location']
        admin_name = request.form['admin_name']
        admin_email = request.form['admin_email']
        admin_password = generate_password_hash(request.form['admin_password'])
        hospital_id = query_db(
            "INSERT INTO hospitals (name, location, subscription_status) VALUES (?, ?, 'pending')",
            (hospital_name, location), commit=True, return_id=True
        )
        query_db(
            "INSERT INTO users (name, email, password, role, hospital_id) VALUES (?, ?, ?, ?, ?)",
            (admin_name, admin_email, admin_password, 'hospital_admin', hospital_id), commit=True
        )
        flash("Hospital registered successfully.", "success")
        return redirect(url_for('super_admin_dashboard'))
    return render_template('hospital_register.html')

@app.route('/add_department', methods=['GET', 'POST'])
@login_required(['hospital_admin'])
def add_department():
    user_id = session['user_id']
    hospital = query_db("SELECT hospital_id FROM users WHERE id = ?", (user_id,), one=True)
    hospital_id = hospital['hospital_id']
    if request.method == 'POST':
        dept_name = request.form['name']
        query_db(
            "INSERT INTO departments (hospital_id, name) VALUES (?, ?)",
            (hospital_id, dept_name), commit=True
        )
        flash("Department added successfully.", "success")
        return redirect(url_for('manage_departments'))
    return render_template('add_department.html')

@app.route('/manage_departments', methods=['GET', 'POST'])
@login_required(['hospital_admin'])
def manage_departments():
    user_id = session['user_id']
    hospital = query_db("SELECT hospital_id FROM users WHERE id = ?", (user_id,), one=True)
    hospital_id = hospital['hospital_id']
    
    if request.method == 'POST' and 'delete_dept' in request.form:
        dept_id = request.form['dept_id']
        doctors = query_db("SELECT id FROM doctors WHERE department_id = ?", (dept_id,))
        appointments = query_db("SELECT id FROM appointments WHERE department_id = ?", (dept_id,))
        if doctors or appointments:
            flash("Cannot delete department with existing doctors or appointments.", "danger")
        else:
            query_db("DELETE FROM departments WHERE id = ? AND hospital_id = ?", (dept_id, hospital_id), commit=True)
            flash("Department deleted successfully.", "success")
        return redirect(url_for('manage_departments'))
    
    if request.method == 'POST' and 'add_doctor' in request.form:
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
            flash(f"Invalid time format: {e}", "danger")
            return redirect(url_for('manage_departments'))
        query_db(
            "INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
            (hospital_id, dept_id, doctor_name, doctor_gender, schedule), commit=True
        )
        flash("Doctor added successfully.", "success")
        return redirect(url_for('manage_departments'))
    
    if request.method == 'POST' and 'delete_doctor' in request.form:
        doctor_id = request.form['doctor_id']
        appointments = query_db("SELECT id FROM appointments WHERE doctor_id = ?", (doctor_id,))
        if appointments:
            flash("Cannot delete doctor with existing appointments.", "danger")
        else:
            query_db("DELETE FROM doctors WHERE id = ? AND hospital_id = ?", (doctor_id, hospital_id), commit=True)
            flash("Doctor deleted successfully.", "success")
        return redirect(url_for('manage_departments'))
    
    departments = query_db("SELECT id, name FROM departments WHERE hospital_id = ?", (hospital_id,))
    dept_doctors = {}
    for dept in departments:
        doctors = query_db("SELECT id, name, gender, schedule FROM doctors WHERE department_id = ?", (dept['id'],))
        dept_doctors[dept['id']] = doctors
    return render_template('manage_departments.html', departments=departments, dept_doctors=dept_doctors)

@app.route('/suspend_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def suspend_hospital(hospital_id):
    query_db("UPDATE hospitals SET subscription_status = 'suspended' WHERE id = ?", (hospital_id,), commit=True)
    flash("Hospital suspended.", "success")
    return redirect(url_for('super_admin_dashboard'))

@app.route('/activate_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def activate_hospital(hospital_id):
    expiry_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
    query_db("UPDATE hospitals SET subscription_status = 'active', subscription_expiry_date = ? WHERE id = ?",
             (expiry_date, hospital_id), commit=True)
    flash("Hospital activated.", "success")
    return redirect(url_for('super_admin_dashboard'))

@app.route('/delete_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def delete_hospital(hospital_id):
    appts = query_db("SELECT id FROM appointments WHERE hospital_id = ?", (hospital_id,))
    if appts:
        flash("Cannot delete hospital with existing appointments.", "danger")
    else:
        query_db("DELETE FROM hospitals WHERE id = ?", (hospital_id,), commit=True)
        query_db("DELETE FROM users WHERE hospital_id = ?", (hospital_id,), commit=True)
        flash("Hospital deleted.", "success")
    return redirect(url_for('super_admin_dashboard'))

@app.route('/reschedule_patient/<int:appt_id>', methods=['POST'])
@login_required(['patient'])
def reschedule_patient(appt_id):
    user_id = session['user_id']
    appointment = query_db("SELECT * FROM appointments WHERE id = ? AND patient_id = ?", (appt_id, user_id), one=True)
    if not appointment:
        flash("Appointment not found or you do not have permission.", "danger")
        return redirect(url_for('patient_dashboard'))
    new_date = request.form['date']
    new_time = request.form['time']
    if not is_doctor_available(appointment['doctor_id'], new_date, new_time):
        flash("Selected doctor is not available at this time.", "danger")
        return redirect(url_for('patient_dashboard'))
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
    patient_gender = {'M': 0, 'F': 1, 'Other': 2}[patient['gender']]
    marriage_status = {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}[patient['marriage_status']]
    has_occupation = 1 if patient['occupation'].strip() else 0
    doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (appointment['doctor_id'],), one=True)['gender']
    doctor_gender_val = 0 if doctor_gender == 'M' else 1
    health_challenge = appointment['health_challenge']
    health_challenge_length = len(health_challenge)
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
    return redirect(url_for('patient_dashboard'))

@app.route('/mark_attended/<int:appt_id>', methods=['POST'])
@login_required(['hospital_admin'])
def mark_attended(appt_id):
    query_db("UPDATE appointments SET status = 'attended' WHERE id = ?", (appt_id,), commit=True)
    flash("Appointment marked as attended.", "success")
    return redirect(url_for('hospital_admin_dashboard'))

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
    # Use only the features the models expect
    features = [lead_time, distance, time_of_day, is_weekday, patient['age'], doctor_gender_val]
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

if __name__ == '__main__':
    init_db()
    # Retrain models on startup
    retrain_model()
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_no_shows_and_reschedule, 'cron', hour=8, minute=0)
    scheduler.add_job(retrain_model, 'cron', day_of_week='sun', hour=2, minute=0)
    scheduler.start()
    app.run(debug=True, use_reloader=False)