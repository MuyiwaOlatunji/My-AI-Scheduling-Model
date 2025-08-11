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
           a.no_show_prob, a.reschedule_prob, u.age, u.location as patient_location, u.gender as patient_gender, 
           u.marriage_status, u.occupation, h.location as hospital_location, doc.gender as doctor_gender, a.health_challenge
    FROM appointments a
    JOIN users u ON a.patient_id = u.id
    JOIN hospitals h ON a.hospital_id = h.id
    JOIN doctors doc ON a.doctor_id = doc.id
    """
    data = pd.read_sql_query(query, conn)
    conn.close()
    return data

def prepare_data():
    data = load_data_from_db()
    if data.empty:
        return pd.DataFrame(), pd.Series(dtype='int'), pd.Series(dtype='int')
    
    current_date = pd.to_datetime(datetime.now().date())
    data['appointment_date'] = pd.to_datetime(data['date'])
    data['lead_time'] = (data['appointment_date'] - current_date).dt.days
    data['distance'] = (data['patient_location'] == data['hospital_location']).astype(int)
    data['time_of_day'] = data['slot_time'].apply(lambda x: 1 if 'AM' in x.upper() else 0)
    data['is_weekday'] = data['appointment_date'].dt.weekday.apply(lambda x: 0 if x < 5 else 1)
    data['age'] = data['age'].fillna(data['age'].mean())
    data['doctor_gender'] = data['doctor_gender'].map({'M': 0, 'F': 1})
    data['patient_gender'] = data['patient_gender'].map({'M': 0, 'F': 1, 'Other': 2})
    data['marriage_status'] = data['marriage_status'].map({'Single': 0, 'Married': 1, 'Divorced': 2, 'Widowed': 3})
    data['has_occupation'] = data['occupation'].apply(lambda x: 1 if x.strip() else 0)
    data['health_challenge_length'] = data['health_challenge'].apply(lambda x: len(x) if x else 0)

    previous_no_shows = []
    for idx, row in data.iterrows():
        past_appointments = data[(data['patient_id'] == row['patient_id']) & (data['appointment_date'] < row['appointment_date'])]
        no_show_count = past_appointments[past_appointments['status'] == 'no_show'].shape[0]
        previous_no_shows.append(no_show_count)
    data['previous_no_shows'] = previous_no_shows

    data['no_show'] = data.apply(lambda row: 1 if row['status'] == 'no_show' else 0, axis=1)
    data['reschedule'] = data.apply(lambda row: 1 if row['status'] == 'rescheduled' else 0, axis=1)

    features = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender',
                'patient_gender', 'marriage_status', 'has_occupation', 'health_challenge_length']
    X = data[features].fillna(0)
    y_no_show = data['no_show']
    y_reschedule = data['reschedule']
    return X, y_no_show, y_reschedule

def train_models():
    X, y_no_show, y_reschedule = prepare_data()
    if len(X) == 0:
        print("No data available for training. Please ensure the appointments table is populated.")
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

    xgb_ns = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_ns = RandomizedSearchCV(xgb_ns, xgb_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    xgb_search_ns.fit(X_train_ns, y_train_ns)
    best_xgb_ns = xgb_search_ns.best_estimator_

    # Train reschedule models
    rf_rs = RandomForestClassifier(random_state=42, class_weight='balanced')
    rf_search_rs = RandomizedSearchCV(rf_rs, rf_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    rf_search_rs.fit(X_train_rs, y_train_rs)
    best_rf_rs = rf_search_rs.best_estimator_

    xgb_rs = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_rs = RandomizedSearchCV(xgb_rs, xgb_param_grid, n_iter=10, cv=5, scoring='roc_auc', random_state=42, n_jobs=-1)
    xgb_search_rs.fit(X_train_rs, y_train_rs)
    best_xgb_rs = xgb_search_rs.best_estimator_

    # Save models
    os.makedirs('model', exist_ok=True)
    joblib.dump(best_rf_ns, 'model/rf_no_show_model.pkl')
    joblib.dump(best_xgb_ns, 'model/xgb_no_show_model.pkl')
    joblib.dump(best_rf_rs, 'model/rf_reschedule_model.pkl')
    joblib.dump(best_xgb_rs, 'model/xgb_reschedule_model.pkl')
    print("Models trained and saved!")

def predict_no_show(features):
    rf_model = joblib.load('model/rf_no_show_model.pkl')
    xgb_model = joblib.load('model/xgb_no_show_model.pkl')
    feature_cols = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender',
                    'patient_gender', 'marriage_status', 'has_occupation', 'health_challenge_length']
    features_df = pd.DataFrame([features], columns=feature_cols)
    rf_prob = rf_model.predict_proba(features_df)[0][1]
    xgb_prob = xgb_model.predict_proba(features_df)[0][1]
    ensemble_prob = (rf_prob + xgb_prob) / 2
    return ensemble_prob * 100

def predict_reschedule(features):
    rf_model = joblib.load('model/rf_reschedule_model.pkl')
    xgb_model = joblib.load('model/xgb_reschedule_model.pkl')
    feature_cols = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday', 'age', 'doctor_gender',
                    'patient_gender', 'marriage_status', 'has_occupation', 'health_challenge_length']
    features_df = pd.DataFrame([features], columns=feature_cols)
    rf_prob = rf_model.predict_proba(features_df)[0][1]
    xgb_prob = xgb_model.predict_proba(features_df)[0][1]
    ensemble_prob = (rf_prob + xgb_prob) / 2
    return ensemble_prob * 100

if __name__ == '__main__':
    import os
    train_models()