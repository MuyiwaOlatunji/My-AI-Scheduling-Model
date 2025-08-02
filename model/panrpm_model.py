import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.metrics import roc_auc_score
from imblearn.over_sampling import SMOTE
import sqlite3
import joblib
from datetime import datetime

def load_data_from_db():
    conn = sqlite3.connect("database.db")
    query = """
    SELECT a.id, a.patient_id, a.hospital_id, a.department_id, a.doctor_id, a.slot_time, a.date, a.status,
           a.no_show_prob, a.reschedule_prob, u.age, h.location, doc.gender
    FROM appointments a
    JOIN users u ON a.patient_id = u.id
    JOIN hospitals h ON a.hospital_id = h.id
    JOIN doctors doc ON a.doctor_id = doc.id
    """
    data = pd.read_sql_query(query, conn)
    conn.close()
    return data

def calculate_no_show_history(patient_id, appointment_date):
    conn = sqlite3.connect("database.db")
    query = """
    SELECT status, date FROM appointments 
    WHERE patient_id = ? AND date < ?
    """
    past_appointments = pd.read_sql_query(query, conn, params=(patient_id, appointment_date))
    conn.close()
    if past_appointments.empty:
        return 0.0
    total_appointments = len(past_appointments)
    no_shows = len(past_appointments[past_appointments['status'] == 'no_show'])
    return no_shows / total_appointments if total_appointments > 0 else 0.0

def calculate_priority_score(no_show_history):
    return 1.0 - no_show_history

def prepare_data():
    data = load_data_from_db()
    current_date = pd.to_datetime(datetime.now().date())
    data['appointment_date'] = pd.to_datetime(data['date'])
    data['lead_time'] = (data['appointment_date'] - current_date).dt.days
    data['distance'] = data['location'].apply(lambda x: 0 if 'Lagos' in x else 1)
    data['time_of_day'] = data['slot_time'].apply(lambda x: 1 if 'AM' in x.upper() else 0)
    data['is_weekday'] = data['appointment_date'].dt.weekday.apply(lambda x: 0 if x < 5 else 1)
    data['age'] = data['age'].fillna(data['age'].mean())
    data['doctor_gender'] = data['gender'].map({'M': 0, 'F': 1})

    previous_no_shows = []
    for idx, row in data.iterrows():
        past_appointments = data[(data['patient_id'] == row['patient_id']) & (data['appointment_date'] < row['appointment_date'])]
        no_show_count = past_appointments[past_appointments['status'] == 'no_show'].shape[0]
        previous_no_shows.append(no_show_count)
    data['previous_no_shows'] = previous_no_shows

    data['no_show'] = data.apply(lambda row: 1 if row['status'] == 'no_show' else 0, axis=1)
    data['reschedule'] = data.apply(lambda row: 1 if row['status'] == 'rescheduled' else 0, axis=1)

    features = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender']
    X = data[features].fillna(0)
    y_no_show = data['no_show']
    y_reschedule = data['reschedule']
    return X, y_no_show, y_reschedule

def train_models():
    X, y_no_show, y_reschedule = prepare_data()
    if len(X) == 0:
        print("No data available for training. Please ensure the appointments table is populated.")
        return

    smote = SMOTE(random_state=42)
    X_ns, y_ns = smote.fit_resample(X, y_no_show)
    X_rs, y_rs = smote.fit_resample(X, y_reschedule)

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

    # No-show model
    rf_ns = RandomForestClassifier(random_state=42, class_weight='balanced')
    rf_search_ns = RandomizedSearchCV(rf_ns, rf_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    rf_search_ns.fit(X_train_ns, y_train_ns)
    best_rf_ns = rf_search_ns.best_estimator_

    xgb_ns = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_ns = RandomizedSearchCV(xgb_ns, xgb_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    xgb_search_ns.fit(X_train_ns, y_train_ns)  # Removed early_stopping_rounds
    best_xgb_ns = xgb_search_ns.best_estimator_

    # Reschedule model
    rf_rs = RandomForestClassifier(random_state=42, class_weight='balanced')
    rf_search_rs = RandomizedSearchCV(rf_rs, rf_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    rf_search_rs.fit(X_train_rs, y_train_rs)
    best_rf_rs = rf_search_rs.best_estimator_

    xgb_rs = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_rs = RandomizedSearchCV(xgb_rs, xgb_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    xgb_search_rs.fit(X_train_rs, y_train_rs)  # Removed early_stopping_rounds
    best_xgb_rs = xgb_search_rs.best_estimator_

    # Save models
    joblib.dump(best_rf_ns, 'model/rf_no_show_model.pkl')
    joblib.dump(best_xgb_ns, 'model/xgb_no_show_model.pkl')
    joblib.dump(best_rf_rs, 'model/rf_reschedule_model.pkl')
    joblib.dump(best_xgb_rs, 'model/xgb_reschedule_model.pkl')
    print("Models trained and saved!")

def predict_no_show(features):
    rf_model = joblib.load('model/rf_no_show_model.pkl')
    xgb_model = joblib.load('model/xgb_no_show_model.pkl')
    feature_cols = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender']
    features_df = pd.DataFrame([features], columns=feature_cols)
    rf_prob = rf_model.predict_proba(features_df)[0][1]
    xgb_prob = xgb_model.predict_proba(features_df)[0][1]
    ensemble_prob = (rf_prob + xgb_prob) / 2
    return ensemble_prob * 100

def predict_reschedule(features):
    rf_model = joblib.load('model/rf_reschedule_model.pkl')
    xgb_model = joblib.load('model/xgb_reschedule_model.pkl')
    feature_cols = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender']
    features_df = pd.DataFrame([features], columns=feature_cols)
    rf_prob = rf_model.predict_proba(features_df)[0][1]
    xgb_prob = xgb_model.predict_proba(features_df)[0][1]
    ensemble_prob = (rf_prob + xgb_prob) / 2
    return ensemble_prob * 100

if __name__ == '__main__':
    train_models()