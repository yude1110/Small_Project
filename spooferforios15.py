import time
import math
import random
import asyncio
import requests
import numpy as np
import webbrowser
import os
import json
import threading
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

from pymobiledevice3.tunneld.api import get_tunneld_devices
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider

# ----------------- 啟動背景 Tunneld 服務 -----------------
def start_tunneld_background():
    print("[*] 正在背景自動啟動 iOS 專用連線隧道 (tunneld)...")
    try:
        # 在背景執行 pymobiledevice3 remote tunneld
        if sys.platform == "win32":
            # Windows 下隱藏命令提示字元視窗，或直接背景執行
            tunnel_process = subprocess.Popen(
                [sys.executable, "-m", "pymobiledevice3", "remote", "tunneld"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            tunnel_process = subprocess.Popen(
                [sys.executable, "-m", "pymobiledevice3", "remote", "tunneld"]
            )
        time.sleep(3)  # 等待 3 秒讓通道完全建立
        print("[+] 背景 Tunnel 服務已就緒！")
        return tunnel_process
    except Exception as e:
        print(f"[-] 自動啟動 Tunnel 失敗: {e}")
        return None

class IOSRouteSpoofer:
    def __init__(self, enable_jitter=True):
        self.rsd = None
        self.enable_jitter = enable_jitter

    async def connect(self):
        print("[*] 正在向 Tunneld 查詢已建立隧道的 iOS 裝置...")
        for attempt in range(5):  # 嘗試連線幾次，避免通道剛開還沒準備好
            try:
                devices = await get_tunneld_devices()
                if devices:
                    self.rsd = devices[0]
                    print(f"[+] 成功連接至 iOS 裝置！UDID: {self.rsd.udid}")
                    return
            except Exception:
                pass
            await asyncio.sleep(1)
        
        print("[-] 找不到可用的 Tunnel 裝置！請確認手機是否已透過傳輸線連接並解鎖信任電腦。")
        exit(1)

    def get_osrm_route(self, start_lat, start_lng, end_lat, end_lng):
        print(f"[*] 正在獲取道路網導航路線: ({start_lat},{start_lng}) -> ({end_lat},{end_lng})...")
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?overview=full&geometries=geojson"
        headers = {'User-Agent': 'iOS-Route-Spoofer/1.0'}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"OSRM API 回應錯誤：{response.status_code}")
        data = response.json()
        if not data.get('routes'):
            raise Exception("無法找到導航路線")
        coordinates = data['routes'][0]['geometry']['coordinates']
        route_points = [(lat, lng) for lng, lat in coordinates]
        print(f"[+] 成功取得道路軌跡！共包含 {len(route_points)} 個節點。")
        return route_points

    @staticmethod
    def haversine_distance(coord1, coord2):
        R = 6371000
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def interpolate_route(self, route_points, speed_kmh=20.0, interval_sec=1.0):
        speed_mps = speed_kmh / 3.6
        step_distance = speed_mps * interval_sec

        cumulative = [0.0]
        for i in range(len(route_points) - 1):
            seg_dist = self.haversine_distance(route_points[i], route_points[i+1])
            cumulative.append(cumulative[-1] + seg_dist)

        total_distance = cumulative[-1]
        if total_distance == 0:
            return [route_points[0]]

        dense_route = []
        target = 0.0
        seg_idx = 0

        while target <= total_distance:
            while seg_idx < len(cumulative) - 2 and cumulative[seg_idx + 1] < target:
                seg_idx += 1

            seg_start_dist = cumulative[seg_idx]
            seg_end_dist = cumulative[seg_idx + 1]
            seg_len = seg_end_dist - seg_start_dist

            p1 = route_points[seg_idx]
            p2 = route_points[seg_idx + 1]

            if seg_len == 0:
                ratio = 0.0
            else:
                ratio = (target - seg_start_dist) / seg_len

            lat = p1[0] + (p2[0] - p1[0]) * ratio
            lng = p1[1] + (p2[1] - p1[1]) * ratio
            dense_route.append((float(lat), float(lng)))
            target += step_distance

        last_point = route_points[-1]
        if dense_route[-1] != last_point:
            dense_route.append((float(last_point[0]), float(last_point[1])))

        return dense_route

    def add_gps_jitter(self, lat, lng):
        if not self.enable_jitter:
            return float(lat), float(lng)
        lat_jitter = random.uniform(-0.00001, 0.00001)
        lng_jitter = random.uniform(-0.00001, 0.00001)
        return float(lat + lat_jitter), float(lng + lng_jitter)

    async def teleport(self, lat, lng):
        await self.connect()
        print(f"[*] 正在將定位傳送到：({lat}, {lng})")
        async with self.rsd:
            async with DvtProvider(self.rsd) as provider:
                async with LocationSimulation(provider) as location_service:
                    res = location_service.set(float(lat), float(lng))
                    if asyncio.iscoroutine(res):
                        await res
                    print("[+] 傳送成功！手機定位已固定在目標位置。")
                    print("[*] 按 Ctrl+C 可結束程式並清除模擬、恢復真實定位。")
                    try:
                        while True:
                            await asyncio.sleep(1.0)
                    except KeyboardInterrupt:
                        print("\n[!] 使用者手動中斷，正在清除模擬座標...")
                        res_clear = location_service.clear()
                        if asyncio.iscoroutine(res_clear):
                            await res_clear
                        print("[+] 已清除模擬座標。")

    async def start_simulation(self, start_lat, start_lng, end_lat, end_lng,
                                speed_kmh=20.0, interval_sec=0.5, log_every=4,
                                round_trip=False, laps=None):
        await self.connect()
        route_points = self.get_osrm_route(start_lat, start_lng, end_lat, end_lng)
        forward_route = self.interpolate_route(route_points, speed_kmh=speed_kmh, interval_sec=interval_sec)
        backward_route = list(reversed(forward_route))

        total_points = len(forward_route)
        print(f"[*] 單趟預計移動時間：約 {total_points * interval_sec:.0f} 秒 (速度: {speed_kmh} km/h)")
        if round_trip:
            laps_desc = "無限" if laps is None else f"{laps} 趟"
            print(f"[*] 已啟用來回模式，將在起點/終點間往返，設定趟數：{laps_desc}")
        print("[*] 正在啟動 LocationSimulation 服務...")

        async with self.rsd:
            async with DvtProvider(self.rsd) as provider:
                async with LocationSimulation(provider) as location_service:
                    print("[+] iOS 定位覆寫服務已就緒，開始推送動態座標...")
                    should_clear = False

                    try:
                        lap_num = 0
                        while True:
                            lap_num += 1
                            current_route = forward_route if (lap_num % 2 == 1) else backward_route
                            direction_label = "去程" if (lap_num % 2 == 1) else "回程"

                            if round_trip:
                                print(f"[*] --- 第 {lap_num} 趟（{direction_label}）開始 ---")

                            loop_start = time.monotonic()
                            for idx, (lat, lng) in enumerate(current_route, start=1):
                                real_lat, real_lng = self.add_gps_jitter(lat, lng)
                                res = location_service.set(real_lat, real_lng)
                                if asyncio.iscoroutine(res):
                                    await res

                                if idx == 1 or idx % log_every == 0 or idx == total_points:
                                    current_time = time.strftime("%H:%M:%S", time.localtime())
                                    print(f"[{current_time}] 進度 ({idx}/{total_points}) -> Lat: {real_lat:.6f}, Lng: {real_lng:.6f}")

                                next_tick = loop_start + idx * interval_sec
                                remaining = next_tick - time.monotonic()
                                if remaining > 0:
                                    await asyncio.sleep(remaining)

                            if not round_trip:
                                print("[+] 導航完成，已到達目的地！")
                                print("[*] 定位將維持停在終點座標，不會自動還原。")
                                print("[*] 按 Ctrl+C 可結束程式並清除模擬、恢復真實定位。")
                                while True:
                                    await asyncio.sleep(1.0)

                            if laps is not None and lap_num >= laps:
                                print(f"[+] 已完成設定的 {laps} 趟來回，定位停在最後位置。")
                                print("[*] 按 Ctrl+C 可結束程式並清除模擬、恢復真實定位。")
                                while True:
                                    await asyncio.sleep(1.0)

                            print(f"[+] 第 {lap_num} 趟（{direction_label}）結束，準備開始下一趟...")

                    except KeyboardInterrupt:
                        print("\n[!] 使用者手動中斷，準備清除模擬座標並恢復真實定位。")
                        should_clear = True
                    except Exception as e:
                        print(f"[-] 模擬過程發生錯誤：{e}")
                        should_clear = True
                    finally:
                        if should_clear:
                            print("[*] 正在清除模擬座標...")
                            try:
                                res_clear = location_service.clear()
                                if asyncio.iscoroutine(res_clear):
                                    await res_clear
                                print("[+] 已清除模擬座標，定位應已恢復真實 GPS。")
                            except Exception as clear_err:
                                print(f"[-] 清除模擬座標時發生錯誤：{clear_err}")

web_result_data = None

class MapServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/'):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>iOS Route Spoofer - Map Selector</title>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
                <style>
                    html, body, #map { height: 100%; margin: 0; padding: 0; }
                    #panel {
                        position: absolute; top: 10px; right: 10px; z-index: 1000;
                        background: white; padding: 15px; border-radius: 8px;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.3); font-family: sans-serif; width: 280px;
                    }
                    button { width: 100%; padding: 8px; margin-top: 5px; cursor: pointer; background: #007bff; color: white; border: none; border-radius: 4px; }
                    button.secondary { background: #6c757d; }
                    button.success { background: #28a745; }
                    .info-text { font-size: 13px; color: #333; margin-top: 8px; }
                </style>
            </head>
            <body>
                <div id="panel">
                    <h3>地圖選點工具</h3>
                    <div id="mode-desc" class="info-text"><b>步驟 1：</b>請點擊地圖選擇【起點】</div>
                    <div class="info-text" id="status-text" style="margin-top: 10px; font-family: monospace;">尚未選擇</div>
                    <button id="btn-action" onclick="nextStep()" style="display:none;" class="success">確認送出</button>
                    <button class="secondary" onclick="resetSelection()" style="margin-top:10px;">重新選取</button>
                </div>
                <div id="map"></div>
                <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
                <script>
                    const urlParams = new URLSearchParams(window.location.search);
                    const targetMode = urlParams.get('mode') || 'route';

                    let map = L.map('map').setView([25.185585, 121.444317], 13);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        maxZoom: 19,
                        attribution: '© OpenStreetMap'
                    }).addTo(map);

                    let startPoint = null;
                    let endPoint = null;
                    let markerStart = null;
                    let markerEnd = null;

                    document.getElementById('mode-desc').innerHTML = targetMode === 'teleport' 
                        ? '<b>模式：</b>請點擊地圖選擇【傳送目標點】' 
                        : '<b>步驟 1：</b>請點擊地圖選擇【起點】';

                    map.on('click', function(e) {
                        let lat = e.latlng.lat;
                        let lng = e.latlng.lng;

                        if (targetMode === 'teleport') {
                            startPoint = [lat, lng];
                            if (markerStart) { markerStart.setLatLng(e.latlng); } 
                            else { markerStart = L.marker(e.latlng).addTo(map); }
                            document.getElementById('status-text').innerHTML = `目標: ${lat.toFixed(6)}, ${lng.toFixed(6)}`;
                            document.getElementById('btn-action').style.display = 'block';
                        } else {
                            if (!startPoint) {
                                startPoint = [lat, lng];
                                if (markerStart) { markerStart.setLatLng(e.latlng); } 
                                else { markerStart = L.marker(e.latlng).addTo(map); }
                                document.getElementById('mode-desc').innerHTML = '<b>步驟 2：</b>請點擊地圖選擇【終點】';
                                document.getElementById('status-text').innerHTML = `起點: ${lat.toFixed(6)}, ${lng.toFixed(6)}`;
                            } else if (!endPoint) {
                                endPoint = [lat, lng];
                                if (markerEnd) { markerEnd.setLatLng(e.latlng); } 
                                else { markerEnd = L.marker(e.latlng).addTo(map); }
                                document.getElementById('mode-desc').innerHTML = '<b>完成：</b>起終點已選定';
                                document.getElementById('status-text').innerHTML = `起: ${startPoint[0].toFixed(4)},${startPoint[1].toFixed(4)}<br>終: ${endPoint[0].toFixed(4)},${endPoint[1].toFixed(4)}`;
                                document.getElementById('btn-action').style.display = 'block';
                            }
                        }
                    });

                    function nextStep() {
                        let data = {};
                        if (targetMode === 'teleport') {
                            if (!startPoint) return alert('請先點選目標點！');
                            data = { type: 'teleport', lat: startPoint[0], lng: startPoint[1] };
                        } else {
                            if (!startPoint || !endPoint) return alert('請完整選擇起點與終點！');
                            data = { type: 'route', start_lat: startPoint[0], start_lng: startPoint[1], end_lat: endPoint[0], end_lng: endPoint[1] };
                        }

                        fetch('/submit', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(data)
                        }).then(res => {
                            document.body.innerHTML = "<h2 style='text-align:center; margin-top:20vh; font-family:sans-serif;'>座標已成功傳回程式！您可以關閉此視窗。</h2>";
                            setTimeout(() => window.close(), 1500);
                        });
                    }

                    function resetSelection() {
                        startPoint = null;
                        endPoint = null;
                        if (markerStart) { map.removeLayer(markerStart); markerStart = null; }
                        if (markerEnd) { map.removeLayer(markerEnd); markerEnd = null; }
                        document.getElementById('btn-action').style.display = 'none';
                        document.getElementById('mode-desc').innerHTML = targetMode === 'teleport' 
                            ? '<b>模式：</b>請點擊地圖選擇【傳送目標點】' 
                            : '<b>步驟 1：</b>請點擊地圖選擇【起點】';
                        document.getElementById('status-text').innerHTML = '尚未選擇';
                    }
                </script>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode('utf-8'))
    
    def do_POST(self):
        global web_result_data
        if self.path == '/submit':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            web_result_data = json.loads(post_data.decode('utf-8'))
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):
        return

