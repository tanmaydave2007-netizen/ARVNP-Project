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
db_file = "vehicle_parking.db"
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
# 2. ANPR & CCTV CAMERA SETUP
# ===================================================
print("Initializing AI Model... Please wait...")
reader = easyocr.Reader(['en'])

CCTV_USER = "anpr"            
CCTV_PASS = "anpr1234"        
CCTV_IP   = "192.168.1.162"    
CCTV_PORT = "554"              

rtsp_url = f"rtsp://{CCTV_USER}:{CCTV_PASS}@{CCTV_IP}:{CCTV_PORT}/cam/realmonitor?channel=1&subtype=0"

print(f"Connecting to CCTV Camera at IP: {CCTV_IP}...")
cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    print("\n[-] Error: Could not connect to the CCTV Camera!")
    exit()

print("\n==================================================")
print(">>> SMART CCTV ANPR CAMERA STARTED (SQLITE MODE) <<<")
print("==================================================")

while True:
    ret, frame = cap.read()
    if not ret:
        print("[-] Failed to grab frame. Retrying connection...")
        time.sleep(2)
        cap = cv2.VideoCapture(rtsp_url)
        continue

    scan_frame = frame.copy()
    h, w, _ = frame.shape
    
    # ગાઈડલાઈન બોક્સ (ROI)
    box_x1, box_y1 = int(w * 0.25), int(h * 0.30)
    box_x2, box_y2 = int(w * 0.75), int(h * 0.70)
    cv2.rectangle(frame, (box_x1, box_y1), (box_x2, box_y2), (0, 0, 255), 2)
    cv2.putText(frame, "KEEP NUMBER PLATE INSIDE THIS BOX", (box_x1, box_y1 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    
    cv2.putText(frame, f"Active Vehicles: {total_now}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow("CCTV ANPR Camera (Press Space to Scan)", frame)

    key = cv2.waitKey(1) & 0xFF
    
    if key == ord(' '):
        print("\n[CAPTURE] Processing image...")
        
        # ૧. બોક્સની અંદરનો ભાગ ક્રોપ (Crop) કરવો
        cropped_roi = scan_frame[box_y1:box_y2, box_x1:box_x2]
        
        # ૨. ગ્રેસ્કેલ (Grayscale) કન્વર્ઝન
        gray = cv2.cvtColor(cropped_roi, cv2.COLOR_BGR2GRAY)
        
        # ૩. ઈમેજને ૨.૫ ગણી મોટી (Resize) કરવી જેથી અક્ષરો એકદમ ચોખ્ખા વંચાય
        resized = cv2.resize(gray, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        
        # ૪. Gaussian Blur વડે આજુબાજુનો ઝીણો કચરો (Noise) દૂર કરવો
        blur = cv2.GaussianBlur(resized, (5, 5), 0)
        
        # ૫. Adaptive Thresholding: આનાથી બેકગ્રાઉન્ડ આખું સફેદ થઈ જશે અને માત્ર અક્ષરો જ કાળા/સ્પષ્ટ દેખાશે
        # આના કારણે પ્લેટની આજુબાજુની વધારાની બધી વસ્તુઓ ગાયબ થઈ જશે
        thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY_INV, 11, 2)
        
        # ૬. Morphology Open: અક્ષરો સિવાયના બાકી બચેલા નાના ટપકાં કે લીટીઓ સાફ કરવા માટે
        kernel = np.ones((2,2), np.uint8)
        clean_img = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # 🎯 નવી વિન્ડો: AI ને હવે આજુબાજુનું કશું જ નહિ દેખાય, માત્ર ચોખ્ખા અક્ષરો દેખાશે
        cv2.imshow("What AI Sees (Cleaned Plate Only)", clean_img)
        
        # ૭. EasyOCR સ્કેનિંગ
        result = reader.readtext(clean_img, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

        if len(result) == 0:
            print("[-] No text detected. પ્લેટને થોડી નજીક લાવો.")
        else:
            valid_plate_detected = False
            vehicle_number = ""

            for detection in result:
                text = detection[1]
                prob = detection[2]
                
                clean_text = text.replace(" ", "").replace("-", "").upper()
                
                # પ્લેટની ધાર પર આવતા વધારાના 'IND' લખાણને કાઢી નાખવા માટે
                if clean_text.startswith("IND"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("IND"):
                    clean_text = clean_text[:-3]

                print(f"[RAW READ] AI read: '{clean_text}' (Confidence: {prob:.2f})")
                
                if len(clean_text) < 5:
                    continue

                # સ્માર્ટ ઓટો-કરેક્શન (ભૂલથી ખોટો અક્ષર વંચાય તો સુધારો કરવા)
                if len(clean_text) >= 8:
                    rto_part = clean_text[2:4]
                    if "I" in rto_part or "Z" in rto_part:
                        rto_fixed = rto_part.replace("I", "1").replace("Z", "4")
                        clean_text = clean_text[:2] + rto_fixed + clean_text[4:]
                    
                    last_4 = clean_text[-4:]
                    if "O" in last_4 or "I" in last_4 or "Z" in last_4:
                        last_4_fixed = last_4.replace("O", "0").replace("I", "1").replace("Z", "2")
                        clean_text = clean_text[:-4] + last_4_fixed

                # ભારતીય નંબર પ્લેટની પેટર્ન (દા.ત. GJ01AA1234)
                plate_pattern = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$'
                
                if re.match(plate_pattern, clean_text) and prob > 0.25:
                    vehicle_number = clean_text
                    print(f"[SUCCESS] Valid Plate Found: {vehicle_number}")
                    valid_plate_detected = True
                    break
            
            if not valid_plate_detected:
                print("[-] યોગ્ય નંબર પ્લેટ ફોર્મેટ મળ્યું નથી. ફરી પ્રયાસ કરો.")
                continue

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

    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
conn.close()
print("System shutdown safely.")
