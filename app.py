from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import psycopg2
from psycopg2 import pool
import os
from model.no_show_model import predict_no_show, predict_reschedule

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Database configuration
DB_TYPE = os.getenv("DB_TYPE", "sqlite")

# SQLite connection
def get_sqlite_conn():
    return sqlite3.connect("database.db")

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
        conn = get_sqlite_conn()
        c = conn.cursor()
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
            (5, "Port Harcourt Specialist Hospital", "Port Harcourt")
        ]
        departments = [
            (1, 1, "Cardiology"), (2, 1, "Pediatrics"), (3, 1, "Orthopedics"),
            (4, 2, "Neurology"), (5, 2, "General Medicine"),
            (6, 3, "Gynecology"), (7, 3, "Pediatrics"),
            (8, 4, "Cardiology"), (9, 4, "Surgery"),
            (10, 5, "Oncology"), (11, 5, "Neurology")
        ]
        doctors = [
            (1, 1, 1, "Dr. John Doe"), (2, 1, 2, "Dr. Jane Smith"),
            (3, 2, 4, "Dr. Ahmed Musa"), (4, 3, 6, "Dr. Chioma Obi"),
            (5, 4, 8, "Dr. Tunde Ade"),
            (6, 5, 10, "Dr. Grace Eke")
        ]
        c.executemany("INSERT OR IGNORE INTO hospitals (id, name, location) VALUES (?, ?, ?)", hospitals)
        c.executemany("INSERT OR IGNORE INTO departments (id, hospital_id, name) VALUES (?, ?, ?)", departments)
        c.executemany("INSERT OR IGNORE INTO doctors (id, hospital_id, department_id, name) VALUES (?, ?, ?, ?)", doctors)
        conn.commit()
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
                    ("Port Harcourt Specialist Hospital", "Port Harcourt")
                ]
                departments = [
                    (1, "Cardiology"), (1, "Pediatrics"), (1, "Orthopedics"),
                    (2, "Neurology"), (2, "General Medicine"),
                    (3, "Gynecology"), (3, "Pediatrics"),
                    (4, "Cardiology"), (4, "Surgery"),
                    (5, "Oncology"), (5, "Neurology")
                ]
                doctors = [
                    (1, 1, "Dr. John Doe"), (1, 2, "Dr. Jane Smith"),
                    (2, 4, "Dr. Ahmed Musa"), (3, 6, "Dr. Chioma Obi"),
                    (4, 8, "Dr. Tunde Ade"),
                    (5, 10, "Dr. Grace Eke")
                ]
                for h in hospitals:
                    c.execute("INSERT INTO hospitals (name, location) VALUES (%s, %s) ON CONFLICT DO NOTHING", h)
                for d in departments:
                    c.execute("INSERT INTO departments (hospital_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", d)
                for d in doctors:
                    c.execute("INSERT INTO doctors (hospital_id, department_id, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", d)
                conn.commit()
        finally:
            db_pool.putconn(conn)

# Database query helper
def query_db(query, args=(), one=False, commit=False):
    if DB_TYPE == "sqlite":
        conn = get_sqlite_conn()
        c = conn.cursor()
        c.execute(query, args)
        if commit:
            conn.commit()
        rv = c.fetchall()
        conn.close()
        return (rv[0] if rv else None) if one else rv
    elif DB_TYPE == "postgresql" and db_pool:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute(query, args)
                if commit:
                    conn.commit()
                rv = c.fetchall() if not commit else None
                return (rv[0] if rv else None) if one else rv
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
        
        # Predict no-show probability
        features = ['31-50', 'weekday', '30-90', '<5km', 'morning']  # Simulated patient data
        no_show_prob = predict_no_show(features)
        
        query = """INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, status) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""" if DB_TYPE == "postgresql" else """INSERT INTO appointments (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, status) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        query_db(query, (patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, 'scheduled'), commit=True)
        flash("Appointment booked successfully!")
        return redirect(url_for('patient_dashboard'))
    
    return render_template('booking.html', hospitals=hospitals, user=session.get('user_id'), role=session.get('role'))

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
               WHERE a.patient_id = %s""" if DB_TYPE == "postgresql" else """SELECT a.id, h.name, d.name, doc.name, a.slot_time, a.date, a.no_show_prob, a.status 
               FROM appointments a 
               JOIN hospitals h ON a.hospital_id = h.id 
               JOIN departments d ON a.department_id = d.id 
               JOIN doctors doc ON a.doctor_id = doc.id 
               WHERE a.patient_id = ?"""
    appointments = query_db(query, (user_id,))
    return render_template('patient.html', appointments=appointments, user=session.get('user_id'), role=session.get('role'))

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
    return render_template('admin.html', appointments=appointments, user=session.get('user_id'), role=session.get('role'))

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

if __name__ == '__main__':
    init_db()
    app.run(debug=True)