def open_interactive_map(mode='route'):
    global web_result_data
    web_result_data = None
    
    PORT = 8765
    try:
        server = HTTPServer(('127.0.0.1', PORT), MapServerHandler)
    except OSError:
        print(f"[-] 連接埠 {PORT} 已被佔用。")
        exit(1)

    url = f"http://127.0.0.1:{PORT}/?mode={mode}"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    print(f"\n[+] 本機地圖伺服器已啟動：{url}")
    webbrowser.open(url)
    
    while web_result_data is None:
        time.sleep(0.5)
        
    return web_result_data

async def main():
    # 1. 自動在背景啟動 tunneld 服務
    tunnel_proc = start_tunneld_background()

    try:
        print("========================================")
        print("      iOS 定位模擬與路徑導航工具        ")
        print("========================================")
        print("1. 單點傳送 (Teleport) - 地圖點選")
        print("2. 模擬路徑導航 (Route Simulation) - 地圖點選")
        print("3. 手動輸入經緯度")
        
        choice = input("請選擇功能模式 (1/2/3): ").strip()
        spoofer = IOSRouteSpoofer(enable_jitter=False)

        if choice == '1':
            print("\n--- 啟動地圖點選單點傳送 ---")
            result = open_interactive_map(mode='teleport')
            await spoofer.teleport(result['lat'], result['lng'])

        elif choice == '2':
            print("\n--- 啟動地圖點選路徑導航 ---")
            result = open_interactive_map(mode='route')
            
            speed_kmh = float(input("請輸入移動速度 km/h (預設 17.0): ") or "17.0")
            round_trip_input = input("是否來回循環？(y/n，預設 y): ").strip().lower()
            round_trip = False if round_trip_input == 'n' else True
            laps = None
            if round_trip:
                laps_input = input("請輸入來回趟數上限 (直接按 Enter 代表無限循環): ").strip()
                laps = int(laps_input) if laps_input else None

            await spoofer.start_simulation(
                result['start_lat'], result['start_lng'], result['end_lat'], result['end_lng'],
                speed_kmh=speed_kmh,
                interval_sec=0.5,
                log_every=4,
                round_trip=round_trip,
                laps=laps,
            )
        elif choice == '3':
            print("\n--- 手動輸入經緯度模式 ---")
            start_lat = float(input("請輸入起點緯度 (Lat): "))
            start_lng = float(input("請輸入起點經度 (Lng): "))
            end_lat = float(input("請輸入終點緯度 (Lat): "))
            end_lng = float(input("請輸入終點經度 (Lng): "))
            speed_kmh = float(input("请输入移動速度 km/h (預設 16.0): ") or "16.0")
            
            await spoofer.start_simulation(
                start_lat, start_lng, end_lat, end_lng,
                speed_kmh=speed_kmh,
                interval_sec=0.5,
                log_every=4,
                round_trip=True,
                laps=2,
            )
        else:
            print("[-] 無效的選項！")
    
    finally:
        # 當主程式結束時，同時關閉背景的 tunneld 處理程序
        if tunnel_proc:
            tunnel_proc.terminate()
            print("[*] 已關閉背景 Tunnel 服務。")

if __name__ == "__main__":
    asyncio.run(main())