"""
================================================================================
Version v2.7 (Render Compatible - MediaPipe Removed)
================================================================================
CHANGES:
1. ❌ Removed MediaPipe (causing libGL crash on Render)
2. ✅ Replaced with OpenCV Haar Cascade (lightweight)
3. ✅ Retained:
   - Multi-frame capture
   - Movement-based liveness detection
   - Face center validation
4. ✅ Fixed success message color
5. ✅ Added CSV header
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
import json

UPLOAD_FOLDER = 'uploads'
DB_FILE = 'attendance.db'
IST = pytz.timezone('Asia/Kolkata')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)

# ------------------------------------------------------------------------------
# ✅ OpenCV Haar Cascade (replacement for MediaPipe)
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
HTML_PAGE = """... (UNCHANGED — keep your existing HTML exactly as is) ..."""
# 👉 KEEP YOUR EXISTING HTML_PAGE (no change needed)

# ------------------------------------------------------------------------------
def validate_face_liveness(images):
    face_positions = []

    for img in images:
        img_np = np.array(img.convert('RGB'))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        if len(faces) == 0:
            return False, "❌ No face detected"

        x, y, w, h = faces[0]

        h_img, w_img = gray.shape

        cx = (x + w/2) / w_img
        cy = (y + h/2) / h_img

        face_positions.append((cx, cy))

    # 🔹 Movement-based liveness
    movement = 0
    for i in range(len(face_positions)-1):
        dx = abs(face_positions[i][0] - face_positions[i+1][0])
        dy = abs(face_positions[i][1] - face_positions[i+1][1])
        movement += dx + dy

    if movement < 0.05:
        return False, "❌ No movement detected (possible spoof)"

    # 🔹 Center validation
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
            msg="❌ All inputs required"
            return render_template_string(HTML_PAGE,message=msg)

        lat,lon=round(float(lat),3),round(float(lon),3)
        ts=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        frames = json.loads
