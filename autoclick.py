import datetime
import sys
import time
import pyautogui
import pytz

# 停用點擊延遲
pyautogui.PAUSE = 0
# 關閉左上角防故障機制 (移至左上角不會中斷程式)
pyautogui.FAILSAFE = False

TW_TZ = pytz.timezone("Asia/Taipei")


def get_target_time_from_input():
    now = datetime.datetime.now(TW_TZ)
    today_str = now.strftime("%Y-%m-%d")

    while True:
        user_input = input("\n輸入今天觸發的時間 (預設 12:00:00 直接按 Enter，或輸入如 14:30:00)\n> ").strip()

        if not user_input:
            user_input = "12:00:00"

        try:
            full_time_str = f"{today_str} {user_input}"
            naive = datetime.datetime.strptime(full_time_str, "%Y-%m-%d %H:%M:%S")
            target_dt = TW_TZ.localize(naive)

            if target_dt <= now:
                print(f" 輸入的時間 ({user_input}) 已過去")
                retry = input("是否設定為明天的這個時間？(y/n): ").strip().lower()
                if retry == 'y':
                    target_dt += datetime.timedelta(days=1)
                    return target_dt
                else:
                    continue

            return target_dt
        except ValueError:
            print(" 格式錯誤，請輸入格式為 HH:MM:SS（含冒號）")


def get_offset_from_input():
    """讓使用者手動輸入時間偏移量 (毫秒)"""
    while True:
        user_input = input("\n請輸入自訂微調時間 (毫秒 ms)\n"
                           "> ").strip()
        if not user_input:
            return 0.0

        try:
            offset_ms = float(user_input)
            return offset_ms / 1000.0  # 轉為秒數回傳
        except ValueError:
            print("格式錯誤")


def wait_until(target_dt, offset_sec=0.0):
    # 將自訂誤差加到原定的目標時間上
    actual_target_dt = target_dt + datetime.timedelta(seconds=offset_sec)
    
    print(f"\n原始預定時間：{target_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    if offset_sec != 0:
        sign = "+" if offset_sec > 0 else ""
        print(f"微調偏移設定：{sign}{offset_sec * 1000:.0f} ms")
    print(f"實際觸發時間：{actual_target_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

    while True:
        now = datetime.datetime.now(TW_TZ)
        remaining = (actual_target_dt - now).total_seconds()

        if remaining <= 0:
            # 觸發時清除倒數顯示列
            print(" " * 50, end="\r")
            break
        elif remaining > 2:
            # 覆蓋整行避免殘影
            print(f"距離觸發還有 {remaining:.1f} 秒".ljust(40), end="\r", flush=True)
            time.sleep(0.5)
        elif remaining > 0.05:
            time.sleep(0.005)
        else:
            # 剩餘 50 毫秒內使用 Busy Wait 提高精確度
            pass


def main():
    print("=========================================================")
    print("     搶課1.0 (請先將電腦時間對準至標準時間)     ")
    print("=========================================================")
    
    target_dt = get_target_time_from_input()
    offset_sec = get_offset_from_input()

    print("\n在接下來 8 秒內，請將滑鼠移至要點擊的位置：")
    for i in range(8, 0, -1):
        x, y = pyautogui.position()
        print(f"倒數 {i} 秒".ljust(20), end="\r", flush=True)
        time.sleep(1)

    # 倒數結束後清除倒數文字列
    print(" " * 30, end="\r")

    x, y = pyautogui.position()
    print(f"鎖定座標：({x}, {y})")

    wait_until(target_dt, offset_sec)

    # 執行點擊
    pyautogui.click(x, y)
    print(f"Success!! 已於 {datetime.datetime.now(TW_TZ).strftime('%H:%M:%S.%f')[:-3]} 執行點擊")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n程式發生未知錯誤請聯繫 YD@imcheating.shop：{e}")

    print("\n程式將於 8 秒後強制退出...")
    time.sleep(8)
    sys.exit()