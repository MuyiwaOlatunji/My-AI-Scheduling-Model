from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_mail import Mail, Message
import sqlite3
import pandas as pd
import numpy as np
import os
import random
from model.panrpm_model import predict_no_show, predict_reschedule
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
def login_required(role=None):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not session.get('user_id'):
                flash("Please log in to access this page.", "danger")
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash("You do not have permission to access this page.", "danger")
                if session.get('role') == 'patient':
                    return redirect(url_for('patient_dashboard'))
                elif session.get('role') == 'admin':
                    return redirect(url_for('admin_dashboard'))
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
    # Drop existing hospitals table to remove UNIQUE constraint
    c.execute("DROP TABLE IF EXISTS hospitals")
    # Recreate hospitals table without UNIQUE constraint on location
    c.execute('''CREATE TABLE hospitals 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, location TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, phone TEXT, password TEXT, role TEXT, age INTEGER)''')
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

    # Seed hospitals
    hospitals = [
        ("Lagos General Hospital", "Lagos"), ("Abuja Medical Center", "Abuja"), ("Kano Health Clinic", "Kano"),
        ("Ibadan Community Hospital", "Ibadan"), ("Port Harcourt Specialist Hospital", "Port Harcourt"),
        ("Enugu Regional Hospital", "Enugu"), ("Benin City Medical Center", "Benin City"),
        ("Kaduna General Hospital", "Kaduna"), ("Jos University Teaching Hospital", "Jos"),
        ("Calabar Specialist Clinic", "Calabar")
    ]
    c.executemany("INSERT OR IGNORE INTO hospitals (name, location) VALUES (?, ?)", hospitals)
    conn.commit()

    # Seed departments
    hospital_ids = [row['id'] for row in c.execute("SELECT id FROM hospitals").fetchall()]
    department_names = ["Cardiology", "Pediatrics", "Orthopedics", "Neurology", "General Medicine",
                        "Gynecology", "Surgery", "Oncology", "Dermatology", "Radiology"]
    for hospital_id in hospital_ids:
        for i in range(4):
            dept_name = department_names[i % len(department_names)]
            c.execute("INSERT OR IGNORE INTO departments (hospital_id, name) VALUES (?, ?)", (hospital_id, dept_name))
    conn.commit()

    # Seed admin user
    admin_email = "admin@example.com"
    admin_password = generate_password_hash("adminpassword", method='pbkdf2:sha256')
    c.execute("INSERT OR IGNORE INTO users (name, email, phone, password, role, age) VALUES (?, ?, ?, ?, ?, ?)",
              ("Admin User", admin_email, "1234567890", admin_password, "admin", 30))
    conn.commit()

    # Seed doctors
    doctor_names = [
        "Dr. John Adebayo", "Dr. Aisha Bello", "Dr. Emeka Okon", "Dr. Fatima Musa", "Dr. Chioma Obi",
        "Dr. Tunde Ade", "Dr. Grace Eke", "Dr. Musa Ibrahim", "Dr. Ngozi Eze", "Dr. Ahmed Yusuf"
    ]
    schedules = ["Mon-Fri 9-5", "Mon-Wed 8-4", "Tue-Thu 10-6"]
    for dept in c.execute("SELECT id, hospital_id FROM departments").fetchall():
        dept_id = dept['id']
        hospital_id = dept['hospital_id']
        for i in range(3):
            doc_name = doctor_names[i % len(doctor_names)]
            schedule = random.choice(schedules)
            gender = random.choice(['M', 'F'])
            c.execute("INSERT OR IGNORE INTO doctors (hospital_id, department_id, name, schedule, gender) VALUES (?, ?, ?, ?, ?)",
                      (hospital_id, dept_id, doc_name, schedule, gender))
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
            conn.rollback()  # Roll back transaction on error
            raise e
        return None if one else []
    finally:
        conn.close()

# Send email notification
def send_reschedule_notification(patient_email, appointment_details):
    subject = "Appointment Rescheduled"
    body = f"""
    Dear Patient,
    Your appointment has been rescheduled. New details:
    - Hospital: {appointment_details['hospital_name']}
    - Department: {appointment_details['department_name']}
    - Doctor: {appointment_details['doctor_name']}
    - Date: {appointment_details['date']}
    - Time: {appointment_details['slot_time']}
    Please ensure you attend this appointment.
    Regards,
    Patient Appointment System
    """
    msg = Message(subject, recipients=[patient_email], body=body)
    try:
        mail.send(msg)
        app.logger.info(f"Reschedule notification sent to {patient_email}")
    except Exception as e:
        app.logger.error(f"Failed to send email to {patient_email}: {e}")

