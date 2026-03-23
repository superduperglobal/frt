"""
================================================================================
Script Name   : attendance_app.py
Version       : v1.3
================================================================================
ENHANCEMENTS:
- Visible success confirmation
- Better UI feedback
- Image size control
- Improved reliability
================================================================================
"""

import os
from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
DB_FILE = 'attendance.db'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

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
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

{% if message %}
<div style="padding:10px; background:#d4edda; color:#155724; margin-bottom:15px;">
    {{ message }}
</div>
{% endif %}

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
@app.route("/", methods=["GET", "POST"])
def index():
    message = None

    if request.method == "POST":

        name = request.form.get("name")
        emp_id = request.form.get("emp_id")
        remarks = request.form.get("remarks")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        file = request.files.get("photo")

        if not file or not allowed_file(file.filename):
            message = "Invalid image file"
            return render_template_string(HTML_PAGE, message=message)

        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = secure_filename(f"{emp_id}_{timestamp_str}.jpg")
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

        message = f"✅ Attendance recorded for {name} at {timestamp}"

    return render_template_string(HTML_PAGE, message=message)

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
