# import cv2
# import easyocr
# import firebase_admin
# from firebase_admin import credentials, firestore
# from firebase_admin.firestore import FieldFilter
# from datetime import datetime
# import os
# import re

# # ===================================================
# # 1. FIREBASE INITIALIZATION
# # ===================================================
# json_file = "socialanprproject-firebase-adminsdk-fbsvc-637ea9bbd9.json"

# if not os.path.exists(json_file):
#     print(f"Error: '{json_file}' missing!")
#     exit()

# cred = credentials.Certificate(json_file)

# if not firebase_admin._apps:
#     firebase_admin.initialize_app(cred)

# db = firestore.client()
# logs_ref = db.collection("vehicle_logs")

# print("Fetching current vehicle count from Database...")
# try:
#     active_vehicles = logs_ref.where(filter=FieldFilter("status", "==", "IN")).get()
#     total_now = len(active_vehicles)
# except Exception as e:
#     print(f"Error fetching initial count: {e}")
#     total_now = 0

# # ===================================================
# # 2. ANPR & CAMERA SETUP
# # ===================================================
# print("Initializing AI Model... Please wait...")
# reader = easyocr.Reader(['en'])

# cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

# print("\n==================================================")
# print(">>> SMART CAMERA STARTED <<<")
# print("1. Bring the number plate in front of the camera.")
# print("2. Press 'SPACEBAR' to capture and scan.")
# print("3. Press 'q' to exit.")
# print("==================================================")

# while True:
#     ret, frame = cap.read()
#     if not ret:
#         print("Failed to grab frame.")
#         break

#     scan_frame = frame.copy()
    
#     cv2.putText(frame, f"Active Vehicles: {total_now}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
#     cv2.imshow("ANPR Camera (Press Space to Scan)", frame)

#     key = cv2.waitKey(1) & 0xFF
    
#     if key == ord(' '):
#         print("\n[CAPTURE] Photo captured! Scanning number plate...")
        
#         gray = cv2.cvtColor(scan_frame, cv2.COLOR_BGR2GRAY)
        
#         # 🎯 🛠️ CRITICAL FIX: ફક્ત Capital A-Z અને 0-9 ને જ પરમિશન આપી, જેથી કન્ટ્રી નેમ ફિલ્ટર થઈ જાય!
#         result = reader.readtext(gray, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

#         if len(result) == 0:
#             print("[-] No text detected at all. Try adjusting camera angle.")
#         else:
#             valid_plate_detected = False
#             vehicle_number = ""

#             for detection in result:
#                 text = detection[1]
#                 confidence = detection[2]
                
#                 # સ્પેસ અને વધારાના કેરેક્ટર કાઢી નાખો
#                 clean_text = text.replace(" ", "").replace("-", "").upper()
                
#                 print(f"[RAW READ] AI read text: '{clean_text}'")
                
#                 # 🛑 જો ટેક્સ્ટની લંબાઈ બહુ નાની હોય (જેમ કે માત્ર 'IND'), તો એને સ્કીપ કરો
#                 if len(clean_text) < 5:
#                     continue
                
#                 # 🛠️ જો ભૂલથી 'IND' લાંબી સ્ટ્રિંગની શરૂઆતમાં ચોંટી ગયું હોય, તો તેને હટાવો
#                 if clean_text.startswith("IND"):
#                     clean_text = clean_text[3:]

#                 # 🛠️ સ્માર્ટ ઓટો-કરેક્શન (Common OCR Mistakes)
#                 if len(clean_text) >= 8:
#                     # RTO સીરીઝ સુધારો (e.g., IZ -> 14)
#                     rto_part = clean_text[2:4]
#                     if "I" in rto_part or "Z" in rto_part:
#                         rto_fixed = rto_part.replace("I", "1").replace("Z", "4")
#                         clean_text = clean_text[:2] + rto_fixed + clean_text[4:]
                    
#                     # છેલ્લી ૪ ડિજિટમાં ઓટો-કરેક્શન (e.g., O -> 0)
#                     last_4 = clean_text[-4:]
#                     if "O" in last_4 or "I" in last_4 or "Z" in last_4:
#                         last_4_fixed = last_4.replace("O", "0").replace("I", "1").replace("Z", "2")
#                         clean_text = clean_text[:-4] + last_4_fixed

