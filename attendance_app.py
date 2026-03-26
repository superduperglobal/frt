"""
================================================================================
Version v1.5
- IST timezone fix
- Map view using OpenStreetMap (Leaflet)
================================================================================
"""

import os
from flask import Flask, request, render_template_string, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime
import sqlite3
import pytz

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
DB_FILE = 'attendance.db'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

IST = pytz.timezone('Asia/Kolkata')

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
<h2>📍 Attendance Capture</h2>
{% if message %}
<div style="padding:10px; background:#d4edda;">{{ message }}</div>
{% endif %}

<form method="POST" enctype="multipart/form-data">
Name:<br><input type="text" name="name" required><br><br>
Employee ID:<br><input type="text" name="emp_id" required><br><br>
Remarks:<br><input type="text" name="remarks"><br><br>
Photo:<br><input type="file" name="photo" accept="image/*" capture="environment" required><br><br>

<input type="hidden" name="latitude" id="latitude">
<input type="hidden" name="longitude" id="longitude">

<button type="submit">Submit</button>
</form>

<script>
navigator.geolocation.getCurrentPosition(function(position) {
document.getElementById("latitude").value = position.coords.latitude;
document.getElementById("longitude").value = position.coords.longitude;
});
</script>
"""

# ------------------------------------------------------------------------------
ADMIN_PAGE = """
<h2>📊 Attendance Records</h2>

<table border="1" cellpadding="5">
<tr>
<th>Name</th>
<th>Emp ID</th>
<th>Remarks</th>
<th>Lat</th>
<th>Long</th>
<th>Map</th>
<th>Image</th>
<th>Time (IST)</th>
</tr>

{% for row in data %}
<tr>
<td>{{row[1]}}</td>
<td>{{row[2]}}</td>
<td>{{row[3]}}</td>
<td>{{row[4]}}</td>
<td>{{row[5]}}</td>
<td><a href="/map/{{row[4]}}/{{row[5]}}" target="_blank">View Map</a></td>
<td><img src="/uploads/{{row[6].split('/')[-1]}}" width="100"></td>
<td>{{row[7]}}</td>
</tr>
{% endfor %}
</table>
"""

# ------------------------------------------------------------------------------
MAP_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Location Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
</head>
<body>

<h3>📍 Location View</h3>
<div id="map" style="height:500px;"></div>

<script>
var lat = {{lat}};
var lon = {{lon}};

var map = L.map('map').setView([lat, lon], 15);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19
}).addTo(map);

L.marker([lat, lon]).addTo(map)
    .bindPopup("Attendance Location")
    .openPopup();
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
            message = "Invalid image"
            return render_template_string(HTML_PAGE, message=message)

        timestamp_str = datetime.now(IST).strftime("%Y%m%d%H%M%S")
        filename = secure_filename(f"{emp_id}_{timestamp_str}.jpg")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO attendance
            VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)
        """, (name, emp_id, remarks, latitude, longitude, filepath, timestamp))
        conn.commit()
        conn.close()

        message = f"✅ Attendance recorded for {name} at {timestamp}"

    return render_template_string(HTML_PAGE, message=message)

# ------------------------------------------------------------------------------
@app.route("/admin")
def admin():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance ORDER BY id DESC")
    data = cursor.fetchall()
    conn.close()

    return render_template_string(ADMIN_PAGE, data=data)

# ------------------------------------------------------------------------------
@app.route("/map/<lat>/<lon>")
def map_view(lat, lon):
    return render_template_string(MAP_PAGE, lat=lat, lon=lon)

# ------------------------------------------------------------------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
