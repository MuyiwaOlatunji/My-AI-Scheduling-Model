from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from apscheduler.schedulers.background import BackgroundScheduler
from flask_mail import Mail, Message
import sqlite3
import pandas as pd
import numpy as np
import os
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta, date, time
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import joblib
import re

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secure_secret_key_here")

# Enhanced Session configuration
app.config.update(
    SESSION_COOKIE_NAME='flask_session',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_COOKIE_SECURE=True,  # Requires HTTPS in production
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_REFRESH_EACH_REQUEST=True,
    # Clear session when browser closes
    SESSION_PERMANENT=False
)

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
            if 'user_id' not in session:
                flash("Please log in first.", "danger")
                return redirect(url_for('hospital_admin_login' if 'hospital_admin' in roles else 'patient_login'))
            
            # Verify user still exists in database
            user = query_db("SELECT id, role FROM users WHERE id = ?", (session['user_id'],), one=True)
            if not user:
                session.clear()
                flash("User account not found. Please log in again.", "danger")
                return redirect(url_for('index'))
            
            if user['role'] not in roles:
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
                  gender TEXT, marriage_status TEXT, occupation TEXT, hospital_id INTEGER, phone TEXT)''')
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
    try:
        doctor = query_db("SELECT schedule FROM doctors WHERE id = ?", (doctor_id,), one=True)
        if not doctor or not doctor['schedule']:
            return False
            
        schedule = doctor['schedule'].lower()
        match = re.match(r'^([a-z]{3})-([a-z]{3})\s+([\d:apm]+)-([\d:apm]+)$', schedule)
        if not match:
            app.logger.error(f"Invalid schedule format for doctor {doctor_id}: {schedule}")
            return False
            
        start_day, end_day, start_time_str, end_time_str = match.groups()
        
        # Convert time to 24-hour format
        def parse_time(time_str):
            time_str = time_str.strip()
            if ':' in time_str:
                time_part, period = time_str[:-2], time_str[-2:]
                hour, minute = map(int, time_part.split(':'))
            else:
                hour = int(time_str[:-2])
                minute = 0
                period = time_str[-2:]
            
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            return hour, minute
        
        start_hour, start_min = parse_time(start_time_str)
        end_hour, end_min = parse_time(end_time_str)
        
        # Check day availability
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
        
        # Check time availability
        try:
            slot_time = datetime.strptime(time_slot, '%I:%M %p').time()
            slot_dt = datetime.combine(date_obj, slot_time)
            
            start_dt = datetime.combine(date_obj, time(start_hour, start_min))
            end_dt = datetime.combine(date_obj, time(end_hour, end_min))
            
            if not (start_dt <= slot_dt < end_dt):
                return False
        except ValueError as e:
            app.logger.error(f"Error parsing time slot: {e}")
            return False
        
        # Check if slot is already booked
        existing = query_db(
            "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status NOT IN ('cancelled', 'closed')",
            (doctor_id, date, time_slot), one=True
        )
        return not bool(existing)
        
    except Exception as e:
        app.logger.error(f"Error in is_doctor_available: {e}")
        return False

# Prediction functions using trained models
def predict_no_show(features):
    try:
        model = joblib.load('model/rf_no_show_model.pkl')
        feature_cols = [
            'previous_no_shows', 'lead_time', 'distance', 'time_of_day', 
            'is_weekday', 'age', 'doctor_gender', 'patient_gender', 
            'marriage_status', 'has_occupation', 'health_challenge_length'
        ]
        features_df = pd.DataFrame([features], columns=feature_cols)
        prob = model.predict_proba(features_df)[0][1] * 100
        return prob
    except Exception as e:
        app.logger.error(f"Error predicting no-show: {e}")
        return 10.0

def predict_reschedule(features):
    try:
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

# Routes
@app.before_request
def check_session():
    # Skip session check for these endpoints
    if request.endpoint in ['patient_login', 'hospital_admin_login', 'super_admin_login', 'logout', 'static', 'index']:
        return
    
    # Check if user is logged in
    if 'user_id' not in session:
        flash("Please log in to access this page.", "danger")
        return redirect(url_for('index'))
    
    # Verify user still exists
    user = query_db("SELECT id FROM users WHERE id = ?", (session['user_id'],), one=True)
    if not user:
        session.clear()
        flash("Session expired. Please log in again.", "warning")
        return redirect(url_for('index'))
        
@app.route('/')
def index():
    if 'user_id' in session:
        user = query_db("SELECT role FROM users WHERE id = ?", (session['user_id'],), one=True)
        if user:
            if user['role'] == 'hospital_admin':
                return redirect(url_for('hospital_admin_dashboard'))
            elif user['role'] == 'patient':
                return redirect(url_for('patient_dashboard'))
            elif user['role'] == 'super_admin':
                return redirect(url_for('super_admin'))
    
    # Clear any invalid session
    session.clear()
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            user_data = {
                'name': request.form['name'],
                'email': request.form['email'],
                'phone': request.form.get('phone', ''),  # Use get with default empty string
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
            # Clear previous session
            session.clear()
            
            # Set new session with strict security
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['_fresh'] = True  # Marks the session as fresh
            
            # Create response with security headers
            response = make_response(redirect(url_for('patient_dashboard')))
            response.headers['Cache-Control'] = 'no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            
            flash('Logged in successfully', 'success')
            return response
        
        flash('Invalid credentials', 'danger')
    return render_template('patient_login.html')

@app.route('/hospital_admin_login', methods=['GET', 'POST'])
def hospital_admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = query_db("SELECT * FROM users WHERE email = ? AND role = 'hospital_admin'", (email,), one=True)
        
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['_fresh'] = True
            
            response = make_response(redirect(url_for('hospital_admin_dashboard')))
            response.headers['Cache-Control'] = 'no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            
            flash("Logged in successfully.", "success")
            return response
        
        flash("Invalid credentials or not a hospital admin.", "danger")
    return render_template('hospital_admin_login.html')

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
            session['_fresh'] = True
            
            response = make_response(redirect(url_for('super_admin')))
            response.headers['Cache-Control'] = 'no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            
            flash("Logged in successfully.", "success")
            return response
        
        flash("Invalid credentials or not a super admin.", "danger")
        return redirect(url_for('super_admin_login'))
    
    return render_template('super_admin_login.html')

@app.route('/patient')
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

@app.route('/book', methods=['GET', 'POST'])
@login_required(['patient'])
def book_appointment():
    if request.method == 'POST':
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

@app.route('/hospital_admin')
@login_required(['hospital_admin'])
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
        
        if 'add_doctor' in request.form:
            # Format the schedule string properly
            start_day = request.form['start_day'].lower()
            end_day = request.form['end_day'].lower()
            start_time = request.form['start_time'].replace(' ', '').lower()
            end_time = request.form['end_time'].replace(' ', '').lower()
            
            schedule = f"{start_day}-{end_day} {start_time}-{end_time}"
            
            query_db(
                "INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                (hospital_id, request.form['dept_id'], request.form['doctor_name'], 
                 request.form['doctor_gender'], schedule),
                commit=True
            )
            flash("Doctor added successfully", "success")
            return redirect(url_for('manage_departments'))
        
        if 'delete_doctor' in request.form:
            query_db("DELETE FROM doctors WHERE id = ?", (request.form['doctor_id'],), commit=True)
            flash("Doctor deleted successfully", "success")
            return redirect(url_for('manage_departments'))
    
    # Get all departments with their doctors
    departments = query_db("""
        SELECT d.id, d.name, 
               (SELECT COUNT(*) FROM doctors WHERE department_id = d.id) AS doctor_count
        FROM departments d 
        WHERE d.hospital_id = ?
        ORDER BY d.name
    """, (hospital_id,))
    
    # Get all doctors for each department
    for dept in departments:
        dept['doctors'] = query_db("""
            SELECT id, name, gender, schedule 
            FROM doctors 
            WHERE department_id = ?
            ORDER BY name
        """, (dept['id'],))
    
    return render_template('manage_departments.html', departments=departments)

@app.route('/get_doctor_details/<int:doctor_id>')
@login_required(['hospital_admin'])
def get_doctor_details(doctor_id):
    doctor = query_db("SELECT * FROM doctors WHERE id = ?", (doctor_id,), one=True)
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    # Parse the schedule if it exists
    schedule_parts = {}
    if doctor['schedule']:
        try:
            parts = doctor['schedule'].lower().split(' ')
            if len(parts) == 2:
                days_part, times_part = parts
                start_day, end_day = days_part.split('-')
                start_time, end_time = times_part.split('-')
                
                # Convert times to 12-hour format for display
                def format_time_for_display(time_str):
                    try:
                        if ':' in time_str:
                            hour, minute = map(int, time_str.split(':'))
                        else:
                            hour = int(time_str)
                            minute = 0
                        
                        period = 'AM' if hour < 12 else 'PM'
                        display_hour = hour % 12 or 12
                        return f"{display_hour}:{minute:02d} {period}"
                    except:
                        return time_str
                
                schedule_parts = {
                    'start_day': start_day,
                    'end_day': end_day,
                    'start_time': format_time_for_display(start_time),
                    'end_time': format_time_for_display(end_time)
                }
        except Exception as e:
            app.logger.error(f"Error parsing schedule: {e}")
    
    return jsonify({
        'id': doctor['id'],
        'name': doctor['name'],
        'gender': doctor['gender'],
        'schedule': doctor['schedule'],
        'schedule_parts': schedule_parts
    })

@app.route('/update_doctor', methods=['POST'])
@login_required(['hospital_admin'])
def update_doctor():
    try:
        doctor_id = request.form['doctor_id']
        name = request.form['name']
        gender = request.form['gender']
        start_day = request.form['start_day']
        end_day = request.form['end_day']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        
        # Format the schedule string
        schedule = f"{start_day}-{end_day} {start_time}-{end_time}"
        
        query_db(
            "UPDATE doctors SET name = ?, gender = ?, schedule = ? WHERE id = ?",
            (name, gender, schedule, doctor_id),
            commit=True
        )
        
        # Return success without message (let frontend handle the message)
        return jsonify({'success': True})
    except Exception as e:
        # Return error without message (let frontend handle the message)
        return jsonify({'success': False}), 400

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
    
    query_db("UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled' WHERE id = ?", 
             (new_date, new_time, appt_id), commit=True)
    flash("Appointment rescheduled", "success")
    return redirect(url_for('patient_dashboard'))

@app.route('/mark_attended/<int:appt_id>', methods=['POST'])
@login_required(['hospital_admin'])
def mark_attended(appt_id):
    query_db("UPDATE appointments SET status = 'attended' WHERE id = ?", (appt_id,), commit=True)
    flash("Appointment marked as attended", "success")
    return redirect(url_for('hospital_admin_dashboard'))

@app.route('/logout')
def logout():
    # Clear server-side session data
    session.clear()
    
    # Create response that clears client-side cookies and prevents caching
    response = make_response(redirect(url_for('index')))
    response.delete_cookie('session')
    response.delete_cookie(app.config['SESSION_COOKIE_NAME'])
    response.headers['Cache-Control'] = 'no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    
    flash("Logged out successfully", "success")
    return response

if __name__ == '__main__':
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_no_shows_and_reschedule, 'cron', hour=8)
    scheduler.start()
    
    # Run with extra security headers
    app.run(
        debug=True,
        use_reloader=False,
        ssl_context='adhoc' if os.getenv('FLASK_ENV') == 'production' else None
    )