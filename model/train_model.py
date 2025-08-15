import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import LabelEncoder
from imblearn.over_sampling import SMOTE
import joblib
from datetime import datetime, timedelta
import random
import os

def simulate_training_data(num_samples=10000):
    """Generate comprehensive simulated data for training"""
    data = []
    current_date = datetime.now()
    
    for _ in range(num_samples):
        patient_id = random.randint(1, 100)
        hospital_id = random.choice([1, 2])
        department_id = random.choice([1, 2])
        doctor_id = random.choice([1, 2])
        appt_date = (current_date + timedelta(days=random.randint(1, 60))).strftime('%Y-%m-%d')
        slot_time = random.choice(['09:00 AM', '10:00 AM', '11:00 AM', '02:00 PM', '03:00 PM'])
        booking_date = current_date.strftime('%Y-%m-%d')
        
        # Generate status with realistic probabilities (higher chance of attended)
        status_weights = [0.6, 0.15, 0.15, 0.05, 0.05]  # attended, scheduled, no-show, cancelled, rescheduled
        status = random.choices(['attended', 'scheduled', 'no-show', 'cancelled', 'rescheduled'], 
                              weights=status_weights)[0]
        
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
        health_challenge = "Sample challenge" if random.random() > 0.7 else ""
        health_challenge_length = len(health_challenge) if health_challenge else 0
        
        # Generate previous no-shows with higher probability for patients who no-show
        if status == 'no-show':
            previous_no_shows = random.choices([0, 1, 2, 3, 4, 5], weights=[0.1, 0.2, 0.3, 0.2, 0.1, 0.1])[0]
        else:
            previous_no_shows = random.choices([0, 1, 2, 3, 4, 5], weights=[0.5, 0.3, 0.1, 0.05, 0.03, 0.02])[0]

        data.append({
            'patient_id': patient_id, 'hospital_id': hospital_id, 'department_id': department_id,
            'doctor_id': doctor_id, 'slot_time': slot_time, 'date': appt_date, 'booking_date': booking_date,
            'status': status, 'lead_time': lead_time, 'distance': distance, 'time_of_day': time_of_day,
            'is_weekday': is_weekday, 'age': age, 'doctor_gender': doctor_gender, 'patient_gender': patient_gender,
            'marriage_status': marriage_status, 'has_occupation': has_occupation, 
            'health_challenge': health_challenge, 'health_challenge_length': health_challenge_length,
            'previous_no_shows': previous_no_shows, 'location': location
        })
    
    df = pd.DataFrame(data)
    df['no_show'] = df['status'].apply(lambda x: 1 if x == 'no-show' else 0)
    df['reschedule'] = df['status'].apply(lambda x: 1 if x == 'rescheduled' else 0)
    return df

def prepare_training_data(df):
    """Prepare the training data with feature engineering"""
    # Initialize encoders
    le_doctor_gender = LabelEncoder()
    le_patient_gender = LabelEncoder()
    le_marriage_status = LabelEncoder()

    # Feature engineering
    df['appointment_date'] = pd.to_datetime(df['date'])
    df['booking_date'] = pd.to_datetime(df['booking_date'])
    df['lead_time'] = (df['appointment_date'] - df['booking_date']).dt.days.fillna(0)
    df['time_of_day'] = df['slot_time'].apply(lambda x: 1 if 'AM' in str(x).upper() else 0)
    df['is_weekday'] = df['appointment_date'].dt.weekday.apply(lambda x: 0 if x < 5 else 1)
    
    # Encode categorical features
    df['doctor_gender'] = le_doctor_gender.fit_transform(df['doctor_gender'].fillna('Unknown'))
    df['patient_gender'] = le_patient_gender.fit_transform(df['patient_gender'].fillna('Unknown'))
    df['marriage_status'] = le_marriage_status.fit_transform(df['marriage_status'].fillna('Unknown'))
    
    # Define features and targets
    features = [
        'previous_no_shows', 'lead_time', 'distance', 'time_of_day', 
        'is_weekday', 'age', 'doctor_gender', 'patient_gender', 
        'marriage_status', 'has_occupation', 'health_challenge_length'
    ]
    
    X = df[features].fillna(0)
    y_no_show = df['no_show']
    y_reschedule = df['reschedule']
    
    return X, y_no_show, y_reschedule

def train_and_save_models(X, y_no_show, y_reschedule):
    """Train models with hyperparameter tuning and save them"""
    # Define hyperparameter grids (from your original code)
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

    # Handle class imbalance with SMOTE
    smote = SMOTE(random_state=42, k_neighbors=5)
    
    # Train no-show models
    X_ns, y_ns = smote.fit_resample(X, y_no_show)
    X_train_ns, X_test_ns, y_train_ns, y_test_ns = train_test_split(X_ns, y_ns, test_size=0.2, random_state=42)
    
    # Random Forest for no-show
    rf_ns = RandomForestClassifier(random_state=42, class_weight='balanced')
    rf_search_ns = RandomizedSearchCV(
        rf_ns, rf_param_grid, n_iter=10, cv=5, 
        scoring='roc_auc', random_state=42, n_jobs=-1
    )
    rf_search_ns.fit(X_train_ns, y_train_ns)
    best_rf_ns = rf_search_ns.best_estimator_
    rf_ns_score = roc_auc_score(y_test_ns, best_rf_ns.predict_proba(X_test_ns)[:, 1])
    print(f"No-show RandomForest ROC AUC: {rf_ns_score:.4f}")
    
    # XGBoost for no-show
    xgb_ns = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_ns = RandomizedSearchCV(
        xgb_ns, xgb_param_grid, n_iter=10, cv=5, 
        scoring='roc_auc', random_state=42, n_jobs=-1
    )
    xgb_search_ns.fit(X_train_ns, y_train_ns)
    best_xgb_ns = xgb_search_ns.best_estimator_
    xgb_ns_score = roc_auc_score(y_test_ns, best_xgb_ns.predict_proba(X_test_ns)[:, 1])
    print(f"No-show XGBoost ROC AUC: {xgb_ns_score:.4f}")
    
    # Train reschedule models
    X_rs, y_rs = smote.fit_resample(X, y_reschedule)
    X_train_rs, X_test_rs, y_train_rs, y_test_rs = train_test_split(X_rs, y_rs, test_size=0.2, random_state=42)
    
    # Random Forest for reschedule
    rf_rs = RandomForestClassifier(random_state=42, class_weight='balanced')
    rf_search_rs = RandomizedSearchCV(
        rf_rs, rf_param_grid, n_iter=10, cv=5, 
        scoring='roc_auc', random_state=42, n_jobs=-1
    )
    rf_search_rs.fit(X_train_rs, y_train_rs)
    best_rf_rs = rf_search_rs.best_estimator_
    rf_rs_score = roc_auc_score(y_test_rs, best_rf_rs.predict_proba(X_test_rs)[:, 1])
    print(f"Reschedule RandomForest ROC AUC: {rf_rs_score:.4f}")
    
    # XGBoost for reschedule
    xgb_rs = XGBClassifier(random_state=42, eval_metric='auc')
    xgb_search_rs = RandomizedSearchCV(
        xgb_rs, xgb_param_grid, n_iter=10, cv=5, 
        scoring='roc_auc', random_state=42, n_jobs=-1
    )
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
    print("Models trained and saved successfully!")

if __name__ == '__main__':
    print("Generating simulated training data...")
    df = simulate_training_data(10000)  # Generate 10,000 samples
    
    print("Preparing data for training...")
    X, y_no_show, y_reschedule = prepare_training_data(df)
    
    print("Training models...")
    train_and_save_models(X, y_no_show, y_reschedule)