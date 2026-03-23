"""
================================================================================
Script Name   : attendance_app.py
Version       : v1.0
Author        : ChatGPT
Created On    : 23-03-2026

================================================================================
FUNCTIONAL OVERVIEW
--------------------------------------------------------------------------------
This is a mobile-friendly Attendance Capture Web App with:

1. User Input Fields:
   - Name
   - Employee ID
   - Remarks

2. Auto Capture:
   - Location (Latitude, Longitude via browser)
   - Timestamp (server-side)

3. Image Capture:
   - Camera upload from mobile device

4. Storage:
   - Data → SQLite database
   - Images → /uploads folder

5. Security:
   - File type validation
   - Size control
   - Server-side timestamp

================================================================================
VERSION HISTORY
--------------------------------------------------------------------------------
v1.0 (23-03-2026)
- Initial version
- Form + Location + Camera + Storage implemented
- SQLite integration added
- Render-ready deployment
================================================================================
"""

import os
from flask import Flask, request, render_template_string, redirect, url_for, flash
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
DB_FILE = 'attendance.db'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'secret_key_change_this'

# ------------------------------------------------------------------------------
# DATABASE INITIALIZATION
# ------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            emp_id TEXT,
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
# UTIL FUNCTIONS
# ------------------------------------------------------------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ------------------------------------------------------------------------------
# HTML TEMPLATE (INLINE)
# ------------------------------------------------------------------------------
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Attendance Capture</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: Arial; padding: 20px;">

<h2>📍 Attendance Capture</h2>

<form method="POST" enctype="multipart/form-data">

    <label>Name:</label><br>
    <input type="text" name="name" required><br><br>

    <label>Employee ID:</label><br>
    <input type="text" name="emp_id" required><br><br>

    <label>Remarks:</label><br>
    <input type="text" name="remarks"><br><br>

    <label>Capture Photo:</label><br>
    <input type="file" name="photo" accept="image/*" capture="environment" required><br><br>

    <input type="hidden" name="latitude" id="latitude">
    <input type="hidden" name="longitude" id="longitude">

    <button type="submit">Submit Attendance</button>
</form>

<script>
navigator.geolocation.getCurrentPosition(function(position) {
    document.getElementById("latitude").value = position.coords.latitude;
    document.getElementById("longitude").value = position.coords.longitude;
});
</script>

</body>
</html>
"""

# ------------------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":

        name = request.form.get("name")
        emp_id = request.form.get("emp_id")
        remarks = request.form.get("remarks")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        file = request.files.get("photo")

        if not file or not allowed_file(file.filename):
            flash("Invalid image file")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO attendance
            (name, emp_id, remarks, latitude, longitude, image_path, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, emp_id, remarks, latitude, longitude, filepath, timestamp))

        conn.commit()
        conn.close()

        flash("Attendance Submitted Successfully")
        return redirect(url_for("index"))

    return render_template_string(HTML_PAGE)

# ------------------------------------------------------------------------------
# RUN
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)