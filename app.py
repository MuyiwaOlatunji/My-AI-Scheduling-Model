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
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER")
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
    
    existing = query_db(
        "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status NOT IN ('cancelled', 'closed')",
        (doctor_id, date, time_slot), one=True
    )
    return not bool(existing)

# Prediction functions using trained models
def predict_no_show(features):
    try:
        rf_model = joblib.load('model/rf_no_show_model.pkl')
        xgb_model = joblib.load('model/xgb_no_show_model.pkl')
        feature_cols = [
            'previous_no_shows', 'lead_time', 'distance', 'time_of_day', 
            'is_weekday', 'age', 'doctor_gender', 'patient_gender', 
            'marriage_status', 'has_occupation', 'health_challenge_length'
        ]
        features_df = pd.DataFrame([features], columns=feature_cols)
        rf_prob = rf_model.predict_proba(features_df)[0][1]
        xgb_prob = xgb_model.predict_proba(features_df)[0][1]
        ensemble_prob = (rf_prob + xgb_prob) / 2 * 100
        return ensemble_prob
    except Exception as e:
        app.logger.error(f"Error predicting no-show: {e}")
        return 10.0

def predict_reschedule(features):
    try:
        rf_model = joblib.load('model/rf_reschedule_model.pkl')
        xgb_model = joblib.load('model/xgb_reschedule_model.pkl')
        feature_cols = [
            'previous_no_shows', 'lead_time', 'distance', 'time_of_day', 
            'is_weekday', 'age', 'doctor_gender', 'patient_gender', 
            'marriage_status', 'has_occupation', 'health_challenge_length'
        ]
        features_df = pd.DataFrame([features], columns=feature_cols)
        rf_prob = rf_model.predict_proba(features_df)[0][1]
        xgb_prob = xgb_model.predict_proba(features_df)[0][1]
        ensemble_prob = (rf_prob + xgb_prob) / 2 * 100
        return ensemble_prob
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

# Retrain models with new data
def retrain_model():
    with app.app_context():
        past_appts = query_db("""
            SELECT a.*, u.age, u.gender AS patient_gender, u.marriage_status, u.occupation, 
                   h.location, doc.gender AS doctor_gender, a.health_challenge
            FROM appointments a
            JOIN users u ON a.patient_id = u.id
            JOIN hospitals h ON a.hospital_id = h.id
            JOIN doctors doc ON a.doctor_id = doc.id
            WHERE a.date < ? AND a.status IN ('attended', 'no-show')
        """, (date.today().strftime('%Y-%m-%d'),))
        
        if not past_appts:
            app.logger.info("No data available for retraining")
            return
        
        df = pd.DataFrame(past_appts)
        df['no_show'] = df['status'].apply(lambda x: 1 if x == 'no-show' else 0)
        df['reschedule'] = df['status'].apply(lambda x: 1 if x == 'rescheduled' else 0)
        
        # Prepare features
        df['previous_no_shows'] = df.apply(lambda row: query_db(
            "SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND date < ? AND status = 'no-show'",
            (row['patient_id'], row['date']), one=True)['COUNT(*)'], axis=1)
        
        df['lead_time'] = (pd.to_datetime(df['date']) - pd.to_datetime(df['booking_date'])).dt.days
        df['distance'] = df.apply(lambda row: 0 if row['location'] == query_db(
            "SELECT location FROM users WHERE id = ?", (row['patient_id'],), one=True)['location'] else 1, axis=1)
        df['time_of_day'] = df['slot_time'].apply(lambda x: 1 if 'AM' in str(x).upper() else 0)
        df['is_weekday'] = pd.to_datetime(df['date']).dt.weekday.apply(lambda x: 0 if x < 5 else 1)
        df['doctor_gender'] = df['doctor_gender'].map({'M': 0, 'F': 1})
        df['patient_gender'] = df['patient_gender'].map({'M': 0, 'F': 1, 'Other': 2})
        df['marriage_status'] = df['marriage_status'].map({
            'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3
        })
        df['has_occupation'] = df['occupation'].apply(lambda x: 1 if x and str(x).strip() else 0)
        df['health_challenge_length'] = df['health_challenge'].apply(lambda x: len(str(x)) if x else 0)
        
        features = [
            'previous_no_shows', 'lead_time', 'distance', 'time_of_day', 
            'is_weekday', 'age', 'doctor_gender', 'patient_gender', 
            'marriage_status', 'has_occupation', 'health_challenge_length'
        ]
        X = df[features]
        y_no_show = df['no_show']
        y_reschedule = df['reschedule']
        
        # Retrain models (simplified - in production you'd use the full training logic)
        from sklearn.ensemble import RandomForestClassifier
        from xgboost import XGBClassifier
        
        rf_ns = RandomForestClassifier(n_estimators=100, random_state=42)
        rf_ns.fit(X, y_no_show)
        joblib.dump(rf_ns, 'model/rf_no_show_model.pkl')
        
        xgb_ns = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42)
        xgb_ns.fit(X, y_no_show)
        joblib.dump(xgb_ns, 'model/xgb_no_show_model.pkl')
        
        app.logger.info("Models retrained successfully")

