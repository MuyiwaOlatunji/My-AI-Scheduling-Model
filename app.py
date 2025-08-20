import os
import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.csrf import generate_csrf
from wtforms import StringField, PasswordField, SubmitField, IntegerField, SelectField, TelField, EmailField
from wtforms.validators import DataRequired, Email, NumberRange, Length
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import joblib
import re
from dateutil.parser import parse

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "5507e4842f2c53c15f4a3bbd1e004e6ef59eb7007920c29d1c2b1bc133d90336"),
    SESSION_COOKIE_NAME='flask_session',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_PERMANENT=False
)

# Initialize CSRF protection
csrf = CSRFProtect(app)

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
logger = logging.getLogger(__name__)

# Flask-WTF Form Classes
class RegisterForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    phone = TelField('Phone', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=1, max=150)])
    location = StringField('Location', validators=[DataRequired()])
    gender = SelectField('Gender', choices=[('M', 'Male'), ('F', 'Female'), ('Other', 'Other')], validators=[DataRequired()])
    marriage_status = SelectField('Marital Status', choices=[('Single', 'Single'), ('Married', 'Married'), ('Divorced', 'Divorced'), ('Widowed', 'Widowed')], validators=[DataRequired()])
    occupation = StringField('Occupation', validators=[DataRequired()])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegisterHospitalForm(FlaskForm):
    hospital_name = StringField('Hospital Name', validators=[DataRequired(), Length(min=2, max=100)])
    location = StringField('Location', validators=[DataRequired()])
    admin_name = StringField('Admin Name', validators=[DataRequired(), Length(min=2, max=100)])
    admin_email = EmailField('Admin Email', validators=[DataRequired(), Email()])
    admin_password = PasswordField('Admin Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Register Hospital')

class UpdateProfileForm(FlaskForm):
    occupation = StringField('Occupation', validators=[DataRequired()])
    location = StringField('Location', validators=[DataRequired()])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=1, max=150)])
    submit = SubmitField('Save Profile')

