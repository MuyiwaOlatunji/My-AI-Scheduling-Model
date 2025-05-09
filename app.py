from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import psycopg2
from psycopg2 import pool
import pandas as pd
import numpy as np
import os
from model.no_show_model import predict_no_show, predict_reschedule, calculate_no_show_history, calculate_priority_score
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Database configuration
DB_TYPE = os.getenv("DB_TYPE", "sqlite")

# SQLite connection
def get_sqlite_conn():
    try:
        conn = sqlite3.connect("database.db")
        return conn
    except sqlite3.Error as e:
        print(f"Failed to connect to SQLite database: {e}")
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
        print(f"Failed to initialize PostgreSQL pool: {e}")
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
                print("Database integrity check failed. Recreating database...")
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
                          doctor_id INTEGER, slot_time TEXT, date TEXT, no_show_prob REAL, status TEXT,
                          FOREIGN KEY (patient_id) REFERENCES users(id),
                          FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
                          FOREIGN KEY (department_id) REFERENCES departments(id),
                          FOREIGN KEY (doctor_id) REFERENCES doctors(id))''')

            # Seed hospitals, departments, and doctors
            hospitals = [
                (1, "Lagos General Hospital", "Lagos"),
                (2, "Abuja Medical Center", "Abuja"),
                (3, "Kano Health Clinic", "Kano"),
                (4, "Ibadan Community Hospital", "Ibadan"),
                (5, "Port Harcourt Specialist Hospital", "Port Harcourt"),
                (6, "Enugu Regional Hospital", "Enugu"),
                (7, "Benin City Medical Center", "Benin City"),
                (8, "Kaduna General Hospital", "Kaduna"),
                (9, "Jos University Teaching Hospital", "Jos"),
                (10, "Calabar Specialist Clinic", "Calabar")
            ]

            # Define department names to cycle through
            department_names = ["Cardiology", "Pediatrics", "Orthopedics", "Neurology", "General Medicine", 
                                "Gynecology", "Surgery", "Oncology", "Dermatology", "Radiology"]
            departments = []
            dept_id = 1
            for hospital_id in range(1, 11):  # For each hospital (1 to 10)
                num_depts = 4  # Each hospital gets 4 departments
                for i in range(num_depts):
                    dept_name = department_names[(hospital_id + i - 1) % len(department_names)]
                    departments.append((dept_id, hospital_id, dept_name))
                    dept_id += 1

            # Generate doctors (3 doctors per department)
            doctor_names = [
                "Dr. John Adebayo", "Dr. Aisha Bello", "Dr. Emeka Okon", "Dr. Fatima Musa", "Dr. Chioma Obi", 
                "Dr. Tunde Ade", "Dr. Grace Eke", "Dr. Musa Ibrahim", "Dr. Ngozi Eze", "Dr. Ahmed Yusuf",
                "Dr. Blessing Nwosu", "Dr. Kemi Adesina", "Dr. David Okafor", "Dr. Zainab Lawal", "Dr. Peter Uche",
                "Dr. Joy Amadi", "Dr. Sani Abubakar", "Dr. Esther Ojo", "Dr. Chukwuma Eze", "Dr. Halima Danjuma"
            ]
            doctors = []
            doc_id = 1
            for dept in departments:
                dept_id = dept[0]
                hospital_id = dept[1]
                for i in range(3):  # 3 doctors per department
                    doc_name = doctor_names[(doc_id - 1) % len(doctor_names)] + f" {doc_id}"  # Ensure unique names
                    doctors.append((doc_id, hospital_id, dept_id, doc_name))
                    doc_id += 1

            # Insert into database
            c.executemany("INSERT OR IGNORE INTO hospitals (id, name, location) VALUES (?, ?, ?)", hospitals)
            c.executemany("INSERT OR IGNORE INTO departments (id, hospital_id, name) VALUES (?, ?, ?)", departments)
            c.executemany("INSERT OR IGNORE INTO doctors (id, hospital_id, department_id, name) VALUES (?, ?, ?, ?)", doctors)
            conn.commit()
        except sqlite3.Error as e:
            print(f"Failed to initialize SQLite database: {e}")
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
                              doctor_id INTEGER, slot_time TEXT, date TEXT, no_show_prob REAL, status TEXT,
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
                dept_id = 1
                for hospital_id in range(1, 11):
                    num_depts = 4
                    for i in range(num_depts):
                        dept_name = department_names[(hospital_id + i - 1) % len(department_names)]
                        departments.append((hospital_id, dept_name))
                        dept_id += 1

                doctor_names = [
                    "Dr. John Adebayo", "Dr. Aisha Bello", "Dr. Emeka Okon", "Dr. Fatima Musa", "Dr. Chioma Obi", 
                    "Dr. Tunde Ade", "Dr. Grace Eke", "Dr. Musa Ibrahim", "Dr. Ngozi Eze", "Dr. Ahmed Yusuf",
                    "Dr. Blessing Nwosu", "Dr. Kemi Adesina", "Dr. David Okafor", "Dr. Zainab Lawal", "Dr. Peter Uche",
                    "Dr. Joy Amadi", "Dr. Sani Abubakar", "Dr. Esther Ojo", "Dr. Chukwuma Eze", "Dr. Halima Danjuma"
                ]
                doctors = []
                doc_id = 1
                for hospital_id in range(1, 11):
                    for dept_id in range((hospital_id - 1) * 4 + 1, hospital_id * 4 + 1):
                        for i in range(3):
                            doc_name = doctor_names[(doc_id - 1) % len(doctor_names)] + f" {doc_id}"
                            doctors.append((hospital_id, dept_id, doc_name))
                            doc_id += 1

                for h in hospitals:
                    c.execute("INSERT INTO hospitals (name, location) VALUES (%s, %s) ON CONFLICT DO NOTHING", h)
                for d in departments:
                    c.execute("INSERT INTO departments (hospital_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", d)
                for d in doctors:
                    c.execute("INSERT INTO doctors (hospital_id, department_id, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", d)
                conn.commit()
        except Exception as e:
            print(f"Failed to initialize PostgreSQL database: {e}")
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
            return (rv[0] if rv else None) if one else rv
        except sqlite3.Error as e:
            print(f"SQLite query error: {e}")
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
                return (rv[0] if rv else None) if one else rv
        except Exception as e:
            print(f"PostgreSQL query error: {e}")
            raise
        finally:
            db_pool.putconn(conn)
    else:
        raise Exception("Database not configured properly")

# Routes
@app.route('/')
def index():
    return render_template('index.html', user=session.get('user_id'), role=session.get('role'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        query = """INSERT INTO users (name, email, phone, password, role) VALUES (%s, %s, %s, %s, %s)""" if DB_TYPE == "postgresql" else """INSERT INTO users (name, email, phone, password, role) VALUES (?, ?, ?, ?, ?)"""
        try:
            query_db(query, (name, email, phone, password, 'patient'), commit=True)
            flash("Registration successful! Please login.")
            return redirect(url_for('login'))
        except Exception as e:
            flash("Email already exists or invalid input.")
    return render_template('register.html', user=session.get('user_id'), role=session.get('role'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        query = "SELECT * FROM users WHERE email = %s AND password = %s" if DB_TYPE == "postgresql" else "SELECT * FROM users WHERE email = ? AND password = ?"
        user = query_db(query, (email, password), one=True)
        if user:
            session['user_id'] = user[0]  # Store user ID in session
            session['role'] = user[5]     # Store role in session
            if user[5] == 'patient':
                return redirect(url_for('patient_dashboard'))
            elif user[5] == 'admin':
                return redirect(url_for('admin_dashboard'))
        flash("Invalid credentials")
    return render_template('login.html', user=session.get('user_id'), role=session.get('role'))

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('index'))

@app.route('/get_departments/<int:hospital_id>', methods=['GET'])
def get_departments(hospital_id):
    query = "SELECT id, name FROM departments WHERE hospital_id = %s" if DB_TYPE == "postgresql" else "SELECT id, name FROM departments WHERE hospital_id = ?"
    departments = query_db(query, (hospital_id,))
    return jsonify(departments)

@app.route('/get_doctors/<int:department_id>', methods=['GET'])
def get_doctors(department_id):
    query = "SELECT id, name FROM doctors WHERE department_id = %s" if DB_TYPE == "postgresql" else "SELECT id, name FROM doctors WHERE department_id = ?"
    doctors = query_db(query, (department_id,))
    return jsonify(doctors)

from dateutil.relativedelta import relativedelta  # Add this import at the top

@app.route('/book', methods=['GET', 'POST'])
def book_appointment():
    if 'user_id' not in session or session.get('role') != 'patient':
        flash("Please log in as a patient to book an appointment.")
        return redirect(url_for('login'))

    hospitals = query_db("SELECT * FROM hospitals")
    if request.method == 'POST':
        patient_id = session['user_id']
        hospital_id = request.form['hospital']
        department_id = request.form['department']
        doctor_id = request.form['doctor']
        date = request.form['date']
        slot_time = request.form['time']
        
        # Validate the date
        try:
            appointment_date = pd.to_datetime(date)
            current_date = pd.to_datetime('2025-05-09')
            max_date = current_date + relativedelta(years=1)
            
            if appointment_date < current_date:
                flash("Cannot book an appointment in the past.")
                return redirect(url_for('book_appointment'))
            if appointment_date > max_date:
                flash("Cannot book an appointment more than one year in the future.")
                return redirect(url_for('book_appointment'))
        except ValueError as e:
            flash("Invalid date format. Please select a valid date.")
            return redirect(url_for('book_appointment'))
        
        # Calculate previous no-shows
        past_appointments = query_db(
            "SELECT status FROM appointments WHERE patient_id = ? AND date < ?",
            (patient_id, date)
        )
        previous_no_shows = sum(1 for appt in past_appointments if appt[0] == 'scheduled')
        
        # Get hospital location
        hospital_location = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
        if not hospital_location:
            flash("Invalid hospital selected.")
            return redirect(url_for('book_appointment'))
        hospital_location = hospital_location[0]
        
        # Prepare features
        lead_time = (appointment_date - current_date).days
        distance_5km = 0 if 'Lagos' in hospital_location else 1
        time_of_day_morning = 1 if 'AM' in slot_time.upper() else 0
        is_weekday = appointment_date.day_name() in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        is_weekday_weekend = 0 if is_weekday else 1  # 0 for weekday, 1 for weekend

        # Validate features
        features = [
            previous_no_shows,  # Should be an integer >= 0
            lead_time,          # Should be an integer >= 0
            distance_5km,       # Should be 0 or 1
            time_of_day_morning,  # Should be 0 or 1
            is_weekday_weekend   # Should be 0 or 1
        ]

        if not (isinstance(previous_no_shows, int) and previous_no_shows >= 0):
            flash("Error calculating patient history. Please try again.")
            return redirect(url_for('book_appointment'))
        if not (isinstance(lead_time, int) and lead_time >= 0):
            flash("Error calculating lead time. Please try again.")
            return redirect(url_for('book_appointment'))
        if distance_5km not in [0, 1]:
            flash("Error determining hospital distance. Please try again.")
            return redirect(url_for('book_appointment'))
        if time_of_day_morning not in [0, 1]:
            flash("Error determining time of day. Please try again.")
            return redirect(url_for('book_appointment'))
        if is_weekday_weekend not in [0, 1]:
            flash("Error determining day type. Please try again.")
            return redirect(url_for('book_appointment'))
        
        try:
            # Predict no-show and reschedule probabilities
            no_show_prob = predict_no_show(features)
            reschedule_prob = predict_reschedule(features)
            
            # Validate prediction outputs before storing
            if not (0 <= no_show_prob <= 100):
                flash(f"Invalid no-show probability: {no_show_prob}. Must be between 0 and 100.")
                return redirect(url_for('book_appointment'))
            if not (0 <= reschedule_prob <= 100):
                flash(f"Invalid reschedule probability: {reschedule_prob}. Must be between 0 and 100.")
                return redirect(url_for('book_appointment'))
            
            # Insert into database
            query = """INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, status) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
            query_db(query, (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, 'scheduled'), commit=True)
            
            # Verify the stored value
            stored_prob = query_db(
                "SELECT no_show_prob FROM appointments WHERE patient_id = ? AND date = ? AND slot_time = ?",
                (patient_id, date, slot_time), one=True
            )[0]
            if abs(stored_prob - no_show_prob) > 0.01:  # Allow for small floating-point differences
                flash("Error storing no-show probability in the database.")
                return redirect(url_for('book_appointment'))
            
            flash(f"Appointment booked successfully! No-show risk: {no_show_prob:.2f}%, Reschedule risk: {reschedule_prob:.2f}%")
            return redirect(url_for('patient_dashboard'))
        except ValueError as e:
            flash(f"Prediction error: {str(e)}")
            return redirect(url_for('book_appointment'))
    
    return render_template('booking.html', hospitals=hospitals, user=session.get('user_id'), role=session.get('role'))


@app.route('/check_slot', methods=['GET'])
def check_slot():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    slot_time = request.args.get('time')
    patient_id = session.get('user_id')

    if not all([doctor_id, date, slot_time, patient_id]):
        return jsonify({'available': False, 'error': 'Missing required parameters'})

    try:
        # Get existing appointments for this slot
        query = """SELECT patient_id, no_show_prob FROM appointments 
                   WHERE doctor_id = ? AND date = ? AND slot_time = ? AND status != 'closed'"""
        existing_appts = query_db(query, (doctor_id, date, slot_time))

        # AI-Driven Scheduling Logic
        max_appointments_per_slot = 2  # Allow up to 2 appointments per slot
        combined_no_show_threshold = 50.0  # Allow overbooking if combined no-show prob < 50%
        priority_threshold = 0.7  # Minimum priority score to overbook

        if not existing_appts:
            # Slot is empty, always available
            return jsonify({'available': True})

        if len(existing_appts) >= max_appointments_per_slot:
            # Slot is full, not available
            return jsonify({'available': False})

        # Calculate patient's priority and no-show history
        no_show_history = calculate_no_show_history(patient_id, date)
        priority_score = calculate_priority_score(no_show_history)

        if priority_score < priority_threshold:
            # Patient's priority is too low for overbooking
            return jsonify({'available': False})

        # Calculate combined no-show probability
        combined_no_show_prob = sum(appt[1] for appt in existing_appts)  # Sum of existing no-show probs
        if combined_no_show_prob >= combined_no_show_threshold:
            # Combined no-show probability too high, don't allow overbooking
            return jsonify({'available': False})

        # Slot can be overbooked
        return jsonify({'available': True})
    except Exception as e:
        print(f"Error checking slot availability: {e}")
        return jsonify({'available': False, 'error': 'Database error'})

@app.route('/get_available_slots', methods=['GET'])
def get_available_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    patient_id = session.get('user_id')

    if not all([doctor_id, date, patient_id]):
        return jsonify({'error': 'Missing required parameters'})

    try:
        # Define all possible time slots (8 AM to 5 PM)
        all_slots = [f"{hour}:00 {'AM' if hour < 12 else 'PM'}" for hour in range(8, 18)]

        # Get existing appointments for the doctor on this date
        query = """SELECT slot_time, patient_id, no_show_prob 
                   FROM appointments 
                   WHERE doctor_id = ? AND date = ? AND status != 'closed'"""
        existing_appts = query_db(query, (doctor_id, date))

        # Group appointments by slot
        slot_appointments = {}
        for slot in all_slots:
            slot_appointments[slot] = [appt for appt in existing_appts if appt[0] == slot]

        # AI-Driven Scheduling Logic
        max_appointments_per_slot = 2
        combined_no_show_threshold = 50.0
        priority_threshold = 0.7

        # Calculate patient's priority
        no_show_history = calculate_no_show_history(patient_id, date)
        priority_score = calculate_priority_score(no_show_history)

        available_slots = []
        for slot in all_slots:
            appts_in_slot = slot_appointments[slot]
            if not appts_in_slot:
                available_slots.append(slot)
            elif len(appts_in_slot) < max_appointments_per_slot:
                if priority_score >= priority_threshold:
                    combined_no_show_prob = sum(appt[2] for appt in appts_in_slot)
                    if combined_no_show_prob < combined_no_show_threshold:
                        available_slots.append(slot)

        return jsonify(available_slots)
    except Exception as e:
        print(f"Error fetching available slots: {e}")
        return jsonify({'error': 'Database error'})

@app.route('/patient')
def patient_dashboard():
    if 'user_id' not in session or session.get('role') != 'patient':
        flash("Please log in as a patient to view your dashboard.")
        return redirect(url_for('login'))

    user_id = session['user_id']
    query = """SELECT a.id, h.name, d.name, doc.name, a.slot_time, a.date, a.no_show_prob, a.status 
               FROM appointments a 
               JOIN hospitals h ON a.hospital_id = h.id 
               JOIN departments d ON a.department_id = d.id 
               JOIN doctors doc ON a.doctor_id = doc.id 
               WHERE a.patient_id = ?"""
    appointments = query_db(query, (user_id,))
    
    # Format no_show_prob to 2 decimal places
    formatted_appointments = []
    for appt in appointments:
        # Convert the tuple to a list to modify it
        appt_list = list(appt)
        # Format no_show_prob (index 6) to 2 decimal places
        appt_list[6] = "{:.2f}".format(float(appt_list[6]))
        formatted_appointments.append(appt_list)
    
    return render_template('patient.html', appointments=formatted_appointments, user=session.get('user_id'), role=session.get('role'))
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Please log in as an admin to view this page.")
        return redirect(url_for('login'))

    query = """SELECT a.id, u.email, h.name, d.name, doc.name, a.slot_time, a.date, a.no_show_prob, a.status 
               FROM appointments a 
               JOIN users u ON a.patient_id = u.id 
               JOIN hospitals h ON a.hospital_id = h.id 
               JOIN departments d ON a.department_id = d.id 
               JOIN doctors doc ON a.doctor_id = doc.id"""
    appointments = query_db(query)
    
    # Format no_show_prob to 2 decimal places
    formatted_appointments = []
    for appt in appointments:
        appt_list = list(appt)
        # Format no_show_prob (index 7) to 2 decimal places
        appt_list[7] = "{:.2f}".format(float(appt_list[7]))
        formatted_appointments.append(appt_list)
    
    return render_template('admin.html', appointments=formatted_appointments, user=session.get('user_id'), role=session.get('role'))

@app.route('/mark_attended/<int:appt_id>', methods=['POST'])
def mark_attended(appt_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Please log in as an admin to perform this action.")
        return redirect(url_for('login'))

    query = "UPDATE appointments SET status = %s WHERE id = %s" if DB_TYPE == "postgresql" else "UPDATE appointments SET status = ? WHERE id = ?"
    query_db(query, ('attended', appt_id), commit=True)
    flash("Appointment marked as attended.")
    return redirect(url_for('admin_dashboard'))

@app.route('/reschedule/<int:appt_id>', methods=['POST'])
def reschedule(appt_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Please log in as an admin to perform this action.")
        return redirect(url_for('login'))

    date = request.form['date']
    slot_time = request.form['time']
    query = "UPDATE appointments SET date = %s, slot_time = %s, status = %s WHERE id = %s" if DB_TYPE == "postgresql" else "UPDATE appointments SET date = ?, slot_time = ?, status = ? WHERE id = ?"
    query_db(query, (date, slot_time, 'scheduled', appt_id), commit=True)
    flash("Appointment rescheduled.")
    return redirect(url_for('admin_dashboard'))

@app.route('/close_appt/<int:appt_id>', methods=['POST'])
def close_appt(appt_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Please log in as an admin to perform this action.")
        return redirect(url_for('login'))

    query = "UPDATE appointments SET status = %s WHERE id = %s" if DB_TYPE == "postgresql" else "UPDATE appointments SET status = ? WHERE id = ?"
    query_db(query, ('closed', appt_id), commit=True)
    flash("Appointment closed.")
    return redirect(url_for('admin_dashboard'))

# Load data from the database
def load_data_from_db():
    query = """
        SELECT 
            a.id AS appointment_id,
            u.id AS patient_id,
            h.name AS hospital_name,
            h.location AS location,
            d.name AS department_name,
            doc.name AS doctor_name,
            a.slot_time AS slot_time,
            a.date AS date,
            a.no_show_prob AS no_show_prob,
            a.status AS status
        FROM appointments a
        JOIN users u ON a.patient_id = u.id
        JOIN hospitals h ON a.hospital_id = h.id
        JOIN departments d ON a.department_id = d.id
        JOIN doctors doc ON a.doctor_id = doc.id
    """
    data = pd.DataFrame(query_db(query))
    data.columns = ['appointment_id', 'patient_id', 'hospital_name', 'location', 'department_name', 'doctor_name', 'slot_time', 'date', 'no_show_prob', 'status']
    return data

# Prepare features and labels
def prepare_data():
    data = load_data_from_db()

    # Log raw data
    print("Raw data sample:\n", data.head())
    
    # Feature engineering
    # 1. Patient history (number of previous no-shows)
    current_date = pd.to_datetime('2025-05-08')
    data['appointment_date'] = pd.to_datetime(data['date'])
    previous_no_shows = []
    for idx, row in data.iterrows():
        past_appointments = data[(data['patient_id'] == row['patient_id']) & (data['appointment_date'] < row['appointment_date'])]
        no_show_count = past_appointments[past_appointments['status'] == 'scheduled'].shape[0]
        previous_no_shows.append(no_show_count)
    data['previous_no_shows'] = previous_no_shows
    
    # Log previous no-shows
    print("Previous no-shows sample:", data['previous_no_shows'].head())
    
    # 2. Lead time (difference between appointment date and current date)
    data['lead_time'] = (data['appointment_date'] - current_date).dt.days
    # Ensure lead_time is non-negative
    data['lead_time'] = data['lead_time'].clip(lower=0)
    
    # Log lead time
    print("Lead time sample:", data['lead_time'].head())
    
    # 3. Distance to hospital
    data['distance'] = data['location'].apply(lambda x: '<5km' if 'Lagos' in x else '>5km')
    
    # 4. Time of day
    data['time_of_day'] = data['slot_time'].apply(lambda x: 'morning' if 'AM' in x.upper() else 'afternoon')
    
    # 5. Day of the week
    data['day_of_week'] = data['appointment_date'].dt.day_name()
    data['is_weekday'] = data['day_of_week'].apply(lambda x: 'weekday' if x in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'] else 'weekend')
    
    # Define target variables
    # No-show: 1 if status is 'scheduled' and date is past, 0 otherwise
    data['no_show'] = data.apply(
        lambda row: 1 if row['status'] == 'scheduled' and row['appointment_date'] < current_date else 0,
        axis=1
    )
    # Reschedule: Simulate based on lead time and previous no-shows (placeholder logic)
    data['reschedule'] = data.apply(
        lambda row: 1 if row['lead_time'] > 60 or row['previous_no_shows'] > 2 else 0,
        axis=1
    )
    
    # Log target variables
    print("No-show labels sample:", data['no_show'].head())
    print("Reschedule labels sample:", data['reschedule'].head())
    
    # Select features
    features = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday']
    X = data[features]
    y_no_show = data['no_show']
    y_reschedule = data['reschedule']
    
    # Encode categorical features
    X_encoded = pd.get_dummies(X, columns=['distance', 'time_of_day', 'is_weekday'], drop_first=True)
    
    # Log encoded features
    print("Encoded features columns:", X_encoded.columns.tolist())
    print("Encoded features sample:\n", X_encoded.head())
    
    return X_encoded, y_no_show, y_reschedule

if __name__ == '__main__':
    init_db()
    app.run(debug=True)