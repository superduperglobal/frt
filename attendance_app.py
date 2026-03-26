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
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    body { font-family: Arial, sans-serif; padding: 10px; max-width: 600px; margin: auto; }
    input[type=text], button { width: 100%; padding: 10px; margin: 5px 0; box-sizing: border-box; }
    video { max-width: 100%; height: auto; border: 1px solid #ccc; }
</style>
</head>
<body>
<h2>📍 Attendance Capture</h2>
<p id="loc_status"></p>

<form method="POST" onsubmit="disableSubmit()">

Name:<br><input type="text" name="name" required><br>
Employee ID:<br><input type="text" name="emp_id" required><br>
Remarks:<br><input type="text" name="remarks"><br>

<video id="video" autoplay></video><br>
<button type="button" onclick="capture()" style="background:#007BFF; color:white; border:none;">Capture</button>

<input type="hidden" name="image_data" id="image_data">
<input type="hidden" name="latitude" id="latitude">
<input type="hidden" name="longitude" id="longitude">

<button type="submit" id="submitBtn" disabled style="background:#28A745; color:white; border:none;">Submit</button>

<div id="msg_box" style="margin-top:10px;">
{% if message %}
<div style="padding:10px; border-radius:5px;
            background:{{'#28A745' if '✅' in message else '#DC3545'}};
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
    document.getElementById("submitBtn").innerText = "Submitting...";
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
        loc_status.innerText = "✅ Location captured";
        submitBtn.disabled = false;
    },
    () => loc_status.innerText = "❌ Location required"
);
</script>
</body>
</html>
"""

# ------------------------------------------------------------------------------
def validate_face_liveness(images):
    """
    images = list of PIL images (multiple frames)
    """

    face_positions = []

    for img in images:
        img_np = np.array(img)
        rgb = img_np

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
    conn = sqlite3.connect(DB_FILE)
    data = conn.execute("SELECT * FROM attendance ORDER BY id DESC").fetchall()

    # Get unique dates
    dates = sorted(list(set([d[7].split(" ")[0] for d in data])), reverse=True)

    selected_date = request.args.get("date", "All")

    if selected_date != "All":
        filtered = [d for d in data if d[7].startswith(selected_date)]
    else:
        filtered = data

    kpi = len(filtered)

    conn.close()

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; padding: 15px; background: #f4f6f9; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; text-align: center; }
        .card h3 { margin: 0; font-size: 2em; color: #007BFF; }
        .card p { margin: 5px 0 0; color: #555; font-size: 1.1em; }
        select, button { padding: 8px; border-radius: 5px; border: 1px solid #ccc; font-size: 1em; }
        a { text-decoration: none; color: white; background: #28a745; padding: 10px 15px; border-radius: 5px; display: inline-block; margin-top: 10px; }
        a.csv { background: #17a2b8; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #007BFF; color: white; }
        .table-container { overflow-x: auto; }
        img { border-radius: 5px; }
        button.view-btn { background: #ffc107; border: none; padding: 5px 10px; cursor: pointer; color: black; font-weight: bold; border-radius: 3px; }
    </style>
    </head>
    <body>
    <h2>📊 Attendance Dashboard</h2>

    <form method="GET" style="margin-bottom:20px;">
        <label><b>Filter by Date:</b></label>
        <select name="date" onchange="this.form.submit()">
            <option value="All" {% if selected_date == "All" %}selected{% endif %}>All Dates</option>
        {% for d in dates %}
            <option value="{{d}}" {% if d==selected_date %}selected{% endif %}>{{d}}</option>
        {% endfor %}
        </select>
    </form>

    <div class="card">
        <h3>{{kpi}}</h3>
        <p>📌 Total Submissions</p>
    </div>

    <div>
        <a href="/map_all?date={{selected_date}}">🗺 View All on Map</a>
        <a href="/export" class="csv">⬇ Download CSV</a>
    </div>

    <div class="table-container">
        <table>
        <tr>
        <th>Name</th><th>ID</th><th>Lat</th><th>Lon</th>
        <th>Map</th><th>Image</th><th>Time</th>
        </tr>

        {% for r in filtered %}
        <tr>
        <td>{{r[1]}}</td>
        <td>{{r[2]}}</td>
        <td>{{r[4]}}</td>
        <td>{{r[5]}}</td>

        <td>
            <button class="view-btn" onclick="showMap({{r[4]}}, {{r[5]}})">View</button>
        </td>

        <td>
            <img src="/uploads/{{r[6].split('/')[-1]}}" width="80">
        </td>

        <td>{{r[7]}}</td>
        </tr>
        {% endfor %}
        </table>
    </div>

    <!-- Modal -->
    <div id="mapModal" style="display:none; position:fixed; top:5%; left:5%; width:90%; height:80%; background:white; border:2px solid black; z-index:9999; box-shadow: 0 0 20px rgba(0,0,0,0.5);">
        <button onclick="closeMap()" style="position:absolute; top:10px; right:10px; z-index:9999; background:red; color:white; border:none; padding:10px; cursor:pointer;">Close</button>
        <div id="map" style="height:100%; width:100%;"></div>
    </div>

    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <script>
    var map;

    function showMap(lat, lon){
        document.getElementById("mapModal").style.display="block";

        if(map) {
            map.remove(); // clear old map inst to avoid leaflet re-initialization error
        }

        setTimeout(function(){
            map = L.map('map').setView([lat, lon], 15);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

            L.marker([lat, lon]).addTo(map);
        }, 200);
    }

    function closeMap(){
        document.getElementById("mapModal").style.display="none";
        document.getElementById("map").innerHTML="";
    }
    </script>
    </body>
    </html>
    """, filtered=filtered, dates=dates, selected_date=selected_date, kpi=kpi)