# Authentication decorator
def login_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please log in first.", "danger")
                return redirect(url_for('hospital_admin_login' if 'hospital_admin' in roles else 'patient_login' if 'patient' in roles else 'super_admin_login'))
            
            user = query_db("SELECT id, role, hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)
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
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise e
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

    c.execute("SELECT COUNT(*) FROM users WHERE role = 'super_admin'")
    if c.fetchone()[0] == 0:
        hospitals = [
            ("Lagos General Hospital", "Lagos", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
            ("Abuja Medical Center", "Abuja", "active", (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')),
        ]
        c.executemany("INSERT INTO hospitals (name, location, subscription_status, subscription_expiry_date) VALUES (?, ?, ?, ?)", hospitals)
        c.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                  ("Super Admin", "admin@example.com", generate_password_hash("admin123"), "super_admin"))
        c.execute("INSERT INTO users (name, email, password, role, hospital_id) VALUES (?, ?, ?, ?, ?)",
                  ("Hospital Admin", "hospitaladmin@example.com", generate_password_hash("hospital123"), "hospital_admin", 1))
        c.execute("INSERT INTO users (name, email, password, role, age, location, gender, marriage_status, occupation, phone) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  ("Test Patient", "patient@example.com", generate_password_hash("patient123"), "patient", 25, "Lagos", "M", "Single", "Engineer", "1234567890"))
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (1, "Cardiology"))
        c.execute("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", (2, "Neurology"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (1, 1, "Dr. Jane Smith", "F", "mon-fri 09:00-17:00"))
        c.execute("INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
                  (2, 2, "Dr. John Brown", "M", "mon-fri 10:00-18:00"))
        conn.commit()
    conn.close()

# Normalize schedule time
def normalize_schedule_time(time_str):
    time_str = time_str.lower().strip()
    match = re.match(r'^(\d{1,2})(?::(\d{1,2}))?(am|pm)?$', time_str)
    if not match:
        raise ValueError(f"Invalid time format: {time_str}")
    hour, minute, period = match.groups()
    hour = int(hour)
    minute = int(minute or 0)
    if hour < 0 or hour > 23:
        raise ValueError("Hour must be between 0 and 23")
    if minute < 0 or minute > 59:
        raise ValueError("Minute must be between 0 and 59")
    if period:
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
    return f"{hour:02d}:{minute:02d}"

# Check doctor availability
def is_doctor_available(doctor_id, date, time_slot):
    try:
        doctor = query_db("SELECT schedule FROM doctors WHERE id = ?", (doctor_id,), one=True)
        if not doctor or not doctor['schedule']:
            return False
            
        schedule = doctor['schedule'].lower().strip()
        
        parts = schedule.split(' ')
        if len(parts) != 2:
            logger.error(f"Invalid schedule format for doctor {doctor_id}: {schedule}")
            return False
            
        days_part, times_part = parts
        
        days = days_part.split('-')
        if len(days) != 2:
            logger.error(f"Invalid days format in schedule: {schedule}")
            return False
            
        start_day, end_day = days
        
        times = times_part.split('-')
        if len(times) != 2:
            logger.error(f"Invalid times format in schedule: {schedule}")
            return False
            
        start_time_str, end_time_str = times
        
        try:
            start_time = parse(start_time_str).time()
            end_time = parse(end_time_str).time()
            slot_time = parse(time_slot).time()
        except ValueError as e:
            logger.error(f"Error parsing times: {start_time_str}-{end_time_str} or slot {time_slot}, Error: {e}")
            return False
        
        days_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
                   'fri': 4, 'sat': 5, 'sun': 6}
        
        start_day_idx = days_map.get(start_day)
        end_day_idx = days_map.get(end_day)
        
        if start_day_idx is None or end_day_idx is None:
            logger.error(f"Invalid days in schedule: {start_day}-{end_day}")
            return False
        
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        day_idx = date_obj.weekday()
        
        if start_day_idx <= end_day_idx:
            if not (start_day_idx <= day_idx <= end_day_idx):
                return False
        else:
            if not (day_idx >= start_day_idx or day_idx <= end_day_idx):
                return False
        
        start_dt = datetime.combine(date_obj, start_time)
        end_dt = datetime.combine(date_obj, end_time)
        slot_dt = datetime.combine(date_obj, slot_time)
        
        if not (start_dt <= slot_dt < end_dt):
            return False
        
        existing = query_db(
            "SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status NOT IN ('cancelled', 'closed')",
            (doctor_id, date, time_slot), one=True
        )
        return not bool(existing)
        
    except Exception as e:
        logger.error(f"Error in is_doctor_available: {e}")
        return False

# Prediction functions
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
        logger.error(f"Error predicting no-show: {e}")
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
        logger.error(f"Error predicting reschedule: {e}")
        return 10.0

# Check no-shows and reschedule
def check_no_shows_and_reschedule():
    with app.app_context():
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        potential_no_shows = query_db("""
            SELECT a.id, a.patient_id, a.doctor_id, a.date, a.slot_time, u.email, h.name AS hospital_name, 
                   d.name AS department_name, doc.name AS doctor_name, doc.schedule
            FROM appointments a
            JOIN users u ON a.patient_id = u.id
            JOIN hospitals h ON a.hospital_id = h.id
            JOIN departments d ON a.department_id = d.id
            JOIN doctors doc ON a.doctor_id = doc.id
            WHERE a.date = ? AND a.status IN ('scheduled', 'rescheduled')
        """, (yesterday,))
        
        for appt in potential_no_shows:
            query_db("UPDATE appointments SET status = 'no_show' WHERE id = ?", (appt['id'],), commit=True)
            
            patient = query_db("SELECT * FROM users WHERE id = ?", (appt['patient_id'],), one=True)
            hospital = query_db("SELECT location FROM hospitals WHERE id = ?", 
                              (query_db("SELECT hospital_id FROM appointments WHERE id = ?", (appt['id'],), one=True)['hospital_id'],), one=True)

            features = [
                query_db("SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND status = 'no_show'", 
                        (appt['patient_id'],), one=True)['COUNT(*)'],
                1,
                0 if patient['location'] == hospital['location'] else 1,
                1 if 'AM' in appt['slot_time'].upper() else 0,
                0 if datetime.strptime(appt['date'], '%Y-%m-%d').weekday() < 5 else 1,
                patient['age'] or 30,
                0 if query_db("SELECT gender FROM doctors WHERE id = ?", (appt['doctor_id'],), one=True)['gender'] == 'M' else 1,
                {'M': 0, 'F': 1, 'Other': 2}.get(patient['gender'], 0),
                {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}.get(patient['marriage_status'], 0),
                1 if patient['occupation'] and patient['occupation'].strip() else 0,
                len(query_db("SELECT health_challenge FROM appointments WHERE id = ?", (appt['id'],), one=True)['health_challenge'] or '')
            ]
            
            no_show_prob = predict_no_show(features)
            reschedule_prob = predict_reschedule(features)
            
            schedule = appt['schedule'].lower().strip()
            parts = schedule.split(' ')
            if len(parts) != 2:
                logger.error(f"Invalid schedule format for doctor {appt['doctor_id']}: {schedule}")
                continue
            
            times = parts[1].split('-')
            if len(times) != 2:
                logger.error(f"Invalid times format in schedule: {schedule}")
                continue
            
            start_time_str, end_time_str = times
            try:
                start_time = parse(start_time_str).time()
                end_time = parse(end_time_str).time()
            except ValueError as e:
                logger.error(f"Error parsing schedule times: {start_time_str}-{end_time_str}, Error: {e}")
                continue
            
            all_slots = []
            current_time = datetime.combine(datetime.today(), start_time)
            end_time_dt = datetime.combine(datetime.today(), end_time)
            while current_time < end_time_dt:
                slot = current_time.strftime('%I:%M %p')
                all_slots.append(slot)
                current_time += timedelta(hours=1)
            
            current_date = datetime.strptime(appt['date'], '%Y-%m-%d')
            for days_ahead in range(1, 8):
                new_date = (current_date + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
                existing_appts = query_db(
                    "SELECT slot_time FROM appointments WHERE doctor_id = ? AND date = ? AND status NOT IN ('cancelled', 'closed')",
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
                else:
                    continue
                break

# Routes
@app.route('/')
def index():
    logger.info(f"Index route session: {session}")
    if 'user_id' in session:
        user = query_db("SELECT role FROM users WHERE id = ?", (session['user_id'],), one=True)
        if user:
            if user['role'] == 'hospital_admin':
                return redirect(url_for('hospital_admin_dashboard'))
            elif user['role'] == 'patient':
                return redirect(url_for('patient_dashboard'))
            elif user['role'] == 'super_admin':
                return redirect(url_for('super_admin'))
    
    session.clear()
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    try:
        return app.send_static_file('favicon.ico')
    except Exception as e:
        logger.error(f"Error serving favicon: {e}")
        return '', 204

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    logger.info(f"Register route session: {session}")
    if request.method == 'POST':
        logger.info(f"Register form data: {request.form}")
        if form.validate_on_submit():
            try:
                user_data = {
                    'name': form.name.data.strip(),
                    'email': form.email.data.lower().strip(),
                    'phone': form.phone.data.strip(),
                    'password': generate_password_hash(form.password.data),
                    'role': 'patient',
                    'age': form.age.data,
                    'location': form.location.data.strip(),
                    'gender': form.gender.data,
                    'marriage_status': form.marriage_status.data,
                    'occupation': form.occupation.data.strip()
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
            except Exception as e:
                logger.error(f"Error registering user: {e}")
                flash("An error occurred during registration.", "danger")
        else:
            logger.error(f"Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field.capitalize()}: {error}", "danger")
    return render_template('register.html', form=form)

@app.route('/patient_login', methods=['GET', 'POST'])
def patient_login():
    form = LoginForm()
    logger.info(f"Patient login session: {session}")
    if request.method == 'POST':
        logger.info(f"Patient login form data: {request.form}")
        if form.validate_on_submit():
            email = form.email.data.lower().strip()
            password = form.password.data
            
            user = query_db("SELECT * FROM users WHERE email = ? AND role = 'patient'", (email,), one=True)
            
            if user and check_password_hash(user['password'], password):
                session.clear()
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['_fresh'] = True
                
                response = make_response(redirect(url_for('patient_dashboard')))
                response.headers['Cache-Control'] = 'no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                
                flash('Logged in successfully', 'success')
                return response
            
            flash('Invalid credentials', 'danger')
        else:
            logger.error(f"Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field.capitalize()}: {error}", "danger")
    return render_template('patient_login.html', form=form, csrf_token=generate_csrf())

@app.route('/hospital_admin_login', methods=['GET', 'POST'])
def hospital_admin_login():
    form = LoginForm()
    logger.info(f"Hospital admin login session: {session}")
    if request.method == 'POST':
        logger.info(f"Hospital admin login form data: {request.form}")
        if form.validate_on_submit():
            email = form.email.data.lower().strip()
            password = form.password.data
            
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
        else:
            logger.error(f"Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field.capitalize()}: {error}", "danger")
    return render_template('hospital_admin_login.html', form=form, csrf_token=generate_csrf())

@app.route('/super_admin_login', methods=['GET', 'POST'])
def super_admin_login():
    form = LoginForm()
    logger.info(f"Super admin login session: {session}")
    if request.method == 'POST':
        logger.info(f"Super admin login form data: {request.form}")
        if form.validate_on_submit():
            email = form.email.data.lower().strip()
            password = form.password.data
            
            user = query_db("SELECT * FROM users WHERE email = ? AND role = 'super_admin'", (email,), one=True)
            
            if user and check_password_hash(user['password'], password):
                session.clear()
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['_fresh'] = True
                
                response = make_response(redirect(url_for('super_admin')))
                response.headers['Cache-Control'] = 'no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                
                flash("Logged in successfully.", "success")
                return response
            
            flash("Invalid credentials or not a super admin.", "danger")
        else:
            logger.error(f"Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field.capitalize()}: {error}", "danger")
    return render_template('super_admin_login.html', form=form, csrf_token=generate_csrf())

@app.route('/patient')
@login_required(['patient'])
def patient_dashboard():
    form = UpdateProfileForm()
    sort_by = request.args.get('sort_by', 'date')
    sort_order = request.args.get('sort_order', 'asc')
    if sort_by not in ['date', 'status']:
        sort_by = 'date'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    user = query_db("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
    appointments = query_db(f"""
        SELECT a.id, h.name AS hospital, d.name AS department, doc.name AS doctor, 
               a.date, a.slot_time, a.status, a.no_show_prob, a.reschedule_prob,
               a.doctor_id, doc.schedule AS doctor_schedule
        FROM appointments a
        JOIN hospitals h ON a.hospital_id = h.id
        JOIN departments d ON a.department_id = d.id
        JOIN doctors doc ON a.doctor_id = doc.id
        WHERE a.patient_id = ?
        ORDER BY {sort_by} {sort_order}
    """, (session['user_id'],))
    form.occupation.data = user['occupation'] or ''
    form.location.data = user['location'] or ''
    form.age.data = user['age'] or ''
    return render_template('patient.html', appointments=appointments, user=user, form=form, csrf_token=generate_csrf())

@app.route('/update_profile', methods=['POST'])
@login_required(['patient'])
def update_profile():
    form = UpdateProfileForm()
    logger.info(f"Update profile session: {session}")
    if request.method == 'POST':
        logger.info(f"Update profile form data: {request.form}")
        if form.validate_on_submit():
            try:
                occupation = form.occupation.data.strip()
                location = form.location.data.strip()
                age = form.age.data
                
                query_db(
                    "UPDATE users SET occupation = ?, location = ?, age = ? WHERE id = ?",
                    (occupation, location, age, session['user_id']),
                    commit=True
                )
                flash("Profile updated successfully", "success")
            except Exception as e:
                logger.error(f"Error updating profile: {e}")
                flash("Error updating profile", "danger")
        else:
            logger.error(f"Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field.capitalize()}: {error}", "danger")
    return redirect(url_for('patient_dashboard'))

@app.route('/book', methods=['GET', 'POST'])
@login_required(['patient'])
def book_appointment():
    if request.method == 'GET':
        hospitals = query_db("SELECT * FROM hospitals WHERE subscription_status = 'active'")
        return render_template('booking.html', hospitals=hospitals, csrf_token=generate_csrf())
    
    try:
        data = request.get_json()
        logger.info(f"Book appointment data: {data}")
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        hospital_id = int(data.get('hospital', 0))
        department_id = int(data.get('department', 0))
        doctor_id = int(data.get('doctor', 0))
        date_str = data.get('date')
        slot_time = data.get('time')
        health_challenge = data.get('health_challenge', '').strip()

        if not all([hospital_id, department_id, doctor_id, date_str, slot_time, health_challenge]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        try:
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format'}), 400

        if appointment_date.date() < date.today():
            return jsonify({'success': False, 'message': 'Cannot book appointments in the past'}), 400

        if not is_doctor_available(doctor_id, date_str, slot_time):
            return jsonify({'success': False, 'message': 'Selected slot is not available'}), 400

        patient = query_db("SELECT * FROM users WHERE id = ?", (session['user_id'],), one=True)
        hospital = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        doctor = query_db("SELECT gender FROM doctors WHERE id = ?", (doctor_id,), one=True)

        if not patient or not hospital or not doctor:
            return jsonify({'success': False, 'message': 'Invalid hospital, doctor, or patient'}), 400

        features = [
            query_db("SELECT COUNT(*) FROM appointments WHERE patient_id = ? AND status = 'no_show'", 
                    (session['user_id'],), one=True)['COUNT(*)'],
            (appointment_date - datetime.now()).days,
            0 if patient['location'] == hospital['location'] else 1,
            1 if 'AM' in slot_time.upper() else 0,
            0 if appointment_date.weekday() < 5 else 1,
            patient['age'] or 30,
            0 if doctor['gender'] == 'M' else 1,
            {'M': 0, 'F': 1, 'Other': 2}.get(patient['gender'], 0),
            {'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3}.get(patient['marriage_status'], 0),
            1 if patient['occupation'] and patient['occupation'].strip() else 0,
            len(health_challenge)
        ]
        
        no_show_prob = predict_no_show(features)
        reschedule_prob = predict_reschedule(features)

        appointment_id = query_db("""
            INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, 
            slot_time, date, booking_date, no_show_prob, reschedule_prob, 
            status, health_challenge)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session['user_id'], hospital_id, department_id, doctor_id, 
              slot_time, date_str, date.today().strftime('%Y-%m-%d'), 
              no_show_prob, reschedule_prob, 'scheduled', health_challenge),
            commit=True, return_id=True)

        user = query_db("SELECT email, name FROM users WHERE id = ?", (session['user_id'],), one=True)
        hospital = query_db("SELECT name FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        department = query_db("SELECT name FROM departments WHERE id = ?", (department_id,), one=True)
        doctor = query_db("SELECT name FROM doctors WHERE id = ?", (doctor_id,), one=True)

        msg = Message(
            "Appointment Confirmation",
            recipients=[user['email']],
            body=f"""
            Dear {user['name']},
            
            Your appointment has been booked:
            Hospital: {hospital['name']}
            Department: {department['name']}
            Doctor: {doctor['name']}
            Date: {date_str}
            Time: {slot_time}
            Health Challenge: {health_challenge}
            
            Thank you.
            """
        )
        mail.send(msg)
        return jsonify({
            'success': True,
            'message': 'Appointment booked successfully',
            'redirect': url_for('patient_dashboard')
        })

    except Exception as e:
        logger.error(f"Error booking appointment: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get_departments/<int:hospital_id>')
def get_departments(hospital_id):
    try:
        departments = query_db("SELECT id, name FROM departments WHERE hospital_id = ?", (hospital_id,))
        return jsonify([{'id': dept['id'], 'name': dept['name']} for dept in departments])
    except Exception as e:
        logger.error(f"Error fetching departments: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_doctors/<int:department_id>')
def get_doctors(department_id):
    try:
        doctors = query_db("SELECT id, name FROM doctors WHERE department_id = ?", (department_id,))
        return jsonify([{'id': doc['id'], 'name': doc['name']} for doc in doctors])
    except Exception as e:
        logger.error(f"Error fetching doctors: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_available_slots')
def get_available_slots():
    try:
        doctor_id = request.args.get('doctor_id')
        date = request.args.get('date')
        
        if not doctor_id or not date:
            return jsonify({'error': 'Missing parameters'}), 400
        
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
        
        doctor = query_db("SELECT schedule FROM doctors WHERE id = ?", (doctor_id,), one=True)
        if not doctor or not doctor['schedule']:
            return jsonify([]), 200
        
        schedule = doctor['schedule'].lower().strip()
        parts = schedule.split(' ')
        if len(parts) != 2:
            logger.error(f"Invalid schedule format for doctor {doctor_id}: {schedule}")
            return jsonify([]), 200
        
        times = parts[1].split('-')
        if len(times) != 2:
            logger.error(f"Invalid times format in schedule: {schedule}")
            return jsonify([]), 200
        
        start_time_str, end_time_str = times
        
        try:
            start_time = parse(start_time_str).time()
            end_time = parse(end_time_str).time()
        except ValueError as e:
            logger.error(f"Error parsing schedule times: {start_time_str}-{end_time_str}, Error: {e}")
            return jsonify([]), 200
        
        all_slots = []
        current_time = datetime.combine(datetime.today(), start_time)
        end_time_dt = datetime.combine(datetime.today(), end_time)
        while current_time < end_time_dt:
            slot = current_time.strftime('%I:%M %p')
            all_slots.append(slot)
            current_time += timedelta(hours=1)
        
        booked_slots = [a['slot_time'] for a in query_db(
            "SELECT slot_time FROM appointments WHERE doctor_id = ? AND date = ? AND status NOT IN ('cancelled', 'closed')",
            (doctor_id, date)
        )]
        
        available_slots = [slot for slot in all_slots if slot not in booked_slots and is_doctor_available(doctor_id, date, slot)]
        
        return jsonify(available_slots), 200
    
    except Exception as e:
        logger.error(f"Error in get_available_slots: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/doctors/<int:doctor_id>/details')
@login_required(['hospital_admin'])
def get_doctor_details(doctor_id):
    try:
        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            return jsonify({'error': 'No hospital assigned to this admin'}), 403
        doctor = query_db("SELECT id, name, gender, schedule FROM doctors WHERE id = ? AND hospital_id = ?", (doctor_id, hospital_id), one=True)
        if not doctor:
            return jsonify({'error': 'Doctor not found or not authorized'}), 404
            
        schedule_parts = {}
        if doctor['schedule']:
            parts = doctor['schedule'].lower().split(' ')
            if len(parts) == 2:
                days = parts[0].split('-')
                times = parts[1].split('-')
                if len(days) == 2:
                    schedule_parts['start_day'] = days[0]
                    schedule_parts['end_day'] = days[1]
                if len(times) == 2:
                    schedule_parts['start_time'] = times[0]
                    schedule_parts['end_time'] = times[1]
        
        return jsonify({
            'id': doctor['id'],
            'name': doctor['name'],
            'gender': doctor['gender'],
            'schedule': doctor['schedule'],
            'schedule_parts': schedule_parts
        })
    except Exception as e:
        logger.error(f"Error getting doctor details: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/departments/<int:department_id>/doctors')
@login_required(['hospital_admin'])
def get_department_doctors(department_id):
    try:
        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            return jsonify({'error': 'No hospital assigned to this admin'}), 403
        doctors = query_db("SELECT id, name, gender, schedule FROM doctors WHERE department_id = ? AND hospital_id = ? ORDER BY name", (department_id, hospital_id))
        return jsonify([dict(doctor) for doctor in doctors])
    except Exception as e:
        logger.error(f"Error fetching department doctors: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search_hospitals')
@login_required(['super_admin', 'patient'])
def search_hospitals():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify([]), 200
        
        hospitals = query_db(
            "SELECT id, name, location AS address FROM hospitals WHERE name LIKE ? OR location LIKE ?",
            (f"%{query}%", f"%{query}%")
        )
        return jsonify(hospitals)
    except Exception as e:
        logger.error(f"Error searching hospitals: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search_doctors')
@login_required(['patient', 'hospital_admin'])
def search_doctors():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify([]), 200
        
        if session['role'] == 'hospital_admin':
            hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
            if hospital_id is None:
                return jsonify({'error': 'No hospital assigned to this admin'}), 403
            doctors = query_db(
                """
                SELECT d.id, d.name, d.schedule, dep.name AS department_name
                FROM doctors d
                JOIN departments dep ON d.department_id = dep.id
                WHERE d.hospital_id = ? AND (d.name LIKE ? OR dep.name LIKE ?)
                """,
                (hospital_id, f"%{query}%", f"%{query}%")
            )
        else:
            doctors = query_db(
                """
                SELECT d.id, d.name, d.schedule, dep.name AS department_name
                FROM doctors d
                JOIN departments dep ON d.department_id = dep.id
                JOIN hospitals h ON d.hospital_id = h.id
                WHERE h.subscription_status = 'active' AND (d.name LIKE ? OR dep.name LIKE ?)
                """,
                (f"%{query}%", f"%{query}%")
            )
        return jsonify(doctors)
    except Exception as e:
        logger.error(f"Error searching doctors: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search_appointments')
@login_required(['patient', 'hospital_admin'])
def search_appointments():
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify([]), 200
        
        if session['role'] == 'hospital_admin':
            hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
            if hospital_id is None:
                return jsonify({'error': 'No hospital assigned to this admin'}), 403
            appointments = query_db(
                """
                SELECT a.id, a.date, a.slot_time AS time, a.status, d.name AS doctor_name,
                       a.doctor_id, d.schedule AS doctor_schedule
                FROM appointments a
                JOIN doctors d ON a.doctor_id = d.id
                JOIN users u ON a.patient_id = u.id
                WHERE a.hospital_id = ? AND (u.name LIKE ? OR d.name LIKE ? OR a.status LIKE ?)
                """,
                (hospital_id, f"%{query}%", f"%{query}%", f"%{query}%")
            )
        else:
            appointments = query_db(
                """
                SELECT a.id, a.date, a.slot_time AS time, a.status, d.name AS doctor_name,
                       a.doctor_id, d.schedule AS doctor_schedule
                FROM appointments a
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.patient_id = ? AND (d.name LIKE ? OR a.status LIKE ?)
                """,
                (session['user_id'], f"%{query}%", f"%{query}%")
            )
        return jsonify(appointments)
    except Exception as e:
        logger.error(f"Error searching appointments: {e}")
        return jsonify({'error': str(e)}), 500

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
    return render_template('super_admin.html', hospitals=hospitals, search=search, csrf_token=generate_csrf())

@app.route('/hospital_admin')
@login_required(['hospital_admin'])
def hospital_admin_dashboard():
    try:
        user = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)
        if not user or user['hospital_id'] is None:
            flash("No hospital assigned to this admin. Contact super admin.", "danger")
            return redirect(url_for('logout'))
        
        hospital_id = user['hospital_id']
        hospital = query_db("SELECT name FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        if not hospital:
            flash("Hospital not found in database", "danger")
            return redirect(url_for('logout'))
        
        hospital_name = hospital['name']
        
        search = request.args.get('search', '')
        search_type = request.args.get('search_type', 'name')
        
        query = """
        SELECT a.id, u.name AS patient_name, u.email, 
               d.name AS department_name, doc.name AS doctor_name,
               a.slot_time, a.date, a.no_show_prob, a.reschedule_prob, 
               a.status, a.doctor_id, doc.schedule AS doctor_schedule
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
            elif search_type == 'status':
                query += " AND a.status LIKE ?"
            args.append(f"%{search}%")
        
        appointments = query_db(query, args)
        return render_template('hospital_admin.html', 
                             appointments=appointments, 
                             search=search, 
                             search_type=search_type,
                             hospital_name=hospital_name,
                             csrf_token=generate_csrf())
    
    except Exception as e:
        logger.error(f"Error in hospital_admin_dashboard: {e}")
        flash("An error occurred while loading the dashboard. Please ensure your hospital ID is set correctly.", "danger")
        return redirect(url_for('logout'))

@app.route('/hospital_register', methods=['GET', 'POST'])
@login_required(['super_admin'])
def hospital_register():
    form = RegisterHospitalForm()
    logger.info(f"Hospital register session: {session}")
    if request.method == 'POST':
        logger.info(f"Hospital register form data: {request.form}")
        if form.validate_on_submit():
            try:
                hospital_name = form.hospital_name.data.strip()
                location = form.location.data.strip()
                admin_name = form.admin_name.data.strip()
                admin_email = form.admin_email.data.lower().strip()
                admin_password = form.admin_password.data.strip()

                hospital_id = query_db(
                    "INSERT INTO hospitals (name, location, subscription_status) VALUES (?, ?, ?)",
                    (hospital_name, location, 'suspended'),
                    commit=True, return_id=True
                )
                query_db(
                    "INSERT INTO users (name, email, password, role, hospital_id) VALUES (?, ?, ?, ?, ?)",
                    (admin_name, admin_email, generate_password_hash(admin_password), 'hospital_admin', hospital_id),
                    commit=True
                )
                flash("Hospital registered successfully and set to suspended status.", "success")
                return redirect(url_for('super_admin'))
            except sqlite3.IntegrityError:
                flash("Admin email already exists.", "danger")
            except Exception as e:
                logger.error(f"Error registering hospital: {e}")
                flash(f"Error registering hospital: {str(e)}", "danger")
        else:
            logger.error(f"Form validation errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field.capitalize()}: {error}", "danger")
    return render_template('hospital_register.html', form=form, csrf_token=generate_csrf())

@app.route('/manage_departments', methods=['GET', 'POST'])
@login_required(['hospital_admin'])
def manage_departments():
    try:
        user = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)
        if not user or user['hospital_id'] is None:
            flash("No hospital assigned to this admin. Contact super admin.", "danger")
            return redirect(url_for('logout'))
        
        hospital_id = user['hospital_id']
        hospital = query_db("SELECT name FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        if not hospital:
            flash("Hospital not found in database", "danger")
            return redirect(url_for('logout'))
        
        hospital_name = hospital['name']
        
        if request.method == 'POST':
            logger.info(f"Manage departments form data: {request.form}")
            if 'add_department' in request.form:
                dept_name = request.form.get('name', '').strip()
                if not dept_name:
                    flash("Department name is required", "danger")
                    return redirect(url_for('manage_departments'))
                query_db("INSERT INTO departments (hospital_id, name) VALUES (?, ?)", 
                         (hospital_id, dept_name), commit=True)
                flash("Department added successfully", "success")
                return redirect(url_for('manage_departments'))
        
        departments = query_db("""
            SELECT d.id, d.name, 
                   (SELECT COUNT(*) FROM doctors WHERE department_id = d.id) AS doctor_count
            FROM departments d 
            WHERE d.hospital_id = ?
            ORDER BY d.name
        """, (hospital_id,))
        
        return render_template('manage_departments.html', 
                             departments=departments,
                             hospital_name=hospital_name,
                             csrf_token=generate_csrf())
    
    except Exception as e:
        logger.error(f"Error in manage_departments: {e}")
        flash("An error occurred while managing departments", "danger")
        return redirect(url_for('hospital_admin_dashboard'))

@app.route('/add_doctor', methods=['POST'])
@login_required(['hospital_admin'])
def add_doctor():
    try:
        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            return jsonify({'success': False, 'message': 'No hospital assigned to this admin'}), 403
        data = request.get_json()
        logger.info(f"Add doctor data: {data}")
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
            
        department_id = data.get('department_id')
        name = data.get('name', '').strip()
        gender = data.get('gender')
        start_day = data.get('start_day', '').lower().strip()
        end_day = data.get('end_day', '').lower().strip()
        start_time = data.get('start_time', '').lower().strip()
        end_time = data.get('end_time', '').lower().strip()
        
        if not all([department_id, name, gender, start_day, end_day, start_time, end_time]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
            
        try:
            start_time = normalize_schedule_time(start_time)
            end_time = normalize_schedule_time(end_time)
        except ValueError as e:
            return jsonify({'success': False, 'message': f"Invalid time format: {str(e)}"}), 400
        
        schedule = f"{start_day}-{end_day} {start_time}-{end_time}"
        
        doctor_id = query_db(
            "INSERT INTO doctors (hospital_id, department_id, name, gender, schedule) VALUES (?, ?, ?, ?, ?)",
            (hospital_id, department_id, name, gender, schedule),
            commit=True, return_id=True
        )
        
        return jsonify({
            'success': True,
            'message': 'Doctor added successfully',
            'doctor_id': doctor_id
        })
    except Exception as e:
        logger.error(f"Error adding doctor: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/update_doctor', methods=['POST'])
@login_required(['hospital_admin'])
def update_doctor():
    try:
        data = request.get_json()
        logger.info(f"Update doctor data: {data}")
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        doctor_id = data.get('doctor_id')
        name = data.get('name', '').strip()
        gender = data.get('gender')
        start_day = data.get('start_day', '').lower().strip()
        end_day = data.get('end_day', '').lower().strip()
        start_time = data.get('start_time', '').lower().strip()
        end_time = data.get('end_time', '').lower().strip()

        if not all([doctor_id, name, gender, start_day, end_day, start_time, end_time]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            return jsonify({'success': False, 'message': 'No hospital assigned to this admin'}), 403
        doctor = query_db("SELECT id FROM doctors WHERE id = ? AND hospital_id = ?", (doctor_id, hospital_id), one=True)
        
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found or not authorized'}), 404

        try:
            start_time = normalize_schedule_time(start_time)
            end_time = normalize_schedule_time(end_time)
        except ValueError as e:
            return jsonify({'success': False, 'message': f"Invalid time format: {str(e)}"}), 400

        schedule = f"{start_day}-{end_day} {start_time}-{end_time}"

        query_db(
            "UPDATE doctors SET name = ?, gender = ?, schedule = ? WHERE id = ?",
            (name, gender, schedule, doctor_id),
            commit=True
        )

        return jsonify({'success': True, 'message': 'Doctor updated successfully'})
    except Exception as e:
        logger.error(f"Error updating doctor: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/suspend_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def suspend_hospital(hospital_id):
    logger.info(f"Suspend hospital session: {session}")
    try:
        hospital = query_db("SELECT id FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        if not hospital:
            flash("Hospital not found", "danger")
            return redirect(url_for('super_admin'))
        query_db("UPDATE hospitals SET subscription_status = 'suspended' WHERE id = ?", (hospital_id,), commit=True)
        flash("Hospital suspended", "success")
    except Exception as e:
        logger.error(f"Error suspending hospital: {e}")
        flash("Error suspending hospital", "danger")
    return redirect(url_for('super_admin'))

@app.route('/activate_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def activate_hospital(hospital_id):
    logger.info(f"Activate hospital session: {session}")
    try:
        hospital = query_db("SELECT id FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        if not hospital:
            flash("Hospital not found", "danger")
            return redirect(url_for('super_admin'))
        expiry_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
        query_db("UPDATE hospitals SET subscription_status = 'active', subscription_expiry_date = ? WHERE id = ?", 
                 (expiry_date, hospital_id), commit=True)
        flash("Hospital activated", "success")
    except Exception as e:
        logger.error(f"Error activating hospital: {e}")
        flash("Error activating hospital", "danger")
    return redirect(url_for('super_admin'))

@app.route('/delete_doctor/<int:doctor_id>', methods=['POST'])
@login_required(['hospital_admin'])
def delete_doctor(doctor_id):
    try:
        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            return jsonify({'success': False, 'error': 'No hospital assigned to this admin'}), 403
        doctor = query_db("SELECT id FROM doctors WHERE id = ? AND hospital_id = ?", (doctor_id, hospital_id), one=True)
        logger.info(f"Delete doctor session: {session}")
        if not doctor:
            return jsonify({'success': False, 'error': 'Doctor not found or not authorized'}), 404
        
        query_db("DELETE FROM doctors WHERE id = ?", (doctor_id,), commit=True)
        
        return jsonify({'success': True, 'message': 'Doctor deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting doctor: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/close_appointment/<int:appt_id>', methods=['POST'])
@login_required(['hospital_admin'])
def close_appointment(appt_id):
    logger.info(f"Close appointment session: {session}")
    try:
        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            flash("No hospital assigned to this admin", "danger")
            return redirect(url_for('hospital_admin_dashboard'))
        appointment = query_db("SELECT id FROM appointments WHERE id = ? AND hospital_id = ?", (appt_id, hospital_id), one=True)
        
        if not appointment:
            flash("Appointment not found or not authorized", "danger")
            return redirect(url_for('hospital_admin_dashboard'))
        
        query_db("UPDATE appointments SET status = 'closed' WHERE id = ?", (appt_id,), commit=True)
        flash("Appointment closed successfully", "success")
    except Exception as e:
        logger.error(f"Error closing appointment: {e}")
        flash("Error closing appointment", "danger")
    return redirect(url_for('hospital_admin_dashboard'))

@app.route('/reschedule_appointment', methods=['POST'])
@login_required(['hospital_admin'])
def reschedule_appointment():
    try:
        data = request.get_json()
        logger.info(f"Reschedule appointment data: {data}")
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        appointment_id = data.get('appointment_id')
        new_date = data.get('date')
        new_time = data.get('time')

        if not all([appointment_id, new_date, new_time]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        try:
            datetime.strptime(new_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format'}), 400

        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            return jsonify({'success': False, 'message': 'No hospital assigned to this admin'}), 403
        appointment = query_db("SELECT id, doctor_id FROM appointments WHERE id = ? AND hospital_id = ?", (appointment_id, hospital_id), one=True)
        
        if not appointment:
            return jsonify({'success': False, 'message': 'Appointment not found or not authorized'}), 404

        if not is_doctor_available(appointment['doctor_id'], new_date, new_time):
            return jsonify({'success': False, 'message': 'Selected slot is not available'}), 400

        query_db(
            "UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled' WHERE id = ?",
            (new_date, new_time, appointment_id), commit=True
        )

        user = query_db("SELECT email, name FROM users WHERE id = (SELECT patient_id FROM appointments WHERE id = ?)", (appointment_id,), one=True)
        appointment_details = query_db("""
            SELECT h.name AS hospital, d.name AS department, doc.name AS doctor
            FROM appointments a
            JOIN hospitals h ON a.hospital_id = h.id
            JOIN departments d ON a.department_id = d.id
            JOIN doctors doc ON a.doctor_id = doc.id
            WHERE a.id = ?
        """, (appointment_id,), one=True)

        msg = Message(
            "Appointment Rescheduled",
            recipients=[user['email']],
            body=f"""
            Dear {user['name']},
            
            Your appointment has been rescheduled:
            Hospital: {appointment_details['hospital']}
            Department: {appointment_details['department']}
            Doctor: {appointment_details['doctor']}
            New Date: {new_date}
            New Time: {new_time}
            
            Thank you.
            """
        )
        mail.send(msg)
        
        return jsonify({'success': True, 'message': 'Appointment rescheduled successfully'})
    except Exception as e:
        logger.error(f"Error rescheduling appointment: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/reschedule_patient/<int:appt_id>', methods=['POST'])
@login_required(['patient'])
def reschedule_patient(appt_id):
    try:
        data = request.get_json()
        logger.info(f"Reschedule patient data: {data}")
        if not data or 'date' not in data or 'time' not in data:
            return jsonify({'success': False, 'message': 'Invalid input'}), 400
        
        new_date = data['date']
        new_time = data['time']
        
        try:
            requested_date = datetime.strptime(new_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format'}), 400
        
        if requested_date < date.today():
            return jsonify({'success': False, 'message': 'Cannot reschedule to a past date'}), 400
        
        appt = query_db("SELECT patient_id, doctor_id FROM appointments WHERE id = ?", (appt_id,), one=True)
        if not appt or appt['patient_id'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Appointment not found or not authorized'}), 404
        
        if not is_doctor_available(appt['doctor_id'], new_date, new_time):
            return jsonify({'success': False, 'message': 'Selected slot is not available'}), 400
        
        query_db(
            "UPDATE appointments SET date = ?, slot_time = ?, status = 'rescheduled', no_show_prob = NULL, reschedule_prob = NULL WHERE id = ?",
            (new_date, new_time, appt_id), commit=True
        )
        
        user = query_db("SELECT email, name FROM users WHERE id = ?", (session['user_id'],), one=True)
        appointment = query_db("""
            SELECT h.name AS hospital, d.name AS department, doc.name AS doctor
            FROM appointments a
            JOIN hospitals h ON a.hospital_id = h.id
            JOIN departments d ON a.department_id = d.id
            JOIN doctors doc ON a.doctor_id = doc.id
            WHERE a.id = ?
        """, (appt_id,), one=True)

        msg = Message(
            "Appointment Rescheduled",
            recipients=[user['email']],
            body=f"""
            Dear {user['name']},
            
            You have rescheduled your appointment:
            Hospital: {appointment['hospital']}
            Department: {appointment['department']}
            Doctor: {appointment['doctor']}
            New Date: {new_date}
            New Time: {new_time}
            
            Thank you.
            """
        )
        mail.send(msg)
        
        return jsonify({'success': True, 'message': 'Appointment rescheduled successfully'})
    except Exception as e:
        logger.error(f"Error rescheduling appointment: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete_hospital/<int:hospital_id>', methods=['POST'])
@login_required(['super_admin'])
def delete_hospital(hospital_id):
    logger.info(f"Delete hospital session: {session}")
    try:
        hospital = query_db("SELECT id, name FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        if not hospital:
            flash("Hospital not found", "danger")
            return redirect(url_for('super_admin'))

        query_db("DELETE FROM appointments WHERE hospital_id = ?", (hospital_id,), commit=True)
        query_db("DELETE FROM doctors WHERE department_id IN (SELECT id FROM departments WHERE hospital_id = ?)", (hospital_id,), commit=True)
        query_db("DELETE FROM departments WHERE hospital_id = ?", (hospital_id,), commit=True)
        query_db("DELETE FROM users WHERE role = 'hospital_admin' AND hospital_id = ?", (hospital_id,), commit=True)
        query_db("DELETE FROM hospitals WHERE id = ?", (hospital_id,), commit=True)

        flash(f"Hospital {hospital['name']} deleted successfully", "success")
        return redirect(url_for('super_admin'))
    except Exception as e:
        logger.error(f"Error deleting hospital: {e}")
        flash(f"Error deleting hospital: {str(e)}", "danger")
        return redirect(url_for('super_admin'))

@app.route('/mark_attended/<int:appt_id>', methods=['POST'])
@login_required(['hospital_admin'])
def mark_attended(appt_id):
    logger.info(f"Mark attended session: {session}")
    try:
        hospital_id = query_db("SELECT hospital_id FROM users WHERE id = ?", (session['user_id'],), one=True)['hospital_id']
        if hospital_id is None:
            flash("No hospital assigned to this admin", "danger")
            return redirect(url_for('hospital_admin_dashboard'))
        appointment = query_db("SELECT id FROM appointments WHERE id = ? AND hospital_id = ?", (appt_id, hospital_id), one=True)
        
        if not appointment:
            flash("Appointment not found or not authorized", "danger")
            return redirect(url_for('hospital_admin_dashboard'))
        
        query_db("UPDATE appointments SET status = 'attended' WHERE id = ?", (appt_id,), commit=True)
        flash("Appointment marked as attended", "success")
    except Exception as e:
        logger.error(f"Error marking appointment as attended: {e}")
        flash("Error marking appointment as attended", "danger")
    return redirect(url_for('hospital_admin_dashboard'))

@app.route('/cancel_appointment/<int:appointment_id>', methods=['POST'])
@login_required(['patient'])
def cancel_appointment(appointment_id):
    try:
        data = request.get_json()
        logger.info(f"Cancel appointment data: {data}")
        appointment = query_db("SELECT patient_id, status FROM appointments WHERE id = ?", (appointment_id,), one=True)
        if not appointment or appointment['patient_id'] != session['user_id']:
            flash("Appointment not found or unauthorized.", "danger")
            return redirect(url_for('patient_dashboard'))
        
        if appointment['status'] in ['cancelled', 'closed']:
            flash("Appointment is already cancelled or closed.", "warning")
            return redirect(url_for('patient_dashboard'))

        query_db("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appointment_id,), commit=True)
        
        user = query_db("SELECT email, name FROM users WHERE id = ?", (session['user_id'],), one=True)
        appointment = query_db("""
            SELECT a.date, a.slot_time, h.name AS hospital, d.name AS department, doc.name AS doctor
            FROM appointments a
            JOIN hospitals h ON a.hospital_id = h.id
            JOIN departments d ON a.department_id = d.id
            JOIN doctors doc ON a.doctor_id = doc.id
            WHERE a.id = ?
        """, (appointment_id,), one=True)

        msg = Message(
            "Appointment Cancellation",
            recipients=[user['email']],
            body=f"""
            Dear {user['name']},
            
            Your appointment has been cancelled:
            Hospital: {appointment['hospital']}
            Department: {appointment['department']}
            Doctor: {appointment['doctor']}
            Date: {appointment['date']}
            Time: {appointment['slot_time']}
            
            Thank you.
            """
        )
        mail.send(msg)
        flash("Appointment cancelled successfully.", "success")
    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}")
        flash("Failed to cancel appointment.", "danger")
    return redirect(url_for('patient_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
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
    app.run(debug=True, use_reloader=False)