# Routes
@app.route('/')
def index():
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
            
            if user['role'] == 'patient':
                return redirect(url_for('patient_dashboard'))
            elif user['role'] == 'hospital_admin':
                return redirect(url_for('hospital_admin_dashboard'))
            elif user['role'] == 'super_admin':
                return redirect(url_for('super_admin_dashboard'))
        
        flash("Invalid credentials.", "danger")
    return render_template('login.html')

@app.route('/patient')
@login_required(['patient'])
def patient_dashboard():
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')
    
    if sort_by not in ['date', 'status']:
        sort_by = 'date'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
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
    
    return render_template('patient.html', appointments=appointments)

@app.route('/book', methods=['GET', 'POST'])
@login_required(['patient'])
def book_appointment():
    if request.method == 'POST':
        try:
            # Get form data
            hospital_id = request.form['hospital']
            department_id = request.form['department']
            doctor_id = request.form['doctor']
            date_str = request.form['date']
            slot_time = request.form['time']
            health_challenge = request.form['health_challenge']
            
            # Validate doctor availability
            if not is_doctor_available(doctor_id, date_str, slot_time):
                flash("Selected slot is not available", "danger")
                return redirect(url_for('book_appointment'))
            
            # Get patient and hospital data for prediction
            patient = query_db("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
            hospital = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
            
            # Prepare features for prediction
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d')
            booking_date = datetime.now()
            lead_time = (appointment_date - booking_date).days
            
            features = [
                query_db("SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND status = 'no-show'", 
                        (session['user_id'],), one=True)['COUNT(*)'],  # previous_no_shows
                lead_time,
                0 if patient['location'] == hospital['location'] else 1,  # distance
                1 if 'AM' in slot_time.upper() else 0,  # time_of_day
                0 if appointment_date.weekday() < 5 else 1,  # is_weekday
                patient['age'],  # age
                0 if query_db("SELECT gender FROM doctors WHERE id = ?", (doctor_id,), one=True)['gender'] == 'M' else 1,  # doctor_gender
                {'M': 0, 'F': 1, 'Other': 2}[patient['gender']],  # patient_gender
                {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}[patient['marriage_status']],  # marriage_status
                1 if patient['occupation'].strip() else 0,  # has_occupation
                len(health_challenge)  # health_challenge_length
            ]
            
            # Make predictions
            no_show_prob = predict_no_show(features)
            reschedule_prob = predict_reschedule(features)
            
            # Create appointment
            query_db("""
                INSERT INTO appointments 
                (patient_id, hospital_id, department_id, doctor_id, slot_time, date, booking_date, 
                 no_show_prob, reschedule_prob, status, health_challenge)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session['user_id'], hospital_id, department_id, doctor_id, slot_time, date_str, 
                booking_date.strftime('%Y-%m-%d'), no_show_prob, reschedule_prob, 'scheduled', health_challenge
            ), commit=True)
            
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
def super_admin_dashboard():
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
            # Create hospital
            hospital_id = query_db(
                "INSERT INTO hospitals (name, location) VALUES (?, ?)",
                (request.form['hospital_name'], request.form['location']),
                commit=True, return_id=True
            )
            
            # Create admin user
            query_db(
                "INSERT INTO users (name, email, password, role, hospital_id) VALUES (?, ?, ?, ?, ?)",
                (
                    request.form['admin_name'],
                    request.form['admin_email'],
                    generate_password_hash(request.form['admin_password']),
                    'hospital_admin',
                    hospital_id
                ),
                commit=True
            )
            
            flash("Hospital registered successfully", "success")
            return redirect(url_for('super_admin_dashboard'))
        except Exception as e:
            flash(f"Error registering hospital: {str(e)}", "danger")
    
    return render_template('hospital_register.html')

@app.route('/manage_departments', methods=['GET', 'POST'])
@login_required(['hospital_admin'])
def manage_departments():
    hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
    
    if request.method == 'POST':
        if 'add_department' in request.form:
            query_db(
                "INSERT INTO departments (hospital_id, name) VALUES (?, ?)",
                (hospital_id, request.form['name']),
                commit=True
            )
            flash("Department added", "success")
        elif 'delete_department' in request.form:
            dept_id = request.form['dept_id']
            if not query_db("SELECT id FROM doctors WHERE department_id = ?", (dept_id,)):
                query_db("DELETE FROM departments WHERE id = ?", (dept_id,), commit=True)
                flash("Department deleted", "success")
            else:
                flash("Cannot delete department with doctors", "danger")
        elif 'add_doctor' in request.form:
            query_db(
                "INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                (
                    hospital_id,
                    request.form['dept_id'],
                    request.form['doctor_name'],
                    request.form['doctor_gender'],
                    f"{request.form['start_day']}-{request.form['end_day']} {request.form['start_time']}-{request.form['end_time']}"
                ),
                commit=True
            )
            flash("Doctor added", "success")
        elif 'delete_doctor' in request.form:
            doctor_id = request.form['doctor_id']
            if not query_db("SELECT id FROM appointments WHERE doctor_id = ?", (doctor_id,)):
                query_db("DELETE FROM doctors WHERE id = ?", (doctor_id,), commit=True)
                flash("Doctor deleted", "success")
            else:
                flash("Cannot delete doctor with appointments", "danger")
        
        return redirect(url_for('manage_departments'))
    
    departments = query_db("SELECT id, name FROM departments WHERE hospital_id = ?", (hospital_id,))
    dept_doctors = {}
    for dept in departments:
        dept_doctors[dept['id']] = query_db(
            "SELECT id, name, gender, schedule FROM doctors WHERE department_id = ?", 
            (dept['id'],)
        )
    
    return render_template('manage_departments.html', departments=departments, dept_doctors=dept_doctors)

@app.route('/suspend_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def suspend_hospital(hospital_id):
    query_db(
        "UPDATE hospitals SET subscription_status = 'suspended' WHERE id = ?",
        (hospital_id,), commit=True
    )
    flash("Hospital suspended", "success")
    return redirect(url_for('super_admin_dashboard'))

@app.route('/activate_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def activate_hospital(hospital_id):
    expiry_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
    query_db(
        "UPDATE hospitals SET subscription_status = 'active', subscription_expiry_date = ? WHERE id = ?",
        (expiry_date, hospital_id), commit=True
    )
    flash("Hospital activated", "success")
    return redirect(url_for('super_admin_dashboard'))

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
    
    # Update appointment
    query_db(
        "UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled' WHERE id = ?",
        (new_date, new_time, appt_id), commit=True
    )
    
    flash("Appointment rescheduled", "success")
    return redirect(url_for('patient_dashboard'))

@app.route('/mark_attended/<int:appt_id>', methods=['POST'])
@login_required(['hospital_admin'])
def mark_attended(appt_id):
    query_db(
        "UPDATE appointments SET status = 'attended' WHERE id = ?",
        (appt_id,), commit=True
    )
    flash("Appointment marked as attended", "success")
    return redirect(url_for('hospital_admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    
    # Schedule background tasks
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_no_shows_and_reschedule, 'cron', hour=8)
    scheduler.add_job(retrain_model, 'cron', day_of_week='sun', hour=2)
    scheduler.start()
    
    app.run(debug=True, use_reloader=False)