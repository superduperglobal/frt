"""
================================================================================
Version v2.4
================================================================================
- Face detection (OpenCV Haarcascade)
- At least 1 face required
- Face center validation
- Basic liveness (reject blank/low variance)
- All previous features retained
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
import cv2
import numpy as np

# ------------------------------------------------------------------------------
UPLOAD_FOLDER = 'uploads'
DB_FILE = 'attendance.db'
IST = pytz.timezone('Asia/Kolkata')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ------------------------------------------------------------------------------
# Load Haarcascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

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
.then(stream => { video.srcObject = stream; });

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
        status.innerText = "❌ Location required";
        status.style.color = "red";
    }
);
</script>
"""

# ------------------------------------------------------------------------------
def validate_face(image):
    img_np = np.array(image)
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    if len(faces) == 0:
        return False, "❌ No face detected"

    # Take first face
    (x, y, w, h) = faces[0]

    img_h, img_w = gray.shape

    face_center_x = x + w/2
    face_center_y = y + h/2

    # Center tolerance (30%)
    if not (0.3*img_w < face_center_x < 0.7*img_w and
            0.3*img_h < face_center_y < 0.7*img_h):
        return False, "❌ Face not centered"

    # Liveness check (variance)
    variance = np.var(gray)
    if variance < 100:
        return False, "❌ Low detail image (possible fake)"

    return True, "OK"

# ------------------------------------------------------------------------------
def stamp_image(image, lat, lon, timestamp):
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    text = f"Lat: {lat} | Lon: {lon}\nTime: {timestamp}"

    bbox = draw.multiline_textbbox((0,0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    x = 10
    y = image.height - h - 10

    draw.rectangle([(x-5, y-5), (x+w+5, y+h+5)], fill=(0,0,0))
    draw.multiline_text((x, y), text, fill=(255,255,255), font=font)

    return image

# ------------------------------------------------------------------------------
@app.route("/", methods=["GET","POST"])
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
            message = "❌ All inputs required"
            return render_template_string(HTML_PAGE, message=message)

        lat = round(float(lat), 3)
        lon = round(float(lon), 3)

        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        header, encoded = image_data.split(",", 1)
        img = Image.open(BytesIO(base64.b64decode(encoded)))
        img = ImageOps.exif_transpose(img)

        # Face validation
        valid, msg = validate_face(img)
        if not valid:
            return render_template_string(HTML_PAGE, message=msg)

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

        message = "✅ Attendance recorded with valid selfie"

    return render_template_string(HTML_PAGE, message=message)

# ------------------------------------------------------------------------------
@app.route("/admin")
def admin():
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
        writer.writerow(["ID","Name","EmpID","Remarks","Lat","Lon","Image","Time"])
        writer.writerows(data)

    return send_file(file_path, as_attachment=True)

# ------------------------------------------------------------------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
