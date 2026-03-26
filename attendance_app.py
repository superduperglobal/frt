"""
================================================================================
Version v2.0 (Field Ready)
================================================================================
Features:
- Login system
- One attendance per day
- CSV export
- Front camera enforced (selfie)
- Location mandatory
- Admin dashboard
================================================================================
"""

import os
from flask import Flask, request, render_template_string, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3
import pytz
import csv

UPLOAD_FOLDER = 'uploads'
DB_FILE = 'attendance.db'
IST = pytz.timezone('Asia/Kolkata')

USERNAME = "admin"
PASSWORD = "1234"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "secret123"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            emp_id TEXT,
            date TEXT,
            remarks TEXT,
            latitude TEXT,
            longitude TEXT,
            image_path TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------------------------------------------------------------------
LOGIN_PAGE = """
<h2>Login</h2>
<form method="POST">
Username:<br><input type="text" name="username"><br><br>
Password:<br><input type="password" name="password"><br><br>
<button type="submit">Login</button>
</form>
<p>{{msg}}</p>
"""

# ------------------------------------------------------------------------------
HTML_PAGE = """
<h2>📍 Attendance Capture</h2>
<p id="loc_status"></p>

{% if message %}
<div style="background:#d4edda;padding:10px;">{{message}}</div>
{% endif %}

<form method="POST" enctype="multipart/form-data">

Name:<br><input type="text" name="name" required><br><br>
Employee ID:<br><input type="text" name="emp_id" required><br><br>
Remarks:<br><input type="text" name="remarks"><br><br>

📷 Selfie (Front Camera):<br>
<input type="file" name="photo" accept="image/*" capture="user" required><br><br>

<input type="hidden" name="latitude" id="latitude">
<input type="hidden" name="longitude" id="longitude">

<button type="submit" id="submitBtn" disabled>Submit</button>
</form>

<script>
let status = document.getElementById("loc_status");
let btn = document.getElementById("submitBtn");

status.innerText = "Fetching location...";

navigator.geolocation.getCurrentPosition(
    function(pos){
        document.getElementById("latitude").value = pos.coords.latitude;
        document.getElementById("longitude").value = pos.coords.longitude;
        status.innerText = "Location captured";
        btn.disabled = false;
    },
    function(){
        status.innerText = "Location required!";
    }
);
</script>
"""

# ------------------------------------------------------------------------------
@app.route("/", methods=["GET","POST"])
def index():
    if "user" not in session:
        return redirect("/login")

    message = None

    if request.method == "POST":
        name = request.form.get("name")
        emp_id = request.form.get("emp_id")
        remarks = request.form.get("remarks")
        lat = request.form.get("latitude")
        lon = request.form.get("longitude")

        if not lat or not lon:
            message = "Location required"
            return render_template_string(HTML_PAGE, message=message)

        today = datetime.now(IST).strftime("%Y-%m-%d")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM attendance WHERE emp_id=? AND date=?", (emp_id, today))
        if cursor.fetchone():
            conn.close()
            message = "Already marked today"
            return render_template_string(HTML_PAGE, message=message)

        file = request.files["photo"]
        filename = secure_filename(f"{emp_id}_{datetime.now(IST).strftime('%H%M%S')}.jpg")
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)

        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO attendance (name, emp_id, date, remarks, latitude, longitude, image_path, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, emp_id, today, remarks, lat, lon, path, timestamp))

        conn.commit()
        conn.close()

        message = "Attendance recorded"

    return render_template_string(HTML_PAGE, message=message)

# ------------------------------------------------------------------------------
@app.route("/login", methods=["GET","POST"])
def login():
    msg = ""
    if request.method == "POST":
        if request.form["username"] == USERNAME and request.form["password"] == PASSWORD:
            session["user"] = "admin"
            return redirect("/")
        else:
            msg = "Invalid credentials"
    return render_template_string(LOGIN_PAGE, msg=msg)

# ------------------------------------------------------------------------------
@app.route("/admin")
def admin():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_FILE)
    data = conn.execute("SELECT * FROM attendance ORDER BY id DESC").fetchall()
    conn.close()

    html = "<h2>Records</h2><a href='/export'>Download CSV</a><br><br><table border=1>"
    for row in data:
        html += f"<tr><td>{row}</td></tr>"
    html += "</table>"
    return html

# ------------------------------------------------------------------------------
@app.route("/export")
def export():
    conn = sqlite3.connect(DB_FILE)
    data = conn.execute("SELECT * FROM attendance").fetchall()
    conn.close()

    file_path = "attendance.csv"

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ID","Name","EmpID","Date","Remarks","Lat","Lon","Image","Time"])
        writer.writerows(data)

    return send_file(file_path, as_attachment=True)

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
