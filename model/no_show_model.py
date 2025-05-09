import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report
from imblearn.over_sampling import SMOTE
import sqlite3
import joblib
from datetime import datetime

# Extract data from the database
def load_data_from_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Query appointments and related data
    query = """
    SELECT a.id, a.patient_id, a.hospital_id, a.department_id, a.doctor_id, a.slot_time, a.date, a.status,
           u.phone, h.location
    FROM appointments a
    JOIN users u ON a.patient_id = u.id
    JOIN hospitals h ON a.hospital_id = h.id
    """
    data = pd.read_sql_query(query, conn)
    conn.close()
    return data

# Calculate a patient's no-show history score (0-1, where 1 is high no-show risk)
def calculate_no_show_history(patient_id, appointment_date):
    conn = sqlite3.connect("database.db")
    query = """
    SELECT status, date FROM appointments 
    WHERE patient_id = ? AND date < ?
    """
    past_appointments = pd.read_sql_query(query, conn, params=(patient_id, appointment_date))
    conn.close()

    if past_appointments.empty:
        return 0.0  # No history, assume low risk

    total_appointments = len(past_appointments)
    no_shows = len(past_appointments[past_appointments['status'] == 'scheduled'])
    return no_shows / total_appointments if total_appointments > 0 else 0.0

# Calculate a patient's priority score (0-1, where 1 is highest priority)
def calculate_priority_score(no_show_history):
    # Lower no-show history = higher priority
    return 1.0 - no_show_history

# Prepare features and labels
def prepare_data():
    data = load_data_from_db()

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

    # 2. Lead time (simulated as 1-90 days)
    data['lead_time'] = [np.random.randint(1, 91) for _ in range(len(data))]

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

    # Select features
    features = ['previous_no_shows', 'lead_time', 'distance', 'time_of_day', 'is_weekday']
    X = data[features]
    y_no_show = data['no_show']
    y_reschedule = data['reschedule']

    # Encode categorical features
    X_encoded = pd.get_dummies(X, columns=['distance', 'time_of_day', 'is_weekday'], drop_first=True)
    return X_encoded, y_no_show, y_reschedule

# Train models
# Train models
def train_models():
    X, y_no_show, y_reschedule = prepare_data()

    # Handle class imbalance with SMOTE
    smote = SMOTE(random_state=42)
    X_ns, y_ns = smote.fit_resample(X, y_no_show)
    X_rs, y_rs = smote.fit_resample(X, y_reschedule)

    # Split data
    X_train_ns, X_test_ns, y_train_ns, y_test_ns = train_test_split(X_ns, y_ns, test_size=0.2, random_state=42)
    X_train_rs, X_test_rs, y_train_rs, y_test_rs = train_test_split(X_rs, y_rs, test_size=0.2, random_state=42)

    # No-show model (Random Forest + XGBoost ensemble)
    rf_ns = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    xgb_ns = XGBClassifier(n_estimators=100, random_state=42, scale_pos_weight=len(y_train_ns[y_train_ns == 0]) / len(y_train_ns[y_train_ns == 1]))
    rf_ns.fit(X_train_ns, y_train_ns)
    xgb_ns.fit(X_train_ns, y_train_ns)

    # Evaluate no-show model
    rf_probs_ns = rf_ns.predict_proba(X_test_ns)[:, 1]
    xgb_probs_ns = xgb_ns.predict_proba(X_test_ns)[:, 1]
    
    # Log sample probabilities
    print("Sample RF no-show probabilities:", rf_probs_ns[:5])
    print("Sample XGB no-show probabilities:", xgb_probs_ns[:5])
    
    ensemble_probs_ns = (rf_probs_ns + xgb_probs_ns) / 2
    auc_ns = roc_auc_score(y_test_ns, ensemble_probs_ns)
    print(f"No-Show Ensemble AUC: {auc_ns:.3f}")
    y_pred_ns = (ensemble_probs_ns > 0.5).astype(int)
    print("No-Show Classification Report:")
    print(classification_report(y_test_ns, y_pred_ns))

    # Reschedule model (Random Forest + XGBoost ensemble)
    rf_rs = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    xgb_rs = XGBClassifier(n_estimators=100, random_state=42, scale_pos_weight=len(y_train_rs[y_train_rs == 0]) / len(y_train_rs[y_train_rs == 1]))
    rf_rs.fit(X_train_rs, y_train_rs)
    xgb_rs.fit(X_train_rs, y_train_rs)

    # Evaluate reschedule model
    rf_probs_rs = rf_rs.predict_proba(X_test_rs)[:, 1]
    xgb_probs_rs = xgb_rs.predict_proba(X_test_rs)[:, 1]
    
    # Log sample probabilities
    print("Sample RF reschedule probabilities:", rf_probs_rs[:5])
    print("Sample XGB reschedule probabilities:", xgb_probs_rs[:5])
    
    ensemble_probs_rs = (rf_probs_rs + xgb_probs_rs) / 2
    auc_rs = roc_auc_score(y_test_rs, ensemble_probs_rs)
    print(f"Reschedule Ensemble AUC: {auc_rs:.3f}")
    y_pred_rs = (ensemble_probs_rs > 0.5).astype(int)
    print("Reschedule Classification Report:")
    print(classification_report(y_test_rs, y_pred_rs))

    # Save models
    joblib.dump(rf_ns, 'model/rf_no_show_model.pkl')
    joblib.dump(xgb_ns, 'model/xgb_no_show_model.pkl')
    joblib.dump(rf_rs, 'model/rf_reschedule_model.pkl')
    joblib.dump(xgb_rs, 'model/xgb_reschedule_model.pkl')
    print("Models trained and saved!")

