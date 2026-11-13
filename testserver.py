"""
選課伺服器時間校準工具（極簡輸出版）
================================
使用說明：
    export TARGET_URL="https://your-school-course-system.edu.tw"
    export COURSE_COOKIE="你的登入 cookie (選填)"
    python server_time_sync.py
"""

import os
import time
import math
import random
import statistics
import email.utils
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import ntplib

# ==================== 設定 ====================
TARGET_URL = os.environ.get("TARGET_URL", "https://eo903zqfefunegb.m.pipedream.net")
USER_COOKIE = os.environ.get("COURSE_COOKIE", "")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
NTP_SERVERS = ["clock.stdtime.gov.tw", "time.stdtime.gov.tw", "watch.stdtime.gov.tw"]

BOUNDARY_SAMPLES = 4         # 邊界抽樣次數（已優化降低請求數）
COARSE_POLL_INTERVAL = 0.3 # 粗略輪詢間隔（秒）
FINE_POLL_INTERVAL = 0.03   # 進入預測窗口後的密集輪詢間隔（秒）
FINE_WINDOW_SEC = 0.15      # 預測邊界前幾秒切換為密集輪詢
RTT_WARMUP_SAMPLES = 3      # RTT 預熱測量次數
USE_HEAD_REQUEST = True     # 優先使用 HEAD 請求
MAX_TOTAL_REQUESTS = 50     # 安全請求上限
# ================================================

_request_count = 0


def fetch_single_ntp(server, timeout=1.2):
    try:
        client = ntplib.NTPClient()
        resp = client.request(server, version=3, timeout=timeout)
        return resp.offset
    except Exception:
        return None


def get_ntp_offset():
    offsets = []
    with ThreadPoolExecutor(max_workers=len(NTP_SERVERS) * 2) as executor:
        futures = [
            executor.submit(fetch_single_ntp, server)
            for server in NTP_SERVERS
            for _ in range(2)
        ]
        for future in as_completed(futures):
            res = future.result()
            if res is not None:
                offsets.append(res)

    if not offsets:
        return 0.0

    return statistics.median(offsets)


def session_with_headers():
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Cookie": USER_COOKIE,
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache"
    })
    return s


def do_request(session):
    global _request_count
    if _request_count >= MAX_TOTAL_REQUESTS:
        raise RuntimeError("已達到安全請求上限。")

    _request_count += 1
    sep = "&" if "?" in TARGET_URL else "?"
    bypass_url = f"{TARGET_URL}{sep}_nc={time.time()}_{random.randint(1000, 9999)}"

    if USE_HEAD_REQUEST:
        try:
            resp = session.head(bypass_url, timeout=4, allow_redirects=True)
            if "Date" in resp.headers:
                return resp
        except Exception:
            pass

    return session.get(bypass_url, timeout=4)


def parse_server_epoch(response) -> float | None:
    date_str = response.headers.get("Date")
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.timestamp()
    except Exception:
        return None


def detect_one_boundary(session, ntp_offset, predicted_boundary_local=None):
    if predicted_boundary_local is not None:
        now_local = time.time() + ntp_offset
        wait_sec = (predicted_boundary_local - FINE_WINDOW_SEC) - now_local
        if wait_sec > 0:
            time.sleep(wait_sec)

    prev_server_sec = None
    prev_local_time = None
    poll_interval = FINE_POLL_INTERVAL if predicted_boundary_local is not None else COARSE_POLL_INTERVAL

    while True:
        t_before = time.time()
        try:
            resp = do_request(session)
        except Exception:
            return None, None

        t_after = time.time()
        local_mid = (t_before + t_after) / 2.0 + ntp_offset
        server_sec = parse_server_epoch(resp)

        if server_sec is None:
            time.sleep(poll_interval)
            continue

        if prev_server_sec is not None and server_sec != prev_server_sec:
            boundary_local_time = (prev_local_time + local_mid) / 2.0
            return server_sec, boundary_local_time

        prev_server_sec = server_sec
        prev_local_time = local_mid
        time.sleep(poll_interval)


def measure_server_time():
    ntp_offset = get_ntp_offset()
    session = session_with_headers()

    # 靜默執行 RTT 預熱
    for _ in range(RTT_WARMUP_SAMPLES):
        try:
            do_request(session)
        except Exception:
            pass
        time.sleep(0.1)

    # 靜默執行邊界抽樣
    diffs_ms = []
    predicted_next = None

    for _ in range(BOUNDARY_SAMPLES):
        server_sec, boundary_local = detect_one_boundary(session, ntp_offset, predicted_next)
        if server_sec is None:
            break

        diff_ms = (server_sec - boundary_local) * 1000.0
        diffs_ms.append(diff_ms)

        now_local = time.time() + ntp_offset
        elapsed = now_local - boundary_local
        future_seconds = math.ceil(elapsed + 0.001)
        predicted_next = boundary_local + future_seconds

    if not diffs_ms:
        print("\n【錯誤】無法取得伺服器時間數據，請檢查網址或連線。")
        return

    median_diff = statistics.median(diffs_ms)
    abs_diff = abs(median_diff)

    # 極簡面板輸出
    print("\n" + "=" * 45)
    if median_diff < 0:
        print(f"選課伺服器比你的電腦【慢了 {abs_diff:.0f} 毫秒】")
    else:
        early_ms = 1000 - int(abs_diff)
        print(f"選課伺服器比你的電腦【快了 {abs_diff:.0f} 毫秒】")
    print("=" * 45 + "\n")


if __name__ == "__main__":
    measure_server_time()