# ------------------------------------------------------------------------------
@app.route("/map_all")
def map_all():
    date = request.args.get("date", "All")

    conn = sqlite3.connect(DB_FILE)
    data = conn.execute("SELECT * FROM attendance").fetchall()
    conn.close()

    if date and date != "All":
        data = [d for d in data if d[7].startswith(date)]

    markers = [
        {"lat": d[4], "lon": d[5], "name": d[1]}
        for d in data
    ]

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; }
        .header { padding: 15px; background: #007BFF; color: white; display: flex; justify-content: space-between; align-items: center; }
        h3 { margin: 0; }
        a { color: white; text-decoration: none; font-weight: bold; background: rgba(255,255,255,0.2); padding: 5px 10px; border-radius: 5px; }
    </style>
    </head>
    <body>

    <div class="header">
        <h3>🗺 Cluster Map View{% if date != 'All' %} ({{date}}){% else %} (All Data){% endif %}</h3>
        <a href="/admin">🔙 Back to Admin</a>
    </div>

    <div id="map" style="height: calc(100vh - 54px); width: 100vw;"></div>

    <script>
    var map = L.map('map').setView([20,78],5);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    var markers = L.markerClusterGroup({
        maxClusterRadius: 50,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: true,
        zoomToBoundsOnClick: true
    });

    var data = {{markers|tojson}};

    data.forEach(d => {
        var marker = L.marker([parseFloat(d.lat), parseFloat(d.lon)])
            .bindPopup("<b>" + d.name + "</b><br>Lat: " + d.lat + "<br>Lon: " + d.lon);
        markers.addLayer(marker);
    });

    map.addLayer(markers);

    // Fit map bounds to show all markers if there are any
    if (data.length > 0) {
        var bounds = L.latLngBounds(data.map(d => [parseFloat(d.lat), parseFloat(d.lon)]));
        map.fitBounds(bounds, {padding: [50, 50]});
    }
    </script>
    </body>
    </html>
    """, markers=markers, date=date)

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
