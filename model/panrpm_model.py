import pandas as pd
import numpy as np
import joblib
from sklearn.preprocessing import LabelEncoder
import sqlite3

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
        print(f"Error predicting no-show: {e}")
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
        print(f"Error predicting reschedule: {e}")
        return 10.0