#                 # લીબરલ ઇન્ડિયન પ્લેટ Regex
#                 plate_pattern = r'^[A-Z]{2}[A-Z0-9]{1,4}[0-9]{4}$'
                
#                 if re.match(plate_pattern, clean_text):
#                     vehicle_number = clean_text
#                     print(f"[SUCCESS] Valid Indian Plate Found: {vehicle_number}")
#                     valid_plate_detected = True
#                     break
            
#             if not valid_plate_detected:
#                 print("[-] No valid Indian number plate format found in this capture. Try again.")
#                 continue

#             # ===================================================
#             # 3. FIREBASE LOGGING
#             # ===================================================
#             now = datetime.now()
#             current_time = now.strftime("%Y-%m-%d %H:%M:%S")
#             current_date = now.strftime("%Y-%m-%d")
            
#             query = logs_ref.where(filter=FieldFilter("vehicle_number", "==", vehicle_number))\
#                             .where(filter=FieldFilter("status", "==", "IN")).stream()
            
#             active_log = None
#             for doc in query:
#                 active_log = doc
#                 break
                
#             if active_log:
#                 data = active_log.to_dict()
#                 time_in_str = data.get('time_in')
                
#                 time_in_obj = datetime.strptime(time_in_str, "%Y-%m-%d %H:%M:%S")
#                 duration = now - time_in_obj
#                 duration_in_minutes = round(duration.total_seconds() / 60, 2)
                
#                 doc_ref = logs_ref.document(active_log.id)
#                 doc_ref.update({
#                     "time_out": current_time, 
#                     "status": "OUT",
#                     "duration_minutes": duration_in_minutes
#                 })
                
#                 print(f"[-] AUTOMATIC TIME OUT LOGGED FOR: {vehicle_number}")
#                 total_now = max(0, total_now - 1)
#                 print(f"🚗 Total Vehicles currently in Parking: {total_now}")
                
#             else:
#                 all_docs = logs_ref.get()
#                 max_id = 0
#                 for doc in all_docs:
#                     if doc.id.isdigit():
#                         max_id = max(max_id, int(doc.id))
#                 next_id = max_id + 1
                
#                 logs_ref.document(str(next_id)).set({
#                     "vehicle_number": vehicle_number,
#                     "log_date": current_date,
#                     "time_in": current_time,
#                     "time_out": None,
#                     "duration_minutes": 0.0,
#                     "status": "IN"
#                 })
#                 print(f"[+] AUTOMATIC TIME IN LOGGED FOR: {vehicle_number} (ID: {next_id})")
                
#                 total_now += 1
#                 print(f"🚗 Total Vehicles currently in Parking: {total_now}")

#     elif key == ord('q'):
#         break

# cap.release()
# cv2.destroyAllWindows()
# print("Camera closed safely.")


import cv2
import easyocr
import sqlite3
from datetime import datetime
import re

# ===================================================
# 1. SQLITE DATABASE INITIALIZATION
# ===================================================
DB_NAME = "anpr_parking.db"

def init_db():
    """ડેટાબેઝ અને ટેબલ બનાવવા માટેનું ફંક્શન"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # જો ટેબલ ન હોય તો નવું ટેબલ બનાવો
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
    conn.close()

# ડેટાબેઝ ચેક કરીને ચાલુ કરો
init_db()

def get_active_vehicle_count():
    """હાલમાં પાર્કિંગમાં કેટલી ગાડીઓ હાજર છે (status='IN') તેની ગણતરી"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vehicle_logs WHERE status = 'IN'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

print("Fetching current vehicle count from SQLite Database...")
total_now = get_active_vehicle_count()
print(f"🚗 Total Vehicles currently in Parking: {total_now}")

# ===================================================
# 2. ANPR & CAMERA SETUP
# ===================================================
print("Initializing AI Model... Please wait...")
reader = easyocr.Reader(['en'])

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

