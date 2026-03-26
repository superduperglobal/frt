"""
================================================================================
Script Name   : attendance_app.py
Version       : v2.3 (Stable + Stamping Fixed)
================================================================================
FEATURES:
- Live camera capture (no gallery upload)
- Location mandatory
- IST timestamp
- Lat/Long rounded (3 decimals)
- Image stamping (visible, fixed)
- Admin view + map + image preview
- CSV export
================================================================================
"""

import os
from flask import Flask, request, render_template_string, send_from_directory, send_file
from datetime import datetime
import sqlite3
import pytz
import csv
from PIL import Image, ImageDraw, ImageFont, ImageOps
import base64
from io import BytesIO

# ------------------------------------------------------------------------------
UPLOAD_FOLDER = 'uploads'
DB_FILE = 'attendance.db'
IST = pytz.timezone('Asia/Kolkata')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# ------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
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
HTML_PAGE = """
<h2>📍 Attendance Capture</h2>

<p id="loc_status" style="color:orange;"></p>

{% if message %}
<div style="background:#d4edda;padding:10px;margin-bottom:10px;">
{{message}}
</div>
{% endif %}

<form method="POST">

Name:<br><input type="text" name="name" required><br><br>

Employee ID:<br><input type="text" name="emp_id" required><br><br>

Remarks:<br><input type="text" name="remarks"><br><br>

📷 Selfie:<br>
<video id="video" width="250" autoplay></video><br>
<button type="button" onclick="capture()">Capture</button><br><br>

<input type="hidden" name="image_data" id="image_data">
<input type="hidden" name="latitude" id="latitude">
<input type="hidden" name="longitude" id="longitude">

<button type="submit" id="submitBtn" disabled>Submit Attendance</button>
</form>

<script>
let video = document.getElementById('video');
let submitBtn = document.getElementById('submitBtn');

navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
.then(stream => {
    video.srcObject = stream;
});

function capture() {
    let canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    let ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    let data = canvas.toDataURL('image/jpeg');
    document.getElementById('image_data').value = data;

    alert("Photo captured");
}

let status = document.getElementById("loc_status");

status.innerText = "📍 Fetching location...";

navigator.geolocation.getCurrentPosition(
    function(pos){
        document.getElementById("latitude").value = pos.coords.latitude;
        document.getElementById("longitude").value = pos.coords.longitude;

        status.innerText = "✅ Location captured";
        status.style.color = "green";
        submitBtn.disabled = false;
    },
    function(){
        status.innerText = "❌ Location required. Please allow GPS.";
        status.style.color = "red";
    }
);
</script>
"""

# ------------------------------------------------------------------------------
ADMIN_PAGE = """
<h2>📊 Attendance Records</h2>

<a href="/export">⬇ Download CSV</a><br><br>

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
<td><a href="/map/{{row[4]}}/{{row[5]}}" target="_blank">View</a></td>
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
<title>Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
</head>
<body>

<div id="map" style="height:500px;"></div>

<script>
var lat = {{lat}};
var lon = {{lon}};

var map = L.map('map').setView([lat, lon], 15);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

L.marker([lat, lon]).addTo(map).bindPopup("Attendance Location").openPopup();
</script>

</body>
</html>
"""

# ------------------------------------------------------------------------------
def stamp_image(image, lat, lon, timestamp):
    draw = ImageDraw.Draw(image)

    text = f"Lat: {lat} | Lon: {lon}\nTime: {timestamp}"

    font = ImageFont.load_default()

    bbox = draw.multiline_textbbox((0,0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = 10
    y = image.height - text_height - 10

    draw.rectangle(
        [(x-5, y-5), (x + text_width + 5, y + text_height + 5)],
        fill=(0, 0, 0)
    )

    draw.multiline_text((x, y), text, fill=(255,255,255), font=font)

    return image

# ------------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    message = None

    if request.method == "POST":
        name = request.form.get("name")
        emp_id = request.form.get("emp_id")
        remarks = request.form.get("remarks")
        lat = request.form.get("latitude")
        lon = request.form.get("longitude")
        image_data = request.form.get("image_data")

        if not lat or not lon or not image_data:
            message = "❌ All fields including location & photo required"
            return render_template_string(HTML_PAGE, message=message)

        lat = round(float(lat), 3)
        lon = round(float(lon), 3)

        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        header, encoded = image_data.split(",", 1)
        img = Image.open(BytesIO(base64.b64decode(encoded)))

        img = ImageOps.exif_transpose(img)

        img = stamp_image(img, lat, lon, timestamp)

        filename = f"{emp_id}_{datetime.now(IST).strftime('%Y%m%d%H%M%S')}.jpg"
        path = os.path.join(UPLOAD_FOLDER, filename)
        img.save(path)

        conn = sqlite3.connect(DB_FILE)
        conn.execute("""
            INSERT INTO attendance (name, emp_id, remarks, latitude, longitude, image_path, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, emp_id, remarks, lat, lon, path, timestamp))
        conn.commit()
        conn.close()

        message = f"✅ Attendance recorded at {timestamp}"

    return render_template_string(HTML_PAGE, message=message)

# ------------------------------------------------------------------------------
@app.route("/admin")
def admin():
    conn = sqlite3.connect(DB_FILE)
    data = conn.execute("SELECT * FROM attendance ORDER BY id DESC").fetchall()
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
@app.route("/export")
def export():
    conn = sqlite3.connect(DB_FILE)
    data = conn.execute("SELECT * FROM attendance").fetchall()
    conn.close()

    file_path = "attendance.csv"

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ID","Name","EmpID","Remarks","Lat","Lon","Image","Time"])
        writer.writerows(data)

    return send_file(file_path, as_attachment=True)

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
