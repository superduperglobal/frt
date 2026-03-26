"""
================================================================================
Version v2.5 (Admin Fixed + Map Dashboard)
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
import mediapipe as mp
import json

UPLOAD_FOLDER = 'uploads'
DB_FILE = 'attendance.db'
IST = pytz.timezone('Asia/Kolkata')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)

mp_face = mp.solutions.face_detection
face_detector = mp_face.FaceDetection(min_detection_confidence=0.6)

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

<form method="POST" onsubmit="disableSubmit()">

Name:<br><input type="text" name="name" required><br><br>
Employee ID:<br><input type="text" name="emp_id" required><br><br>
Remarks:<br><input type="text" name="remarks"><br><br>

<video id="video" width="250" autoplay></video><br>
<button type="button" onclick="capture()">Capture</button><br><br>

<input type="hidden" name="image_data" id="image_data">
<input type="hidden" name="latitude" id="latitude">
<input type="hidden" name="longitude" id="longitude">

<button type="submit" id="submitBtn" disabled>Submit</button>

<div id="msg_box" style="margin-top:10px;">
{% if message %}
<div style="padding:10px;
            background:{{'green' if '✅' in message else 'red'}};
            color:white;">
{{message}}
{% if '❌' in message %}
<br>👉 Please retry ensuring face is centered and move slightly
{% endif %}
</div>
{% endif %}
</div>

</form>

<script>
function disableSubmit() {
    document.getElementById("submitBtn").disabled = true;
}

navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
.then(stream => video.srcObject = stream);

async function capture() {
    let frames = [];

    for (let i = 0; i < 3; i++) {
        let canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        let ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);

        frames.push(canvas.toDataURL('image/jpeg'));

        await new Promise(r => setTimeout(r, 300)); // slight delay
    }

    document.getElementById('image_data').value = JSON.stringify(frames);

    alert("Captured multiple frames");
}

navigator.geolocation.getCurrentPosition(
    pos => {
        latitude.value = pos.coords.latitude;
        longitude.value = pos.coords.longitude;
        loc_status.innerText = "Location captured";
        submitBtn.disabled = false;
    },
    () => loc_status.innerText = "Location required"
);
</script>
"""

# ------------------------------------------------------------------------------
def validate_face_liveness(images):
    """
    images = list of PIL images (multiple frames)
    """

    face_positions = []

    for img in images:
        img_np = np.array(img)
        rgb = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)

        results = face_detector.process(rgb)

        if not results.detections:
            return False, "❌ No face detected"

        # Take first detection
        det = results.detections[0]
        bbox = det.location_data.relative_bounding_box

        cx = bbox.xmin + bbox.width / 2
        cy = bbox.ymin + bbox.height / 2

        face_positions.append((cx, cy))

    # 🔹 Liveness check: movement between frames
    movement = 0
    for i in range(len(face_positions)-1):
        dx = abs(face_positions[i][0] - face_positions[i+1][0])
        dy = abs(face_positions[i][1] - face_positions[i+1][1])
        movement += dx + dy

    if movement < 0.02:
        return False, "❌ No movement detected (possible spoof)"

    # 🔹 Center check (use last frame)
    cx, cy = face_positions[-1]
    if not (0.3 < cx < 0.7 and 0.3 < cy < 0.7):
        return False, "❌ Face not centered"

    return True, "OK"

# ------------------------------------------------------------------------------
def stamp_image(image, lat, lon, timestamp):
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    text = f"Lat:{lat} Lon:{lon}\nTime:{timestamp}"

    bbox = draw.multiline_textbbox((0,0),text,font=font)
    x,y = 10, image.height-(bbox[3]-bbox[1])-10

    draw.rectangle([x-5,y-5,x+(bbox[2]-bbox[0])+5,y+(bbox[3]-bbox[1])+5],fill=(0,0,0))
    draw.multiline_text((x,y),text,fill=(255,255,255),font=font)

    return image

