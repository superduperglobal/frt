"""
================================================================================
Version v2.7.1 (Render Stable Final)
================================================================================
CHANGES:
1. ❌ Removed MediaPipe (Render libGL issue)
2. ✅ Replaced with OpenCV Haar Cascade
3. ✅ Fixed Flask return error (always returns response)
4. ✅ Fixed success/error UI (green/red message)
5. ✅ Fixed duplicate submissions
6. ✅ Admin:
   - Popup map per row
   - Cluster map
   - Date filter + KPI
7. ✅ CSV export header fixed
================================================================================
"""

import os, json, base64, sqlite3, csv
from flask import Flask, request, render_template_string, send_from_directory, send_file
from datetime import datetime
import pytz
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import cv2
import numpy as np

# ------------------------------------------------------------------------------
UPLOAD_FOLDER = 'uploads'
DB_FILE = 'attendance.db'
IST = pytz.timezone('Asia/Kolkata')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)

# ------------------------------------------------------------------------------
# Face detector (OpenCV)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

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

<div style="margin-top:10px;">
{% if message %}
<div style="padding:10px;
background:{{'green' if '✅' in message else 'red'}};
color:white;">
{{message}}
{% if '❌' in message %}
<br>👉 Retry: keep face centered & move slightly
{% endif %}
</div>
{% endif %}
</div>

</form>

<script>
navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
.then(stream => video.srcObject = stream);

async function capture() {
    let frames = [];
    for (let i=0;i<3;i++){
        let c=document.createElement('canvas');
        c.width=video.videoWidth;
        c.height=video.videoHeight;
        c.getContext('2d').drawImage(video,0,0);
        frames.push(c.toDataURL('image/jpeg'));
        await new Promise(r=>setTimeout(r,300));
    }
    image_data.value = JSON.stringify(frames);
    alert("Captured");
}

navigator.geolocation.getCurrentPosition(
    pos=>{
        latitude.value=pos.coords.latitude;
        longitude.value=pos.coords.longitude;

        if(pos.coords.accuracy>100){
            loc_status.innerText="⚠️ Low GPS accuracy";
        } else {
            loc_status.innerText="✅ Location captured";
        }
        submitBtn.disabled=false;
    },
    ()=>loc_status.innerText="❌ Location required"
);

