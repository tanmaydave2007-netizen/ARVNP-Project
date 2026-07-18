import cv2
import easyocr
import numpy as np
import time

# 1. Initialize Reader (ગ્રાફિક્સ કાર્ડ na હોય તો gpu=False)
reader = easyocr.Reader(['en'], gpu=False) 

# કેમેરા ઇનપુટ (0 વેબકેમ માટે, અથવા CCTV ની RTSP લિંક)
cap = cv2.VideoCapture(0) 

print(">>> ANPR LIVE CAMERA STARTED <<<")

frame_count = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    # 1. Grayscale and Blur
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    bfilter = cv2.bilateralFilter(gray, 11, 17, 17) # Noise ઘટાડવા

    # 2. Find Edges
    edged = cv2.Canny(bfilter, 30, 200)

    # 3. Find Contours
    keypoints = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours = keypoints[0] if len(keypoints) == 2 else keypoints[1]
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

    location = None
    for contour in contours:
        approx = cv2.approxPolyDP(contour, 10, True)
        if len(approx) == 4: # લંબચોરસ આકાર
            location = approx
            break

    if location is not None:
        # 🎯 Fast Bounding Box Logic (np.where ની ભૂલ અને ક્રેશ ફિક્સ કરવા માટે)
        x, y, w, h = cv2.boundingRect(location)
        
        # પ્લેટ ક્રોપ કરવી (થોડી સેફ્ટી બોર્ડર સાથે)
        cropped_image = gray[max(0, y-2):y+h+2, max(0, x-2):x+w+2]

        # ⚡ વિડીયો હેંગ ન થાય એટલે દર ૪થી ફ્રેમ પર જ OCR સ્કેન થશે
        if frame_count % 4 == 0 and cropped_image.size > 0:
            
            # ઈમેજ પ્રોસેસિંગ સ્મૂધ કરવા થોડી મોટી કરવી
            cropped_image = cv2.resize(cropped_image, (0, 0), fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
            
            # 4. Use EasyOCR
            result = reader.readtext(cropped_image, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
            
            # 5. Render Result
            if len(result) > 0:
                text = result[0][-2].strip().upper().replace(" ", "")
                if len(text) >= 5: # ઓછામાં ઓછા ૫ અક્ષર હોવા જોઈએ
                    print(f"Detected Plate: {text}")
                    
                    # સ્ક્રીન પર લાઈવ ગ્રીન બોક્સ અને નંબર બતાવવો
                    cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # લાઈવ કેમેરો વિન્ડોમાં દેખાશે
    cv2.imshow('CCTV ANPR System', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