print("\n==================================================")
print(">>> SMART CAMERA STARTED (SQLITE VERSION) <<<")
print("1. Bring the number plate in front of the camera.")
print("2. Press 'SPACEBAR' to capture and scan.")
print("3. Press 'q' to exit.")
print("==================================================")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame.")
        break

    scan_frame = frame.copy()
    
    cv2.putText(frame, f"Active Vehicles: {total_now}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow("ANPR Camera (Press Space to Scan)", frame)

    key = cv2.waitKey(1) & 0xFF
    
    if key == ord(' '):
        print("\n[CAPTURE] Photo captured! Scanning number plate...")
        
        gray = cv2.cvtColor(scan_frame, cv2.COLOR_BGR2GRAY)
        
        # ફક્ત Capital A-Z અને 0-9 ને જ પરમિશન
        result = reader.readtext(gray, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')

        if len(result) == 0:
            print("[-] No text detected at all. Try adjusting camera angle.")
        else:
            valid_plate_detected = False
            vehicle_number = ""

            for detection in result:
                text = detection[1]
                confidence = detection[2]
                
                clean_text = text.replace(" ", "").replace("-", "").upper()
                print(f"[RAW READ] AI read text: '{clean_text}'")
                
                if len(clean_text) < 5:
                    continue
                
                if clean_text.startswith("IND"):
                    clean_text = clean_text[3:]

                # સ્માર્ટ ઓટો-કરેક્શન
                if len(clean_text) >= 8:
                    rto_part = clean_text[2:4]
                    if "I" in rto_part or "Z" in rto_part:
                        rto_fixed = rto_part.replace("I", "1").replace("Z", "4")
                        clean_text = clean_text[:2] + rto_fixed + clean_text[4:]
                    
                    last_4 = clean_text[-4:]
                    if "O" in last_4 or "I" in last_4 or "Z" in last_4:
                        last_4_fixed = last_4.replace("O", "0").replace("I", "1").replace("Z", "2")
                        clean_text = clean_text[:-4] + last_4_fixed

                # ઇન્ડિયન પ્લેટ Regex
                plate_pattern = r'^[A-Z]{2}[A-Z0-9]{1,4}[0-9]{4}$'
                
                if re.match(plate_pattern, clean_text):
                    vehicle_number = clean_text
                    print(f"[SUCCESS] Valid Indian Plate Found: {vehicle_number}")
                    valid_plate_detected = True
                    break
            
            if not valid_plate_detected:
                print("[-] No valid Indian number plate format found in this capture. Try again.")
                continue

            # ===================================================
            # 3. SQLITE DATABASE LOGGING (IN / OUT LOGIC)
            # ===================================================
            now = datetime.now()
            current_time = now.strftime("%Y-%m-%d %H:%M:%S")
            current_date = now.strftime("%Y-%m-%d")
            
            # SQLite કનેક્શન ખોલો
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # ચેક કરો કે આ ગાડી ઓલરેડી અંદર (IN STATUS) છે કે નહીં?
            cursor.execute(
                "SELECT id, time_in FROM vehicle_logs WHERE vehicle_number = ? AND status = 'IN'", 
                (vehicle_number,)
            )
            active_log = cursor.fetchone()
            
            if active_log:
                # ગાડી ઓલરેડી અંદર છે -> એનો મતલબ હવે બહાર જાય છે (AUTOMATIC TIME OUT)
                log_id, time_in_str = active_log
                
                time_in_obj = datetime.strptime(time_in_str, "%Y-%m-%d %H:%M:%S")
                duration = now - time_in_obj
                duration_in_minutes = round(duration.total_seconds() / 60, 2)
                
                # ડેટા અપડેટ કરો
                cursor.execute('''
                    UPDATE vehicle_logs 
                    SET time_out = ?, status = 'OUT', duration_minutes = ? 
                    WHERE id = ?
                ''', (current_time, duration_in_minutes, log_id))
                
                conn.commit()
                print(f"[-] AUTOMATIC TIME OUT LOGGED FOR: {vehicle_number}")
                
            else:
                # નવી ગાડી એન્ટ્રી કરે છે -> (AUTOMATIC TIME IN)
                cursor.execute('''
                    INSERT INTO vehicle_logs (vehicle_number, log_date, time_in, time_out, duration_minutes, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (vehicle_number, current_date, current_time, None, 0.0, "IN"))
                
                conn.commit()
                print(f"[+] AUTOMATIC TIME IN LOGGED FOR: {vehicle_number}")
            
            # કનેક્શન બંધ કરો અને નવો લાઈવ કાઉન્ટ મેળવો
            conn.close()
            total_now = get_active_vehicle_count()
            print(f"🚗 Total Vehicles currently in Parking: {total_now}")

    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("Camera closed safely.")