# Predict no-show probability
# Predict no-show probability
def predict_no_show(features):
    rf_model = joblib.load('model/rf_no_show_model.pkl')
    xgb_model = joblib.load('model/xgb_no_show_model.pkl')
    
    # Convert features to DataFrame with correct column names
    feature_cols = ['previous_no_shows', 'lead_time', 'distance_>5km', 'time_of_day_morning', 'is_weekday_weekend']
    features_df = pd.DataFrame([features], columns=feature_cols)
    
    # Log the input features
    print(f"Input features for predict_no_show: {features}")
    
    # Predict
    rf_prob = rf_model.predict_proba(features_df)[0][1]
    xgb_prob = xgb_model.predict_proba(features_df)[0][1]
    
    # Log individual probabilities
    print(f"RF no-show probability: {rf_prob}")
    print(f"XGB no-show probability: {xgb_prob}")
    
    # Compute ensemble probability
    ensemble_prob = (rf_prob + xgb_prob) / 2
    
    # Log ensemble probability before scaling
    print(f"Ensemble no-show probability (before scaling): {ensemble_prob}")
    
    # Validate the ensemble probability
    if not (0 <= ensemble_prob <= 1):
        raise ValueError(f"Invalid ensemble probability: {ensemble_prob}. Must be between 0 and 1.")
    
    # Convert to percentage
    final_prob = ensemble_prob * 100
    
    # Log final probability
    print(f"Final no-show probability: {final_prob}%")
    
    return final_prob

# Predict rescheduling probability
def predict_reschedule(features):
    rf_model = joblib.load('model/rf_reschedule_model.pkl')
    xgb_model = joblib.load('model/xgb_reschedule_model.pkl')
    
    # Convert features to DataFrame with correct column names
    feature_cols = ['previous_no_shows', 'lead_time', 'distance_>5km', 'time_of_day_morning', 'is_weekday_weekend']
    features_df = pd.DataFrame([features], columns=feature_cols)
    
    # Log the input features
    print(f"Input features for predict_reschedule: {features}")
    
    # Predict
    rf_prob = rf_model.predict_proba(features_df)[0][1]
    xgb_prob = xgb_model.predict_proba(features_df)[0][1]
    
    # Log individual probabilities
    print(f"RF reschedule probability: {rf_prob}")
    print(f"XGB reschedule probability: {xgb_prob}")
    
    # Compute ensemble probability
    ensemble_prob = (rf_prob + xgb_prob) / 2
    
    # Log ensemble probability before scaling
    print(f"Ensemble reschedule probability (before scaling): {ensemble_prob}")
    
    # Validate the ensemble probability
    if not (0 <= ensemble_prob <= 1):
        raise ValueError(f"Invalid ensemble probability: {ensemble_prob}. Must be between 0 and 1.")
    
    # Convert to percentage
    final_prob = ensemble_prob * 100
    
    # Log final probability
    print(f"Final reschedule probability: {final_prob}%")
    
    return final_prob

if __name__ == '__main__':
    train_models()