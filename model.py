import cv2
import numpy as np
import json
import pytesseract
import os

# 1. 指向你剛才找到的正確路徑
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\a5711\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

class GameOCR:
    def __init__(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def get_color_and_status(self, roi):
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        avg_h = np.mean(hsv[:, :, 0])
        avg_s = np.mean(hsv[:, :, 1])
        
        # 簡單判斷：綠底且顏色純 = 空位
        if 35 < avg_h < 90 and avg_s > 40:
            if np.std(roi) < 5: 
                return "Green", "EMPTY"
            return "Green", "HAS_CONTENT"
        elif avg_h < 10 or avg_h > 160: return "Red", "HAS_CONTENT"
        elif 100 < avg_h < 140: return "Blue", "HAS_CONTENT"
        return "Black", "HAS_CONTENT"

    def process_poker(self, image, zone):
        x, y, w, h = zone['x'], zone['y'], zone['w'], zone['h']
        if w <= 0 or h <= 0: return None
        roi = image[y:y+h, x:x+w]
        debug_filename = f"debug_card_{x}_{y}.png"
        cv2.imwrite(debug_filename, roi)
        color, status = self.get_color_and_status(roi)
        if status == "EMPTY": return {"color": color, "value": None}
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        val = pytesseract.image_to_string(thresh, config='--psm 10 -c tessedit_char_whitelist=AJQK23456789').strip()
        return {"color": color, "value": val}
    

    def process_string(self, image, zone):
        x, y, w, h = zone['x'], zone['y'], zone['w'], zone['h']
        if w <= 0 or h <= 0: return None
        roi = image[y:y+h, x:x+w]
        roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC) # 放大增加準確率
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        val = pytesseract.image_to_string(thresh, config='--psm 7 -c tessedit_char_whitelist=0123456789.').strip()
        return val

    def run(self, frame):
        results = {"poker_slots": [], "group_2": [], "group_3": []}
        for z in self.config.get('card_zones', []):
            results["poker_slots"].append(self.process_poker(frame, z))
        for z in self.config.get('numeric_groups', {}).get('group_2', []):
            results["group_2"].append(self.process_string(frame, z))
        for z in self.config.get('numeric_groups', {}).get('group_3', []):
            results["group_3"].append(self.process_string(frame, z))
        return results

if __name__ == "__main__":
    img_file = 'test.png'  # 確保圖片檔名對應
    json_file = 'coordinates.json'
    
    if not os.path.exists(img_file):
        print(f"❌ 錯誤：找不到圖片 {img_file}")
    elif not os.path.exists(json_file):
        print(f"❌ 錯誤：找不到設定檔 {json_file}")
    else:
        img = cv2.imread(img_file)
        app = GameOCR(json_file)
        data = app.run(img)
        print("\n=== 辨識結果 ===")
        import pprint
        pprint.pprint(data)