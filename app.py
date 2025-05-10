from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_mail import Mail, Message
import sqlite3
import psycopg2
from psycopg2 import pool
import pandas as pd
import numpy as np
import os
from model.no_show_model import predict_no_show, predict_reschedule, calculate_no_show_history, calculate_priority_score
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Configure Flask-Mail with Gmail SMTP settings
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False  # Use TLS, not SSL, for Gmail on port 587
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME", "lrdmuyi85@gmail.com")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD", "fjqdyzjlfudatoky")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER", "lrdmuyi85@gmail.com")

mail = Mail(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Authentication decorator
def login_required(role):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role:
                flash(f"Please log in as a {role} to view this page.")
                return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

# Database configuration
DB_TYPE = os.getenv("DB_TYPE", "sqlite")

# SQLite connection
def get_sqlite_conn():
    try:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        app.logger.error(f"Failed to connect to SQLite database: {e}")
        raise

# PostgreSQL connection pool
if DB_TYPE == "postgresql":
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
    except Exception as e:
        app.logger.error(f"Failed to initialize PostgreSQL pool: {e}")
        db_pool = None
else:
    db_pool = None

# Initialize database schema
def init_db():
    if DB_TYPE == "sqlite":
        try:
            conn = get_sqlite_conn()
            c = conn.cursor()

            # Check database integrity
            c.execute("PRAGMA integrity_check;")
            result = c.fetchone()[0]
            if result != "ok":
                app.logger.warning("Database integrity check failed. Recreating database...")
                conn.close()
                os.remove("database.db")
                conn = get_sqlite_conn()
                c = conn.cursor()

            # Create tables
            c.execute('''CREATE TABLE IF NOT EXISTS users 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, phone TEXT, password TEXT, role TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS hospitals 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, location TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS departments 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, name TEXT,
                          FOREIGN KEY (hospital_id) REFERENCES hospitals(id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS doctors 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER, department_id INTEGER, name TEXT,
                          FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                          FOREIGN KEY (department_id) REFERENCES departments(id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, hospital_id INTEGER, department_id INTEGER, 
                          doctor_id INTEGER, slot_time TEXT, date TEXT, no_show_prob REAL, reschedule_prob REAL, status TEXT,
                          FOREIGN KEY (patient_id) REFERENCES users(id),
                          FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                          FOREIGN KEY (department_id) REFERENCES departments(id),
                          FOREIGN KEY (doctor_id) REFERENCES doctors(id))''')

            # Seed hospitals, departments, and doctors
            hospitals = [
                ("Lagos General Hospital", "Lagos"),
                ("Abuja Medical Center", "Abuja"),
                ("Kano Health Clinic", "Kano"),
                ("Ibadan Community Hospital", "Ibadan"),
                ("Port Harcourt Specialist Hospital", "Port Harcourt"),
                ("Enugu Regional Hospital", "Enugu"),
                ("Benin City Medical Center", "Benin City"),
                ("Kaduna General Hospital", "Kaduna"),
                ("Jos University Teaching Hospital", "Jos"),
                ("Calabar Specialist Clinic", "Calabar")
            ]

            department_names = ["Cardiology", "Pediatrics", "Orthopedics", "Neurology", "General Medicine", 
                               "Gynecology", "Surgery", "Oncology", "Dermatology", "Radiology"]
            departments = []
            doctors = []

            # Seed a default admin user
            admin_email = "admin@example.com"
            admin_password = generate_password_hash("adminpassword", method='pbkdf2:sha256')
            c.execute("INSERT OR IGNORE INTO users (name, email, phone, password, role) VALUES (?, ?, ?, ?, ?)",
                     ("Admin User", admin_email, "1234567890", admin_password, "admin"))

            # Insert hospitals and get their IDs
            c.executemany("INSERT OR IGNORE INTO hospitals (name, location) VALUES (?, ?)", hospitals)
            conn.commit()
            hospital_ids = [row['id'] for row in c.execute("SELECT id FROM hospitals").fetchall()]

            # Seed departments
            dept_id = 1
            for hospital_id in hospital_ids:
                num_depts = 4
                for i in range(num_depts):
                    dept_name = department_names[(hospital_id + i - 1) % len(department_names)]
                    c.execute("INSERT OR IGNORE INTO departments (id, hospital_id, name) VALUES (?, ?, ?)", 
                             (dept_id, hospital_id, dept_name))
                    departments.append((dept_id, hospital_id, dept_name))
                    dept_id += 1

            doctor_names = [
                "Dr. John Adebayo", "Dr. Aisha Bello", "Dr. Emeka Okon", "Dr. Fatima Musa", "Dr. Chioma Obi", 
                "Dr. Tunde Ade", "Dr. Grace Eke", "Dr. Musa Ibrahim", "Dr. Ngozi Eze", "Dr. Ahmed Yusuf",
                "Dr. Blessing Nwosu", "Dr. Kemi Adesina", "Dr. David Okafor", "Dr. Zainab Lawal", "Dr. Peter Uche",
                "Dr. Joy Amadi", "Dr. Sani Abubakar", "Dr. Esther Ojo", "Dr. Chukwuma Eze", "Dr. Halima Danjuma"
            ]
            
            # Seed doctors
            doc_id = 1
            for dept in departments:
                dept_id = dept[0]
                hospital_id = dept[1]
                for i in range(3):
                    doc_name = doctor_names[(doc_id - 1) % len(doctor_names)] + f" {doc_id}"
                    c.execute("INSERT OR IGNORE INTO doctors (id, hospital_id, department_id, name) VALUES (?, ?, ?, ?)",
                             (doc_id, hospital_id, dept_id, doc_name))
                    doctors.append((doc_id, hospital_id, dept_id, doc_name))
                    doc_id += 1

            conn.commit()
            app.logger.info("SQLite database initialized and seeded successfully")
        except sqlite3.Error as e:
            app.logger.error(f"Failed to initialize SQLite database: {e}")
            raise
        finally:
            conn.close()
    elif DB_TYPE == "postgresql" and db_pool:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute('''CREATE TABLE IF NOT EXISTS users 
                             (id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, phone TEXT, password TEXT, role TEXT)''')
                c.execute('''CREATE TABLE IF NOT EXISTS hospitals 
                             (id SERIAL PRIMARY KEY, name TEXT, location TEXT)''')
                c.execute('''CREATE TABLE IF NOT EXISTS departments 
                             (id SERIAL PRIMARY KEY, hospital_id INTEGER, name TEXT,
                              FOREIGN KEY (hospital_id) REFERENCES hospitals(id))''')
                c.execute('''CREATE TABLE IF NOT EXISTS doctors 
                             (id SERIAL PRIMARY KEY, hospital_id INTEGER, department_id INTEGER, name TEXT,
                              FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                              FOREIGN KEY (department_id) REFERENCES departments(id))''')
                c.execute('''CREATE TABLE IF NOT EXISTS appointments 
                             (id SERIAL PRIMARY KEY, patient_id INTEGER, hospital_id INTEGER, department_id INTEGER, 
                              doctor_id INTEGER, slot_time TEXT, date TEXT, no_show_prob REAL, reschedule_prob REAL, status TEXT,
                              FOREIGN KEY (patient_id) REFERENCES users(id),
                              FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                              FOREIGN KEY (department_id) REFERENCES departments(id),
                              FOREIGN KEY (doctor_id) REFERENCES doctors(id))''')

                hospitals = [
                    ("Lagos General Hospital", "Lagos"),
                    ("Abuja Medical Center", "Abuja"),
                    ("Kano Health Clinic", "Kano"),
                    ("Ibadan Community Hospital", "Ibadan"),
                    ("Port Harcourt Specialist Hospital", "Port Harcourt"),
                    ("Enugu Regional Hospital", "Enugu"),
                    ("Benin City Medical Center", "Benin City"),
                    ("Kaduna General Hospital", "Kaduna"),
                    ("Jos University Teaching Hospital", "Jos"),
                    ("Calabar Specialist Clinic", "Calabar")
                ]

                department_names = ["Cardiology", "Pediatrics", "Orthopedics", "Neurology", "General Medicine", 
                                   "Gynecology", "Surgery", "Oncology", "Dermatology", "Radiology"]
                departments = []
                
                doctor_names = [
                    "Dr. John Adebayo", "Dr. Aisha Bello", "Dr. Emeka Okon", "Dr. Fatima Musa", "Dr. Chioma Obi", 
                    "Dr. Tunde Ade", "Dr. Grace Eke", "Dr. Musa Ibrahim", "Dr. Ngozi Eze", "Dr. Ahmed Yusuf",
                    "Dr. Blessing Nwosu", "Dr. Kemi Adesina", "Dr. David Okafor", "Dr. Zainab Lawal", "Dr. Peter Uche",
                    "Dr. Joy Amadi", "Dr. Sani Abubakar", "Dr. Esther Ojo", "Dr. Chukwuma Eze", "Dr. Halima Danjuma"
                ]
                
                admin_email = "admin@example.com"
                admin_password = generate_password_hash("adminpassword", method='pbkdf2:sha256')
                c.execute("INSERT INTO users (name, email, phone, password, role) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                         ("Admin User", admin_email, "1234567890", admin_password, "admin"))

                # Insert hospitals and get their IDs
                for h in hospitals:
                    c.execute("INSERT INTO hospitals (name, location) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id", h)
                    hospital_id = c.fetchone()[0] if c.rowcount > 0 else None
                    if hospital_id:
                        num_depts = 4
                        for i in range(num_depts):
                            dept_name = department_names[(hospital_id + i - 1) % len(department_names)]
                            c.execute("INSERT INTO departments (hospital_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id", 
                                     (hospital_id, dept_name))
                            dept_id = c.fetchone()[0] if c.rowcount > 0 else None
                            if dept_id:
                                departments.append((hospital_id, dept_name))
                                for j in range(3):
                                    doc_name = doctor_names[(len(departments) * 3 + j - 1) % len(doctor_names)] + f" {len(departments) * 3 + j}"
                                    c.execute("INSERT INTO doctors (hospital_id, department_id, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                                             (hospital_id, dept_id, doc_name))

                conn.commit()
                app.logger.info("PostgreSQL database initialized and seeded successfully")
        except Exception as e:
            app.logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise
        finally:
            db_pool.putconn(conn)

# Database query helper
def query_db(query, args=(), one=False, commit=False):
    if DB_TYPE == "sqlite":
        conn = get_sqlite_conn()
        try:
            c = conn.cursor()
            c.execute(query, args)
            if commit:
                conn.commit()
            rv = c.fetchall()
            if rv:
                columns = [desc[0] for desc in c.description]
                rv = [dict(zip(columns, row)) for row in rv]
                return rv[0] if one else rv
            return None if one else []
        except sqlite3.Error as e:
            app.logger.error(f"SQLite query error: {e}")
            raise
        finally:
            conn.close()
    elif DB_TYPE == "postgresql" and db_pool:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute(query, args)
                if commit:
                    conn.commit()
                rv = c.fetchall() if not commit else None
                if rv:
                    columns = [desc[0] for desc in c.description]
                    rv = [dict(zip(columns, row)) for row in rv]
                    return rv[0] if one else rv
                return None if one else []
        except Exception as e:
            app.logger.error(f"PostgreSQL query error: {e}")
            raise
        finally:
            db_pool.putconn(conn)
    else:
        raise Exception("Database not configured properly")

# Function to send email notifications
def send_reschedule_notification(patient_email, appointment_details):
    subject = "Appointment Rescheduled Due to No-Show"
    body = f"""
    Dear Patient,

    You missed your recent appointment. We have automatically rescheduled it for you. Here are the new details:
    - Hospital: {appointment_details['hospital_name']}
    - Department: {appointment_details['department_name']}
    - Doctor: {appointment_details['doctor_name']}
    - Date: {appointment_details['date']}
    - Time: {appointment_details['slot_time']}

    Please ensure you attend this appointment. If you have any questions, feel free to contact us.

    Best regards,
    Patient Appointment System
    """
    msg = Message(subject, recipients=[patient_email], body=body)
    try:
        mail.send(msg)
        app.logger.info(f"Reschedule notification sent to {patient_email}")
    except Exception as e:
        app.logger.error(f"Failed to send reschedule notification to {patient_email}: {e}")

# Helper function for auto-rescheduling
def find_available_slot(doctor_id, current_date, patient_id, max_attempts=7):
    try:
        all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
        current_date_dt = pd.to_datetime(current_date)
        for days_ahead in range(1, max_attempts + 1):
            new_date = (current_date_dt + pd.Timedelta(days=days_ahead)).strftime('%Y-%m-%d')
            existing_appts = query_db(
                "SELECT slot_time, patient_id, no_show_prob FROM appointments WHERE doctor_id = ? AND date = ? AND status != 'closed'",
                (doctor_id, new_date)
            )
            booked_slots = {appt['slot_time']: appt for appt in existing_appts}

            for slot in all_slots:
                if slot not in booked_slots:
                    max_appointments_per_slot = 2
                    combined_no_show_threshold = 50.0
                    priority_threshold = 0.7
                    no_show_history = calculate_no_show_history(patient_id, new_date)
                    priority_score = calculate_priority_score(no_show_history)
                    if priority_score >= priority_threshold:
                        return new_date, slot
                else:
                    appt = booked_slots[slot]
                    if len(existing_appts) < max_appointments_per_slot:
                        no_show_history = calculate_no_show_history(patient_id, new_date)
                        priority_score = calculate_priority_score(no_show_history)
                        if priority_score >= priority_threshold:
                            combined_no_show_prob = appt['no_show_prob']
                            if combined_no_show_prob < combined_no_show_threshold:
                                return new_date, slot
        app.logger.warning(f"No available slots found for doctor_id {doctor_id} within {max_attempts} days.")
        return None, None
    except Exception as e:
        app.logger.error(f"Error finding available slot for doctor_id {doctor_id}: {e}")
        return None, None

# Function to check for no-shows and reschedule them after 1 day
def check_no_shows_and_reschedule():
    with app.app_context():
        try:
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

            if not potential_no_shows:
                app.logger.info("No potential no-show appointments from yesterday.")
                return

            for appt in potential_no_shows:
                appt_id = appt['id']
                patient_id = appt['patient_id']
                hospital_id = appt['hospital_id']
                department_id = appt['department_id']
                doctor_id = appt['doctor_id']
                current_date = appt['date']

                query = "UPDATE appointments SET status = ? WHERE id = ?"
                query_db(query, ('no_show', appt_id), commit=True)
                app.logger.info(f"Marked appointment ID {appt_id} as no_show")

                new_date, new_time = find_available_slot(doctor_id, current_date, patient_id)
                if not new_date or not new_time:
                    app.logger.warning(f"No available slot found for rescheduling appointment ID {appt_id}")
                    continue

                try:
                    appointment_date = pd.to_datetime(new_date)
                    current_date_dt = pd.to_datetime(today)
                    max_date = current_date_dt + relativedelta(years=1)

                    if appointment_date < current_date_dt or appointment_date > max_date:
                        app.logger.warning(f"Invalid date range for rescheduling appointment ID {appt_id}: {new_date}")
                        continue
                except ValueError as e:
                    app.logger.error(f"Invalid date format for rescheduling appointment ID {appt_id}: {new_date}. Error: {e}")
                    continue

                past_appointments = query_db(
                    "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
                    (patient_id, new_date)
                )
                previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')

                hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
                if not hospital_location:
                    app.logger.warning(f"Invalid hospital_id {hospital_id} for appointment ID {appt_id}")
                    continue
                hospital_location = hospital_location['location']

                lead_time = (appointment_date - current_date_dt).days
                distance_5km = 0 if 'Lagos' in hospital_location else 1
                time_of_day_morning = 1 if 'AM' in new_time.upper() else 0
                is_weekday = appointment_date.day_name() in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
                is_weekday_weekend = 0 if is_weekday else 1

                features = [previous_no_shows, lead_time, distance_5km, time_of_day_morning, is_weekday_weekend]

                try:
                    no_show_prob = predict_no_show(features)
                    reschedule_prob = predict_reschedule(features)

                    if not (0 <= no_show_prob <= 100 and 0 <= reschedule_prob <= 100):
                        app.logger.warning(f"Invalid probabilities for appointment ID {appt_id}: no_show_prob={no_show_prob}, reschedule_prob={reschedule_prob}")
                        continue
                except Exception as e:
                    app.logger.error(f"Error predicting probabilities for appointment ID {appt_id}: {e}")
                    continue

                query = """
                UPDATE appointments 
                SET date = ?, slot_time = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? 
                WHERE id = ?
                """
                query_db(query, (new_date, new_time, no_show_prob, reschedule_prob, appt_id), commit=True)
                app.logger.info(f"Rescheduled no-show appointment ID {appt_id} to {new_date} at {new_time}")

                patient_email = appt['email']
                appointment_details = {
                    'hospital_name': appt['hospital_name'],
                    'department_name': appt['department_name'],
                    'doctor_name': appt['doctor_name'],
                    'date': new_date,
                    'slot_time': new_time
                }
                send_reschedule_notification(patient_email, appointment_details)

        except Exception as e:
            app.logger.error(f"Error in check_no_shows_and_reschedule: {e}")

# Routes
@app.route('/', endpoint='index')
def index():
    return render_template('index.html', user=session.get('user_id'), role=session.get('role'))

@app.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')

        if not all([name, email, phone, password]):
            flash("All fields are required.")
            return redirect(url_for('register'))

        if len(password) < 8:
            flash("Password must be at least 8 characters long.")
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        query = """INSERT INTO users (name, email, phone, password, role) VALUES (%s, %s, %s, %s, %s)""" if DB_TYPE == "postgresql" else """INSERT INTO users (name, email, phone, password, role) VALUES (?, ?, ?, ?, ?)"""
        try:
            query_db(query, (name, email, phone, password_hash, 'patient'), commit=True)
            flash("Registration successful! Please login.")
            return redirect(url_for('login'))
        except Exception as e:
            app.logger.error(f"Registration error: {e}")
            flash("Email already exists or invalid input.")
    return render_template('register.html', user=session.get('user_id'), role=session.get('role'))

@app.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        query = "SELECT * FROM users WHERE email = %s" if DB_TYPE == "postgresql" else "SELECT * FROM users WHERE email = ?"
        user = query_db(query, (email,), one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            flash("Logged in successfully.")
            if user['role'] == 'patient':
                return redirect(url_for('patient_dashboard'))
            elif user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
        flash("Invalid credentials.")
    return render_template('login.html', user=session.get('user_id'), role=session.get('role'))

@app.route('/logout', endpoint='logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('index'))

@app.route('/get_departments/<int:hospital_id>', methods=['GET'], endpoint='get_departments')
def get_departments(hospital_id):
    query = "SELECT id, name FROM departments WHERE hospital_id = %s" if DB_TYPE == "postgresql" else "SELECT id, name FROM departments WHERE hospital_id = ?"
    departments = query_db(query, (hospital_id,))
    return jsonify([(dept['id'], dept['name']) for dept in departments])

@app.route('/get_doctors/<int:department_id>', methods=['GET'], endpoint='get_doctors')
def get_doctors(department_id):
    query = "SELECT id, name FROM doctors WHERE department_id = %s" if DB_TYPE == "postgresql" else "SELECT id, name FROM doctors WHERE department_id = ?"
    doctors = query_db(query, (department_id,))
    return jsonify([(doc['id'], doc['name']) for doc in doctors])

@app.route('/book', methods=['GET', 'POST'], endpoint='book_appointment')
@login_required('patient')
def book_appointment():
    hospitals = query_db("SELECT * FROM hospitals")
    app.logger.info(f"Fetched hospitals: {hospitals}")  # Debug log
    if not hospitals:
        flash("No hospitals available. Please contact the administrator.", "danger")
        return redirect(url_for('patient_dashboard'))
    
    if request.method == 'POST':
        patient_id = session['user_id']
        hospital_id = request.form.get('hospital')
        department_id = request.form.get('department')
        doctor_id = request.form.get('doctor')
        date = request.form.get('date')
        slot_time = request.form.get('time')

        if not all([hospital_id, department_id, doctor_id, date, slot_time]):
            flash("All fields are required.", "danger")
            return redirect(url_for('book_appointment'))

        try:
            appointment_date = pd.to_datetime(date)
            current_date = pd.to_datetime('2025-05-09')
            max_date = current_date + relativedelta(years=1)

            if appointment_date < current_date:
                flash("Cannot book an appointment in the past.", "danger")
                return redirect(url_for('book_appointment'))
            if appointment_date > max_date:
                flash("Cannot book an appointment more than one year in the future.", "danger")
                return redirect(url_for('book_appointment'))
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for('book_appointment'))

        past_appointments = query_db(
            "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
            (patient_id, date)
        )
        previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')

        hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        if not hospital_location:
            flash("Invalid hospital selected.", "danger")
            return redirect(url_for('book_appointment'))
        hospital_location = hospital_location['location']

        lead_time = (appointment_date - current_date).days
        distance_5km = 0 if 'Lagos' in hospital_location else 1
        time_of_day_morning = 1 if 'AM' in slot_time.upper() else 0
        is_weekday = appointment_date.day_name() in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        is_weekday_weekend = 0 if is_weekday else 1

        features = [previous_no_shows, lead_time, distance_5km, time_of_day_morning, is_weekday_weekend]

        try:
            no_show_prob = predict_no_show(features)
            reschedule_prob = predict_reschedule(features)

            if not (0 <= no_show_prob <= 100 and 0 <= reschedule_prob <= 100):
                flash("Invalid prediction probabilities.", "danger")
                return redirect(url_for('book_appointment'))

            query = """INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, reschedule_prob, status) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            query_db(query, (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, reschedule_prob, 'scheduled'), commit=True)

            flash(f"Appointment booked successfully! No-show risk: {no_show_prob:.2f}%, Reschedule risk: {reschedule_prob:.2f}%", "success")
            return redirect(url_for('patient_dashboard'))
        except Exception as e:
            app.logger.error(f"Booking error: {e}")
            flash("Error booking appointment. Please try again.", "danger")
            return redirect(url_for('book_appointment'))

    return render_template('booking.html', hospitals=hospitals, user=session.get('user_id'), role=session.get('role'))

@app.route('/check_slot', methods=['GET'], endpoint='check_slot')
@login_required('patient')
def check_slot():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    slot_time = request.args.get('time')
    patient_id = session.get('user_id')

    if not all([doctor_id, date, slot_time]):
        return jsonify({'available': False, 'error': 'Missing required parameters'})

    try:
        query = """SELECT patient_id, no_show_prob FROM appointments 
                   WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'closed'"""
        existing_appts = query_db(query, (doctor_id, date, slot_time))

        max_appointments_per_slot = 2
        combined_no_show_threshold = 50.0
        priority_threshold = 0.7

        if not existing_appts:
            return jsonify({'available': True})

        if len(existing_appts) >= max_appointments_per_slot:
            return jsonify({'available': False, 'error': 'Slot is fully booked'})

        no_show_history = calculate_no_show_history(patient_id, date)
        priority_score = calculate_priority_score(no_show_history)

        if priority_score < priority_threshold:
            return jsonify({'available': False, 'error': 'Priority score too low'})

        combined_no_show_prob = sum(appt['no_show_prob'] for appt in existing_appts)
        if combined_no_show_prob >= combined_no_show_threshold:
            return jsonify({'available': False, 'error': 'Combined no-show risk too high'})

        return jsonify({'available': True})
    except Exception as e:
        app.logger.error(f"Error checking slot availability: {e}")
        return jsonify({'available': False, 'error': 'Database error'})

@app.route('/get_available_slots', methods=['GET'], endpoint='get_available_slots')
@login_required('patient')
def get_available_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    patient_id = session.get('user_id')

    if not all([doctor_id, date]):
        return jsonify({'error': 'Missing required parameters'})

    try:
        all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
        query = """SELECT slot_time, patient_id, no_show_prob 
                   FROM appointments 
                   WHERE doctor_id = ? AND date = ? AND status != 'closed'"""
        existing_appts = query_db(query, (doctor_id, date))

        slot_appointments = {slot: [appt for appt in existing_appts if appt['slot_time'] == slot] for slot in all_slots}

        max_appointments_per_slot = 2
        combined_no_show_threshold = 50.0
        priority_threshold = 0.7

        no_show_history = calculate_no_show_history(patient_id, date)
        priority_score = calculate_priority_score(no_show_history)

        available_slots = []
        for slot in all_slots:
            appts_in_slot = slot_appointments[slot]
            if not appts_in_slot:
                available_slots.append(slot)
            elif len(appts_in_slot) < max_appointments_per_slot:
                if priority_score >= priority_threshold:
                    combined_no_show_prob = sum(appt['no_show_prob'] for appt in appts_in_slot)
                    if combined_no_show_prob < combined_no_show_threshold:
                        available_slots.append(slot)

        return jsonify(available_slots)
    except Exception as e:
        app.logger.error(f"Error fetching available slots: {e}")
        return jsonify({'error': 'Database error'})

@app.route('/patient', endpoint='patient_dashboard')
@login_required('patient')
def patient_dashboard():
    user_id = session['user_id']
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')

    query = """SELECT a.id, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name, a.slot_time, a.date, a.status 
               FROM appointments a 
               JOIN hospitals h ON a.hospital_id = h.id 
               JOIN departments d ON a.department_id = d.id 
               JOIN doctors doc ON a.doctor_id = doc.id 
               WHERE a.patient_id = ?"""
    if sort_by in ['date', 'status']:
        query += f" ORDER BY {sort_by} {'ASC' if sort_order == 'asc' else 'DESC'}"
    appointments = query_db(query, (user_id,))

    reordered_appointments = [
        (appt['hospital_name'], appt['department_name'], appt['doctor_name'], appt['date'], appt['slot_time'], appt['status'])
        for appt in appointments
    ]

    return render_template('patient.html', appointments=reordered_appointments, user=session.get('user_id'), role=session.get('role'))

@app.route('/admin', endpoint='admin_dashboard')
@login_required('admin')
def admin_dashboard():
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')

    query = """SELECT a.id, u.email, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name, a.slot_time, a.date, a.no_show_prob, a.status 
               FROM appointments a 
               JOIN users u ON a.patient_id = u.id 
               JOIN hospitals h ON a.hospital_id = h.id 
               JOIN departments d ON a.department_id = d.id 
               JOIN doctors doc ON a.doctor_id = doc.id"""
    if sort_by in ['date', 'status']:
        query += f" ORDER BY {sort_by} {'ASC' if sort_order == 'asc' else 'DESC'}"
    appointments = query_db(query)

    formatted_appointments = [[appt['id'], appt['email'], appt['hospital_name'], appt['department_name'], appt['doctor_name'], appt['slot_time'], appt['date'], f"{float(appt['no_show_prob']):.2f}", appt['status']] for appt in appointments]

    return render_template('admin.html', appointments=formatted_appointments, user=session.get('user_id'), role=session.get('role'))

@app.route('/mark_attended/<int:appt_id>', methods=['POST'], endpoint='mark_attended')
@login_required('admin')
def mark_attended(appt_id):
    query = "UPDATE appointments SET status = %s WHERE id = %s" if DB_TYPE == "postgresql" else "UPDATE appointments SET status = ? WHERE id = ?"
    query_db(query, ('attended', appt_id), commit=True)
    flash("Appointment marked as attended.")
    return redirect(url_for('admin_dashboard'))

@app.route('/reschedule/<int:appt_id>', methods=['POST'], endpoint='reschedule')
@login_required('admin')
def reschedule(appt_id):
    # Fetch appointment details including patient email
    appointment = query_db(
        """
        SELECT a.status, a.patient_id, a.hospital_id, a.department_id, a.doctor_id,
               u.email, h.name AS hospital_name, d.name AS department_name, doc.name AS doctor_name
        FROM appointments a
        JOIN users u ON a.patient_id = u.id
        JOIN hospitals h ON a.hospital_id = h.id
        JOIN departments d ON a.department_id = d.id
        JOIN doctors doc ON a.doctor_id = doc.id
        WHERE a.id = ?
        """,
        (appt_id,), one=True
    )
    if not appointment:
        flash("Appointment not found.", "danger")
        return redirect(url_for('admin_dashboard'))

    if appointment['status'] == 'attended':
        flash("Cannot reschedule an appointment that has already been attended.", "danger")
        return redirect(url_for('admin_dashboard'))

    new_date = request.form.get('date')
    new_time = request.form.get('time')

    if not all([new_date, new_time]):
        flash("Date and time are required.", "danger")
        return redirect(url_for('admin_dashboard'))

    try:
        appointment_date = pd.to_datetime(new_date)
        current_date = pd.to_datetime(date.today())
        max_date = current_date + relativedelta(years=1)

        if appointment_date < current_date:
            flash("Cannot reschedule to a past date.", "danger")
            return redirect(url_for('admin_dashboard'))
        if appointment_date > max_date:
            flash("Cannot reschedule more than one year in the future.", "danger")
            return redirect(url_for('admin_dashboard'))
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
        return redirect(url_for('admin_dashboard'))

    patient_id = appointment['patient_id']
    hospital_id = appointment['hospital_id']
    department_id = appointment['department_id']
    doctor_id = appointment['doctor_id']

    existing_appointment = query_db(
        "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND id != ?",
        (doctor_id, new_date, new_time, appt_id), one=True
    )
    if existing_appointment:
        flash("The new slot is already booked.", "danger")
        return redirect(url_for('admin_dashboard'))

    past_appointments = query_db(
        "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
        (patient_id, new_date)
    )
    previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')

    hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
    if not hospital_location:
        flash("Invalid hospital.", "danger")
        return redirect(url_for('admin_dashboard'))
    hospital_location = hospital_location['location']

    lead_time = (appointment_date - current_date).days
    distance_5km = 0 if 'Lagos' in hospital_location else 1
    time_of_day_morning = 1 if 'AM' in new_time.upper() else 0
    is_weekday = appointment_date.day_name() in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    is_weekday_weekend = 0 if is_weekday else 1

    features = [previous_no_shows, lead_time, distance_5km, time_of_day_morning, is_weekday_weekend]

    try:
        no_show_prob = predict_no_show(features)
        reschedule_prob = predict_reschedule(features)

        if not (0 <= no_show_prob <= 100 and 0 <= reschedule_prob <= 100):
            flash("Invalid prediction probabilities.", "danger")
            return redirect(url_for('admin_dashboard'))

        query = """UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? WHERE id = ?"""
        query_db(query, (new_date, new_time, no_show_prob, reschedule_prob, appt_id), commit=True)

        # Prepare appointment details for email notification
        appointment_details = {
            'hospital_name': appointment['hospital_name'],
            'department_name': appointment['department_name'],
            'doctor_name': appointment['doctor_name'],
            'date': new_date,
            'slot_time': new_time
        }
        patient_email = appointment['email']

        # Send email notification to the patient
        send_reschedule_notification(patient_email, appointment_details)

        app.logger.info(f"Rescheduled appointment ID {appt_id} to {new_date} at {new_time}")
        flash(f"Appointment rescheduled successfully! New no-show risk: {no_show_prob:.2f}%", "success")
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        app.logger.error(f"Rescheduling error for appointment ID {appt_id}: {e}")
        flash("Error rescheduling appointment.", "danger")
        return redirect(url_for('admin_dashboard'))
    
        
@app.route('/close_appt/<int:appt_id>', methods=['POST'], endpoint='close_appt')
@login_required('admin')
def close_appt(appt_id):
    query = "UPDATE appointments SET status = ? WHERE id = ?"
    query_db(query, ('closed', appt_id), commit=True)
    flash("Appointment closed.")
    return redirect(url_for('admin_dashboard'))

@app.route('/auto_reschedule/<int:appt_id>', methods=['POST'], endpoint='auto_reschedule')
@login_required('admin')
def auto_reschedule(appt_id):
    try:
        appointment = query_db(
            "SELECT * FROM appointments WHERE id = ? AND no_show_prob > 0.5 AND status IN ('scheduled', 'rescheduled')",
            (appt_id,), one=True
        )
        
        if not appointment:
            app.logger.info(f"Appointment ID {appt_id} not eligible for auto-rescheduling: no_show_prob <= 0.5 or invalid status")
            flash("Appointment not eligible for auto-rescheduling.", "info")
            return jsonify({"status": "info", "message": "Appointment not eligible for auto-rescheduling."})

        app.logger.debug(f"Processing appointment ID {appt_id}: {appointment}")

        date_str = appointment['date']
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            try:
                current_date = datetime.strptime(date_str, '%m/%d/%Y')
            except ValueError as e:
                app.logger.error(f"Invalid date format for appointment ID {appt_id}: {date_str}. Error: {e}")
                flash("Invalid date format for the appointment.", "danger")
                return jsonify({"status": "error", "message": "Invalid date format for the appointment."}), 500

        all_slots = [f"{hour:02d}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]
        new_date = None
        new_slot_time = None
        for i in range(1, 8):
            candidate_date = current_date + timedelta(days=i)
            candidate_date_str = candidate_date.strftime('%Y-%m-%d')
            for slot in all_slots:
                conflict = query_db(
                    "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'cancelled'",
                    (appointment['doctor_id'], candidate_date_str, slot)
                )
                if not conflict:
                    new_date = candidate_date_str
                    new_slot_time = slot
                    break
            if new_date:
                break

        if not new_date:
            app.logger.warning(f"No available slots found for appointment ID {appt_id}")
            flash("No available slots found for rescheduling.", "warning")
            return jsonify({"status": "warning", "message": "No available slots found for rescheduling."})

        query_db(
            "UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled' WHERE id = ?",
            (new_date, new_slot_time, appt_id), commit=True
        )

        app.logger.info(f"Auto-rescheduled appointment ID {appt_id} to {new_date} at {new_slot_time}")
        flash(f"Appointment auto-rescheduled to {new_date} at {new_slot_time}.", "success")
        return jsonify({"status": "success", "message": f"Appointment auto-rescheduled to {new_date} at {new_slot_time}."})

    except Exception as e:
        app.logger.error(f"Error during auto-rescheduling of appointment ID {appt_id}: {e}")
        flash("An error occurred during auto-rescheduling.", "danger")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/auto_reschedule_all', methods=['POST'], endpoint='auto_reschedule_all')
@login_required('admin')
def auto_reschedule_all():
    try:
        high_risk_appts = query_db(
            "SELECT a.id, a.patient_id, a.hospital_id, a.department_id, a.doctor_id, a.date, a.no_show_prob "
            "FROM appointments a WHERE a.no_show_prob > 50 AND a.status = 'scheduled'"
        )

        if not high_risk_appts:
            app.logger.info("No high-risk appointments found for auto-rescheduling.")
            flash("No high-risk appointments to reschedule.", "info")
            return redirect(url_for('admin_dashboard'))

        rescheduled_count = 0
        for appt in high_risk_appts:
            appt_id = appt['id']
            patient_id = appt['patient_id']
            hospital_id = appt['hospital_id']
            department_id = appt['department_id']
            doctor_id = appt['doctor_id']
            current_date = appt['date']
            no_show_prob = appt['no_show_prob']
            app.logger.debug(f"Processing high-risk appointment ID {appt_id}: no_show_prob={no_show_prob}")

            new_date, new_time = find_available_slot(doctor_id, current_date, patient_id)
            if not new_date or not new_time:
                app.logger.warning(f"No available slot found for appointment ID {appt_id}")
                continue

            try:
                appointment_date = pd.to_datetime(new_date)
                current_date_dt = pd.to_datetime('2025-05-09')
                max_date = current_date_dt + relativedelta(years=1)

                if appointment_date < current_date_dt or appointment_date > max_date:
                    app.logger.warning(f"Invalid date range for appointment ID {appt_id}: {new_date}")
                    continue
            except ValueError as e:
                app.logger.error(f"Invalid date format for appointment ID {appt_id}: {new_date}. Error: {e}")
                continue

            past_appointments = query_db(
                "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
                (patient_id, new_date)
            )
            previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')

            hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
            if not hospital_location:
                app.logger.warning(f"Invalid hospital_id {hospital_id} for appointment ID {appt_id}")
                continue
            hospital_location = hospital_location['location']

            lead_time = (appointment_date - current_date_dt).days
            distance_5km = 0 if 'Lagos' in hospital_location else 1
            time_of_day_morning = 1 if 'AM' in new_time.upper() else 0
            is_weekday = appointment_date.day_name() in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            is_weekday_weekend = 0 if is_weekday else 1

            features = [previous_no_shows, lead_time, distance_5km, time_of_day_morning, is_weekday_weekend]

            try:
                no_show_prob = predict_no_show(features)
                reschedule_prob = predict_reschedule(features)

                if not (0 <= no_show_prob <= 100 and 0 <= reschedule_prob <= 100):
                    app.logger.warning(f"Invalid probabilities for appointment ID {appt_id}: no_show_prob={no_show_prob}, reschedule_prob={reschedule_prob}")
                    continue
            except Exception as e:
                app.logger.error(f"Error predicting probabilities for appointment ID {appt_id}: {e}")
                continue

            query = "UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled', no_show_prob = ?, reschedule_prob = ? WHERE id = ?"
            query_db(query, (new_date, new_time, no_show_prob, reschedule_prob, appt_id), commit=True)

            app.logger.info(f"Auto-rescheduled appointment ID {appt_id} to {new_date} at {new_time}")
            rescheduled_count += 1

        flash(f"Successfully rescheduled {rescheduled_count} high-risk appointments.", "success")
        return redirect(url_for('admin_dashboard'))

    except Exception as e:
        app.logger.error(f"Error during auto-rescheduling all: {e}")
        flash("An error occurred during auto-rescheduling.", "danger")
        return redirect(url_for('admin_dashboard'))

# Debug Routes (Remove after testing)
# Debug route to view all appointments
@app.route('/debug_appointments', methods=['GET'])
@login_required('admin')
def debug_appointments():
    appointments = query_db("SELECT * FROM appointments")
    return jsonify(appointments)

# Debug route to manually trigger the no-show check
@app.route('/debug_check_no_shows', methods=['GET'])
@login_required('admin')
def debug_check_no_shows():
    check_no_shows_and_reschedule()
    return "No-show check and rescheduling completed."

# Debug route to test email sending
@app.route('/debug_email', methods=['GET'])
@login_required('admin')
def debug_email():
    msg = Message("Test Email from Patient Appointment System", 
                  recipients=["lrdmuyi85@gmail.com"], 
                  body="This is a test email to verify email sending works.")
    try:
        mail.send(msg)
        return "Test email sent successfully."
    except Exception as e:
        return f"Failed to send test email: {str(e)}"
    
@app.route('/debug_users', methods=['GET'])
@login_required('admin')
def debug_users():
    users = query_db("SELECT * FROM users")
    return jsonify(users)

if __name__ == '__main__':
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_no_shows_and_reschedule, 'cron', hour=8, minute=0)
    scheduler.start()

    try:
        app.run(debug=True, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()