function disableSubmit(){
    submitBtn.disabled=true;
}
</script>
"""

# ------------------------------------------------------------------------------
def validate_face_liveness(images):
    positions = []

    for img in images:
        img_np = np.array(img.convert('RGB'))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        faces = face_cascade.detectMultiScale(gray,1.3,5)

        if len(faces)==0:
            return False,"❌ No face detected"

        x,y,w,h = faces[0]
        h_img,w_img = gray.shape

        cx = (x+w/2)/w_img
        cy = (y+h/2)/h_img

        positions.append((cx,cy))

    movement = sum(abs(positions[i][0]-positions[i+1][0]) +
                   abs(positions[i][1]-positions[i+1][1])
                   for i in range(len(positions)-1))

    if movement < 0.05:
        return False,"❌ No movement detected"

    cx,cy = positions[-1]
    if not (0.3<cx<0.7 and 0.3<cy<0.7):
        return False,"❌ Face not centered"

    return True,"OK"

# ------------------------------------------------------------------------------
def stamp_image(image, lat, lon, ts):
    d = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    text = f"Lat:{lat} Lon:{lon}\nTime:{ts}"

    bbox = d.multiline_textbbox((0,0),text,font=font)
    x,y = 10,image.height-(bbox[3]-bbox[1])-10

    d.rectangle([x-5,y-5,x+(bbox[2]-bbox[0])+5,y+(bbox[3]-bbox[1])+5],fill=(0,0,0))
    d.multiline_text((x,y),text,fill=(255,255,255),font=font)

    return image

# ------------------------------------------------------------------------------
@app.route("/",methods=["GET","POST"])
def index():
    msg=None

    try:
        if request.method=="POST":
            name=request.form.get("name")
            emp_id=request.form.get("emp_id")
            remarks=request.form.get("remarks")
            lat=request.form.get("latitude")
            lon=request.form.get("longitude")
            img_data=request.form.get("image_data")

            if not lat or not lon or not img_data:
                return render_template_string(HTML_PAGE,message="❌ All inputs required")

            # Duplicate guard
            conn=sqlite3.connect(DB_FILE)
            cur=conn.cursor()
            cur.execute("SELECT timestamp FROM attendance WHERE emp_id=? ORDER BY id DESC LIMIT 1",(emp_id,))
            last=cur.fetchone()

            if last:
                last_time=datetime.strptime(last[0],"%Y-%m-%d %H:%M:%S")
                if (datetime.now(IST)-last_time).seconds<5:
                    conn.close()
                    return render_template_string(HTML_PAGE,message="❌ Duplicate submission")

            lat,lon=round(float(lat),3),round(float(lon),3)
            ts=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

            frames=json.loads(img_data)
            images=[]

            for f in frames:
                encoded=f.split(",")[1]
                img=Image.open(BytesIO(base64.b64decode(encoded)))
                img=ImageOps.exif_transpose(img)
                images.append(img)

            valid,msg=validate_face_liveness(images)
            if not valid:
                return render_template_string(HTML_PAGE,message=msg)

            img=stamp_image(images[-1],lat,lon,ts)

            fname=f"{emp_id}_{datetime.now(IST).strftime('%Y%m%d%H%M%S')}.jpg"
            path=os.path.join(UPLOAD_FOLDER,fname)
            img.save(path)

            conn.execute("INSERT INTO attendance VALUES(NULL,?,?,?,?,?,?,?)",
                         (name,emp_id,remarks,lat,lon,path,ts))
            conn.commit()
            conn.close()

            msg="✅ Attendance recorded successfully"

    except Exception as e:
        msg=f"❌ Error: {str(e)}"

    return render_template_string(HTML_PAGE,message=msg)

# ------------------------------------------------------------------------------
@app.route("/admin")
def admin():
    conn=sqlite3.connect(DB_FILE)
    data=conn.execute("SELECT * FROM attendance ORDER BY id DESC").fetchall()
    conn.close()

    dates=sorted(list(set([d[7].split(" ")[0] for d in data])),reverse=True)
    sel=request.args.get("date",dates[0] if dates else None)

    filtered=[d for d in data if d[7].startswith(sel)]
    kpi=len(filtered)

    return render_template_string("""
    <h2>📊 Dashboard</h2>

    <form>
    <select name="date" onchange="this.form.submit()">
    {% for d in dates %}
    <option value="{{d}}" {% if d==sel %}selected{% endif %}>{{d}}</option>
    {% endfor %}
    </select>
    </form>

    <h3>Total: {{kpi}}</h3>

    <a href="/map_all?date={{sel}}">Map All</a> | <a href="/export">CSV</a><br><br>

    <table border=1>
    {% for r in data %}
    <tr>
    <td>{{r[1]}}</td>
    <td>{{r[2]}}</td>
    <td><button onclick="showMap({{r[4]}},{{r[5]}})">Map</button></td>
    <td><img src="/uploads/{{r[6].split('/')[-1]}}" width=80></td>
    </tr>
    {% endfor %}
    </table>

    <div id="mapModal" style="display:none;position:fixed;top:10%;left:10%;width:80%;height:70%;background:white;">
    <button onclick="closeMap()">Close</button>
    <div id="map" style="height:90%"></div>
    </div>

    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>

    <script>
    function showMap(lat,lon){
        mapModal.style.display="block";
        setTimeout(()=>{
            var map=L.map('map').setView([lat,lon],15);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            L.marker([lat,lon]).addTo(map);
        },200);
    }
    function closeMap(){
        mapModal.style.display="none";
        map.innerHTML="";
    }
    </script>
    """,data=filtered,dates=dates,sel=sel,kpi=kpi)

# ------------------------------------------------------------------------------
@app.route("/map_all")
def map_all():
    date=request.args.get("date")

    conn=sqlite3.connect(DB_FILE)
    data=conn.execute("SELECT * FROM attendance").fetchall()
    conn.close()

    if date:
        data=[d for d in data if d[7].startswith(date)]

    markers=[{"lat":d[4],"lon":d[5],"name":d[1]} for d in data]

    return render_template_string("""
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster/dist/MarkerCluster.css"/>
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster/dist/leaflet.markercluster.js"></script>

    <div id="map" style="height:600px;"></div>

    <script>
    var map=L.map('map').setView([20,78],5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    var cluster=L.markerClusterGroup();
    var data={{markers|tojson}};

    data.forEach(d=>{
        cluster.addLayer(L.marker([d.lat,d.lon]).bindPopup(d.name));
    });

    map.addLayer(cluster);
    </script>
    """,markers=markers)

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
        w=csv.writer(f)
        w.writerow(["ID","Name","EmpID","Remarks","Lat","Lon","Image","Time"])
        w.writerows(data)

    return send_file("attendance.csv",as_attachment=True)

# ------------------------------------------------------------------------------
if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