# Find available slot for rescheduling
def find_available_slot(doctor_id, current_date, patient_id, max_attempts=7):
    all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
    current_date_dt = pd.to_datetime(current_date)
    for days_ahead in range(1, max_attempts + 1):
        new_date = (current_date_dt + pd.Timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        existing_appts = query_db(
            "SELECT slot_time FROM appointments WHERE doctor_id = ? AND date = ? AND status != 'closed'",
            (doctor_id, new_date)
        )
        booked_slots = [appt['slot_time'] for appt in existing_appts]
        for slot in all_slots:
            if slot not in booked_slots:
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
        SELECT a.*, u.age, h.location, doc.gender
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

        features = ['lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender']
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
        password_hash = generate_password_hash(password)
        query = "INSERT INTO users (name, email, phone, password, role, age) VALUES (?, ?, ?, ?, ?, ?)"
        try:
            query_db(query, (name, email, phone, password_hash, 'patient', age), commit=True)
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
        user = query_db("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash("Logged in successfully.", "success")
            return redirect(url_for('patient_dashboard' if user['role'] == 'patient' else 'admin_dashboard'))
        flash("Invalid credentials.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('index'))

@app.route('/patient')
@login_required('patient')
def patient_dashboard():
    user_id = session['user_id']
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')
    query = """
    SELECT a.id, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name, a.slot_time, a.date, a.status 
    FROM appointments a 
    JOIN hospitals h ON a.hospital_id = h.id 
    JOIN departments d ON a.department_id = d.id 
    JOIN doctors doc ON a.doctor_id = doc.id 
    WHERE a.patient_id = ?
    """
    if sort_by in ['date', 'status']:
        query += f" ORDER BY {sort_by} {'ASC' if sort_order == 'asc' else 'DESC'}"
    appointments = query_db(query, (user_id,))
    reordered_appointments = [
        (appt['hospital_name'], appt['department_name'], appt['doctor_name'], appt['date'], appt['slot_time'], appt['status'])
        for appt in appointments
    ]
    return render_template('patient.html', appointments=reordered_appointments)

@app.route('/book', methods=['GET', 'POST'])
@login_required('patient')
def book_appointment():
    hospitals = query_db("SELECT * FROM hospitals")
    if request.method == 'POST':
        patient_id = session['user_id']
        hospital_id = request.form['hospital']
        department_id = request.form['department']
        doctor_id = request.form['doctor']
        date_str = request.form['date']
        slot_time = request.form['time']
        booking_date = date.today().strftime('%Y-%m-%d')

        appointment_date = pd.to_datetime(date_str)
        current_date = pd.to_datetime(date.today())
        max_date = current_date + relativedelta(years=1)
        if appointment_date < current_date or appointment_date > max_date:
            flash("Invalid date range.", "danger")
            return redirect(url_for('book_appointment'))

        past_appointments = query_db(
            "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
            (patient_id, date_str)
        )
        previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')
        hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)['location']
        lead_time = (appointment_date - pd.to_datetime(booking_date)).days
        distance = 0 if 'Lagos' in hospital_location else 1
        time_of_day = 1 if 'AM' in slot_time.upper() else 0
        is_weekday = 0 if appointment_date.weekday() < 5 else 1
        user_age = query_db("SELECT age FROM users WHERE id = ?", (patient_id,), one=True)['age']
        doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (doctor_id,), one=True)['gender']
        doctor_gender_val = 0 if doctor_gender == 'M' else 1
        features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, user_age, doctor_gender_val]
        no_show_prob = predict_no_show(features)
        reschedule_prob = predict_reschedule(features)

        query = """
        INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, booking_date, no_show_prob, reschedule_prob, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        query_db(query, (patient_id, hospital_id, department_id, doctor_id, slot_time, date_str, booking_date, no_show_prob, reschedule_prob, 'scheduled'), commit=True)
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
@login_required('patient')
def get_available_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
    existing_appts = query_db(
        "SELECT slot_time FROM appointments WHERE doctor_id = ? AND date = ? AND status != 'closed'",
        (doctor_id, date)
    )
    booked_slots = [appt['slot_time'] for appt in existing_appts]
    available_slots = [slot for slot in all_slots if slot not in booked_slots]
    return jsonify(available_slots)

@app.route('/check_slot')
@login_required('patient')
def check_slot():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    time = request.args.get('time')
    existing = query_db(
        "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'closed'",
        (doctor_id, date, time), one=True
    )
    return jsonify({'available': not bool(existing)})

@app.route('/admin')
@login_required('admin')
def admin_dashboard():
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'desc')
    query = """
    SELECT a.id, u.name, u.email, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name, 
           a.slot_time, a.date, a.no_show_prob, a.reschedule_prob, a.status 
    FROM appointments a 
    JOIN users u ON a.patient_id = u.id 
    JOIN hospitals h ON a.hospital_id = h.id 
    JOIN departments d ON a.department_id = d.id 
    JOIN doctors doc ON a.doctor_id = doc.id
    """
    if sort_by in ['date', 'status']:
        query += f" ORDER BY {sort_by} {'ASC' if sort_order == 'asc' else 'DESC'}"
    appointments = query_db(query)
    formatted_appointments = [
        [
            appt['id'], appt['name'], appt['email'], appt['hospital_name'], appt['department_name'],
            appt['doctor_name'], appt['slot_time'], appt['date'],
            f"{float(appt['no_show_prob']):.2f}" if appt['no_show_prob'] is not None else "0.00",
            f"{float(appt['reschedule_prob']):.2f}" if appt['reschedule_prob'] is not None else "0.00",
            appt['status']
        ]
        for appt in appointments
    ]
    return render_template('admin.html', appointments=formatted_appointments)

@app.route('/hospital_register', methods=['GET', 'POST'])
@login_required('admin')
def hospital_register():
    if request.method == 'POST':
        hospital_name = request.form['hospital_name']
        location = request.form['location']
        hospital_id = query_db(
            "INSERT INTO hospitals (name, location) VALUES (?, ?)",
            (hospital_name, location), commit=True, return_id=True
        )
        dept_keys = [key for key in request.form if key.startswith('departments[') and key.endswith('][name]')]
        dept_indices = set(int(key.split('[')[1].split(']')[0]) for key in dept_keys)
        for idx in dept_indices:
            dept_name = request.form[f'departments[{idx}][name]']
            dept_id = query_db(
                "INSERT INTO departments (hospital_id, name) VALUES (?, ?)",
                (hospital_id, dept_name), commit=True, return_id=True
            )
            doctor_keys = [key for key in request.form if key.startswith(f'departments[{idx}][doctors][') and key.endswith('][name]')]
            doctor_indices = set(int(key.split('[')[3].split(']')[0]) for key in doctor_keys)
            for doc_idx in doctor_indices:
                doc_name = request.form[f'departments[{idx}][doctors][{doc_idx}][name]']
                doc_gender = request.form[f'departments[{idx}][doctors][{doc_idx}][gender]']
                doc_schedule = request.form[f'departments[{idx}][doctors][{doc_idx}][schedule]']
                query_db(
                    "INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                    (hospital_id, dept_id, doc_name, doc_gender, doc_schedule), commit=True
                )
        flash("Hospital registered successfully.", "success")
        return redirect(url_for('admin_dashboard'))
    return render_template('hospital_register.html')

@app.route('/mark_attended/<int:appt_id>', methods=['POST'])
@login_required('admin')
def mark_attended(appt_id):
    query = "UPDATE appointments SET status = 'attended' WHERE id = ?"
    query_db(query, (appt_id,), commit=True)
    flash("Appointment marked as attended.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/reschedule/<int:appt_id>', methods=['POST'])
@login_required('admin')
def reschedule(appt_id):
    new_date = request.form['date']
    new_time = request.form['time']
    appointment = query_db(
        "SELECT a.*, u.email, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name FROM appointments a "
        "JOIN users u ON a.patient_id = u.id JOIN hospitals h ON a.hospital_id = h.id "
        "JOIN departments d ON a.department_id = d.id JOIN doctors doc ON a.doctor_id = doc.id WHERE a.id = ?",
        (appt_id,), one=True
    )
    if appointment['status'] in ['attended', 'closed']:
        flash("Cannot reschedule this appointment.", "danger")
        return redirect(url_for('admin_dashboard'))
    appointment_date = pd.to_datetime(new_date)
    current_date = pd.to_datetime(date.today())
    max_date = current_date + relativedelta(years=1)
    if appointment_date < current_date or appointment_date > max_date:
        flash("Invalid date range.", "danger")
        return redirect(url_for('admin_dashboard'))
    past_appointments = query_db(
        "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
        (appointment['patient_id'], new_date)
    )
    previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')
    hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (appointment['hospital_id'],), one=True)['location']
    lead_time = (appointment_date - current_date).days
    distance = 0 if 'Lagos' in hospital_location else 1
    time_of_day = 1 if 'AM' in new_time.upper() else 0
    is_weekday = 0 if appointment_date.weekday() < 5 else 1
    user_age = query_db("SELECT age FROM users WHERE id = ?", (appointment['patient_id'],), one=True)['age']
    doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (appointment['doctor_id'],), one=True)['gender']
    doctor_gender_val = 0 if doctor_gender == 'M' else 1
    features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, user_age, doctor_gender_val]
    no_show_prob = predict_no_show(features)
    reschedule_prob = predict_reschedule(features)
    booking_date = date.today().strftime('%Y-%m-%d')
    query = """
    UPDATE appointments SET date = ?, slot_time = ?, booking_date = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? WHERE id = ?
    """
    query_db(query, (new_date, new_time, booking_date, no_show_prob, reschedule_prob, appt_id), commit=True)
    appointment_details = {
        'hospital_name': appointment['hospital_name'],
        'department_name': appointment['department_name'],
        'doctor_name': appointment['doctor_name'],
        'date': new_date,
        'slot_time': new_time
    }
    send_reschedule_notification(appointment['email'], appointment_details)
    flash("Appointment rescheduled successfully.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/close_appt/<int:appt_id>', methods=['POST'])
@login_required('admin')
def close_appt(appt_id):
    query = "UPDATE appointments SET status = 'closed' WHERE id = ?"
    query_db(query, (appt_id,), commit=True)
    flash("Appointment closed.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/auto_reschedule/<int:appt_id>', methods=['POST'])
@login_required('admin')
def auto_reschedule(appt_id):
    appointment = query_db(
        "SELECT a.*, u.email, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name "
        "FROM appointments a JOIN users u ON a.patient_id = u.id JOIN hospitals h ON a.hospital_id = h.id "
        "JOIN departments d ON a.department_id = d.id JOIN doctors doc ON a.doctor_id = doc.id WHERE a.id = ?",
        (appt_id,), one=True
    )
    if appointment['no_show_prob'] <= 50 or appointment['status'] not in ['scheduled', 'rescheduled']:
        flash("Appointment not eligible for auto-rescheduling.", "info")
        return jsonify({"status": "info", "message": "Not eligible"})
    new_date, new_time = find_available_slot(appointment['doctor_id'], appointment['date'], appointment['patient_id'])
    if not new_date:
        flash("No available slots found.", "warning")
        return jsonify({"status": "warning", "message": "No slots available"})
    appointment_date = pd.to_datetime(new_date)
    current_date = pd.to_datetime(date.today())
    past_appointments = query_db(
        "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
        (appointment['patient_id'], new_date)
    )
    previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')
    hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (appointment['hospital_id'],), one=True)['location']
    lead_time = (appointment_date - current_date).days
    distance = 0 if 'Lagos' in hospital_location else 1
    time_of_day = 1 if 'AM' in new_time.upper() else 0
    is_weekday = 0 if appointment_date.weekday() < 5 else 1
    user_age = query_db("SELECT age FROM users WHERE id = ?", (appointment['patient_id'],), one=True)['age']
    doctor_gender = query_db("SELECT gender FROM doctors WHERE id = ?", (appointment['doctor_id'],), one=True)['gender']
    doctor_gender_val = 0 if doctor_gender == 'M' else 1
    features = [previous_no_shows, lead_time, distance, time_of_day, is_weekday, user_age, doctor_gender_val]
    no_show_prob = predict_no_show(features)
    reschedule_prob = predict_reschedule(features)
    booking_date = date.today().strftime('%Y-%m-%d')
    query = """
    UPDATE appointments SET date = ?, slot_time = ?, booking_date = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? WHERE id = ?
    """
    query_db(query, (new_date, new_time, booking_date, no_show_prob, reschedule_prob, appt_id), commit=True)
    appointment_details = {
        'hospital_name': appointment['hospital_name'],
        'department_name': appointment['department_name'],
        'doctor_name': appointment['doctor_name'],
        'date': new_date,
        'slot_time': new_time
    }
    send_reschedule_notification(appointment['email'], appointment_details)
    flash("Appointment auto-rescheduled.", "success")
    return jsonify({"status": "success", "message": "Auto-rescheduled"})

@app.route('/auto_reschedule_all', methods=['POST'])
@login_required('admin')
def auto_reschedule_all():
    high_risk_appts = query_db(
        "SELECT id FROM appointments WHERE no_show_prob > 50 AND status = 'scheduled'"
    )
    for appt in high_risk_appts:
        auto_reschedule(appt['id'])
    flash("High-risk appointments rescheduled.", "success")
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_no_shows_and_reschedule, 'cron', hour=8, minute=0)
    scheduler.add_job(retrain_model, 'cron', day_of_week='sun', hour=2, minute=0)
    scheduler.start()
    app.run(debug=True, use_reloader=False)