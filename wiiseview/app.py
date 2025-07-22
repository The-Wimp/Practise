from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "your_secret_key"
DB_FILE = "health_data.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize SQLite DB with updated fields
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            PatientID TEXT PRIMARY KEY,
            Name TEXT,
            Age INTEGER,
            Gender TEXT,
            SystolicBP INTEGER,
            DiastolicBP INTEGER,
            BMI REAL,
            GlucoseLevel INTEGER,
            SpO2 INTEGER,
            PulseRate INTEGER,
            Outcome INTEGER,
            LastUpdated TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_history (
            PatientID TEXT,
            Timestamp TEXT,
            HealthIndex REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            PatientID TEXT,
            filename TEXT,
            description TEXT,
            filepath TEXT,
            uploaded_at TEXT
        )
    """)
    conn.commit()
    conn.close()

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form["name"].strip()
        patient_id = request.form["patient_id"].strip().upper()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM patients
            WHERE LOWER(Name) = LOWER(?) AND UPPER(PatientID) = UPPER(?)
        """, (name, patient_id))
        row = cursor.fetchone()
        conn.close()

        if row:
            keys = ["PatientID", "Name", "Age", "Gender", "SystolicBP", "DiastolicBP", "BMI", "GlucoseLevel", "SpO2", "PulseRate", "Outcome", "LastUpdated"]
            user = dict(zip(keys, row))

            glucose = user["GlucoseLevel"]
            systolic = user["SystolicBP"]
            diastolic = user["DiastolicBP"]
            bmi = user["BMI"]
            spo2 = user["SpO2"]
            pulse = user["PulseRate"]
            ideal_bmi = 22

            health_index = max(0, round(
                100 - 0.1 * glucose - 0.05 * systolic - 0.05 * diastolic
                - 0.5 * abs(bmi - ideal_bmi) - 0.2 * (100 - spo2) + 0.05 * pulse,
                2
            ))

            session["user"] = user
            session["health_index"] = health_index

            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid Name or Patient ID.")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filename, description FROM uploaded_files
        WHERE PatientID=?
        ORDER BY uploaded_at DESC
    """, (session["user"]["PatientID"],))
    rows = cursor.fetchall()
    conn.close()

    uploaded_files = [{"name": r[0], "description": r[1], "url": f"/uploads/{r[0]}"} for r in rows]

    return render_template("dashboard.html", user=session["user"], health_index=session["health_index"], uploaded_files=uploaded_files)

@app.route("/add_patient", methods=["GET", "POST"])
def add_patient():
    if request.method == "POST":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = (
            request.form["patient_id"].strip().upper(),
            request.form["name"].strip(),
            int(request.form["age"]),
            request.form["gender"],
            int(request.form["systolic"]),
            int(request.form["diastolic"]),
            float(request.form["bmi"]),
            int(request.form["glucose"]),
            int(request.form["spo2"]),
            int(request.form["pulse"]),
            int(request.form["outcome"]),
            now
        )

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO patients 
                (PatientID, Name, Age, Gender, SystolicBP, DiastolicBP, BMI, GlucoseLevel, SpO2, PulseRate, Outcome, LastUpdated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
            message = "✅ Patient added successfully!"
        except sqlite3.IntegrityError:
            message = "❌ Patient ID already exists!"
        conn.close()

        return render_template("add_patient.html", message=message)

    return render_template("add_patient.html")

@app.route("/update_health", methods=["GET", "POST"])
def update_health():
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        systolic = int(request.form["systolic"])
        diastolic = int(request.form["diastolic"])
        bmi = float(request.form["bmi"])
        glucose = int(request.form["glucose"])
        spo2 = int(request.form["spo2"])
        pulse = int(request.form["pulse"])
        updated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pid = session["user"]["PatientID"]

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE patients
            SET SystolicBP=?, DiastolicBP=?, BMI=?, GlucoseLevel=?, SpO2=?, PulseRate=?, LastUpdated=?
            WHERE PatientID=?
        """, (systolic, diastolic, bmi, glucose, spo2, pulse, updated_time, pid))
        conn.commit()

        ideal_bmi = 22
        health_index = max(0, round(
            100 - 0.1 * glucose - 0.05 * systolic - 0.05 * diastolic
            - 0.5 * abs(bmi - ideal_bmi) - 0.2 * (100 - spo2) + 0.05 * pulse,
            2
        ))

        cursor.execute("""
            INSERT INTO patient_history (PatientID, Timestamp, HealthIndex)
            VALUES (?, ?, ?)
        """, (pid, updated_time, health_index))

        cursor.execute("SELECT * FROM patients WHERE PatientID=?", (pid,))
        row = cursor.fetchone()
        conn.commit()
        conn.close()

        keys = ["PatientID", "Name", "Age", "Gender", "SystolicBP", "DiastolicBP", "BMI", "GlucoseLevel", "SpO2", "PulseRate", "Outcome", "LastUpdated"]
        user = dict(zip(keys, row))

        session["user"] = user
        session["health_index"] = health_index

        return redirect("/dashboard")

    return render_template("update_health.html", user=session["user"])

@app.route("/get_trend_data")
def get_trend_data():
    if "user" not in session:
        return jsonify({"labels": [], "values": []})

    patient_id = session["user"]["PatientID"]
    days = int(request.args.get("days", 7))
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Timestamp, HealthIndex FROM patient_history
        WHERE PatientID=? AND Timestamp >= ?
        ORDER BY Timestamp ASC
    """, (patient_id, since_date))
    rows = cursor.fetchall()
    conn.close()

    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]

    return jsonify({"labels": labels, "values": values})

@app.route("/upload_file", methods=["POST"])
def upload_file():
    if "user" not in session:
        return redirect("/")

    file = request.files["file"]
    description = request.form["description"]
    if file.filename == "":
        return redirect("/dashboard")

    filename = file.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO uploaded_files (PatientID, filename, description, filepath, uploaded_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session["user"]["PatientID"], filename, description, filepath, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/delete_file", methods=["POST"])
def delete_file():
    if "user" not in session:
        return redirect("/")

    filename = request.form["filename"]

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filepath FROM uploaded_files WHERE PatientID=? AND filename=?
    """, (session["user"]["PatientID"], filename))
    row = cursor.fetchone()

    if row:
        try:
            os.remove(row[0])
        except:
            pass
        cursor.execute("""
            DELETE FROM uploaded_files WHERE PatientID=? AND filename=?
        """, (session["user"]["PatientID"], filename))
        conn.commit()

    conn.close()
    return redirect("/dashboard")

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("health_index", None)
    return redirect("/")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
