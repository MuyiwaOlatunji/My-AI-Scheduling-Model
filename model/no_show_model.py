import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
import joblib

# Simulate dataset
def generate_data(n_samples=1000):
    np.random.seed(42)
    data = {
        'patient_age': np.random.choice(['18-30', '31-50', '51+'], n_samples),
        'appointment_day': np.random.choice(['weekday', 'weekend'], n_samples),
        'time_since_last_appointment': np.random.choice(['<30', '30-90', '>90'], n_samples),
        'distance_to_clinic': np.random.choice(['<5km', '5-15km', '>15km'], n_samples),
        'appointment_time': np.random.choice(['morning', 'afternoon', 'evening'], n_samples),
        'no_show': np.random.choice([0, 1], n_samples, p=[0.6, 0.4]),  # 40% no-show rate
        'reschedule': np.random.choice([0, 1], n_samples, p=[0.3, 0.7])  # 70% reschedule rate
    }
    df = pd.DataFrame(data)
    df.to_csv('model/data.csv', index=False)
    return df

# Train models
def train_models():
    df = generate_data()
    X = df.drop(['no_show', 'reschedule'], axis=1)
    y_no_show = df['no_show']
    y_reschedule = df['reschedule']
    
    # Encode categorical features
    le = LabelEncoder()
    for col in X.columns:
        X[col] = le.fit_transform(X[col])
    
    # No-show model
    X_train_ns, X_test_ns, y_train_ns, y_test_ns = train_test_split(X, y_no_show, test_size=0.2, random_state=42)
    no_show_model = LogisticRegression()
    no_show_model.fit(X_train_ns, y_train_ns)
    joblib.dump(no_show_model, 'model/no_show_model.pkl')
    
    # Reschedule model
    X_train_rs, X_test_rs, y_train_rs, y_test_rs = train_test_split(X, y_reschedule, test_size=0.2, random_state=42)
    reschedule_model = LogisticRegression()
    reschedule_model.fit(X_train_rs, y_train_rs)
    joblib.dump(reschedule_model, 'model/reschedule_model.pkl')
    print("Models trained and saved!")

# Predict no-show probability
def predict_no_show(features):
    model = joblib.load('model/no_show_model.pkl')
    le = LabelEncoder()
    features_encoded = [le.fit_transform([f])[0] for f in features]
    prob = model.predict_proba([features_encoded])[0][1]
    return prob

# Predict rescheduling probability
def predict_reschedule(features):
    model = joblib.load('model/reschedule_model.pkl')
    le = LabelEncoder()
    features_encoded = [le.fit_transform([f])[0] for f in features]
    prob = model.predict_proba([features_encoded])[0][1]
    return prob

if __name__ == '__main__':
    train_models()