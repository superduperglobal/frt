"""
================================================================================
Version v2.2
================================================================================
- Live camera capture (no gallery upload)
- Image stamping (lat, lon, timestamp)
- Rounded lat/long (3 decimals)
================================================================================
"""

import os
from flask import Flask, request, render_template_string, send_from_directory
from datetime import datetime
import sqlite3
import pytz
from PIL import Image, ImageDraw, ImageFont
import base64
from io import BytesIO

UPLOAD_FOLDER = 'uploads'
DB_FILE = 'attendance.db'
IST = pytz.timezone('Asia/Kolkata')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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

<p id="loc_status"></p>

{% if message %}
<div style="background:#d4edda;padding:10px;">{{message}}</div>
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

<button type="submit" id="submitBtn" disabled>Submit</button>
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

navigator.geolocation.getCurrentPosition(
    function(pos){
        document.getElementById("latitude").value = pos.coords.latitude;
        document.getElementById("longitude").value = pos.coords.longitude;
        submitBtn.disabled = false;
    },
    function(){
        alert("Location required");
    }
);
</script>
"""

# ------------------------------------------------------------------------------
def stamp_image(image, lat, lon, timestamp):
    draw = ImageDraw.Draw(image)

    text = f"Lat: {lat} | Lon: {lon}\\nTime: {timestamp}"

    draw.text((10, image.height - 60), text, fill=(255,0,0))

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
            message = "All fields required"
            return render_template_string(HTML_PAGE, message=message)

        lat = round(float(lat), 3)
        lon = round(float(lon), 3)

        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        # Decode image
        header, encoded = image_data.split(",", 1)
        img = Image.open(BytesIO(base64.b64decode(encoded)))

        # Stamp image
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

        message = "✅ Attendance recorded with stamped selfie"

    return render_template_string(HTML_PAGE, message=message)

# ------------------------------------------------------------------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
