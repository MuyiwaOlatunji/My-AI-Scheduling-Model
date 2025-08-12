import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import LabelEncoder  # Added import for LabelEncoder
from imblearn.over_sampling import SMOTE
import sqlite3
import joblib
from datetime import datetime, timedelta  # Added timedelta import
import random
from dateutil.relativedelta import relativedelta
import os  # Moved os import to the top for consistency

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
        location = random.choice(['Lagos', 'Abuja'])
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

def load_data_from_db():
    conn = sqlite3.connect("database.db")
    query = """
    SELECT a.id, a.patient_id, a.hospital_id, a.department_id, a.doctor_id, a.slot_time, a.date, a.status,
           a.no_show_prob, a.reschedule_prob, u.age, u.location as patient_location, u.gender as patient_gender, 
           u.marriage_status, u.occupation, h.location as hospital_location, doc.gender as doctor_gender, a.health_challenge
    FROM appointments a
    JOIN users u ON a.patient_id = u.id
    JOIN hospitals h ON a.hospital_id = h.id
    JOIN doctors doc ON a.doctor_id = doc.id
    WHERE a.status IN ('attended', 'no-show')
    """
    data = pd.read_sql_query(query, conn)
    conn.close()
    return data

def prepare_data():
    # Load real data
    data = load_data_from_db()
    
    # Generate simulated data to ensure sufficient training data
    simulated_df = simulate_appointments(1000)  # Generate 1000 simulated appointments
    
    # Combine real and simulated data
    if not data.empty:
        combined_df = pd.concat([data, simulated_df], ignore_index=True)
    else:
        combined_df = simulated_df
    
    # Initialize LabelEncoders
    le_doctor_gender = LabelEncoder()
    le_patient_gender = LabelEncoder()
    le_marriage_status = LabelEncoder()

    # Prepare features
    current_date = pd.to_datetime(datetime.now().date())
    combined_df['appointment_date'] = pd.to_datetime(combined_df['date'])
    combined_df['lead_time'] = (combined_df['appointment_date'] - pd.to_datetime(combined_df['booking_date'])).dt.days.fillna(0)
    combined_df['distance'] = combined_df.apply(
        lambda row: 0 if row['patient_location'] == row['hospital_location'] else 1 
        if 'patient_location' in row and 'hospital_location' in row else row.get('distance', 1), axis=1)
    combined_df['time_of_day'] = combined_df['slot_time'].apply(lambda x: 1 if 'AM' in str(x).upper() else 0)
    combined_df['is_weekday'] = combined_df['appointment_date'].dt.weekday.apply(lambda x: 0 if x < 5 else 1)
    combined_df['age'] = combined_df['age'].fillna(combined_df['age'].mean())
    combined_df['doctor_gender'] = le_doctor_gender.fit_transform(combined_df['doctor_gender'].fillna('Unknown'))
    combined_df['patient_gender'] = le_patient_gender.fit_transform(combined_df['patient_gender'].fillna('Unknown'))
    combined_df['marriage_status'] = le_marriage_status.fit_transform(combined_df['marriage_status'].fillna('Unknown'))
    combined_df['has_occupation'] = combined_df['occupation'].apply(lambda x: 1 if x and str(x).strip() else 0).fillna(0)
    combined_df['health_challenge_length'] = combined_df['health_challenge'].apply(lambda x: len(str(x)) if x else 0).fillna(0)
    
    # Calculate previous no-shows
    previous_no_shows = []
    for idx, row in combined_df.iterrows():
        past_appointments = combined_df[(combined_df['patient_id'] == row['patient_id']) & (combined_df['appointment_date'] < row['appointment_date'])]
        no_show_count = past_appointments[past_appointments['status'] == 'no_show'].shape[0]
        previous_no_shows.append(no_show_count)
    combined_df['previous_no_shows'] = previous_no_shows

    combined_df['no_show'] = combined_df['status'].apply(lambda x: 1 if x == 'no-show' else 0)
    combined_df['reschedule'] = combined_df['status'].apply(lambda x: 1 if x == 'rescheduled' else 0)

    features = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender',
                'patient_gender', 'marriage_status', 'has_occupation', 'health_challenge_length']
    X = combined_df[features].fillna(0)
    y_no_show = combined_df['no_show']
    y_reschedule = combined_df['reschedule']
    return X, y_no_show, y_reschedule

