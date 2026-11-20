import psutil
import time
import subprocess
import urllib.request

def test_close_and_restart():
    # 1. Check if chrome is running
    chrome_procs = [p for p in psutil.process_iter(['pid', 'name']) if 'chrome' in p.name().lower()]
    print(f"Found {len(chrome_procs)} chrome processes")
    
    # Check if port 9222 is already open
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1) as resp:
            if resp.status == 200:
                print("Port 9222 is already active! No restart needed.")
                return
    except Exception:
        pass

    print("Port 9222 not active.")

if __name__ == "__main__":
    test_close_and_restart()

