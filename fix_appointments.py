from app import query_db, app
from model.no_show_model import predict_no_show, predict_reschedule
from datetime import datetime
import pandas as pd

def recalculate_probabilities():
    with app.app_context():
        # Find appointments with NULL probabilities
        null_appts = query_db("SELECT id, patient_id, hospital_id, doctor_id, date, slot_time FROM appointments WHERE no_show_prob IS NULL OR reschedule_prob IS NULL")
        
        for appt in null_appts:
            appt_id = appt['id']
            patient_id = appt['patient_id']
            hospital_id = appt['hospital_id']
            date = appt['date']
            
            # Fetch hospital location
            hospital = query_db("SELECT location FROM hospitals WHERE id = ?", (hospital_id,), one=True)
            if not hospital:
                print(f"Skipping appointment {appt_id}: Invalid hospital_id")
                continue
            hospital_location = hospital['location']
            
            # Calculate features
            past_appointments = query_db("SELECT status FROM appointments WHERE patient_id = ? AND date < ?", (patient_id, date))
            previous_no_shows = sum(1 for appt in past_appointments if appt['status'] == 'no_show')
            
            appointment_date = pd.to_datetime(date)
            current_date = pd.to_datetime(datetime.now().date())
            lead_time = (appointment_date - current_date).days
            distance_5km = 0 if 'Lagos' in hospital_location else 1
            time_of_day_morning = 1 if 'AM' in appt['slot_time'].upper() else 0
            is_weekday = appointment_date.day_name() in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            is_weekday_weekend = 0 if is_weekday else 1
            
            features = [previous_no_shows, lead_time, distance_5km, time_of_day_morning, is_weekday_weekend]
            
            try:
                no_show_prob = predict_no_show(features)
                reschedule_prob = predict_reschedule(features)
                
                if not (0 <= no_show_prob <= 100 and 0 <= reschedule_prob <= 100):
                    print(f"Invalid probabilities for appointment {appt_id}: no_show_prob={no_show_prob}, reschedule_prob={reschedule_prob}")
                    continue
                
                # Update appointment
                query_db(
                    "UPDATE appointments SET no_show_prob = ?, reschedule_prob = ? WHERE id = ?",
                    (no_show_prob, reschedule_prob, appt_id),
                    commit=True
                )
                print(f"Updated appointment {appt_id} with no_show_prob={no_show_prob}, reschedule_prob={reschedule_prob}")
            except Exception as e:
                print(f"Error updating appointment {appt_id}: {e}")

if __name__ == "__main__":
    recalculate_probabilities()