def train_models():
    X, y_no_show, y_reschedule = prepare_data()
    if len(X) == 0:
        print("No data available for training. Please ensure the appointments table is populated or simulated data is generated.")
        return

    # Determine SMOTE parameters based on minority class size
    min_samples_no_show = min(sum(y_no_show == 0), sum(y_no_show == 1))
    min_samples_reschedule = min(sum(y_reschedule == 0), sum(y_reschedule == 1))
    n_neighbors = min(5, max(1, min_samples_no_show - 1), max(1, min_samples_reschedule - 1))

    # Train no-show models
    if len(np.unique(y_no_show)) > 1 and min_samples_no_show > 1:
        smote = SMOTE(random_state=42, k_neighbors=n_neighbors)
        X_ns, y_ns = smote.fit_resample(X, y_no_show)
    else:
        print("Insufficient data or single class for y_no_show. Skipping SMOTE for no-show model.")
        X_ns, y_ns = X, y_no_show

    # Train reschedule models
    if len(np.unique(y_reschedule)) > 1 and min_samples_reschedule > 1:
        smote = SMOTE(random_state=42, k_neighbors=n_neighbors)
        X_rs, y_rs = smote.fit_resample(X, y_reschedule)
    else:
        print("Insufficient data or single class for y_reschedule. Skipping SMOTE for reschedule model.")
        X_rs, y_rs = X, y_reschedule

    X_train_ns, X_test_ns, y_train_ns, y_test_ns = train_test_split(X_ns, y_ns, test_size=0.2, random_state=42)
    X_train_rs, X_test_rs, y_train_rs, y_test_rs = train_test_split(X_rs, y_rs, test_size=0.2, random_state=42)

    rf_param_grid = {
        'n_estimators': [50, 100, 200],
        'max_depth': [10, 20, None],
        'min_samples_split': [2, 5],
        'min_samples_leaf': [1, 2]
    }
    xgb_param_grid = {
        'n_estimators': [50, 100, 200],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.1],
        'subsample': [0.8, 1.0]
    }

    # Train no-show models
    rf_ns = RandomForestClassifier(random_state=42, class_weight='balanced')
    rf_search_ns = RandomizedSearchCV(rf_ns, rf_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    rf_search_ns.fit(X_train_ns, y_train_ns)
    best_rf_ns = rf_search_ns.best_estimator_
    rf_ns_score = roc_auc_score(y_test_ns, best_rf_ns.predict_proba(X_test_ns)[:, 1])
    print(f"No-show RandomForest ROC AUC: {rf_ns_score:.4f}")

    xgb_ns = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_ns = RandomizedSearchCV(xgb_ns, xgb_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    xgb_search_ns.fit(X_train_ns, y_train_ns)
    best_xgb_ns = xgb_search_ns.best_estimator_
    xgb_ns_score = roc_auc_score(y_test_ns, best_xgb_ns.predict_proba(X_test_ns)[:, 1])
    print(f"No-show XGBoost ROC AUC: {xgb_ns_score:.4f}")

    # Train reschedule models
    rf_rs = RandomForestClassifier(random_state=42, class_weight='balanced')
    rf_search_rs = RandomizedSearchCV(rf_rs, rf_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    rf_search_rs.fit(X_train_rs, y_train_rs)
    best_rf_rs = rf_search_rs.best_estimator_
    rf_rs_score = roc_auc_score(y_test_rs, best_rf_rs.predict_proba(X_test_rs)[:, 1])
    print(f"Reschedule RandomForest ROC AUC: {rf_rs_score:.4f}")

    xgb_rs = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_rs = RandomizedSearchCV(xgb_rs, xgb_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    xgb_search_rs.fit(X_train_rs, y_train_rs)
    best_xgb_rs = xgb_search_rs.best_estimator_
    xgb_rs_score = roc_auc_score(y_test_rs, best_xgb_rs.predict_proba(X_test_rs)[:, 1])
    print(f"Reschedule XGBoost ROC AUC: {xgb_rs_score:.4f}")

    # Save models
    os.makedirs('model', exist_ok=True)
    joblib.dump(best_rf_ns, 'model/rf_no_show_model.pkl')
    joblib.dump(best_xgb_ns, 'model/xgb_no_show_model.pkl')
    joblib.dump(best_rf_rs, 'model/rf_reschedule_model.pkl')
    joblib.dump(best_xgb_rs, 'model/xgb_reschedule_model.pkl')
    print("Models trained and saved!")

def predict_no_show(features):
    try:
        rf_model = joblib.load('model/rf_no_show_model.pkl')
        xgb_model = joblib.load('model/xgb_no_show_model.pkl')
        feature_cols = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender',
                        'patient_gender', 'marriage_status', 'has_occupation', 'health_challenge_length']
        features_df = pd.DataFrame([features], columns=feature_cols)
        rf_prob = rf_model.predict_proba(features_df)[0][1]
        xgb_prob = xgb_model.predict_proba(features_df)[0][1]
        ensemble_prob = (rf_prob + xgb_prob) / 2 * 100
        return ensemble_prob
    except Exception as e:
        print(f"Error predicting no-show: {e}")
        return 10.0

def predict_reschedule(features):
    try:
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
        print(f"Error predicting reschedule: {e}")
        return 10.0

if __name__ == '__main__':
    train_models()