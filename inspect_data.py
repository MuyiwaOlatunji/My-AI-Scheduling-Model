import sqlite3
import pandas as pd

# Connect to the database
conn = sqlite3.connect("database.db")
c = conn.cursor()

# Query appointments data
query = """
SELECT patient_id, hospital_id, department_id, doctor_id, slot_time, date, no_show_prob, status
FROM appointments
"""
appointments = pd.read_sql_query(query, conn)
conn.close()

# Display basic information about the dataset
print("Dataset Info:")
print(appointments.info())
print("\nFirst 5 rows:")
print(appointments.head())

# Check class distribution (no-show vs. attended)
# Assuming 'status' = 'scheduled' (past date) means no-show, 'attended' means attended
appointments['no_show'] = appointments['status'].apply(
    lambda x: 1 if x == 'scheduled' else 0  # Adjust logic based on your app's definition
)
print("\nClass Distribution (0 = Attended, 1 = No-Show):")
print(appointments['no_show'].value_counts())

# Check for missing values
print("\nMissing Values:")
print(appointments.isnull().sum())

# Basic statistics
print("\nBasic Statistics:")
print(appointments.describe())

from app import query_db
print(query_db("PRAGMA table_info(appointments)"))