import cv2
import easyocr
import sqlite3
from datetime import datetime
import os
import re
import time
import numpy as np

# ===================================================
# 1. SQLITE DATABASE INITIALIZATION & SETUP
# ===================================================
db_file = "anpr_database.db"
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS vehicle_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehicle_number TEXT NOT NULL,
        log_date TEXT NOT NULL,
        time_in TEXT NOT NULL,
        time_out TEXT,
        duration_minutes REAL DEFAULT 0.0,
        status TEXT NOT NULL
    )
''')
conn.commit()

print("Fetching current vehicle count from SQLite Database...")
try:
    cursor.execute("SELECT COUNT(*) FROM vehicle_logs WHERE status = 'IN'")
    total_now = cursor.fetchone()[0]
except Exception as e:
    print(f"Error fetching initial count: {e}")
    total_now = 0

# ===================================================
# 2. ANPR & CCTV CAMERA SETUP (NO YOLO - ONLY OPENCV)
# ===================================================
print("Initializing OCR Engine... Please wait...")
# GPU સપોર્ટ માટે gpu=True (જો ગ્રાફિક્સ કાર્ડ ન હોય તો False કરી શકો)
reader = easyocr.Reader(['en'], gpu=True) 

CCTV_USER = "anpr"            
CCTV_PASS = "anpr1234"        
CCTV_IP   = "192.168.1.162"    
CCTV_PORT = "554"              

# RTSP પ્રોટોકોલમાં લેગ ઓછો કરવા માટે FFMPEG ઓપ્શન
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
rtsp_url = f"rtsp://{CCTV_USER}:{CCTV_PASS}@{CCTV_IP}:{CCTV_PORT}/cam/realmonitor?channel=1&subtype=0"

print(f"Connecting to CCTV Camera at IP: {CCTV_IP}...")
cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # મિનિમમ બફર સાઈઝ

if not cap.isOpened():
    print("\n[-] Error: Could not connect to the CCTV Camera!")
    exit()

print("\n==================================================")
print(">>> SMART CCTV ANPR STARTED (OPENCV + EASYOCR) <<<")
print("==================================================")

frame_count = 0
last_detected_plate = ""
last_save_time = 0

while True:
    # 🛑 CCTV વિડીયોનો લેગ/લેટન્સી દૂર કરવા માટે બફર ફ્લશિંગ
    for _ in range(4):
        cap.grab()
        
    ret, frame = cap.read()
    if not ret:
        print("[-] Failed to grab frame. Retrying connection...")
        time.sleep(2)
        cap = cv2.VideoCapture(rtsp_url)
        continue

    frame_count += 1
    scan_frame = frame.copy()
    h, w, _ = frame.shape
    
    # ગાઈડલાઈન બોક્સ (Region of Interest - ROI)
    box_x1, box_y1 = int(w * 0.20), int(h * 0.25)
    box_x2, box_y2 = int(w * 0.80), int(h * 0.75)
    
    # લાઈવ સ્ક્રીન પર બોક્સ દોરવું
    cv2.rectangle(frame, (box_x1, box_y1), (box_x2, box_y2), (0, 255, 255), 2)
    cv2.putText(frame, "AUTOMATIC SCANNING AREA", (box_x1, box_y1 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    
    cv2.putText(frame, f"Active Vehicles: {total_now}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    # ⚡ સીસ્ટમ હેંગ ન થાય એટલે દર ત્રીજી (3rd) ફ્રેમ પર જ પ્રોસેસિંગ થશે
    if frame_count % 3 == 0:
        # ૧. બોક્સની અંદરનો ભાગ ક્રોપ (Crop) કરવો
        cropped_roi = scan_frame[box_y1:box_y2, box_x1:box_x2]
        
        if cropped_roi.size > 0:
            # ૨. ઈમેજ પ્રોસેસિંગ ફિલ્ટર્સ (OpenCV Contour/Thresholding)
            gray = cv2.cvtColor(cropped_roi, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            blur = cv2.GaussianBlur(resized, (5, 5), 0)
            thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                           cv2.THRESH_BINARY_INV, 11, 2)
            
            kernel = np.ones((2,2), np.uint8)
            clean_img = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            
            # AI ને ક્લીન ઈમેજ કેવી દેખાય છે તેની વિન્ડો
            cv2.imshow("What AI Sees (Cleaned ROI)", clean_img)
            
            # ૩. EasyOCR સ્કેનિંગ
            result = reader.readtext(clean_img, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

            for detection in result:
                text = detection[1]
                prob = detection[2]
                
                # અક્ષરો ક્લીન કરવા
                clean_text = text.replace(" ", "").replace("-", "").replace(".", "").upper()
                
                if clean_text.startswith("IND"): clean_text = clean_text[3:]
                if clean_text.endswith("IND"): clean_text = clean_text[:-3]

                if len(clean_text) < 5:
                    continue

                # 🛠️ સ્માર્ટ ઓટો-કરેક્શન લોજિક
                if len(clean_text) >= 7:
                    rto_part = clean_text[2:4]
                    rto_fixed = rto_part.replace("I", "1").replace("Z", "2").replace("O", "0")
                    clean_text = clean_text[:2] + rto_fixed + clean_text[4:]
                    
                    last_4 = clean_text[-4:]
                    last_4_fixed = last_4.replace("O", "0").replace("I", "1").replace("Z", "2").replace("S", "5").replace("B", "8")
                    clean_text = clean_text[:-4] + last_4_fixed

                # 📋 ઇન્ડિયન નંબર પ્લેટ રેજિક્સ ફોર્મેટ વેરિફિકેશન
                plate_pattern = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{2,4}$'
                
                if re.match(plate_pattern, clean_text) and prob > 0.25:
                    vehicle_number = clean_text
                    current_sec = time.time()
                    
                    # ⏱️ સેવિંગ ફિલ્ટર: સેમ ગાડી ફરીથી સ્ટોર ન થાય તે માટે ૧૦ સેકન્ડનો ડિલે
                    if vehicle_number != last_detected_plate or (current_sec - last_save_time > 10):
                        last_detected_plate = vehicle_number
                        last_save_time = current_sec
                        
                        print(f"\n[SUCCESS] Plate Detected: {vehicle_number} (Conf: {prob:.2f})")
                        
                        # ===================================================
                        # 3. SQLITE DATABASE LOGGING (IN / OUT Logic)
                        # ===================================================
                        now = datetime.now()
                        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
                        current_date = now.strftime("%Y-%m-%d")
                        
                        cursor.execute(
                            "SELECT id, time_in FROM vehicle_logs WHERE vehicle_number = ? AND status = 'IN'", 
                            (vehicle_number,)
                        )
                        active_log = cursor.fetchone()
                        
                        if active_log:
                            log_id = active_log[0]
                            time_in_str = active_log[1]
                            
                            time_in_obj = datetime.strptime(time_in_str, "%Y-%m-%d %H:%M:%S")
                            duration = now - time_in_obj
                            duration_minutes = round(duration.total_seconds() / 60, 2)
                         
                            cursor.execute('''
                                UPDATE vehicle_logs 
                                SET time_out = ?, status = 'OUT', duration_minutes = ? 
                                WHERE id = ?
                            ''', (current_time, duration_minutes, log_id))
                            conn.commit()
                            
                            print(f"[-] AUTOMATIC TIME OUT LOGGED FOR: {vehicle_number}")
                            total_now = max(0, total_now - 1)
                            print(f"🚗 Total Vehicles in Parking: {total_now}")
                            
                        else:
                            cursor.execute('''
                                INSERT INTO vehicle_logs (vehicle_number, log_date, time_in, time_out, duration_minutes, status)
                                VALUES (?, ?, ?, None, 0.0, 'IN')
                            ''', (vehicle_number, current_date, current_time))
                            conn.commit()
                            
                            print(f"[+] AUTOMATIC TIME IN LOGGED FOR: {vehicle_number}")
                            total_now += 1
                            print(f"🚗 Total Vehicles in Parking: {total_now}")

    # લાઈવ કેમેરા સ્ક્રીન આઉટપુટ
    cv2.imshow("CCTV ANPR Camera Feed", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27: # 'q' અથવા 'Esc' કીથી પ્રોગ્રામ બંધ થશે
        break

cap.release()
cv2.destroyAllWindows()
conn.close()
print("System shutdown safely.")