# ------------------------------------------------------------------------------
@app.route("/",methods=["GET","POST"])
def index():
    msg=None

    if request.method=="POST":
        name=request.form["name"]
        emp_id=request.form["emp_id"]
        remarks=request.form["remarks"]
        lat=request.form["latitude"]
        lon=request.form["longitude"]
        img_data=request.form["image_data"]

        if not lat or not lon or not img_data:
            msg="All inputs required"
            return render_template_string(HTML_PAGE,message=msg)

        lat,lon=round(float(lat),3),round(float(lon),3)
        ts=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        frames = json.loads(img_data)

        images = []
        for f in frames:
            encoded = f.split(",")[1]
            img = Image.open(BytesIO(base64.b64decode(encoded)))
            img = ImageOps.exif_transpose(img)
            images.append(img)

        valid,m=validate_face_liveness(images)
        if not valid:
            return render_template_string(HTML_PAGE,message=m)

        # Use LAST frame for saving
        img = images[-1]

        img=stamp_image(img,lat,lon,ts)

        fname=f"{emp_id}_{datetime.now(IST).strftime('%Y%m%d%H%M%S')}.jpg"
        path=os.path.join(UPLOAD_FOLDER,fname)
        img.save(path)

        # Prevent duplicate within 5 seconds
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
        SELECT timestamp FROM attendance 
        WHERE emp_id=? 
        ORDER BY id DESC LIMIT 1
        """, (emp_id,))

        last = cursor.fetchone()

        if last:
            last_time = datetime.strptime(last[0], "%Y-%m-%d %H:%M:%S")
            now_time = datetime.now(IST).replace(tzinfo=None)

            if (now_time - last_time).seconds < 5:
                conn.close()
                return render_template_string(HTML_PAGE, message="❌ Duplicate submission detected. Please wait.")

        conn.execute("INSERT INTO attendance VALUES(NULL,?,?,?,?,?,?,?)",
                     (name,emp_id,remarks,lat,lon,path,ts))
        conn.commit()
        conn.close()

        msg="Attendance recorded"

    return render_template_string(HTML_PAGE,message=msg)

# ------------------------------------------------------------------------------
@app.route("/admin")
def admin():
    conn=sqlite3.connect(DB_FILE)
    data=conn.execute("SELECT * FROM attendance ORDER BY id DESC").fetchall()
    conn.close()

    return render_template_string("""
    <h2>📊 Records</h2>
    <a href="/map_all">🗺 View All on Map</a> | <a href="/export">⬇ CSV</a><br><br>

    <table border=1>
    <tr><th>Name</th><th>ID</th><th>Lat</th><th>Lon</th><th>Map</th><th>Image</th><th>Time</th></tr>

    {% for r in data %}
    <tr>
    <td>{{r[1]}}</td>
    <td>{{r[2]}}</td>
    <td>{{r[4]}}</td>
    <td>{{r[5]}}</td>
    <td><a href="/map/{{r[4]}}/{{r[5]}}" target="_blank">View</a></td>
    <td><img src="/uploads/{{r[6].split('/')[-1]}}" width="80"></td>
    <td>{{r[7]}}</td>
    </tr>
    {% endfor %}
    </table>
    """,data=data)

# ------------------------------------------------------------------------------
@app.route("/map_all")
def map_all():
    conn=sqlite3.connect(DB_FILE)
    data=conn.execute("SELECT * FROM attendance").fetchall()
    conn.close()

    markers=[{"lat":r[4],"lon":r[5],"name":r[1]} for r in data]

    return render_template_string("""
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>

    <div id="map" style="height:500px;"></div>

    <script>
    var map=L.map('map').setView([20,78],5);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    var data={{markers|tojson}};

    data.forEach(d=>{
        L.marker([d.lat,d.lon]).addTo(map)
        .bindPopup(d.name);
    });
    </script>
    """,markers=markers)

# ------------------------------------------------------------------------------
@app.route("/map/<lat>/<lon>")
def map_view(lat,lon):
    return f"<h3>{lat},{lon}</h3>"

# ------------------------------------------------------------------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ------------------------------------------------------------------------------
@app.route("/export")
def export():
    conn=sqlite3.connect(DB_FILE)
    data=conn.execute("SELECT * FROM attendance").fetchall()
    conn.close()

    with open("attendance.csv","w",newline="") as f:
        csv.writer(f).writerows(data)

    return send_file("attendance.csv",as_attachment=True)

# ------------------------------------------------------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
