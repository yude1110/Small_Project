# viGPS_Project

| 檔案 | 說明 |
|---|---|
| `spooferforios15.py` | iOS 虛擬定位（pymobiledevice3） |
| `autoclick.py` | 定時自動點擊（台灣時區校時） |
| `testserver.py` | 伺服器時間校準（NTP 對時） |
| `model.py` | 遊戲畫面 OCR 辨識（OpenCV + pytesseract） |
| `coordinates.json` | `model.py` 的辨識區塊座標設定 |
| `test.png` | `model.py` 的測試截圖 |
| `html/` | 靜態網頁（`index.html`、`sitemap.xml`） |
| `requirements.txt` | 套件清單，用 `pip install -r requirements.txt` 安裝 |

注意：`model.py` 需另外安裝 Tesseract-OCR，路徑寫在檔案開頭。
